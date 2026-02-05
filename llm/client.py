"""
大模型客户端：根据品类文本生成品类描述，支持 MCP 工具（搜索等）。
配置从 core.config 获取（get_llm_config、get_mcp_config）。
日志：每轮调用、工具调用、耗时与异常均记录；一次完整调用流程写为一条 JSON 日志（llm.http）。
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


def _http_logger() -> logging.Logger:
    """HTTP/流程 专用 logger，写入 category_matching_http_YYYYMMDD.log。"""
    return logging.getLogger(HTTP_LOG_NAME)


# 系统提示在 snapshot 中超过此长度则只保留占位，避免刷屏
_SYSTEM_SNAPSHOT_MAX = 200
# 单条 tool 返回在 snapshot 中超过此长度则截断
_TOOL_OUTPUT_SNAPSHOT_MAX = 800
# 清洗 assistant content 时，仅在前缀区段内查找 { 或 <，超过则不再截断（避免误删正常正文）
_ASSISTANT_CONTENT_STRIP_LOOKAHEAD = 512


def _sanitize_assistant_content_with_tool_call(content: str | None) -> str:
    """当 assistant 同时返回 tool_calls 时，content 里常含「多余字符 + JSON/tool_call」。
    部分模型会先输出多余字符（如单个汉字）再输出工具调用，此处去掉该前缀，便于日志与展示。
    """
    s = (content or "").strip()
    if not s:
        return s
    # 若以 { 或 < 开头，视为已是合法工具调用/JSON 前缀，不处理
    if s[0] in ("{", "<"):
        return s
    # 在整段前缀（最多 _ASSISTANT_CONTENT_STRIP_LOOKAHEAD 字符）内找第一个 { 或 <，从该处截取
    look = s[:_ASSISTANT_CONTENT_STRIP_LOOKAHEAD]
    for i, c in enumerate(look):
        if c in ("{", "<"):
            return s[i:].strip()
    return s


def _content_looks_like_tool_call(content: str | None) -> bool:
    """判断 content 是否实为工具调用文本（部分模型只把 tool_call 放在 content 里且不返回结构化 tool_calls）。
    若为 True，不应把该 content 当作最终品类描述返回。
    """
    s = (content or "").strip()
    if not s:
        return False
    # 含 </tool_call> 标记则视为工具调用片段
    if "</tool_call>" in s:
        return True
    # 清洗前缀后再看：可能是单一 JSON 对象 {"name":"...", "arguments":{...}}
    cleaned = _sanitize_assistant_content_with_tool_call(s)
    if not cleaned:
        return False
    if cleaned.startswith("{"):
        try:
            # 取第一行或第一个完整 JSON 对象，避免后面跟自然语言时误判
            end = cleaned.find("\n")
            if end == -1:
                end = len(cleaned)
            first = cleaned[:end].strip()
            if first.endswith("</tool_call>"):
                first = first.replace("</tool_call>", "").strip()
            obj = json.loads(first)
            if isinstance(obj, dict) and "name" in obj and "arguments" in obj:
                return True
        except Exception:
            pass
    return False


def _messages_to_snapshot(messages: list[dict[str, Any]], max_chars: int = 12000) -> str:
    """将 messages 序列化为可读的 prompt_snapshot，系统提示与过长 tool 输出做省略。"""
    parts: list[str] = []
    for m in messages:
        role = m.get("role", "")
        content = (m.get("content") or "").strip()
        if role == "system":
            if len(content) <= _SYSTEM_SNAPSHOT_MAX:
                parts.append(f"System: {content}")
            else:
                parts.append(f"System: [系统提示已省略，共 {len(content)} 字]")
        elif role == "user":
            parts.append(f"User: {content}")
        elif role == "assistant":
            if m.get("tool_calls"):
                # 展示时再次清洗，避免多余前缀（如单个汉字）出现在 snapshot/日志
                content = _sanitize_assistant_content_with_tool_call(content or "")
                tc_sum = ", ".join(
                    str(tc.get("function", {}).get("name", "")) for tc in (m.get("tool_calls") or [])
                )
                parts.append(f"Assistant: [tool_calls: {tc_sum}] {content or ''}")
            else:
                parts.append(f"Assistant: {content}")
        elif role == "tool":
            tid = m.get("tool_call_id", "")[:8] if m.get("tool_call_id") else ""
            if len(content) <= _TOOL_OUTPUT_SNAPSHOT_MAX:
                parts.append(f"Tool({tid}): {content}")
            else:
                parts.append(f"Tool({tid}): {content[:_TOOL_OUTPUT_SNAPSHOT_MAX]}...(已省略 {len(content) - _TOOL_OUTPUT_SNAPSHOT_MAX} 字)")
        else:
            parts.append(f"{role}: {content}")
    s = "\n".join(parts)
    if len(s) > max_chars:
        s = s[:max_chars] + "\n...(全文已截断)"
    return s


def _emit_flow_log(flow: dict[str, Any]) -> None:
    """将一次调用的流程日志写为单行 JSON（格式：trace_id / config / full_history / metrics）。"""
    try:
        usage = flow.get("total_usage") or {}
        if usage.get("total_tokens", 0) == 0:
            usage["total_tokens"] = usage.get("prompt_tokens", 0) + usage.get("completion_tokens", 0)
        payload: dict[str, Any] = {
            "trace_id": flow["trace_id"],
            "timestamp": flow["timestamp"],
            "config": flow["config"],
            "full_history": flow["full_history"],
            "metrics": {
                "total_latency": flow["total_latency_ms"],
                "total_tokens": usage.get("total_tokens", 0),
            },
        }
        if flow.get("status") != "success":
            payload["status"] = flow["status"]
            if flow.get("error") is not None:
                payload["error"] = flow["error"]
        _http_logger().info("%s", json.dumps(payload, ensure_ascii=False))
    except Exception:
        pass


def _llm_client_config():
    """LLM 客户端配置（来自 app_config.yaml llm_client 节）；需已调用 load_app_config()。"""
    from core.config import get_app_config
    return get_app_config().llm_client


def _summary(text: str, max_len: int | None = None) -> str:
    """对长文本做摘要，用于日志，避免输出全文。"""
    if max_len is None:
        max_len = _llm_client_config().log_input_summary_len
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
    input_summary = _summary(category_text)
    base_url_masked = _mask_base_url(base_url)

    max_tokens = _llm_client_config().max_tokens
    logger.info(
        "[LLM] 开始调用 | context={%s} | input_summary=%s | model=%s | base_url=%s | max_tokens=%s",
        ctx_str or "无",
        input_summary,
        model,
        base_url_masked,
        max_tokens,
    )
    start_time = time.perf_counter()
    trace_id = f"flow_{uuid.uuid4().hex[:8]}_{datetime.now(timezone.utc).strftime('%Y')}_{uuid.uuid4().hex[:4]}"
    flow: dict[str, Any] = {
        "trace_id": trace_id,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "config": {
            "model": model,
            "temperature": 0,
            "max_tokens": max_tokens,
        },
        "full_history": [],
        "total_latency_ms": 0,
        "status": "running",
        "final_answer": None,
        "total_usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }
    step_index = 0
    flow["full_history"].append({
        "step": 1,
        "role": "user_input",
        "content": category_text.strip(),
    })
    step_index = 1

    def _ensure_step1_system_summary(msgs: list[dict[str, Any]]) -> None:
        """为 step 1 补上系统提示摘要（不嵌全文），仅补一次。"""
        if not flow["full_history"] or flow["full_history"][0].get("system_prompt_summary") is not None:
            return
        system_content = (msgs[0].get("content") or "") if msgs and msgs[0].get("role") == "system" else ""
        flow["full_history"][0]["system_prompt_summary"] = f"[系统提示已省略，共 {len(system_content)} 字]"

    def _add_usage(usage_obj: Any) -> None:
        if not usage_obj:
            return
        p = getattr(usage_obj, "prompt_tokens", None)
        c = getattr(usage_obj, "completion_tokens", None)
        t = getattr(usage_obj, "total_tokens", None)
        if p is not None:
            flow["total_usage"]["prompt_tokens"] = flow["total_usage"].get("prompt_tokens", 0) + int(p)
        if c is not None:
            flow["total_usage"]["completion_tokens"] = flow["total_usage"].get("completion_tokens", 0) + int(c)
        if t is not None:
            flow["total_usage"]["total_tokens"] = flow["total_usage"].get("total_tokens", 0) + int(t)

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

    async with AsyncOpenAI(api_key=api_key, base_url=base_url.rstrip("/")) as client:
        max_rounds = 8
        for round_no in range(1, max_rounds + 1):
            try:
                response = await client.chat.completions.create(
                    model=model,
                    messages=messages_with_system,
                    tools=tools if tools else None,
                    max_tokens=_llm_client_config().max_tokens,
                )
            except Exception as e:
                elapsed_ms = int((time.perf_counter() - start_time) * 1000)
                flow["total_latency_ms"] = elapsed_ms
                flow["status"] = "error"
                flow["error"] = str(e)
                _emit_flow_log(flow)
                logger.error(
                    "[LLM] 模型请求异常 | round=%s | trace_id=%s | context={%s} | input_summary=%s | elapsed=%.2fs | error=%s",
                    round_no,
                    trace_id,
                    ctx_str or "无",
                    input_summary,
                    elapsed_ms / 1000.0,
                    e,
                    exc_info=True,
                )
                return None

            _add_usage(getattr(response, "usage", None))

            choice = response.choices[0] if response.choices else None
            if not choice:
                logger.warning("[LLM] 无有效 choice | round=%s | trace_id=%s | context={%s}", round_no, trace_id, ctx_str or "无")
                elapsed_ms = int((time.perf_counter() - start_time) * 1000)
                flow["total_latency_ms"] = elapsed_ms
                flow["status"] = "no_choice"
                _ensure_step1_system_summary(messages_with_system)
                _emit_flow_log(flow)
                return None
            msg = choice.message
            if not msg:
                logger.warning("[LLM] 无 message | round=%s | trace_id=%s | context={%s}", round_no, trace_id, ctx_str or "无")
                elapsed_ms = int((time.perf_counter() - start_time) * 1000)
                flow["total_latency_ms"] = elapsed_ms
                flow["status"] = "no_message"
                _ensure_step1_system_summary(messages_with_system)
                _emit_flow_log(flow)
                return None

            usage_for_step = None
            if getattr(response, "usage", None):
                u = response.usage
                usage_for_step = {
                    "prompt_tokens": getattr(u, "prompt_tokens", 0) or 0,
                    "completion_tokens": getattr(u, "completion_tokens", 0) or 0,
                }

            # 仅当「无 tool_calls」时把 content 当作最终答案；若同时有 tool_calls，多为模型把工具调用写在 content 里，应走工具分支
            has_tool_calls = bool(getattr(msg, "tool_calls", None))
            if msg.content and (msg.content or "").strip() and not has_tool_calls:
                raw = (msg.content or "").strip()
                result = _sanitize_assistant_content_with_tool_call(raw)
                # 部分模型只把工具调用写在 content 里且不返回结构化 tool_calls，此时不应把该 content 当最终答案
                if _content_looks_like_tool_call(result):
                    logger.info(
                        "[LLM] content 实为工具调用文本，按无有效结果处理 | round=%s | trace_id=%s | context={%s}",
                        round_no,
                        trace_id,
                        ctx_str or "无",
                    )
                    # 不 return，落到下方 no_content 分支
                else:
                    elapsed_ms = int((time.perf_counter() - start_time) * 1000)
                    step_index += 1
                    _ensure_step1_system_summary(messages_with_system)
                    flow["full_history"].append({
                        "step": step_index,
                        "role": "final_output",
                        "prompt_snapshot": _messages_to_snapshot(messages_with_system),
                        "content": result,
                    })
                    flow["total_latency_ms"] = elapsed_ms
                    flow["status"] = "success"
                    flow["final_answer"] = result
                    _emit_flow_log(flow)
                    logger.info(
                        "[LLM] 返回成功 | round=%s | trace_id=%s | context={%s} | result_len=%s | result_summary=%s | elapsed=%.2fs",
                        round_no,
                        trace_id,
                        ctx_str or "无",
                        len(result),
                        _summary(result, _llm_client_config().log_result_summary_len),
                        elapsed_ms / 1000.0,
                    )
                    return result

            if not tools or not has_tool_calls:
                logger.info("[LLM] 无内容且无 tool_calls，结束 | round=%s | trace_id=%s | context={%s}", round_no, trace_id, ctx_str or "无")
                elapsed_ms = int((time.perf_counter() - start_time) * 1000)
                flow["total_latency_ms"] = elapsed_ms
                flow["status"] = "no_content"
                _ensure_step1_system_summary(messages_with_system)
                _emit_flow_log(flow)
                return None

            tool_calls = list(msg.tool_calls or [])
            step_index += 1
            calls_for_log: list[dict[str, Any]] = []
            for tc in tool_calls:
                fn = getattr(tc.function, "name", None) or tc.function.get("name") or ""
                args_raw = getattr(tc.function, "arguments", None) or tc.function.get("arguments") or "{}"
                try:
                    args_dict = json.loads(args_raw) if args_raw else {}
                except Exception:
                    args_dict = {}
                calls_for_log.append({"function": fn, "args": args_dict})
            _ensure_step1_system_summary(messages_with_system)
            flow["full_history"].append({
                "step": step_index,
                "role": "assistant_tool_call",
                "prompt_snapshot": _messages_to_snapshot(messages_with_system),
                "calls": calls_for_log,
            })
            called_names = [c["function"] for c in calls_for_log]
            logger.info(
                "[LLM] 本轮需调用工具 | round=%s | trace_id=%s | context={%s} | tool_calls=%s",
                round_no,
                trace_id,
                ctx_str or "无",
                called_names,
            )

            # 清洗 content：部分模型在 tool_calls 时会在 content 里带多余前缀（如单个汉字），去掉以便日志可读
            assistant_content = _sanitize_assistant_content_with_tool_call(msg.content)
            messages_with_system.append({
                "role": "assistant",
                "content": assistant_content,
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
                t0 = time.perf_counter()
                content = ""
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
                else:
                    content = "{}"
                step_index += 1
                flow["full_history"].append({
                    "step": step_index,
                    "role": "tool_response",
                    "tool_name": name,
                    "raw_output": content,
                })
                messages_with_system.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": content,
                })

        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        flow["total_latency_ms"] = elapsed_ms
        flow["status"] = "max_rounds_exceeded"
        _ensure_step1_system_summary(messages_with_system)
        _emit_flow_log(flow)
        logger.warning(
            "[LLM] 达到最大轮数未得到文本结果 | trace_id=%s | context={%s} | input_summary=%s | rounds=%s | elapsed=%.2fs",
            trace_id,
            ctx_str or "无",
            input_summary,
            max_rounds,
            elapsed_ms / 1000.0,
        )
        return None


def _get_llm_call_params(rules: list[Any] | None) -> Any | None:
    """获取 LLM+MCP 调用参数；未配置时打 warning 并返回 None。返回 LlmCallParams。"""
    from models.schemas import LlmCallParams

    from core.config import get_llm_config, get_mcp_config

    cfg = get_llm_config()
    if not cfg.api_key:
        logger.warning(
            "未配置大模型 API Key，跳过大模型调用（请配置 config/app_config.yaml 或环境变量 OPENAI_API_KEY）"
        )
        return None
    mcp_config = get_mcp_config()
    if not mcp_config:
        logger.warning(
            "未找到 MCP 配置（app_config.yaml 的 mcp.servers），大模型调用需要该配置；请在 config/app_config.yaml 中配置 mcp.servers"
        )
        return None
    from . import prompt as _prompt
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
    """
    根据品类文本调用大模型（带 MCP 工具）生成品类描述；未配置或失败返回 None。

    context 可选，用于日志追踪，如 batch_id、item_id、similarity_threshold 等。
    """
    params = _get_llm_call_params(rules)
    if params is None:
        return None
    try:
        return asyncio.run(
            _call_llm_with_mcp_async(
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
        logger.error(
            "[LLM] 调用失败 | input_summary=%s | context=%s | error=%s",
            _summary(category_text),
            context,
            e,
            exc_info=True,
        )
        return None