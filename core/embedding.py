"""基于 sentence-transformers + BGE 的文本向量与相似度，并组合 Jaro-Winkler 提升准确性。"""

from __future__ import annotations

import logging

import numpy as np
from tqdm import tqdm  # type: ignore[import-untyped]

from .models import VerifiedBrand
from .utils.similarity import (
    jaro_winkler_similarity,
    weighted_combined,
)

_model = None


def _normalize_cosine_to_0_1(cos: float) -> float:
    """将余弦相似度 [-1, 1] 线性映射到 [0, 1]。"""
    return (cos + 1.0) / 2.0


def _embedding_config():
    """embedding 配置（来自 app_config.yaml）；需已调用 load_app_config()。"""
    from core.config import inject, EmbeddingConfig
    return inject(EmbeddingConfig)


def _suppress_third_party_logging() -> tuple[tuple[logging.Logger, ...], tuple[int, ...]]:
    """临时将 modelscope / huggingface_hub / transformers / sentence_transformers 日志设为 WARNING。返回 (loggers, old_levels)。"""
    loggers = (
        logging.getLogger("modelscope"),
        logging.getLogger("huggingface_hub"),
        logging.getLogger("transformers"),
        logging.getLogger("sentence_transformers"),
    )
    old_levels = tuple(logger.level for logger in loggers)
    for logger in loggers:
        logger.setLevel(logging.WARNING)
    return loggers, old_levels


def _restore_logging(
    loggers: tuple[logging.Logger, ...],
    old_levels: tuple[int, ...],
) -> None:
    """恢复第三方库日志级别。"""
    for logger, level in zip(loggers, old_levels):
        logger.setLevel(level)


def _get_model():
    """懒加载 BGE 模型：通过 modelscope 下载到 model 目录，再用 sentence-transformers 加载。"""
    global _model
    if _model is None:
        from modelscope import snapshot_download  # type: ignore[import-untyped]
        from sentence_transformers import SentenceTransformer  # type: ignore[import-untyped]

        from paths import get_model_dir

        model_id = _embedding_config().bge_model_id
        loggers, old_levels = _suppress_third_party_logging()
        try:
            model_dir = get_model_dir()
            model_dir.mkdir(parents=True, exist_ok=True)
            local_dir = snapshot_download(
                model_id,
                cache_dir=str(model_dir),
                progress_callbacks=[],
            )
            _model = SentenceTransformer(local_dir)
        finally:
            _restore_logging(loggers, old_levels)
    return _model


def ensure_model_loaded() -> None:
    """启动时先下载并加载 BGE 模型，后续编码将直接使用已加载模型。"""
    _get_model()


def encode(
    texts: list[str],
    normalize: bool = True,
    batch_size: int = 256,
    show_progress_bar: bool = False,
):
    """
    批量编码文本为向量。返回 numpy 数组 (n, dim)，默认 L2 归一化。
    batch_size 为模型前向的批大小，适当调大可加速（显存/内存允许时）。
    """
    model = _get_model()
    return model.encode(
        texts,
        normalize_embeddings=normalize,
        batch_size=batch_size,
        show_progress_bar=show_progress_bar,
    )


def cosine_similarity(text_a: str, text_b: str) -> float:
    """
    计算两段文本的余弦相似度，返回值在 [-1, 1]。
    BGE 向量 L2 归一化后，余弦 = 点积。
    """
    if not text_a.strip() or not text_b.strip():
        return 0.0
    model = _get_model()
    emb = model.encode([text_a, text_b], normalize_embeddings=True)
    return float(emb[0] @ emb[1])


def cosine_similarity_0_1(text_a: str, text_b: str) -> float:
    """
    计算两段文本的相似度，线性映射到 [0, 1]，便于与阈值 0.97 等比较。
    余弦范围 [-1, 1] -> (cos + 1) / 2 -> [0, 1]。
    """
    return _normalize_cosine_to_0_1(cosine_similarity(text_a, text_b))


