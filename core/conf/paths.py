"""配置路径解析：config 目录、llm_config.json、mcp_client_config.json。"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _exe_dir() -> Path:
    """打包为 exe 时，exe 所在目录。"""
    return Path(sys.executable).resolve().parent


def get_base_dir() -> Path:
    """基准目录：打包后为 exe 所在目录，否则为项目根（core 的父目录）。"""
    if os.environ.get("CATEGORY_MATCHING_BASE_DIR"):
        return Path(os.environ["CATEGORY_MATCHING_BASE_DIR"]).resolve()
    if getattr(sys, "frozen", False):
        return _exe_dir()
    return Path(__file__).resolve().parent.parent.parent


def _config_dir_candidates() -> list[Path]:
    """配置文件所在目录的候选；未打包=基准目录/config，打包后=当前工作目录/config。"""
    if getattr(sys, "frozen", False):
        return [Path.cwd() / "config"]
    return [get_base_dir() / "config"]


def get_config_dir_raw() -> Path:
    """配置文件目录（不触发加载）。"""
    candidates = _config_dir_candidates()
    return candidates[0] if candidates else get_base_dir() / "config"


def get_llm_config_path_raw() -> Path | None:
    """大模型配置文件路径（不触发加载）。"""
    for config_dir in _config_dir_candidates():
        p = config_dir / "llm_config.json"
        if p.exists():
            return p
    return None


def get_mcp_config_path_raw() -> Path | None:
    """MCP 客户端配置文件路径（不触发加载）；仅从 config 目录加载 mcp_client_config.json。"""
    for config_dir in _config_dir_candidates():
        p = config_dir / "mcp_client_config.json"
        if p.exists():
            return p
    return None
