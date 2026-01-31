"""大模型调用：根据品类文本生成简短描述，用于二次关键词规则匹配。key/url/model 可配置，key 加密存储、不可直接展示。"""

from __future__ import annotations

from .llm_config import load_llm_config

# 配置说明见 core/llm_config.py（llm_config.json 或环境变量）

_PROMPT = """你是一个品类标注助手。请根据用户给出的一条「门店/商品品类」文本，用一句简短的中文描述其含义，便于后续用关键词规则匹配。只输出这一句描述，不要解释、不要序号、不要换行。

用户输入的品类文本：
{input_text}

简短描述（一句）："""


def get_category_description(category_text: str) -> str | None:
    """
    调用大模型根据品类文本生成一句简短描述，用于二次规则匹配。
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

    try:
        client = OpenAI(api_key=api_key, base_url=base_url)
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": _PROMPT.format(input_text=category_text)}],
            max_tokens=150,
            temperature=0.3,
        )
    except Exception:
        return None

    choice = (resp.choices or [None])[0] if resp.choices else None
    if not choice or not choice.message:
        return None
    content = (choice.message.content or "").strip()
    return content if content else None