# 从 utils.similarity 导出，供 matching 等模块使用
def combined_similarity(
    text_a: str,
    text_b: str,
    bge_weight: float | None = None,
) -> float:
    """
    BGE 余弦相似度与 Jaro-Winkler 的加权组合，返回值在 [0, 1]。
    bge_weight：BGE 权重（0~1），(1 - bge_weight) 为 Jaro-Winkler 权重。
    提高对语义相近且字面相近（含拼写变体）的匹配准确性。
    """
    if bge_weight is None:
        bge_weight = _embedding_config().bge_weight
    bge_sim = cosine_similarity_0_1(text_a, text_b)
    jw_sim = jaro_winkler_similarity(text_a, text_b)
    return weighted_combined(bge_sim, jw_sim, bge_weight)


def fill_brand_embeddings(verified_brands: list[VerifiedBrand]) -> None:
    """
    一次性编码所有品牌名并写入各 VerifiedBrand.embedding。
    全量或大块调用 model.encode，利用库内 batch_size 加速；超长列表分块避免 OOM。
    """
    if not verified_brands:
        return
    embedding_config = _embedding_config()
    chunk_size = embedding_config.fill_embedding_chunk
    batch_size = embedding_config.encode_batch_size
    brand_texts = [brand.brand_name or "" for brand in verified_brands]
    total = len(verified_brands)
    for start in tqdm(
        range(0, total, chunk_size),
        desc="编码品牌向量",
        unit="块",
        total=(total + chunk_size - 1) // chunk_size,
    ):
        end = min(start + chunk_size, total)
        chunk_texts = brand_texts[start:end]
        embeddings = encode(
            chunk_texts,
            batch_size=batch_size,
            show_progress_bar=False,
        )
        for i, brand in enumerate(verified_brands[start:end]):
            brand.embedding = embeddings[i].tolist()


def _compute_bge_scores_for_brands(
    query_embedding: np.ndarray,
    verified_brands: list[VerifiedBrand],
) -> list[float]:
    """根据缓存的品牌向量计算 query 与每个品牌的 BGE 相似度 [0, 1]，无 embedding 的为 0.0。"""
    scores: list[float] = []
    for brand in verified_brands:
        if brand.embedding is None:
            scores.append(0.0)
            continue
        brand_vec = np.array(brand.embedding, dtype=np.float32)
        cos = float(np.dot(query_embedding, brand_vec))
        scores.append(_normalize_cosine_to_0_1(cos))
    return scores


def _compute_combined_scores_for_brands(
    query: str,
    verified_brands: list[VerifiedBrand],
    bge_scores: list[float],
    bge_weight: float,
) -> list[float]:
    """将 BGE 分数与 Jaro-Winkler 加权组合，返回与 verified_brands 顺序一致的 [0, 1] 分数。"""
    scores: list[float] = []
    for i, brand in enumerate(verified_brands):
        if brand.brand_name is None:
            scores.append(0.0)
            continue
        bge_score = bge_scores[i] if i < len(bge_scores) else 0.0
        jw_score = jaro_winkler_similarity(query, brand.brand_name or "")
        scores.append(weighted_combined(bge_score, jw_score, bge_weight))
    return scores


def similarity_scores_with_cached(
    query: str,
    verified_brands: list[VerifiedBrand],
    use_combined: bool = True,
    bge_weight: float | None = None,
) -> list[float]:
    """
    使用缓存的品牌向量计算 query 与每个品牌的相似度 [0, 1]。
    若 use_combined 为 True（默认），则返回 BGE 与 Jaro-Winkler 的加权组合，提高准确性。
    若某条无 embedding 则返回 0.0。与 verified_brands 顺序一致。
    """
    if not query.strip() or not verified_brands:
        return []
    query_embedding = encode([query.strip()])[0]
    bge_scores = _compute_bge_scores_for_brands(query_embedding, verified_brands)
    if not use_combined:
        return bge_scores
    if bge_weight is None:
        bge_weight = _embedding_config().bge_weight
    return _compute_combined_scores_for_brands(
        query.strip(), verified_brands, bge_scores, bge_weight
    )
