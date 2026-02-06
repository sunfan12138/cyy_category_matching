"""MCP 客户端配置：ServerConfig 与从 JSON 加载（Pydantic 解析）。"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from models.schemas import McpConfigSchema, McpServerSchema

# 向后兼容：对外仍称 ServerConfig
ServerConfig = McpServerSchema


def load_mcp_config(config_path: Path | None) -> list[ServerConfig]:
    """
    从 JSON 文件加载 MCP 服务器列表。
    若 config_path 为 None 或文件不存在，返回空列表。
    使用 McpConfigSchema.model_validate 解析，无效条目已由 Schema 过滤或使用默认值。
    """
    if not config_path or not config_path.exists():
        return []
    try:
        file_content = config_path.read_text(encoding="utf-8")
        parsed_json = json.loads(file_content)
        mcp_config_schema = McpConfigSchema.model_validate(parsed_json)
    except (ValidationError, json.JSONDecodeError):
        return []
    return [server for server in mcp_config_schema.servers if server.name]
