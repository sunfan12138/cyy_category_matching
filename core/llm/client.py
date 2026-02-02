"""大模型客户端：根据品类文本生成描述，支持 MCP 工具调用。"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from .llm_config import load_llm_config
from .prompt import PROMPT_BASE, PROMPT_TOOLS, PROMPT_WITH_KEYWORDS, build_keyword_hint

if TYPE_CHECKING:
    from ..models import CategoryRule

logger = logging.getLogger(__name__)

# MCP 工具名前缀，用于在 OpenAI 工具调用中区分服务器与工具：mcp__{server}__{tool_name}
MCP_TOOL_PREFIX = "mcp__"


def _mcp_tool_to_openai(server_name: str, tool: Any) -> dict[str, Any]:
    """将 MCP Tool 转为 OpenAI API 的 tools 项。工具名为 mcp__{server}__{tool.name} 便于回路由。"""
    openai_name = f"{MCP_TOOL_PREFIX}{server_name}__{getattr(tool, 'name', '')}"
    desc = getattr(tool, "description", None) or ""
    schema = getattr(tool, "inputSchema", None) or {"type": "object", "properties": {}}
    return {
        "type": "function",
        "function": {
            "name": openai_name,
            "description": desc,
            "parameters": schema,
        },
    }


def _call_tool_result_to_text(result: Any) -> str:
    """从 MCP CallToolResult 中提取文本内容。"""
    if result is None:
        return ""
    content = getattr(result, "content", None) or []
    parts: list[str] = []
    for block in content if isinstance(content, list) else []:
        if isinstance(block, dict):
            if block.get("type") == "text":
                parts.append(block.get("text") or "")
        elif getattr(block, "type", None) == "text":
            parts.append(getattr(block, "text", "") or "")
    return "\n".join(parts).strip() or str(result)


def get_category_description_with_search(
    category_text: str,
    rules: list[CategoryRule] | None = None,
) -> str | None:
    """
    调用大模型生成品类描述，可使用 MCP 工具（如搜索）；无工具或调用失败时返回 None。
    """
    category_text = (category_text or "").strip()
    if not category_text:
        return None

    api_key, base_url, model = load_llm_config()
    if not api_key:
        return None

    try:
        from mcp_client import load_config, run_async
        from paths import get_mcp_config_path
    except ImportError:
        return None

    config_path = get_mcp_config_path()
    if not config_path:
        return None
    config_list = load_config(config_path)
    if not config_list:
        return None

    _httpx_log = logging.getLogger("httpx")
    _old_httpx_level = _httpx_log.level
    _httpx_log.setLevel(logging.WARNING)

    logger.info("========== 开始调用大模型 [输入=%s] ==========", category_text[:50])

    session_events: list[str] = []

    def _flush_log() -> None:
        root = logging.getLogger()
        for h in root.handlers:
            h.flush()

    async def _run_with_tools() -> str | None:
        from mcp_client import MCPClientManager
        from openai import OpenAI

        async with MCPClientManager(config_list) as manager:
            tools_raw = await manager.list_tools()
            if not tools_raw:
                session_events.append("未发现可用工具")
                logger.info("  [大模型] 未发现可用工具，流程结束")
                return None
            openai_tools: list[dict[str, Any]] = []
            name_to_server_tool: dict[str, tuple[str, str]] = {}
            tool_names_readable: list[str] = []
            for server_name, tool in tools_raw:
                openai_tools.append(_mcp_tool_to_openai(server_name, tool))
                tname = getattr(tool, "name", "")
                openai_name = f"{MCP_TOOL_PREFIX}{server_name}__{tname}"
                name_to_server_tool[openai_name] = (server_name, tname)
                tool_names_readable.append(f"{server_name}/{tname}")
            logger.info("  [大模型] 可用工具: %s", ", ".join(tool_names_readable))

            keyword_hint = build_keyword_hint(rules) if rules else ""
            if keyword_hint:
                sys_prompt = PROMPT_BASE + PROMPT_WITH_KEYWORDS.format(reference_keywords=keyword_hint) + PROMPT_TOOLS
            else:
                sys_prompt = PROMPT_BASE + PROMPT_TOOLS
            user_content = f"品类文本：{category_text}\n\n描述："

            logger.info("  [大模型] 系统提示词已加载，共 %d 字", len(sys_prompt))
            _flush_log()

            client = OpenAI(api_key=api_key, base_url=base_url)
            messages: list[dict[str, Any]] = [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_content},
            ]
            max_rounds = 5
            for round_no in range(max_rounds):
                # 记录本轮请求：第1轮为用户输入，后续轮为含工具返回
                if round_no == 0:
                    logger.info("  [第 %d 轮] 请求 | 用户: 品类文本=%s", round_no + 1, category_text[:80])
                else:
                    logger.info("  [第 %d 轮] 请求 | （含上轮工具返回）", round_no + 1)
                _flush_log()

                # 因可能先调用搜索再写描述，且描述尽量多写以提高规则匹配率，预留较多 token
                call_params = {
                    "model": model,
                    "messages": messages,
                    "tools": openai_tools,
                    "tool_choice": "auto",
                    "max_tokens": 768,
                    "temperature": 0.3,
                }
                logger.info("  [大模型] 调用参数: %s", json.dumps(call_params, ensure_ascii=False, indent=2))
                _flush_log()

                resp = client.chat.completions.create(
                    model=call_params["model"],
                    messages=call_params["messages"],
                    tools=call_params["tools"],
                    tool_choice=call_params["tool_choice"],
                    max_tokens=call_params["max_tokens"],
                    temperature=call_params["temperature"],
                )
                choice = (resp.choices or [None])[0] if resp.choices else None
                if not choice or not choice.message:
                    return None
                msg = choice.message
                content = (getattr(msg, "content", None) or "").strip()
                tool_calls = getattr(msg, "tool_calls", None) or []

                if tool_calls:
                    session_events.append(f"第{round_no + 1}轮 调用{len(tool_calls)}个工具")
                    logger.info("  [第 %d 轮] 响应 | 助手请求调用 %d 个工具", round_no + 1, len(tool_calls))
                    _flush_log()
                    messages.append(
                        {
                            "role": "assistant",
                            "content": content or None,
                            "tool_calls": [
                                {
                                    "id": getattr(tc, "id", ""),
                                    "type": "function",
                                    "function": {
                                        "name": getattr(tc.function, "name", ""),
                                        "arguments": getattr(tc.function, "arguments", "{}"),
                                    },
                                }
                                for tc in tool_calls
                            ],
                        }
                    )
                    for idx, tc in enumerate(tool_calls, 1):
                        fn = getattr(tc, "function", None)
                        if not fn:
                            continue
                        tc_id = getattr(tc, "id", "")
                        fname = getattr(fn, "name", "")
                        fargs_str = getattr(fn, "arguments", "{}") or "{}"
                        try:
                            fargs = json.loads(fargs_str)
                        except Exception:
                            fargs = {}
                        server_tool = fname.replace(MCP_TOOL_PREFIX, "").replace("__", "/") if fname.startswith(MCP_TOOL_PREFIX) else fname
                        args_preview = ", ".join(f"{k}={str(v)[:40]}" for k, v in (fargs or {}).items())
                        session_events.append(f"  调用 {server_tool}({args_preview or '无'})")
                        logger.info("      ▶ 工具调用: %s | 参数: %s", server_tool, args_preview or "(无)")
                        _flush_log()
                        if fname not in name_to_server_tool:
                            messages.append({"role": "tool", "tool_call_id": tc_id, "content": "未知工具"})
                            session_events.append("  返回: 未知工具")
                            logger.warning("      ◀ 工具返回: 未知工具")
                            continue
                        server_name, tool_name = name_to_server_tool[fname]
                        try:
                            result = await manager.call_tool(server_name, tool_name, fargs)
                            text = _call_tool_result_to_text(result)
                            messages.append({"role": "tool", "tool_call_id": tc_id, "content": text or "(无文本结果)"})
                            session_events.append(f"  返回 {len(text)}字")
                            preview = (text[:200] + "…") if len(text) > 200 else (text or "(空)")
                            logger.info("      ◀ 工具返回: %d 字 | 内容: %s", len(text), preview)
                            _flush_log()
                        except Exception as e:
                            messages.append({"role": "tool", "tool_call_id": tc_id, "content": f"调用失败: {e}"})
                            session_events.append(f"  返回: 失败 {e}")
                            logger.warning("      ◀ 工具返回: 调用失败 %s", e)
                    continue
                if content:
                    session_events.append(f"直接返回描述 {len(content)}字")
                    logger.info("  [第 %d 轮] 响应 | 助手: 共 %d 字（未调用工具）", round_no + 1, len(content))
                    logger.info("  [大模型] 对话内容: %s", content[:300] + "…" if len(content) > 300 else content)
                    return content
                session_events.append("模型未返回描述")
                logger.info("  [第 %d 轮] 响应 | 助手未返回描述", round_no + 1)
                return None
            session_events.append("已达最大轮数未得到描述")
            logger.info("  [大模型] 已达最大轮数，未得到描述")
            return None

    try:
        out = run_async(_run_with_tools())
        _httpx_log.setLevel(_old_httpx_level)
        summary = " | ".join(session_events) if session_events else "(无事件)"
        logger.info("  [大模型] 会话摘要: %s", summary)
        logger.info("========== 大模型调用结束 [输入=%s] ==========", category_text[:50])
        _flush_log()
        return out
    except Exception as e:
        _httpx_log.setLevel(_old_httpx_level)
        logger.warning("  [大模型] 流程异常: %s", e)
        if session_events:
            logger.info("  [大模型] 会话摘要: %s | 异常结束", " | ".join(session_events))
        else:
            logger.info("  [大模型] 会话摘要: 异常结束（未产生工具调用记录）")
        logger.info("========== 大模型调用结束 [输入=%s] ==========", category_text[:50])
        _flush_log()
        return None
