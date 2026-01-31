"""从 JSON 配置文件加载 MCP 服务器列表。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ServerConfig:
    """单个 MCP 服务器配置。"""

    name: str
    transport: str  # "stdio" | "streamable-http" | "sse"
    command: str = ""
    args: list[str] | None = None
    env: dict[str, str] | None = None
    cwd: str | None = None
    url: str = ""

    def __post_init__(self) -> None:
        if self.args is None:
            self.args = []


def load_config(config_path: Path | None = None) -> list[ServerConfig]:
    """
    从 JSON 文件加载 MCP 服务器配置。
    若 config_path 为 None，则返回空列表（调用方可通过 paths.get_mcp_config_path() 获取路径后再调本函数）。
    """
    if config_path is None or not config_path.exists():
        return []

    raw = config_path.read_text(encoding="utf-8")
    data = json.loads(raw)
    # 支持 "servers" 数组 或 "mcpServers" 对象（Cursor/Claude 风格）
    servers_raw = data.get("servers")
    if servers_raw is None and "mcpServers" in data:
        mcp_servers = data["mcpServers"] or {}
        servers_raw = [
            {"name": k, "transport": (v.get("type") or v.get("transport") or "sse"), **v}
            for k, v in mcp_servers.items()
            if isinstance(v, dict)
        ]
    servers = servers_raw or []
    result: list[ServerConfig] = []

    for s in servers:
        if not isinstance(s, dict):
            continue
        name = s.get("name") or ""
        transport = (s.get("transport") or s.get("type") or "stdio").strip().lower()
        if not name:
            continue
        if transport == "stdio":
            result.append(
                ServerConfig(
                    name=name,
                    transport="stdio",
                    command=str(s.get("command", "")),
                    args=list[str](s["args"]) if isinstance(s.get("args"), list) else [],
                    env=s.get("env") if isinstance(s.get("env"), dict) else None,
                    cwd=s.get("cwd"),
                )
            )
        elif transport in ("streamable-http", "streamable_http"):
            result.append(
                ServerConfig(
                    name=name,
                    transport="streamable-http",
                    url=str(s.get("url", "")),
                )
            )
        elif transport == "sse":
            result.append(
                ServerConfig(
                    name=name,
                    transport="sse",
                    url=str(s.get("url", "")),
                )
            )
    return result
