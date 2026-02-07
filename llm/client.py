"""
大模型客户端：根据品类文本生成品类描述，支持 MCP 工具（搜索等）。
配置从 core.config 获取。可观测性由 llm.trace_file 负责（Logfire 本地 trace 文件）。

Agent 按文档只实例化一次并复用，参见 https://ai.pydantic.org.cn/agents/
MCP 用法参见 https://ai.pydantic.org.cn/mcp/client/
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from dataclasses import dataclass
from typing import Any, Sequence

from .prompt import PROMPT_BASE, PROMPT_TOOLS
from .trace_file import ensure_logfire_file_export

logger = logging.getLogger(__name__)

# 最大请求轮数（含工具调用）
MAX_REQUEST_ROUNDS = 8


@dataclass(frozen=True)
class RunDeps:
    """单次运行的依赖：参考词汇等，供动态 instructions 使用。"""

    reference_keywords: str = ""


def _ensure_logfire() -> None:
    """确保 Logfire 已启用（仅本地 trace 文件），由 trace_file 模块实现。"""
    ensure_logfire_file_export()


def _llm_client_config():
    from core.config import inject, LlmClientConfig
    return inject(LlmClientConfig)


def _summary(text: str, max_len: int | None = None) -> str:
    stripped = (text or "").strip()
    if max_len is None:
        max_len = _llm_client_config().log_input_summary_len
    return stripped if len(stripped) <= max_len else stripped[:max_len] + "..."


def _mask_base_url(url: str) -> str:
    if not url or not url.strip():
        return "(未配置)"
    url_stripped = url.strip().rstrip("/")
    for prefix in ("https://", "http://"):
        if url_stripped.startswith(prefix):
            host_part = url_stripped[len(prefix):].split("/")[0].split("?")[0]
            return prefix + host_part
    return "(无效)"


# ----- MCP 服务器构建 -----
# 对应 Pydantic AI：MCPServerStdio / MCPServerStreamableHTTP / MCPServerSSE，toolsets=[...]，async with agent

# stdio 子进程默认超时（秒），与文档示例一致；可在配置中覆盖
DEFAULT_STDIO_TIMEOUT = 10


def _create_stdio_server(server_cfg: Any, tool_prefix: str | None) -> Any | None:
    """从单条配置创建 MCPServerStdio，配置无效时返回 None。"""
    from pydantic_ai.mcp import MCPServerStdio

    command = getattr(server_cfg, "command", None) or ""
    if not command:
        return None
    timeout = getattr(server_cfg, "timeout_seconds", None)
    if timeout is None or (isinstance(timeout, (int, float)) and timeout <= 0):
        timeout = DEFAULT_STDIO_TIMEOUT
    timeout_int = int(timeout) if isinstance(timeout, (int, float)) else DEFAULT_STDIO_TIMEOUT
    return MCPServerStdio(
        command,
        args=getattr(server_cfg, "args", None) or [],
        env=getattr(server_cfg, "env", None),
        cwd=getattr(server_cfg, "cwd", None),
        tool_prefix=tool_prefix,
        timeout=timeout_int,
    )


def _create_streamable_http_server(server_cfg: Any, tool_prefix: str | None) -> Any | None:
    """从单条配置创建 MCPServerStreamableHTTP，无 url 时返回 None。"""
    from pydantic_ai.mcp import MCPServerStreamableHTTP

    url = getattr(server_cfg, "url", None) or ""
    return MCPServerStreamableHTTP(url, tool_prefix=tool_prefix) if url else None


def _create_sse_server(server_cfg: Any, tool_prefix: str | None) -> Any | None:
    """从单条配置创建 MCPServerSSE，无 url 时返回 None。"""
    from pydantic_ai.mcp import MCPServerSSE

    url = getattr(server_cfg, "url", None) or ""
    return MCPServerSSE(url, tool_prefix=tool_prefix) if url else None


def _build_mcp_servers(mcp_config: list[Any]) -> list[Any]:
    """
    从项目 MCP 配置构建 Pydantic AI 的 MCP 服务器列表。
    每个服务器作为 Agent 的 toolset 注册；tool_prefix 使用「服务器名__」避免多服务器工具名冲突。
    """
    servers: list[Any] = []
    for server_cfg in mcp_config:
        name = getattr(server_cfg, "name", None) or ""
        transport = (getattr(server_cfg, "transport", None) or "stdio").strip().lower()
        tool_prefix = f"{name}__" if name else None
        server = None
        if transport == "stdio":
            server = _create_stdio_server(server_cfg, tool_prefix)
        elif transport == "streamable-http":
            server = _create_streamable_http_server(server_cfg, tool_prefix)
        elif transport == "sse":
            server = _create_sse_server(server_cfg, tool_prefix)
        if server is not None:
            servers.append(server)
    return servers


# ----- Agent 单例（文档：实例化一次、全局复用） -----

_agent_cache: Any = None
_agent_lock = threading.Lock()


def _create_agent(llm_cfg: Any, mcp_config: list[Any]) -> Any | None:
    """根据配置创建 Agent 实例；MCP 构建失败时返回 None。"""
    _ensure_logfire()
    try:
        mcp_servers = _build_mcp_servers(mcp_config)
    except Exception as err:
        logger.exception("[LLM] MCP 服务器构建失败 | error=%s", err)
        return None
    from pydantic_ai import Agent, RunContext
    from pydantic_ai.models.openai import OpenAIChatModel
    from pydantic_ai.providers.openai import OpenAIProvider

    model = OpenAIChatModel(
        llm_cfg.model,
        provider=OpenAIProvider(base_url=llm_cfg.base_url.rstrip("/"), api_key=llm_cfg.api_key),
    )
    agent = Agent(
        model,
        instructions=PROMPT_BASE + "\n\n" + PROMPT_TOOLS,
        toolsets=mcp_servers,
        deps_type=RunDeps,
    )

    @agent.instructions
    def _add_reference_keywords(ctx: RunContext[RunDeps]) -> str:
        if not ctx.deps.reference_keywords:
            return ""
        return "\n\n## 参考词汇\n\n可优先选用：" + ctx.deps.reference_keywords + "\n"

    if mcp_servers:
        logger.info("[LLM] MCP 工具集 | prefixes=%s", [getattr(srv, "tool_prefix", "") for srv in mcp_servers])
    return agent


def _get_agent() -> Any | None:
    """
    获取或创建全局 Agent 实例（仅创建一次，后续复用）。
    配置无效（未配置 API Key 或 MCP）时返回 None。
    """
    global _agent_cache
    with _agent_lock:
        if _agent_cache is not None:
            return _agent_cache
        from core.config import inject, LlmConfig, McpConfigList

        llm_cfg = inject(LlmConfig)
        mcp_config = inject(McpConfigList)
        if not llm_cfg.api_key or not mcp_config:
            return None
        agent = _create_agent(llm_cfg, mcp_config)
        if agent is not None:
            _agent_cache = agent
        return agent


# ----- 主调用 -----


async def _call_llm_with_mcp_async(
    category_text: str,
    reference_keywords: str,
    *,
    context: dict[str, Any] | None = None,
) -> str | None:
    """异步：使用全局 Agent 单例运行一次，返回品类描述或 None。"""
    from pydantic_ai import UsageLimitExceeded, UsageLimits
    from pydantic_ai.settings import ModelSettings

    agent = _get_agent()
    if agent is None:
        return None

    llm_cfg = _llm_client_config()
    context_str = ",".join(
        f"{k}={v}" for k, v in sorted((context or {}).items()) if v is not None
    )
    start_time = time.perf_counter()
    logger.info(
        "[LLM] 开始调用 | context={%s} | input=%s | model=%s | base_url=%s",
        context_str or "无",
        _summary(category_text),
        llm_cfg.model or "",
        _mask_base_url(llm_cfg.base_url or ""),
    )

    try:
        async with agent:
            result = await agent.run(
                category_text.strip(),
                deps=RunDeps(reference_keywords=reference_keywords or ""),
                usage_limits=UsageLimits(request_limit=MAX_REQUEST_ROUNDS),
                model_settings=ModelSettings(max_tokens=llm_cfg.max_tokens, temperature=0),
            )
    except UsageLimitExceeded as err:
        logger.warning("[LLM] 达到最大轮数 | error=%s", err)
        return None
    except Exception as err:
        logger.exception("[LLM] 模型请求异常 | error=%s", err)
        return None

    output_text = (result.output or "").strip() if isinstance(result.output, str) else str(result.output or "").strip()
    # Pydantic AI 会在内部执行工具调用并继续对话，run() 正常结束时 result.output 为最终文本，无需再判工具调用格式

    elapsed = time.perf_counter() - start_time
    logger.info(
        "[LLM] 成功 | len=%s | summary=%s | elapsed=%.2fs",
        len(output_text),
        _summary(output_text, llm_cfg.log_result_summary_len),
        elapsed,
    )
    return output_text or None


# ----- 参数与对外 API -----


def _get_llm_call_params(rules: list[Any] | None) -> Any | None:
    from core.config import inject, LlmConfig, McpConfigList
    from models.schemas import LlmCallParams

    from . import prompt as prompt_module

    llm_cfg = inject(LlmConfig)
    if not llm_cfg.api_key:
        logger.warning("未配置大模型 API Key，请配置 config/app_config.yaml 或环境变量 OPENAI_API_KEY")
        return None
    mcp_config = inject(McpConfigList)
    if not mcp_config:
        logger.warning("未找到 MCP 配置（app_config.yaml 的 mcp.servers）")
        return None
    return LlmCallParams(
        api_key=llm_cfg.api_key,
        base_url=llm_cfg.base_url,
        model=llm_cfg.model,
        mcp_config=mcp_config,
        prompt_base=prompt_module.PROMPT_BASE,
        prompt_tools=prompt_module.PROMPT_TOOLS,
        reference_keywords=prompt_module.build_keyword_hint(rules) if rules else "",
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
            params.reference_keywords,
            context=context,
        ))
    except Exception as err:
        logger.error("[LLM] 调用失败 | input=%s | error=%s", _summary(category_text), err, exc_info=True)
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
            params.reference_keywords,
            context=context,
        )
    except Exception as err:
        logger.error("[LLM] 调用失败 | input=%s | error=%s", _summary(category_text), err, exc_info=True)
        return None
