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
from models.schemas import MatchStoreResult

from .file_io import METHOD_EXCEPTION, ResultRow

logger = logging.getLogger(__name__)


def _matching_config():
    """匹配配置（来自 app_config.yaml matching 节）；需已调用 load_app_config()。"""
    from core.config import inject, MatchingConfig
    return inject(MatchingConfig)


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
    # 无内容且无 tool_calls 时仍输出相似度匹配结果，但标记为「搜索后未匹配」
    return MatchStoreResult(
        matched_rules=sim_result.rules,
        from_similarity=True,
        ref_brand=sim_result.brand,
        score=sim_result.score,
        llm_desc="大模型无有效返回（无内容且无 tool_calls）",
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
    # 无内容且无 tool_calls 时仍输出相似度匹配结果，但标记为「搜索后未匹配」
    return MatchStoreResult(
        matched_rules=sim_result.rules,
        from_similarity=True,
        ref_brand=sim_result.brand,
        score=sim_result.score,
        llm_desc="大模型无有效返回（无内容且无 tool_calls）",
    )


def _build_result_row(lead_code: str, lead_name: str, out: MatchStoreResult) -> ResultRow:
    """根据单条匹配结果构建 11 列 ResultRow（相似度拆为 品牌/编码/原子品类/相似度 四列）。"""
    matched = out.matched_rules
    mc = _matching_config()
    llm_desc = out.llm_desc or ""
    if not matched:
        return (
            lead_code,
            lead_name,
            "",
            "",
            "",
            "未匹配",
            "",
            "",
            "",
            "",
            llm_desc,
        )
    if llm_desc and llm_desc.strip() in mc.llm_unmatched_aliases:
        method = "未搜索到"
    elif llm_desc and not out.from_similarity:
        method = "搜索后匹配"
    elif llm_desc and out.from_similarity:
        method = "搜索后未匹配"
    else:
        method = "相似度" if out.from_similarity else "规则"
    ref_brand = out.ref_brand
    sim_brand = (ref_brand.brand_name or "").strip() if ref_brand else ""
    sim_code = str(ref_brand.brand_code) if ref_brand else ""
    sim_atomic = (ref_brand.atomic_category or "").strip() if ref_brand else ""
    score_str = f"{out.score:.4f}" if out.from_similarity and ref_brand else ""
    if method in ("未搜索到", "搜索后未匹配"):
        level1_cat = code_cat = atomic_cat = ""
    else:
        level1_parts = [(r.level1_category or "").strip() for r in matched if (r.level1_category or "").strip()]
        code_parts = [str(r.category_code) for r in matched if r.category_code != ""]
        atomic_parts = [(r.atomic_category or "").strip() for r in matched if (r.atomic_category or "").strip()]
        level1_cat = "；".join(level1_parts) if level1_parts else ""
        code_cat = "；".join(code_parts) if code_parts else ""
        atomic_cat = "；".join(atomic_parts) if atomic_parts else ""
    return (
        lead_code,
        lead_name,
        level1_cat,
        code_cat,
        atomic_cat,
        method,
        sim_brand,
        sim_code,
        sim_atomic,
        score_str,
        llm_desc,
    )


async def _match_one_with_sem(
    item: tuple[str, str],
    rules: list[CategoryRule],
    verified_brands: list[VerifiedBrand],
    sem: asyncio.Semaphore,
) -> tuple[tuple[str, str], MatchStoreResult | None]:
    """单条匹配：item=(线索编码, 线索名称)，按线索名称匹配。异常时返回 (item, None)，由调用方记为「程序异常」并标红。"""
    lead_code, lead_name = item
    async with sem:
        try:
            out = await match_store_categories_async(lead_name, rules, verified_brands)
            return (item, out)
        except Exception:
            logger.exception("单条匹配异常 | lead_code=%s | lead_name=%s", lead_code, (lead_name or "")[:50])
            return (item, None)


def _build_exception_result_row(lead_code: str, lead_name: str) -> ResultRow:
    """单条匹配发生异常时返回的 11 列结果行（匹配方式为「程序异常」，会标红）。"""
    return (
        lead_code,
        lead_name,
        "",
        "",
        "",
        METHOD_EXCEPTION,
        "",
        "",
        "",
        "",
        METHOD_EXCEPTION,
    )


async def run_batch_match_async(
    items: list[tuple[str, str]],
    rules: list[CategoryRule],
    verified_brands: list[VerifiedBrand],
) -> list[ResultRow]:
    """批量匹配（asyncio 并发）。单条异常记为「程序异常」并标红，其余继续。返回 11 列顺序与输入一致。"""
    if not items:
        return []
    sem = asyncio.Semaphore(_matching_config().batch_max_workers)
    tasks = [_match_one_with_sem(item, rules, verified_brands, sem) for item in items]
    raw_results: list[tuple[tuple[str, str], MatchStoreResult | None]] = []
    for coro in tqdm(asyncio.as_completed(tasks), total=len(tasks), desc="品类匹配", unit="条"):
        raw_results.append(await coro)
    completed: dict[tuple[str, str], ResultRow] = {}
    for (lead_code, lead_name), out in raw_results:
        if out is None:
            completed[(lead_code, lead_name)] = _build_exception_result_row(lead_code, lead_name)
        else:
            completed[(lead_code, lead_name)] = _build_result_row(lead_code, lead_name, out)
    return [completed[item] for item in items]


def run_batch_match(
    items: list[tuple[str, str]],
    rules: list[CategoryRule],
    verified_brands: list[VerifiedBrand],
) -> list[ResultRow]:
    """批量匹配（同步入口，内部 asyncio.run 跑并发）。items=(线索编码, 线索名称)，返回 11 列。"""
    return asyncio.run(run_batch_match_async(items, rules, verified_brands))
