"""
大模型客户端：根据品类文本生成品类描述，支持 MCP 工具（搜索等）。
配置从 core.config 获取。可观测性由 llm.trace_file 负责（Logfire 本地 trace 文件）。

Agent 按文档只实例化一次并复用，参见 https://ai.pydantic.org.cn/agents/
MCP 用法参见 https://ai.pydantic.org.cn/mcp/client/
"""

from __future__ import annotations

import asyncio
import json
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
# 对应 Pydantic AI：MCPServerStdio / MCPServerStreamableHTTP / MCPServerSSE，toolsets=[...]，async with agent

# stdio 子进程默认超时（秒），与文档示例一致；可在配置中覆盖
DEFAULT_STDIO_TIMEOUT = 10


def _build_mcp_servers(mcp_config: list[Any]) -> list[Any]:
    """
    从项目 MCP 配置构建 Pydantic AI 的 MCP 服务器列表。
    每个服务器作为 Agent 的 toolset 注册；tool_prefix 使用「服务器名__」避免多服务器工具名冲突。
    """
    from pydantic_ai.mcp import MCPServerSSE, MCPServerStdio, MCPServerStreamableHTTP

    servers: list[Any] = []
    for cfg in mcp_config:
        name = getattr(cfg, "name", None) or ""
        transport = (getattr(cfg, "transport", None) or "stdio").strip().lower()
        tool_prefix = f"{name}__" if name else None  # 文档：tool_prefix 避免命名冲突
        if transport == "stdio":
            command = getattr(cfg, "command", None) or ""
            if not command:
                continue
            timeout = getattr(cfg, "timeout_seconds", None)
            if timeout is None or (isinstance(timeout, (int, float)) and timeout <= 0):
                timeout = DEFAULT_STDIO_TIMEOUT
            servers.append(MCPServerStdio(
                command,
                args=getattr(cfg, "args", None) or [],
                env=getattr(cfg, "env", None),
                cwd=getattr(cfg, "cwd", None),
                tool_prefix=tool_prefix,
                timeout=int(timeout) if isinstance(timeout, (int, float)) else DEFAULT_STDIO_TIMEOUT,
            ))
        elif transport == "streamable-http":
            # 文档推荐的可流式 HTTP 传输
            url = getattr(cfg, "url", None) or ""
            if url:
                servers.append(MCPServerStreamableHTTP(url, tool_prefix=tool_prefix))
        elif transport == "sse":
            # 文档注明 SSE 已弃用，建议改用 streamable-http
            url = getattr(cfg, "url", None) or ""
            if url:
                servers.append(MCPServerSSE(url, tool_prefix=tool_prefix))
    return servers


# ----- Agent 单例（文档：实例化一次、全局复用） -----

_agent_cache: Any = None
_agent_lock = threading.Lock()


def _get_agent() -> Any | None:
    """
    获取或创建全局 Agent 实例（仅创建一次，后续复用）。
    配置无效（未配置 API Key 或 MCP）时返回 None。
    """
    global _agent_cache
    with _agent_lock:
        if _agent_cache is not None:
            return _agent_cache
        from core.config import get_llm_config, get_mcp_config
        from pydantic_ai import Agent, RunContext
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openai import OpenAIProvider

        cfg = get_llm_config()
        mcp_config = get_mcp_config()
        if not cfg.api_key or not mcp_config:
            return None

        _ensure_logfire()
        try:
            mcp_servers = _build_mcp_servers(mcp_config)
        except Exception as e:
            logger.exception("[LLM] MCP 服务器构建失败 | error=%s", e)
            return None

        model = OpenAIChatModel(
            cfg.model,
            provider=OpenAIProvider(base_url=cfg.base_url.rstrip("/"), api_key=cfg.api_key),
        )
        static_instructions = PROMPT_BASE + "\n\n" + PROMPT_TOOLS
        agent = Agent(
            model,
            instructions=static_instructions,
            toolsets=mcp_servers,
            deps_type=RunDeps,
        )

        @agent.instructions
        def _add_reference_keywords(ctx: RunContext[RunDeps]) -> str:
            if not ctx.deps.reference_keywords:
                return ""
            return "\n\n## 参考词汇\n\n可优先选用：" + ctx.deps.reference_keywords + "\n"

        if mcp_servers:
            logger.info("[LLM] MCP 工具集 | prefixes=%s", [getattr(s, "tool_prefix", "") for s in mcp_servers])
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

    cfg = _llm_client_config()
    ctx_str = ",".join(f"{k}={v}" for k, v in sorted((context or {}).items()) if v is not None)
    start_time = time.perf_counter()
    base_url = ""
    model_name = ""
    try:
        from core.config import get_llm_config
        llm_cfg = get_llm_config()
        base_url = llm_cfg.base_url or ""
        model_name = llm_cfg.model or ""
    except Exception:
        pass

    logger.info(
        "[LLM] 开始调用 | context={%s} | input=%s | model=%s | base_url=%s",
        ctx_str or "无",
        _summary(category_text),
        model_name,
        _mask_base_url(base_url),
    )

    try:
        async with agent:
            result = await agent.run(
                category_text.strip(),
                deps=RunDeps(reference_keywords=reference_keywords or ""),
                usage_limits=UsageLimits(request_limit=MAX_REQUEST_ROUNDS),
                model_settings=ModelSettings(max_tokens=cfg.max_tokens, temperature=0),
            )
    except UsageLimitExceeded as e:
        logger.warning("[LLM] 达到最大轮数 | error=%s", e)
        return None
    except Exception as e:
        logger.exception("[LLM] 模型请求异常 | error=%s", e)
        return None

    output_text = (result.output or "").strip() if isinstance(result.output, str) else str(result.output or "").strip()
    if output_text and _is_tool_call_like_text(output_text):
        logger.info("[LLM] 输出为工具调用文本，忽略")
        return None

    elapsed = time.perf_counter() - start_time
    logger.info(
        "[LLM] 成功 | len=%s | summary=%s | elapsed=%.2fs",
        len(output_text),
        _summary(output_text, cfg.log_result_summary_len),
        elapsed,
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
            params.reference_keywords,
            context=context,
        )
    except Exception as e:
        logger.error("[LLM] 调用失败 | input=%s | error=%s", _summary(category_text), e, exc_info=True)
        return None
