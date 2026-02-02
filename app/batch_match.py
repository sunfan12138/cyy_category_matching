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

from .io import ResultRow

logger = logging.getLogger(__name__)

# 批量匹配时的并发数（asyncio 同时跑多少条），用于加速大模型等 I/O
BATCH_MAX_WORKERS = 8

SIMILARITY_THRESHOLD = 0
# 相似度低于此值时，用大模型生成品类描述并再次做关键词规则匹配
LLM_FALLBACK_SIMILARITY_THRESHOLD = 0.9
# 大模型明确返回「未匹配到结果」或「未匹配到」时，匹配方式记为「未搜索到」并标红
LLM_UNMATCHED_MARKER = "未匹配到结果"
LLM_UNMATCHED_ALIASES = ("未匹配到结果", "未匹配到")


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
        if desc.strip() in LLM_UNMATCHED_ALIASES:
            return matched, True, ref_brand, score, LLM_UNMATCHED_MARKER
        # 大模型搜索到结果后，必须对描述做关键词匹配
        rule_matched = match_store(desc.strip(), rules)
        if rule_matched:
            return rule_matched, False, None, 0.0, desc
        # 关键词未命中：仍保留相似度信息，并带上大模型描述，记为「搜索后未匹配」
        return matched, True, ref_brand, score, desc
    return matched, True, ref_brand, score, None


async def match_store_categories_async(
    store_text: str,
    rules: list[CategoryRule],
    verified_brands: list[VerifiedBrand],
) -> tuple[list[CategoryRule], bool, VerifiedBrand | None, float, str | None]:
    """
    单条匹配（异步版）：逻辑与 match_store_categories 一致，大模型调用使用 await。
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
    logger.info("开始调用大模型 [%s]：相似度 < 0.9", store_text[:40])
    desc = await get_category_description_with_search_async(store_text, rules=rules)
    if desc:
        if desc.strip() in LLM_UNMATCHED_ALIASES:
            return matched, True, ref_brand, score, LLM_UNMATCHED_MARKER
        rule_matched = match_store(desc.strip(), rules)
        if rule_matched:
            return rule_matched, False, None, 0.0, desc
        return matched, True, ref_brand, score, desc
    return matched, True, ref_brand, score, None


def _build_result_row(
    name: str,
    matched: list[CategoryRule],
    from_similarity: bool,
    ref_brand: VerifiedBrand | None,
    ref_score: float,
    llm_desc: str | None,
) -> ResultRow:
    """根据单条匹配结果拼成一行 7 列。"""
    if not matched:
        return (name, "", "", "", "未匹配", "", "")
    if llm_desc is not None and llm_desc.strip() in LLM_UNMATCHED_ALIASES:
        method = "未搜索到"
    elif llm_desc is not None and not from_similarity:
        method = "搜索后匹配"
    elif llm_desc is not None and from_similarity:
        method = "搜索后未匹配"
    else:
        method = "相似度" if from_similarity else "规则"
    ref_code = str(ref_brand.brand_code) if ref_brand else ""
    ref_name = (ref_brand.brand_name or "") if ref_brand else ""
    ref_atomic = (ref_brand.atomic_category or "").strip() if ref_brand else ""
    score_str = f"{ref_score:.4f}" if from_similarity and ref_brand else ""
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
    return (
        name,
        level1_cat,
        code_cat,
        atomic_cat,
        method,
        similarity_col,
        llm_desc or "",
    )


async def _match_one_with_sem(
    name: str,
    rules: list[CategoryRule],
    verified_brands: list[VerifiedBrand],
    sem: asyncio.Semaphore,
) -> tuple[str, list[CategoryRule], bool, VerifiedBrand | None, float, str | None]:
    async with sem:
        out = await match_store_categories_async(name, rules, verified_brands)
        return (name, out[0], out[1], out[2], out[3], out[4])


async def run_batch_match_async(
    categories: list[str],
    rules: list[CategoryRule],
    verified_brands: list[VerifiedBrand],
) -> list[ResultRow]:
    """批量匹配（asyncio 并发）。返回 7 列，顺序与输入一致。"""
    if not categories:
        return []
    sem = asyncio.Semaphore(BATCH_MAX_WORKERS)
    tasks = [_match_one_with_sem(name, rules, verified_brands, sem) for name in categories]
    raw_results: list[tuple[str, list[CategoryRule], bool, VerifiedBrand | None, float, str | None]] = []
    for coro in tqdm(asyncio.as_completed(tasks), total=len(tasks), desc="品类匹配", unit="条"):
        raw_results.append(await coro)
    # 按输入顺序还原：as_completed 乱序，需用 name 映射后按 categories 顺序排列
    completed: dict[str, ResultRow] = {}
    for name, matched, from_sim, ref_brand, ref_score, llm_desc in raw_results:
        completed[name] = _build_result_row(name, matched, from_sim, ref_brand, ref_score, llm_desc)
    return [completed[name] for name in categories]


def run_batch_match(
    categories: list[str],
    rules: list[CategoryRule],
    verified_brands: list[VerifiedBrand],
) -> list[ResultRow]:
    """批量匹配（同步入口，内部 asyncio.run 跑并发）。返回 7 列。"""
    return asyncio.run(run_batch_match_async(categories, rules, verified_brands))
