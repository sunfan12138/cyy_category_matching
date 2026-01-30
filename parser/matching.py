"""规则匹配与相似度回退。"""

from __future__ import annotations

from .models import CategoryRule, VerifiedBrand


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


def text_similarity(text_a: str, text_b: str) -> float:
    """
    计算两段文本的相似度，返回值在 [0, 1]。基于 sentence-transformers + BGE 的余弦相似度。
    """
    from .embedding import cosine_similarity_0_1

    return cosine_similarity_0_1(text_a, text_b)


def match_by_similarity(
    store_text: str,
    verified_brands: list[VerifiedBrand],
    threshold: float = 0.97,
) -> list[CategoryRule]:
    """
    与已校验品牌做相似度比对，若存在相似度 >= threshold 的品牌，则返回其原子品类（单条规则）。
    否则返回空列表。
    """
    store_text = store_text.strip()
    if not store_text or not verified_brands:
        return []

    best_score = -1.0
    best_brand: VerifiedBrand | None = None
    for vb in verified_brands:
        if not vb.brand_name:
            continue
        score = text_similarity(store_text, vb.brand_name)
        if score >= threshold and score > best_score:
            best_score = score
            best_brand = vb

    if best_brand is None or best_score < threshold:
        return []

    return [
        CategoryRule(
            level1_category="",
            category_code=best_brand.brand_code,
            atomic_category=best_brand.atomic_category,
        )
    ]
