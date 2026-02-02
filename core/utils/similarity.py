"""相似度计算工具：Jaro-Winkler、加权组合等，与向量模型解耦便于单测与复用。"""

from __future__ import annotations

from rapidfuzz.distance import JaroWinkler

# 组合相似度默认权重：BGE 语义为主，Jaro-Winkler 辅助
DEFAULT_BGE_WEIGHT = 0.5


def jaro_winkler_similarity(text_a: str, text_b: str) -> float:
    """
    计算两段文本的 Jaro-Winkler 相似度，返回值在 [0, 1]。
    对拼写变体、字符级相似更敏感，与 BGE 语义相似度互补。
    """
    a, b = text_a.strip(), text_b.strip()
    if not a or not b:
        return 0.0
    return float(JaroWinkler.similarity(a, b))


def weighted_combined(bge_0_1: float, jaro_winkler: float, bge_weight: float = DEFAULT_BGE_WEIGHT) -> float:
    """
    BGE [0,1] 与 Jaro-Winkler [0,1] 的加权组合，返回值在 [0, 1]。
    bge_weight：BGE 权重（0~1），(1 - bge_weight) 为 Jaro-Winkler 权重。
    """
    return bge_weight * bge_0_1 + (1.0 - bge_weight) * jaro_winkler
