"""批量品类匹配：单条匹配 + 批量运行（async 并发）。"""

import asyncio
import logging
from tqdm import tqdm  # type: ignore[import-untyped]

from core import (
    CategoryRule,
    VerifiedBrand,
    match_by_similarity,
    match_store,
)
from llm import get_category_description_with_search, get_category_description_with_search_async
from models.schemas import MatchResult, MatchStoreResult

from .file_io import ResultRow

logger = logging.getLogger(__name__)


def _matching_config():
    """匹配配置（来自 app_config.yaml matching 节）；需已调用 load_app_config()。"""
    from core.config import get_app_config
    return get_app_config().matching


def match_store_categories(
    store_text: str,
    rules: list[CategoryRule],
    verified_brands: list[VerifiedBrand],
) -> MatchStoreResult:
    """
    单条匹配：规则优先，无结果时走相似度。
    若相似度匹配结果 < LLM_FALLBACK_SIMILARITY_THRESHOLD（0.9），则首次对话即调用带 MCP 工具的大模型
    （可调用搜索等工具），根据描述做关键词规则匹配；若规则命中则按规则结果返回（记为「搜索后匹配」）。
    返回 MatchStoreResult(matched_rules, from_similarity, ref_brand, score, llm_desc)。
    """
    mc = _matching_config()
    store_text = store_text.strip()
    matched = match_store(store_text, rules)
    if matched:
        return MatchStoreResult(matched_rules=matched, from_similarity=False, score=0.0)
    if not verified_brands:
        logger.debug("未进入 LLM/MCP：无已校验品牌")
        return MatchStoreResult(matched_rules=[], from_similarity=False, score=0.0)
    sim_result = match_by_similarity(
        store_text, verified_brands, threshold=mc.similarity_threshold
    )
    if not sim_result.rules or sim_result.brand is None:
        logger.info("未进入 LLM/MCP [%s]：无相似度匹配（与已校验品牌均不相似）", store_text[:40])
        return MatchStoreResult(matched_rules=[], from_similarity=False, score=0.0)
    if sim_result.score >= mc.llm_fallback_threshold:
        logger.info("未进入 LLM/MCP [%s]：相似度 %.2f >= %.2f，直接采用相似度结果", store_text[:40], sim_result.score, mc.llm_fallback_threshold)
        return MatchStoreResult(
            matched_rules=sim_result.rules,
            from_similarity=True,
            ref_brand=sim_result.brand,
            score=sim_result.score,
        )
    # 相似度低于阈值时，调用大模型（带 MCP 工具），再对描述做规则匹配
    logger.info("开始调用大模型 [%s]：相似度 < %.2f", store_text[:40], mc.llm_fallback_threshold)
    desc = get_category_description_with_search(
        store_text,
        rules=rules,
        context={
            "similarity_threshold": mc.llm_fallback_threshold,
            "similarity_score": round(sim_result.score, 4),
            "item": store_text[:50] + ("..." if len(store_text) > 50 else ""),
        },
    )
    if desc:
        if desc.strip() in mc.llm_unmatched_aliases:
            return MatchStoreResult(
                matched_rules=sim_result.rules,
                from_similarity=True,
                ref_brand=sim_result.brand,
                score=sim_result.score,
                llm_desc=mc.llm_unmatched_marker,
            )
        rule_matched = match_store(desc.strip(), rules)
        if rule_matched:
            return MatchStoreResult(matched_rules=rule_matched, from_similarity=False, llm_desc=desc)
        return MatchStoreResult(
            matched_rules=sim_result.rules,
            from_similarity=True,
            ref_brand=sim_result.brand,
            score=sim_result.score,
            llm_desc=desc,
        )
    return MatchStoreResult(
        matched_rules=sim_result.rules,
        from_similarity=True,
        ref_brand=sim_result.brand,
        score=sim_result.score,
    )


async def match_store_categories_async(
    store_text: str,
    rules: list[CategoryRule],
    verified_brands: list[VerifiedBrand],
) -> MatchStoreResult:
    """
    单条匹配（异步版）：逻辑与 match_store_categories 一致，大模型调用使用 await。
    """
    store_text = store_text.strip()
    matched = match_store(store_text, rules)
    if matched:
        return MatchStoreResult(matched_rules=matched, from_similarity=False, score=0.0)
    mc = _matching_config()
    if not verified_brands:
        logger.debug("未进入 LLM/MCP：无已校验品牌")
        return MatchStoreResult(matched_rules=[], from_similarity=False, score=0.0)
    sim_result = match_by_similarity(
        store_text, verified_brands, threshold=mc.similarity_threshold
    )
    if not sim_result.rules or sim_result.brand is None:
        logger.info("未进入 LLM/MCP [%s]：无相似度匹配（与已校验品牌均不相似）", store_text[:40])
        return MatchStoreResult(matched_rules=[], from_similarity=False, score=0.0)
    if sim_result.score >= mc.llm_fallback_threshold:
        logger.info("未进入 LLM/MCP [%s]：相似度 %.2f >= %.2f，直接采用相似度结果", store_text[:40], sim_result.score, mc.llm_fallback_threshold)
        return MatchStoreResult(
            matched_rules=sim_result.rules,
            from_similarity=True,
            ref_brand=sim_result.brand,
            score=sim_result.score,
        )
    logger.info("开始调用大模型 [%s]：相似度 < %.2f", store_text[:40], mc.llm_fallback_threshold)
    desc = await get_category_description_with_search_async(
        store_text,
        rules=rules,
        context={
            "similarity_threshold": mc.llm_fallback_threshold,
            "similarity_score": round(sim_result.score, 4),
            "item": store_text[:50] + ("..." if len(store_text) > 50 else ""),
        },
    )
    if desc:
        if desc.strip() in mc.llm_unmatched_aliases:
            return MatchStoreResult(
                matched_rules=sim_result.rules,
                from_similarity=True,
                ref_brand=sim_result.brand,
                score=sim_result.score,
                llm_desc=mc.llm_unmatched_marker,
            )
        rule_matched = match_store(desc.strip(), rules)
        if rule_matched:
            return MatchStoreResult(matched_rules=rule_matched, from_similarity=False, llm_desc=desc)
        return MatchStoreResult(
            matched_rules=sim_result.rules,
            from_similarity=True,
            ref_brand=sim_result.brand,
            score=sim_result.score,
            llm_desc=desc,
        )
    return MatchStoreResult(
        matched_rules=sim_result.rules,
        from_similarity=True,
        ref_brand=sim_result.brand,
        score=sim_result.score,
    )


