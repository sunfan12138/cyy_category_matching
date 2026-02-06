"""
MCP 客户端管理器：基于 mcp 库直接连接多个配置的服务器，聚合 list_tools / call_tool。

注意：与 LLM 联动的 MCP 调用由 Pydantic AI Agent 完成（见 llm.client），
使用 MCPServerStdio / MCPServerStreamableHTTP / MCPServerSSE 作为 toolsets。
本模块适用于不经过 Agent 的直接 MCP 会话（如列出工具、单独调用工具）。
参见 https://ai.pydantic.org.cn/mcp/client/
"""

from __future__ import annotations

import asyncio
from contextlib import AsyncExitStack
from typing import Any

from mcp import ClientSession
from mcp.client.sse import sse_client
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.client.streamable_http import streamable_http_client

from .config import ServerConfig


class MCPClientManager:
    """
    通过配置连接多个 MCP 服务器，提供聚合的 list_tools 与 call_tool。
    传输支持：stdio、streamable-http、sse（与 Pydantic AI 文档一致）。
    使用方式：async with MCPClientManager(config_list) as manager: ...
    """

    def __init__(self, config_list: list[ServerConfig]) -> None:
        self._config_list = config_list
        self._stack: AsyncExitStack | None = None
        self._sessions: dict[str, ClientSession] = {}

    async def __aenter__(self) -> MCPClientManager:
        self._stack = AsyncExitStack()
        try:
            for cfg in self._config_list:
                if cfg.transport == "stdio":
                    params = StdioServerParameters(
                        command=cfg.command,
                        args=cfg.args or [],
                        env=cfg.env,
                        cwd=cfg.cwd,
                    )
                    read, write = await self._stack.enter_async_context(
                        stdio_client(params)
                    )
                elif cfg.transport == "streamable-http":
                    read, write, _ = await self._stack.enter_async_context(
                        streamable_http_client(cfg.url)
                    )
                elif cfg.transport == "sse":
                    read, write = await self._stack.enter_async_context(
                        sse_client(cfg.url)
                    )
                else:
                    continue
                session = await self._stack.enter_async_context(ClientSession(read, write))
                await session.initialize()
                self._sessions[cfg.name] = session
        except Exception:
            await self._stack.aclose()
            raise
        return self

    async def __aexit__(self, *args: Any) -> None:
        if self._stack:
            await self._stack.aclose()
            self._stack = None
        self._sessions.clear()

    def server_names(self) -> list[str]:
        """已连接的服务器名称列表。"""
        return list(self._sessions.keys())

    async def list_tools(self, server_name: str | None = None) -> list[tuple[str, Any]]:
        """
        列出工具。若 server_name 为 None，则聚合所有服务器的工具。
        返回 [(server_name, tool), ...]，tool 为 MCP Tool 对象。
        """
        if server_name:
            names = [server_name] if server_name in self._sessions else []
        else:
            names = list(self._sessions.keys())
        out: list[tuple[str, Any]] = []
        for name in names:
            session = self._sessions.get(name)
            if not session:
                continue
            try:
                result = await session.list_tools()
                for t in getattr(result, "tools", []) or []:
                    out.append((name, t))
            except Exception:
                continue
        return out

    async def call_tool(
        self,
        server_name: str,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> Any:
        """
        调用指定服务器的工具。返回 CallToolResult（含 content / is_error 等）。
        """
        session = self._sessions.get(server_name)
        if not session:
            raise ValueError(f"未知服务器: {server_name}")
        return await session.call_tool(tool_name, arguments or {})


def run_async(coro: Any) -> Any:
    """在同步代码中运行异步 MCP 调用（每次新建事件循环）。"""
    return asyncio.run(coro)
