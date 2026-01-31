"""批量品类匹配：单条匹配 + 批量运行。"""

import logging
from tqdm import tqdm  # type: ignore[import-untyped]

from core import (
    CategoryRule,
    VerifiedBrand,
    match_by_similarity,
    match_store,
)
from core.llm import get_category_description_with_search

from .io import ResultRow

logger = logging.getLogger(__name__)

SIMILARITY_THRESHOLD = 0
# 相似度低于此值时，用大模型生成品类描述并再次做关键词规则匹配
LLM_FALLBACK_SIMILARITY_THRESHOLD = 0.9


def match_store_categories(
    store_text: str,
    rules: list[CategoryRule],
    verified_brands: list[VerifiedBrand],
) -> tuple[list[CategoryRule], bool, VerifiedBrand | None, float, str | None]:
    """
    单条匹配：规则优先，无结果时走相似度。
    若相似度匹配结果 < LLM_FALLBACK_SIMILARITY_THRESHOLD（0.9），则首次对话即调用带 MCP 工具的大模型
    （可调用搜索等工具），根据描述做关键词规则匹配；若规则命中则按规则结果返回（记为「搜索后匹配」）。
    返回 (匹配规则列表, 是否相似度匹配, 命中品牌, 相似度, 大模型描述或 None)。
    """
    store_text = store_text.strip()
    matched = match_store(store_text, rules)
    if matched:
        return matched, False, None, 0.0, None
    if not verified_brands:
        logger.debug("未进入 LLM/MCP：无已校验品牌")
        return [], False, None, 0.0, None
    matched, ref_brand, score = match_by_similarity(
        store_text, verified_brands, threshold=SIMILARITY_THRESHOLD
    )
    if not matched or ref_brand is None:
        logger.info("未进入 LLM/MCP [%s]：无相似度匹配（与已校验品牌均不相似）", store_text[:40])
        return [], False, None, 0.0, None
    if score >= LLM_FALLBACK_SIMILARITY_THRESHOLD:
        logger.info("未进入 LLM/MCP [%s]：相似度 %.2f >= 0.9，直接采用相似度结果", store_text[:40], score)
        return matched, True, ref_brand, score, None
    # 相似度 < 0.9 时，调用大模型（带 MCP 工具），再对描述做规则匹配
    logger.info("开始调用大模型 [%s]：相似度 < 0.9", store_text[:40])
    desc = get_category_description_with_search(store_text, rules=rules)
    if desc:
        rule_matched = match_store(desc.strip(), rules)
        if rule_matched:
            return rule_matched, False, None, 0.0, desc
    return matched, True, ref_brand, score, None


def run_batch_match(
    categories: list[str],
    rules: list[CategoryRule],
    verified_brands: list[VerifiedBrand],
) -> list[ResultRow]:
    """批量匹配。返回 9 列：(输入品类, 一级, 编码, 原子品类, 匹配方式, 原品牌编码, 原品牌名, 相似度, 大模型描述)。"""
    result: list[ResultRow] = []
    for name in tqdm(categories, desc="品类匹配", unit="条"):
        matched, from_similarity, ref_brand, ref_score, llm_desc = match_store_categories(
            name, rules, verified_brands
        )
        if not matched:
            result.append((name, "", "", "", "未匹配", "", "", "", ""))
            continue
        r = matched[0]
        if llm_desc is not None:
            method = "搜索后匹配"
        else:
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
                llm_desc or "",
            )
        )
    return result
