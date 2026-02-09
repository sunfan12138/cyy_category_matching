"""
路径与配置路径入口：从 core.config 统一导出，供 main、app、embedding 等使用。

实现位于 core.config.paths；需加载后的配置路径通过 core.config.inject(ConfigDirPath/AppConfigFilePath) 获取。
"""

from __future__ import annotations

from pathlib import Path

from core.config import (
    inject,
    AppConfigFilePath,
    ConfigDirPath,
)
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


def get_config_dir() -> Path:
    """配置文件目录（需已调用 load_app_config）。"""
    return inject(ConfigDirPath)


def get_llm_config_path() -> Path:
    """大模型配置文件路径 app_config.yaml（需已调用 load_app_config）。"""
    return inject(AppConfigFilePath)


def get_mcp_config_path() -> Path:
    """MCP 配置文件路径 app_config.yaml（需已调用 load_app_config）。"""
    return inject(AppConfigFilePath)


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
