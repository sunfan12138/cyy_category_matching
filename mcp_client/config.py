"""MCP 客户端配置：从 core.conf 统一 re-export。"""

from __future__ import annotations

from core.conf import ServerConfig, load_mcp_config


def load_config(config_path):
    """从 JSON 文件加载 MCP 服务器列表；委托 core.conf.load_mcp_config。"""
    return load_mcp_config(config_path)


__all__ = ["ServerConfig", "load_config"]
