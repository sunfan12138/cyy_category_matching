"""
大模型客户端：根据品类文本生成品类描述，支持 MCP 工具（搜索等）。
配置从 core.config 获取；调用结果写一条 JSON 到 llm.http 日志。
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)
HTTP_LOG_NAME = "llm.http"

# 最大请求轮数（含工具调用）
MAX_REQUEST_ROUNDS = 8


def _http_logger() -> logging.Logger:
    return logging.getLogger(HTTP_LOG_NAME)


def _llm_client_config():
    from core.config import get_app_config
    return get_app_config().llm_client


def _summary(text: str, max_len: int | None = None) -> str:
    s = (text or "").strip()
    if max_len is None:
        max_len = _llm_client_config().log_input_summary_len
    return s if len(s) <= max_len else s[:max_len] + "..."


def _mask_base_url(url: str) -> str:
    if not url or not url.strip():
        return "(未配置)"
    u = url.strip().rstrip("/")
    for prefix in ("https://", "http://"):
        if u.startswith(prefix):
            rest = u[len(prefix):].split("/")[0].split("?")[0]
            return prefix + rest
    return "(无效)"


def _is_tool_call_like_text(text: str) -> bool:
    """若输出形如工具调用（如 </tool_call> 或 {"name":..., "arguments":...}），不当作最终答案。"""
    s = (text or "").strip()
    if not s:
        return False
    if "</tool_call>" in s:
        return True
    if s.startswith("{") and '"name"' in s and '"arguments"' in s:
        try:
            json.loads(s.split("\n")[0].strip().rstrip("</tool_call>").strip())
            return True
        except Exception:
            pass
    return False


# ----- MCP 服务器构建 -----


def _build_mcp_servers(mcp_config: list[Any]) -> list[Any]:
    """从项目 MCP 配置构建 Pydantic AI 的 MCP 服务器列表。"""
    from pydantic_ai.mcp import MCPServerSSE, MCPServerStdio, MCPServerStreamableHTTP

    servers: list[Any] = []
    for cfg in mcp_config:
        name = getattr(cfg, "name", None) or ""
        transport = (getattr(cfg, "transport", None) or "stdio").strip().lower()
        prefix = f"{name}__" if name else None
        if transport == "stdio":
            command = getattr(cfg, "command", None) or ""
            if not command:
                continue
            servers.append(MCPServerStdio(
                command,
                args=getattr(cfg, "args", None) or [],
                env=getattr(cfg, "env", None),
                cwd=getattr(cfg, "cwd", None),
                tool_prefix=prefix,
                timeout=10,
            ))
        elif transport == "streamable-http":
            url = getattr(cfg, "url", None) or ""
            if url:
                servers.append(MCPServerStreamableHTTP(url, tool_prefix=prefix))
        elif transport == "sse":
            url = getattr(cfg, "url", None) or ""
            if url:
                servers.append(MCPServerSSE(url, tool_prefix=prefix))
    return servers


# ----- 流程日志 -----


def _log_flow(
    trace_id: str,
    config: dict[str, Any],
    result: Any,
    start_time: float,
    status: str,
    error: str | None = None,
) -> None:
    """写单次调用的 JSON 流程日志（成功/失败统一入口）。"""
    elapsed_ms = int((time.perf_counter() - start_time) * 1000)
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    final_answer = None
    if result is not None:
        try:
            u = result.usage()
            usage["prompt_tokens"] = getattr(u, "input_tokens", 0) or 0
            usage["completion_tokens"] = getattr(u, "output_tokens", 0) or 0
            usage["total_tokens"] = usage["prompt_tokens"] + usage["completion_tokens"]
        except Exception:
            pass
        if status == "success":
            final_answer = result.output
    if usage.get("total_tokens", 0) == 0:
        usage["total_tokens"] = usage["prompt_tokens"] + usage["completion_tokens"]
    try:
        payload = {
            "trace_id": trace_id,
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "config": config,
            "metrics": {"total_latency": elapsed_ms, "total_tokens": usage.get("total_tokens", 0)},
        }
        if status != "success":
            payload["status"] = status
            if error is not None:
                payload["error"] = error
        if final_answer is not None:
            payload["final_answer"] = final_answer
        _http_logger().info("%s", json.dumps(payload, ensure_ascii=False))
    except Exception:
        pass


# ----- 主调用 -----


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
    from pydantic_ai import Agent, UsageLimitExceeded, UsageLimits
    from pydantic_ai.models.openai import OpenAIChatModel
    from pydantic_ai.providers.openai import OpenAIProvider
    from pydantic_ai.settings import ModelSettings

    ctx_str = ",".join(f"{k}={v}" for k, v in sorted((context or {}).items()) if v is not None)
    cfg = _llm_client_config()
    config = {"model": model, "temperature": 0, "max_tokens": cfg.max_tokens}
    start_time = time.perf_counter()
    trace_id = f"flow_{uuid.uuid4().hex[:8]}_{datetime.now(timezone.utc).strftime('%Y')}_{uuid.uuid4().hex[:4]}"

    logger.info(
        "[LLM] 开始调用 | context={%s} | input=%s | model=%s | base_url=%s",
        ctx_str or "无",
        _summary(category_text),
        model,
        _mask_base_url(base_url),
    )

    instructions = prompt_base
    if reference_keywords:
        instructions += "\n\n## 参考词汇\n\n可优先选用：" + reference_keywords + "\n"
    instructions += "\n\n" + prompt_tools

    try:
        mcp_servers = _build_mcp_servers(mcp_config)
    except Exception as e:
        logger.exception("[LLM] MCP 服务器构建失败 | error=%s", e)
        _log_flow(trace_id, config, None, start_time, "error", str(e))
        return None

    if mcp_servers:
        logger.info("[LLM] MCP 工具集 | prefixes=%s", [getattr(s, "tool_prefix", "") for s in mcp_servers])

    # 文档：兼容 OpenAI 的 API 使用 OpenAIProvider(base_url=..., api_key=...) + OpenAIChatModel
    # https://ai.pydantic.org.cn/models/openai/#兼容-openai-的模型
    model_instance = OpenAIChatModel(
        model,
        provider=OpenAIProvider(base_url=base_url.rstrip("/"), api_key=api_key),
    )
    agent = Agent(model_instance, instructions=instructions, toolsets=mcp_servers)

    try:
        async with agent:
            result = await agent.run(
                category_text.strip(),
                usage_limits=UsageLimits(request_limit=MAX_REQUEST_ROUNDS),
                model_settings=ModelSettings(max_tokens=cfg.max_tokens, temperature=0),
            )
    except UsageLimitExceeded as e:
        logger.warning("[LLM] 达到最大轮数 | trace_id=%s | error=%s", trace_id, e)
        _log_flow(trace_id, config, None, start_time, "max_rounds_exceeded", str(e))
        return None
    except Exception as e:
        logger.exception("[LLM] 模型请求异常 | trace_id=%s | error=%s", trace_id, e)
        _log_flow(trace_id, config, None, start_time, "error", str(e))
        return None

    output_text = (result.output or "").strip() if isinstance(result.output, str) else str(result.output or "").strip()
    if output_text and _is_tool_call_like_text(output_text):
        logger.info("[LLM] 输出为工具调用文本，忽略 | trace_id=%s", trace_id)
        _log_flow(trace_id, config, result, start_time, "no_content")
        return None

    _log_flow(trace_id, config, result, start_time, "success")
    logger.info(
        "[LLM] 成功 | trace_id=%s | len=%s | summary=%s | elapsed=%.2fs",
        trace_id,
        len(output_text),
        _summary(output_text, cfg.log_result_summary_len),
        (time.perf_counter() - start_time),
    )
    return output_text or None


# ----- 参数与对外 API -----


def _get_llm_call_params(rules: list[Any] | None) -> Any | None:
    from models.schemas import LlmCallParams
    from core.config import get_llm_config, get_mcp_config
    from . import prompt as _prompt

    cfg = get_llm_config()
    if not cfg.api_key:
        logger.warning("未配置大模型 API Key，请配置 config/app_config.yaml 或环境变量 OPENAI_API_KEY")
        return None
    mcp_config = get_mcp_config()
    if not mcp_config:
        logger.warning("未找到 MCP 配置（app_config.yaml 的 mcp.servers）")
        return None
    return LlmCallParams(
        api_key=cfg.api_key,
        base_url=cfg.base_url,
        model=cfg.model,
        mcp_config=mcp_config,
        prompt_base=_prompt.PROMPT_BASE,
        prompt_tools=_prompt.PROMPT_TOOLS,
        reference_keywords=_prompt.build_keyword_hint(rules) if rules else "",
    )


def get_category_description_with_search(
    category_text: str,
    *,
    rules: list[Any] | None = None,
    context: dict[str, Any] | None = None,
) -> str | None:
    """根据品类文本调用大模型（带 MCP 工具）生成品类描述；未配置或失败返回 None。"""
    params = _get_llm_call_params(rules)
    if params is None:
        return None
    try:
        return asyncio.run(_call_llm_with_mcp_async(
            category_text,
            params.api_key,
            params.base_url,
            params.model,
            params.mcp_config,
            params.prompt_base,
            params.prompt_tools,
            params.reference_keywords,
            context=context,
        ))
    except Exception as e:
        logger.error("[LLM] 调用失败 | input=%s | error=%s", _summary(category_text), e, exc_info=True)
        return None


async def get_category_description_with_search_async(
    category_text: str,
    *,
    rules: list[Any] | None = None,
    context: dict[str, Any] | None = None,
) -> str | None:
    """异步：根据品类文本调用大模型（带 MCP 工具）生成品类描述；未配置或失败返回 None。"""
    params = _get_llm_call_params(rules)
    if params is None:
        return None
    try:
        return await _call_llm_with_mcp_async(
            category_text,
            params.api_key,
            params.base_url,
            params.model,
            params.mcp_config,
            params.prompt_base,
            params.prompt_tools,
            params.reference_keywords,
            context=context,
        )
    except Exception as e:
        logger.error("[LLM] 调用失败 | input=%s | error=%s", _summary(category_text), e, exc_info=True)
        return None
