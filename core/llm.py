"""大模型调用：根据品类文本生成简短描述，用于二次关键词规则匹配。key/url/model 可配置，key 加密存储、不可直接展示。"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from .llm_config import load_llm_config

if TYPE_CHECKING:
    from .models import CategoryRule

logger = logging.getLogger(__name__)

# 配置说明见 core/llm_config.py（llm_config.json 或环境变量）

# 基础提示：简短，强调多写几个相关词
_PROMPT_BASE = """根据下面的「门店/商品品类」文本，用一句中文描述其含义，用于关键词匹配。要求：描述中尽量多写几个相关品类词汇（同义、近义或相关词都可），不要解释、不要序号、不要换行。
"""

# 有参考关键词时只给少量示例（占位 {reference_keywords}）
_PROMPT_WITH_KEYWORDS = """参考关键词示例：{reference_keywords}
"""

_PROMPT_TAIL = """品类文本：{input_text}

描述："""

# 只取少量关键词示例（个数与总字数都限制）
_MAX_KEYWORD_EXAMPLES = 10
_MAX_KEYWORD_HINT_CHARS = 120


def _build_keyword_hint(rules: list[CategoryRule]) -> str:
    """从规则中抽取少量关键词示例，用于提示词。"""
    seen: set[str] = set()
    words: list[str] = []
    for r in rules:
        if r.atomic_category and r.atomic_category.strip() and r.atomic_category.strip() not in seen:
            seen.add(r.atomic_category.strip())
            words.append(r.atomic_category.strip())
        for g in (r.keyword_group_1, r.keyword_group_2, r.keyword_group_3, r.keyword_group_4, r.keyword_group_5):
            for kw in g:
                if kw and kw.strip() and kw.strip() not in seen:
                    seen.add(kw.strip())
                    words.append(kw.strip())
                if len(words) >= _MAX_KEYWORD_EXAMPLES:
                    break
            if len(words) >= _MAX_KEYWORD_EXAMPLES:
                break
        if len(words) >= _MAX_KEYWORD_EXAMPLES:
            break
    if not words:
        return ""
    s = "、".join(words[: _MAX_KEYWORD_EXAMPLES])
    if len(s) > _MAX_KEYWORD_HINT_CHARS:
        s = s[:_MAX_KEYWORD_HINT_CHARS].rsplit("、", 1)[0] if "、" in s[:_MAX_KEYWORD_HINT_CHARS] else s[:_MAX_KEYWORD_HINT_CHARS]
    return s


def get_category_description(category_text: str, rules: list[CategoryRule] | None = None) -> str | None:
    """
    调用大模型根据品类文本生成一句简短描述，用于二次规则匹配。
    若传入 rules，会从规则中抽取参考关键词并写入提示词，使描述更易命中关键词规则。
    使用可配置的 key/url/model（见 llm_config），key 仅内存使用，不写入日志或展示。
    若未配置 API Key 或调用失败，返回 None。
    """
    category_text = (category_text or "").strip()
    if not category_text:
        return None

    api_key, base_url, model = load_llm_config()
    if not api_key:
        return None

    try:
        from openai import OpenAI
    except ImportError:
        return None

    # 根据规则生成带参考关键词的提示词
    keyword_hint = _build_keyword_hint(rules) if rules else ""
    if keyword_hint:
        prompt = _PROMPT_BASE + _PROMPT_WITH_KEYWORDS.format(reference_keywords=keyword_hint) + _PROMPT_TAIL
    else:
        prompt = _PROMPT_BASE + _PROMPT_TAIL
    prompt = prompt.format(input_text=category_text)

    logger.info("---------- 调用开始 ----------")
    logger.info("model=%s", model)
    logger.info("输入: %s", category_text)
    logger.info("系统提示词: %s", prompt)

    t0 = time.perf_counter()
    try:
        client = OpenAI(api_key=api_key, base_url=base_url)
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=280,
            temperature=0.3,
        )
    except Exception as e:
        elapsed = time.perf_counter() - t0
        logger.warning("调用失败 model=%s error=%s 耗时=%.2fs", model, e, elapsed)
        logger.info("---------- 调用结束 ----------")
        return None

    elapsed = time.perf_counter() - t0
    usage = getattr(resp, "usage", None)
    if usage is not None:
        pt = getattr(usage, "prompt_tokens", None)
        ct = getattr(usage, "completion_tokens", None)
        tt = getattr(usage, "total_tokens", None)
        logger.info("token消耗 prompt_tokens=%s completion_tokens=%s total_tokens=%s", pt, ct, tt)

    choice = (resp.choices or [None])[0] if resp.choices else None
    if not choice or not choice.message:
        logger.warning("调用返回无有效内容 model=%s 耗时=%.2fs", model, elapsed)
        logger.info("---------- 调用结束 ----------")
        return None
    content = (choice.message.content or "").strip()
    if content:
        logger.info("输出: %s", content)
    logger.info("调用成功 model=%s 耗时=%.2fs", model, elapsed)
    logger.info("---------- 调用结束 ----------")
    return content if content else None
