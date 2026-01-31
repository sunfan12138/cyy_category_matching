"""基于 sentence-transformers + BGE 的文本向量与相似度。"""

from __future__ import annotations

from parser.models import VerifiedBrand
from pathlib import Path

from tqdm import tqdm  # type: ignore[import-untyped]

from .models import VerifiedBrand

# 中文场景推荐，体积与速度平衡；ModelScope / HuggingFace 均可用此 ID
BGE_MODEL_ID = "BAAI/bge-small-zh-v1.5"

_model = None


def _get_model():
    """懒加载 BGE 模型：通过 modelscope 下载到 model 目录，再用 sentence-transformers 加载。"""
    global _model
    if _model is None:
        from modelscope import snapshot_download  # type: ignore[import-untyped]
        from sentence_transformers import SentenceTransformer  # type: ignore[import-untyped]

        from paths import get_model_dir

        model_dir = get_model_dir()
        model_dir.mkdir(parents=True, exist_ok=True)
        local_dir = snapshot_download(BGE_MODEL_ID, cache_dir=str(model_dir))
        _model = SentenceTransformer(local_dir)
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
    cos = cosine_similarity(text_a, text_b)
    return (cos + 1.0) / 2.0


# 单次编码的最大条数，超过则分批以免 OOM（品牌名较短，可设较大）
_FILL_EMBEDDING_CHUNK = 16_000


def fill_brand_embeddings(verified_brands: list[VerifiedBrand]) -> None:
    """
    一次性编码所有品牌名并写入各 VerifiedBrand.embedding。
    全量或大块调用 model.encode，利用库内 batch_size 加速；超长列表分块避免 OOM。
    """
    if not verified_brands:
        return
    texts = [vb.brand_name or "" for vb in verified_brands]
    total = len(verified_brands)
    # 库内前向批大小，GPU 下可适当调大（如 256～512）
    encode_batch_size = 512
    for start in tqdm(
        range(0, total, _FILL_EMBEDDING_CHUNK),
        desc="编码品牌向量",
        unit="块",
        total=(total + _FILL_EMBEDDING_CHUNK - 1) // _FILL_EMBEDDING_CHUNK,
    ):
        end = min(start + _FILL_EMBEDDING_CHUNK, total)
        chunk_texts = texts[start:end]
        emb = encode(
            chunk_texts,
            batch_size=encode_batch_size,
            show_progress_bar=False,
        )
        for i, vb in enumerate[VerifiedBrand](verified_brands[start:end]):
            vb.embedding = emb[i].tolist()


def similarity_scores_with_cached(
    query: str, verified_brands: list[VerifiedBrand]
) -> list[float]:
    """
    使用缓存的品牌向量计算 query 与每个品牌的相似度 [0, 1]。
    若某条无 embedding 则返回 0.0。与 verified_brands 顺序一致。
    """
    import numpy as np  # noqa: E402

    if not query.strip() or not verified_brands:
        return []
    q = encode([query.strip()])
    q = q[0]
    scores: list[float] = []
    for vb in verified_brands:
        if vb.embedding is None:
            scores.append(0.0)
            continue
        arr = np.array(vb.embedding, dtype=np.float32)
        cos = float(np.dot(q, arr))
        scores.append((cos + 1.0) / 2.0)
    return scores
