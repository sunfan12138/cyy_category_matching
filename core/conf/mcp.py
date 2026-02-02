"""MCP 客户端配置：ServerConfig 与从 JSON 加载。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ServerConfig:
    """单个 MCP 服务器配置。"""
    name: str
    transport: str  # stdio | streamable-http | sse
    url: str = ""
    command: str = ""
    args: list[str] | None = None
    env: dict[str, str] | None = None
    cwd: str | None = None


def load_mcp_config(config_path: Path | None) -> list[ServerConfig]:
    """
    从 JSON 文件加载 MCP 服务器列表。
    若 config_path 为 None 或文件不存在，返回空列表。
    """
    if not config_path or not config_path.exists():
        return []
    try:
        raw = config_path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except Exception:
        return []
    servers = data.get("servers") or []
    out: list[ServerConfig] = []
    for s in servers:
        if not isinstance(s, dict):
            continue
        name = (s.get("name") or "").strip()
        transport = (s.get("transport") or "stdio").strip().lower()
        if not name:
            continue
        out.append(
            ServerConfig(
                name=name,
                transport=transport,
                url=(s.get("url") or "").strip(),
                command=(s.get("command") or "").strip(),
                args=s.get("args") if isinstance(s.get("args"), list) else None,
                env=s.get("env") if isinstance(s.get("env"), dict) else None,
                cwd=s.get("cwd") if isinstance(s.get("cwd"), str) else None,
            )
        )
    return out
