"""批量品类匹配：单条匹配 + 批量运行。"""

from tqdm import tqdm  # type: ignore[import-untyped]

from core import (
    CategoryRule,
    VerifiedBrand,
    match_by_similarity,
    match_store,
)
from core.llm import get_category_description

from .io import ResultRow

SIMILARITY_THRESHOLD = 0
# 相似度低于此值时，用大模型生成品类描述并再次做关键词规则匹配
LLM_FALLBACK_SIMILARITY_THRESHOLD = 0.9


def match_store_categories(
    store_text: str,
    rules: list[CategoryRule],
    verified_brands: list[VerifiedBrand],
) -> tuple[list[CategoryRule], bool, VerifiedBrand | None, float]:
    """
    单条匹配：规则优先，无结果时走相似度。
    若相似度匹配结果 < LLM_FALLBACK_SIMILARITY_THRESHOLD（0.9），则调用大模型生成品类描述，
    再对描述做一次关键词规则匹配；若规则命中则按规则结果返回。
    返回 (匹配规则列表, 是否相似度匹配, 命中品牌, 相似度)。
    """
    matched = match_store(store_text.strip(), rules)
    if matched:
        return matched, False, None, 0.0
    if not verified_brands:
        return [], False, None, 0.0
    matched, ref_brand, score = match_by_similarity(
        store_text, verified_brands, threshold=SIMILARITY_THRESHOLD
    )
    # 相似度 < 0.9 时，用大模型生成描述再规则匹配
    if matched and ref_brand is not None and score < LLM_FALLBACK_SIMILARITY_THRESHOLD:
        desc = get_category_description(store_text)
        if desc:
            rule_matched = match_store(desc.strip(), rules)
            if rule_matched:
                return rule_matched, False, None, 0.0
    return matched, bool(matched), ref_brand, score if ref_brand is not None else 0.0


def run_batch_match(
    categories: list[str],
    rules: list[CategoryRule],
    verified_brands: list[VerifiedBrand],
) -> list[ResultRow]:
    """批量匹配。返回 8 列：(输入品类, 一级, 编码, 原子品类, 匹配方式, 原品牌编码, 原品牌名, 相似度)。"""
    result: list[ResultRow] = []
    for name in tqdm(categories, desc="品类匹配", unit="条"):
        matched, from_similarity, ref_brand, ref_score = match_store_categories(
            name, rules, verified_brands
        )
        if not matched:
            result.append((name, "", "", "", "未匹配", "", "", ""))
            continue
        r = matched[0]
        method = "相似度" if from_similarity else "规则"
        ref_code = str(ref_brand.brand_code) if ref_brand else ""
        ref_name = (ref_brand.brand_name or "") if ref_brand else ""
        score_str = f"{ref_score:.4f}" if from_similarity and ref_brand else ""
        result.append(
            (
                name,
                r.level1_category or "",
                str(r.category_code) if r.category_code != "" else "",
                r.atomic_category or "",
                method,
                ref_code,
                ref_name,
                score_str,
            )
        )
    return result
