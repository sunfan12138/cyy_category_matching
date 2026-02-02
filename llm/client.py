"""
大模型客户端：根据品类文本生成品类描述，支持 MCP 工具（搜索等）。
配置从 core.conf 获取（get_llm_config、get_mcp_config）。
日志：每轮调用、工具调用、耗时与异常均记录，便于调试与追踪；敏感信息（API Key）不输出。
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

# 单次调用最大 token
MAX_TOKENS = 768

# 日志用摘要最大长度（避免 prompt/结果全文打日志）
LOG_INPUT_SUMMARY_LEN = 80
LOG_RESULT_SUMMARY_LEN = 120


def _summary(text: str, max_len: int = LOG_INPUT_SUMMARY_LEN) -> str:
    """对长文本做摘要，用于日志，避免输出全文。"""
    s = (text or "").strip()
    if len(s) <= max_len:
        return s
    return s[:max_len] + "..."


def _mask_base_url(url: str) -> str:
    """仅输出 scheme + netloc，不包含 path/query，避免敏感信息。"""
    if not url or not url.strip():
        return "(未配置)"
    u = url.strip().rstrip("/")
    for prefix in ("https://", "http://"):
        if u.startswith(prefix):
            rest = u[len(prefix) :]
            netloc = rest.split("/")[0].split("?")[0]
            return prefix + netloc
    return "(无效)"


async def _call_llm_with_mcp_async(
    category_text: str,
    api_key: str,
    base_url: str,
    model: str,
    mcp_config: list[Any],
    prompt_base: str,
    prompt_tools: str,
    reference_keywords: str,
    *,
    context: dict[str, Any] | None = None,
) -> str | None:
    """异步：带 MCP 工具调用大模型，返回品类描述或 None。"""
    from openai import AsyncOpenAI
    from mcp_client import MCPClientManager

    ctx = context or {}
    ctx_str = ",".join(f"{k}={v}" for k, v in sorted(ctx.items()) if v is not None)
    input_summary = _summary(category_text, LOG_INPUT_SUMMARY_LEN)
    base_url_masked = _mask_base_url(base_url)

    logger.info(
        "[LLM] 开始调用 | context={%s} | input_summary=%s | model=%s | base_url=%s | max_tokens=%s",
        ctx_str or "无",
        input_summary,
        model,
        base_url_masked,
        MAX_TOKENS,
    )
    start_time = time.perf_counter()

    messages: list[dict[str, Any]] = [
        {"role": "user", "content": category_text.strip()},
    ]
    tools: list[dict[str, Any]] = []
    tool_name_to_server_and_tool: dict[str, tuple[str, str, Any]] = {}

    try:
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
        tool_names = list(tool_name_to_server_and_tool.keys())
        if tool_names:
            logger.info("[LLM] MCP 工具已加载 | tools=%s", tool_names)
    except Exception as e:
        logger.exception("[LLM] MCP 工具加载失败 | context={%s} | error=%s", ctx_str or "无", e)
        return None

    system_content = prompt_base
    if reference_keywords:
        system_content += "\n\n## 参考词汇\n\n可优先选用：" + reference_keywords + "\n"
    if tools:
        system_content += "\n\n" + prompt_tools

    messages_with_system = [{"role": "system", "content": system_content}] + messages
    client = AsyncOpenAI(api_key=api_key, base_url=base_url.rstrip("/"))

    max_rounds = 8
    for round_no in range(1, max_rounds + 1):
        try:
            response = await client.chat.completions.create(
                model=model,
                messages=messages_with_system,
                tools=tools if tools else None,
                max_tokens=MAX_TOKENS,
            )
        except Exception as e:
            elapsed = time.perf_counter() - start_time
            logger.error(
                "[LLM] 模型请求异常 | round=%s | context={%s} | input_summary=%s | elapsed=%.2fs | error=%s",
                round_no,
                ctx_str or "无",
                input_summary,
                elapsed,
                e,
                exc_info=True,
            )
            return None

        choice = response.choices[0] if response.choices else None
        if not choice:
            logger.warning("[LLM] 无有效 choice | round=%s | context={%s}", round_no, ctx_str or "无")
            return None
        msg = choice.message
        if not msg:
            logger.warning("[LLM] 无 message | round=%s | context={%s}", round_no, ctx_str or "无")
            return None

        if msg.content and (msg.content or "").strip():
            result = (msg.content or "").strip()
            elapsed = time.perf_counter() - start_time
            logger.info(
                "[LLM] 返回成功 | round=%s | context={%s} | result_len=%s | result_summary=%s | elapsed=%.2fs",
                round_no,
                ctx_str or "无",
                len(result),
                _summary(result, LOG_RESULT_SUMMARY_LEN),
                elapsed,
            )
            return result

        if not tools or not getattr(msg, "tool_calls", None):
            logger.info("[LLM] 无内容且无 tool_calls，结束 | round=%s | context={%s}", round_no, ctx_str or "无")
            return None

        tool_calls = list(msg.tool_calls or [])
        called_names = [
            getattr(tc.function, "name", None) or tc.function.get("name") or ""
            for tc in tool_calls
        ]
        logger.info(
            "[LLM] 本轮需调用工具 | round=%s | context={%s} | tool_calls=%s",
            round_no,
            ctx_str or "无",
            called_names,
        )

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
                try:
                    async with MCPClientManager(mcp_config) as manager:
                        result = await manager.call_tool(server_name, tool_name, args)
                    content = str(getattr(result, "content", None) or result) if result else ""
                    logger.info(
                        "[LLM] 工具调用完成 | tool=%s | server=%s | context={%s}",
                        tool_name,
                        server_name,
                        ctx_str or "无",
                    )
                except Exception as e:
                    logger.warning(
                        "[LLM] 工具调用失败 | tool=%s | server=%s | context={%s} | error=%s",
                        tool_name,
                        server_name,
                        ctx_str or "无",
                        e,
                    )
                    content = ""
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

    elapsed = time.perf_counter() - start_time
    logger.warning(
        "[LLM] 达到最大轮数未得到文本结果 | context={%s} | input_summary=%s | rounds=%s | elapsed=%.2fs",
        ctx_str or "无",
        input_summary,
        max_rounds,
        elapsed,
    )
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
    context: dict[str, Any] | None = None,
) -> str | None:
    """
    根据品类文本调用大模型（带 MCP 工具）生成品类描述；未配置或失败返回 None。

    context 可选，用于日志追踪，如 batch_id、item_id、similarity_threshold 等。
    """
    params = _get_llm_call_params(rules)
    if params is None:
        return None
    api_key, base_url, model, mcp_config, prompt_base, prompt_tools, ref_kw = params
    try:
        return asyncio.run(
            _call_llm_with_mcp_async(
                category_text, api_key, base_url, model,
                mcp_config, prompt_base, prompt_tools, ref_kw,
                context=context,
            )
        )
    except Exception as e:
        logger.error(
            "[LLM] 调用失败 | input_summary=%s | context=%s | error=%s",
            _summary(category_text),
            context,
            e,
            exc_info=True,
        )
        return None


async def get_category_description_with_search_async(
    category_text: str,
    *,
    rules: list[Any] | None = None,
    context: dict[str, Any] | None = None,
) -> str | None:
    """
    异步：根据品类文本调用大模型（带 MCP 工具）生成品类描述；未配置或失败返回 None。

    context 可选，用于日志追踪，如 batch_id、item_id、similarity_threshold 等。
    """
    params = _get_llm_call_params(rules)
    if params is None:
        return None
    api_key, base_url, model, mcp_config, prompt_base, prompt_tools, ref_kw = params
    try:
        return await _call_llm_with_mcp_async(
            category_text, api_key, base_url, model,
            mcp_config, prompt_base, prompt_tools, ref_kw,
            context=context,
        )
    except Exception as e:
        logger.error(
            "[LLM] 调用失败 | input_summary=%s | context=%s | error=%s",
            _summary(category_text),
            context,
            e,
            exc_info=True,
        )
        return None