"""
大模型客户端：根据品类文本生成品类描述，支持 MCP 工具（搜索等）。
配置统一从 core.config 获取（get_llm_config、get_mcp_config）。
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

# 单次调用最大 token
MAX_TOKENS = 768


async def _call_llm_with_mcp_async(
    category_text: str,
    api_key: str,
    base_url: str,
    model: str,
    mcp_config: list[Any],
    prompt_base: str,
    prompt_tools: str,
    reference_keywords: str,
) -> str | None:
    """异步：带 MCP 工具调用大模型，返回品类描述或 None。"""
    from openai import AsyncOpenAI
    from mcp_client import MCPClientManager

    messages: list[dict[str, Any]] = [
        {"role": "user", "content": category_text.strip()},
    ]
    tools: list[dict[str, Any]] = []
    tool_name_to_server_and_tool: dict[str, tuple[str, str, Any]] = {}

    async with MCPClientManager(mcp_config) as manager:
        mcp_tools = await manager.list_tools()
        if mcp_tools:
            for server_name, tool in mcp_tools:
                name = getattr(tool, "name", None) or ""
                full_name = f"{server_name}__{name}"
                tool_name_to_server_and_tool[full_name] = (server_name, name, tool)
                tools.append({
                    "type": "function",
                    "function": {
                        "name": full_name,
                        "description": getattr(tool, "description", None) or "",
                        "parameters": getattr(tool, "inputSchema", None) or {},
                    },
                })

    system_content = prompt_base
    if reference_keywords:
        system_content += "\n\n## 参考词汇\n\n可优先选用：" + reference_keywords + "\n"
    if tools:
        system_content += "\n\n" + prompt_tools

    messages_with_system = [{"role": "system", "content": system_content}] + messages
    client = AsyncOpenAI(api_key=api_key, base_url=base_url.rstrip("/"))

    max_rounds = 8
    for _ in range(max_rounds):
        response = await client.chat.completions.create(
            model=model,
            messages=messages_with_system,
            tools=tools if tools else None,
            max_tokens=MAX_TOKENS,
        )
        choice = response.choices[0] if response.choices else None
        if not choice:
            return None
        msg = choice.message
        if not msg:
            return None
        if msg.content and (msg.content or "").strip():
            return (msg.content or "").strip()
        if not tools or not getattr(msg, "tool_calls", None):
            return None
        tool_calls = list(msg.tool_calls or [])
        messages_with_system.append({
            "role": "assistant",
            "content": msg.content or "",
            "tool_calls": [
                {"id": tc.id, "type": "function", "function": {"name": tc.function.name, "arguments": tc.function.arguments or "{}"}}
                for tc in tool_calls
            ],
        })
        for tc in tool_calls:
            name = tc.function.name if hasattr(tc.function, "name") else (tc.function.get("name") or "")
            args_str = tc.function.arguments if hasattr(tc.function, "arguments") else (tc.function.get("arguments") or "{}")
            try:
                args = json.loads(args_str)
            except Exception:
                args = {}
            if name in tool_name_to_server_and_tool:
                server_name, tool_name, _ = tool_name_to_server_and_tool[name]
                async with MCPClientManager(mcp_config) as manager:
                    result = await manager.call_tool(server_name, tool_name, args)
                content = str(getattr(result, "content", None) or result) if result else ""
                messages_with_system.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": content,
                })
            else:
                messages_with_system.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": "{}",
                })
    return None


def _get_llm_call_params(rules: list[Any] | None) -> tuple[str, str, str, list[Any], str, str, str] | None:
    """获取 LLM+MCP 调用参数；未配置时打 warning 并返回 None。"""
    from core.conf import get_llm_config, get_mcp_config

    api_key, base_url, model = get_llm_config()
    if not api_key:
        logger.warning(
            "未配置大模型 API Key，跳过大模型调用（请配置 config/llm_config.json 或环境变量 OPENAI_API_KEY）"
        )
        return None
    mcp_config = get_mcp_config()
    if not mcp_config:
        logger.warning(
            "未找到 MCP 配置文件（mcp_client_config.json），大模型调用需要该文件；请将 mcp_client_config.json 放在 config 目录"
        )
        return None
    from . import prompt as _prompt
    prompt_base = _prompt.PROMPT_BASE
    prompt_tools = _prompt.PROMPT_TOOLS
    reference_keywords = _prompt.build_keyword_hint(rules) if rules else ""
    return (api_key, base_url, model, mcp_config, prompt_base, prompt_tools, reference_keywords)


def get_category_description_with_search(
    category_text: str,
    *,
    rules: list[Any] | None = None,
) -> str | None:
    """根据品类文本调用大模型（带 MCP 工具）生成品类描述；未配置或失败返回 None。"""
    params = _get_llm_call_params(rules)
    if params is None:
        return None
    api_key, base_url, model, mcp_config, prompt_base, prompt_tools, ref_kw = params
    try:
        return asyncio.run(
            _call_llm_with_mcp_async(
                category_text, api_key, base_url, model,
                mcp_config, prompt_base, prompt_tools, ref_kw,
            )
        )
    except Exception as e:
        logger.warning("大模型调用失败: %s", e)
        return None


async def get_category_description_with_search_async(
    category_text: str,
    *,
    rules: list[Any] | None = None,
) -> str | None:
    """异步：根据品类文本调用大模型（带 MCP 工具）生成品类描述；未配置或失败返回 None。"""
    params = _get_llm_call_params(rules)
    if params is None:
        return None
    api_key, base_url, model, mcp_config, prompt_base, prompt_tools, ref_kw = params
    try:
        return await _call_llm_with_mcp_async(
            category_text, api_key, base_url, model,
            mcp_config, prompt_base, prompt_tools, ref_kw,
        )
    except Exception as e:
        logger.warning("大模型调用失败: %s", e)
        return None