def _build_result_row(name: str, out: MatchStoreResult) -> ResultRow:
    """根据单条匹配结果 MatchStoreResult 构建 MatchResult 并转为 7 列 ResultRow。"""
    matched = out.matched_rules
    mc = _matching_config()
    if not matched:
        result = MatchResult(raw_text=name, method="未匹配")
        return result.to_result_row()
    llm_desc = out.llm_desc
    if llm_desc is not None and llm_desc.strip() in mc.llm_unmatched_aliases:
        method = "未搜索到"
    elif llm_desc is not None and not out.from_similarity:
        method = "搜索后匹配"
    elif llm_desc is not None and out.from_similarity:
        method = "搜索后未匹配"
    else:
        method = "相似度" if out.from_similarity else "规则"
    ref_brand = out.ref_brand
    ref_code = str(ref_brand.brand_code) if ref_brand else ""
    ref_name = (ref_brand.brand_name or "").strip() if ref_brand else ""
    ref_atomic = (ref_brand.atomic_category or "").strip() if ref_brand else ""
    score_str = f"{out.score:.4f}" if out.from_similarity and ref_brand else ""
    if method == "规则":
        similarity_col = "已使用关键词匹配到"
    elif method == "搜索后匹配":
        similarity_col = "搜索后匹配到"
    else:
        parts = []
        if ref_name:
            parts.append(ref_name)
        if ref_code:
            parts.append(f"（{ref_code}）")
        if ref_atomic:
            parts.append(f" 原子品类 {ref_atomic}")
        if score_str:
            parts.append(f" 相似度 {score_str}")
        similarity_col = "".join(parts).strip() if parts else ""
    if method in ("未搜索到", "搜索后未匹配"):
        level1_cat = code_cat = atomic_cat = ""
    else:
        level1_parts = [(r.level1_category or "").strip() for r in matched if (r.level1_category or "").strip()]
        code_parts = [str(r.category_code) for r in matched if r.category_code != ""]
        atomic_parts = [(r.atomic_category or "").strip() for r in matched if (r.atomic_category or "").strip()]
        level1_cat = "；".join(level1_parts) if level1_parts else ""
        code_cat = "；".join(code_parts) if code_parts else ""
        atomic_cat = "；".join(atomic_parts) if atomic_parts else ""
    result = MatchResult(
        raw_text=name,
        level1_category=level1_cat,
        category_code=code_cat,
        atomic_category=atomic_cat,
        method=method,
        similarity_detail=similarity_col,
        score=out.score if out.from_similarity and ref_brand else 0.0,
        llm_desc=llm_desc or "",
    )
    return result.to_result_row()


async def _match_one_with_sem(
    name: str,
    rules: list[CategoryRule],
    verified_brands: list[VerifiedBrand],
    sem: asyncio.Semaphore,
) -> tuple[str, MatchStoreResult]:
    async with sem:
        out = await match_store_categories_async(name, rules, verified_brands)
        return (name, out)


async def run_batch_match_async(
    categories: list[str],
    rules: list[CategoryRule],
    verified_brands: list[VerifiedBrand],
) -> list[ResultRow]:
    """批量匹配（asyncio 并发）。返回 7 列，顺序与输入一致。"""
    if not categories:
        return []
    sem = asyncio.Semaphore(_matching_config().batch_max_workers)
    tasks = [_match_one_with_sem(name, rules, verified_brands, sem) for name in categories]
    raw_results: list[tuple[str, MatchStoreResult]] = []
    for coro in tqdm(asyncio.as_completed(tasks), total=len(tasks), desc="品类匹配", unit="条"):
        raw_results.append(await coro)
    # 按输入顺序还原：as_completed 乱序，需用 name 映射后按 categories 顺序排列
    completed: dict[str, ResultRow] = {}
    for name, out in raw_results:
        completed[name] = _build_result_row(name, out)
    return [completed[name] for name in categories]


def run_batch_match(
    categories: list[str],
    rules: list[CategoryRule],
    verified_brands: list[VerifiedBrand],
) -> list[ResultRow]:
    """批量匹配（同步入口，内部 asyncio.run 跑并发）。返回 7 列。"""
    return asyncio.run(run_batch_match_async(categories, rules, verified_brands))
