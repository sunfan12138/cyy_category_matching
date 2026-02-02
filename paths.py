"""
路径与配置路径入口：从 core.config 统一导出，供 main、app、embedding 等使用。

实现位于 core.config.paths；配置相关路径（get_config_dir 等）委托 core.config 加载后返回。
"""

from __future__ import annotations

from core.config.paths import (
    get_base_dir,
    get_config_dir_raw,
    get_excel_dir,
    get_llm_config_path_raw,
    get_log_dir,
    get_model_dir,
    get_mcp_config_path_raw,
    get_output_dir,
    normalize_input_path,
)
from core.config import (
    get_config_dir,
    get_llm_config_path,
    get_mcp_config_path,
)

__all__ = [
    "get_base_dir",
    "get_config_dir",
    "get_config_dir_raw",
    "get_excel_dir",
    "get_llm_config_path",
    "get_llm_config_path_raw",
    "get_log_dir",
    "get_model_dir",
    "get_mcp_config_path",
    "get_mcp_config_path_raw",
    "get_output_dir",
    "normalize_input_path",
]
