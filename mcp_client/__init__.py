"""
MCP 客户端：通过配置文件连接外部 MCP 服务器并调用其工具。

配置：mcp_client_config.json（或环境变量 CATEGORY_MATCHING_MCP_CONFIG 指定路径）
格式示例：
  {
    "servers": [
      {
        "name": "example",
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-everything"]
      },
      {
        "name": "local_http",
        "transport": "streamable-http",
        "url": "http://localhost:8000/mcp"
      }
    ]
  }
"""

from .config import load_config
from .manager import MCPClientManager, run_async


def manager_from_project_config():
    """
    使用项目路径（paths.get_mcp_config_path）加载配置并返回 MCPClientManager。
    若无配置文件或路径未设置，返回 None。
    用法：config = load_config(get_mcp_config_path()); if config: async with MCPClientManager(config) as m: ...
    """
    from paths import get_mcp_config_path

    path = get_mcp_config_path()
    if not path:
        return None
    cfg = load_config(path)
    return MCPClientManager(cfg) if cfg else None


__all__ = ["load_config", "MCPClientManager", "run_async", "manager_from_project_config"]
