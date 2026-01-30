"""基于 sentence-transformers + BGE 的文本向量与相似度。"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

# 中文场景推荐，体积与速度平衡
BGE_MODEL_NAME = "BAAI/bge-small-zh-v1.5"

# 项目根目录下的 model 目录，用于存放 BGE 模型
_model_dir = Path(__file__).resolve().parent.parent / "model"
_model = None


def _get_model():
    """懒加载 BGE 模型，首次调用时下载到 model 目录并加载。"""
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer  # type: ignore[import-untyped]

        _model_dir.mkdir(parents=True, exist_ok=True)
        _model = SentenceTransformer(BGE_MODEL_NAME, cache_folder=str(_model_dir))
    return _model


def encode(texts: list[str], normalize: bool = True):
    """
    批量编码文本为向量。返回 numpy 数组 (n, dim)，默认 L2 归一化。
    """
    model = _get_model()
    return model.encode(texts, normalize_embeddings=normalize)


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
