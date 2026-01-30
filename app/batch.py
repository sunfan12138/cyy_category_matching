"""批量品类匹配：单条匹配 + 批量运行。"""

from parser import (
    CategoryRule,
    VerifiedBrand,
    match_by_similarity,
    match_store,
)

SIMILARITY_THRESHOLD = 0.97

ResultRow = tuple[str, str, str, str, str]  # 输入品类, 一级, 编码, 原子品类, 匹配方式


def match_store_categories(
    store_text: str,
    rules: list[CategoryRule],
    verified_brands: list[VerifiedBrand],
) -> tuple[list[CategoryRule], bool]:
    """单条匹配：规则优先，无结果时走相似度。返回 (匹配规则列表, 是否相似度匹配)。"""
    matched = match_store(store_text.strip(), rules)
    from_similarity = False
    if not matched and verified_brands:
        matched = match_by_similarity(
            store_text, verified_brands, threshold=SIMILARITY_THRESHOLD
        )
        from_similarity = bool(matched)
    return matched, from_similarity


def run_batch_match(
    categories: list[str],
    rules: list[CategoryRule],
    verified_brands: list[VerifiedBrand],
) -> list[ResultRow]:
    """批量匹配。返回 (输入品类, 一级原子品类, 品类编码, 原子品类, 匹配方式)，多条匹配取第一条。"""
    result: list[ResultRow] = []
    for name in categories:
        matched, from_similarity = match_store_categories(name, rules, verified_brands)
        if not matched:
            result.append((name, "", "", "", "未匹配"))
            continue
        r = matched[0]
        method = "相似度" if from_similarity else "规则"
        result.append(
            (
                name,
                r.level1_category or "",
                str(r.category_code) if r.category_code != "" else "",
                r.atomic_category or "",
                method,
            )
        )
    return result
