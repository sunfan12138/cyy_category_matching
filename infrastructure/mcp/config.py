"""MCP 客户端配置：从 core.config 加载并对外提供 ServerConfig、load_config。"""

from __future__ import annotations

from core.config import ServerConfig, load_mcp_config


def load_config(config_path):
    """从 JSON 文件加载 MCP 服务器列表；委托 core.config.load_mcp_config。"""
    return load_mcp_config(config_path)


__all__ = ["ServerConfig", "load_config"]
