"""规则匹配与相似度回退。"""

from __future__ import annotations

from typing import Callable

from models.schemas import SimilarityMatchResult

from .models import CategoryRule, VerifiedBrand


def _argmax_with_threshold(
    scores: list[float],
    threshold: float,
    *,
    skip_indices: Callable[[int], bool] | None = None,
) -> tuple[int, float] | None:
    """返回 (最大分索引, 最大分)；若最大分 < threshold 或无有效项则返回 None。"""
    best_score = -1.0
    best_idx = -1
    for i, s in enumerate(scores):
        if skip_indices and skip_indices(i):
            continue
        if s > best_score:
            best_score = s
            best_idx = i
    if best_idx < 0 or best_score < threshold:
        return None
    return best_idx, best_score


def match_rule(text: str, rule: CategoryRule) -> bool:
    """
    按判断逻辑校验：门店文本是否满足该规则。
    关键词组1-4：至少有一组非空且该组内所有关键词均在文本中出现。
    关键词组5：若非空，则至少包含其中一个关键词即可。
    一定不包含：文本中不能出现其中任一关键词。
    """
    t = text.strip()
    if not t:
        return False
    for kw in rule.must_not_contain:
        if kw and kw in t:
            return False
    if rule.keyword_group_5:
        if not any(kw and kw in t for kw in rule.keyword_group_5):
            return False
    groups = [
        rule.keyword_group_1,
        rule.keyword_group_2,
        rule.keyword_group_3,
        rule.keyword_group_4,
    ]
    non_empty_groups = [g for g in groups if g]
    if non_empty_groups:
        if not any(all(kw in t for kw in g) for g in non_empty_groups):
            return False
    if not non_empty_groups and not rule.keyword_group_5:
        return False
    return True


def match_store(text: str, rules: list[CategoryRule]) -> list[CategoryRule]:
    """对门店文本循环所有规则，返回匹配的规则列表（即对应的原子分类）。"""
    return [r for r in rules if match_rule(text, r)]


def text_similarity(
    text_a: str,
    text_b: str,
    use_combined: bool = True,
    bge_weight: float | None = None,
) -> float:
    """
    计算两段文本的相似度，返回值在 [0, 1]。
    默认使用 BGE 余弦 + Jaro-Winkler 组合，提高准确性（语义与字面/拼写变体兼顾）。
    """
    from .embedding import combined_similarity, cosine_similarity_0_1, DEFAULT_BGE_WEIGHT

    if use_combined:
        w = bge_weight if bge_weight is not None else DEFAULT_BGE_WEIGHT
        return combined_similarity(text_a, text_b, bge_weight=w)
    return cosine_similarity_0_1(text_a, text_b)


def match_by_similarity(
    store_text: str,
    verified_brands: list[VerifiedBrand],
    threshold: float = 0.97,
) -> SimilarityMatchResult:
    """
    与已校验品牌做相似度比对，取相似度最高的品牌；若最高分 >= threshold 则返回其原子品类（单条规则）。
    返回 SimilarityMatchResult(rules, brand, score)；无匹配时为 rules=[], brand=None, score=0.0。
    """
    store_text = store_text.strip()
    if not store_text or not verified_brands:
        return SimilarityMatchResult(rules=[], brand=None, score=0.0)

    def skip_empty_brand(i: int) -> bool:
        return not (verified_brands[i].brand_name)

    use_cached = any(vb.embedding is not None for vb in verified_brands)
    if use_cached:
        from .embedding import similarity_scores_with_cached
        scores = similarity_scores_with_cached(store_text, verified_brands)
        best = _argmax_with_threshold(scores, threshold, skip_indices=skip_empty_brand)
    else:
        scores = [text_similarity(store_text, vb.brand_name) for vb in verified_brands]
        best = _argmax_with_threshold(scores, threshold, skip_indices=skip_empty_brand)
    if best is None:
        return SimilarityMatchResult(rules=[], brand=None, score=0.0)
    best_idx, best_score = best
    best_brand = verified_brands[best_idx]
    rule = CategoryRule(
        level1_category="",
        category_code="",
        atomic_category=best_brand.atomic_category,
    )
    return SimilarityMatchResult(rules=[rule], brand=best_brand, score=best_score)
