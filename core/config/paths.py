"""
路径解析：基准目录、配置目录、模型/Excel/输出/日志目录及用户输入路径规范化。

- 配置相关：config 目录、app_config.yaml
- 应用目录：model、excel、output、logs
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path


def _exe_dir() -> Path:
    """打包为 exe 时，exe 所在目录。"""
    return Path(sys.executable).resolve().parent


def get_base_dir() -> Path:
    """基准目录：打包后为 exe 所在目录，否则为项目根（core 的父目录）。"""
    if getattr(sys, "frozen", False):
        return _exe_dir()
    return Path(__file__).resolve().parent.parent.parent


def _config_dir_candidates() -> list[Path]:
    """配置文件所在目录的候选；未打包=基准目录/config，打包后=exe 所在目录/config。"""
    return [get_base_dir() / "config"]


def get_config_dir_raw() -> Path:
    """配置文件目录（不触发加载）。"""
    candidates = _config_dir_candidates()
    return candidates[0] if candidates else get_base_dir() / "config"


def get_llm_config_path_raw() -> Path:
    """大模型配置所在文件路径（app_config.yaml，不触发加载）。"""
    return get_config_dir_raw() / "app_config.yaml"


def get_mcp_config_path_raw() -> Path:
    """MCP 客户端配置所在文件路径（app_config.yaml，不触发加载）。"""
    return get_config_dir_raw() / "app_config.yaml"


def get_model_dir() -> Path:
    """BGE 模型目录。"""
    return get_base_dir() / "model"


def get_excel_dir() -> Path:
    """规则与已校验品牌 Excel 目录。"""
    return get_base_dir() / "excel"


def get_output_dir() -> Path:
    """匹配结果输出目录。"""
    return get_base_dir() / "output"


def get_log_dir() -> Path:
    """日志文件目录。"""
    return get_base_dir() / "logs"


def normalize_input_path(raw: str) -> Path:
    """
    规范化用户输入的文件路径：去首尾引号/空白；WSL 下将 Windows 盘符路径转为可访问路径。
    例：'c:/Users/cyy/Desktop/文件.txt' -> /mnt/c/Users/cyy/Desktop/文件.txt
    """
    s = raw.strip().strip("\"'\"''")
    if not s:
        return Path("")
    if os.name == "posix" and len(s) >= 2:
        m = re.match(r"^([a-zA-Z])\s*[:\\](.*)$", s)
        if m:
            drive = m.group(1).lower()
            rest = (m.group(2) or "").replace("\\", "/").strip("/")
            s = f"/mnt/{drive}/{rest}" if rest else f"/mnt/{drive}"
    return Path(s)
