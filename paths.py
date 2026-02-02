"""
路径与输入规范化：基准目录、model/excel/output、用户路径解析。
配置相关（config 目录、llm_config.json、mcp_client_config.json）已统一到 core.conf 模块。
"""

import os
import re
import sys
from pathlib import Path


def _exe_dir() -> Path:
    """打包为 exe 时，exe 所在目录（与 sys.executable 同目录）。"""
    return Path(sys.executable).resolve().parent


def get_base_dir() -> Path:
    """基准目录：打包后为 exe 所在目录，否则为 main.py 所在目录。"""
    if os.environ.get("CATEGORY_MATCHING_BASE_DIR"):
        return Path(os.environ["CATEGORY_MATCHING_BASE_DIR"]).resolve()
    if getattr(sys, "frozen", False):
        return _exe_dir()
    return Path(__file__).resolve().parent


def get_model_dir() -> Path:
    """BGE 模型目录，可自行替换或放置模型文件。"""
    if os.environ.get("CATEGORY_MATCHING_MODEL_DIR"):
        return Path(os.environ["CATEGORY_MATCHING_MODEL_DIR"]).resolve()
    return get_base_dir() / "model"


def get_excel_dir() -> Path:
    """规则与已校验品牌 Excel 目录，可自行替换或添加文件。"""
    if os.environ.get("CATEGORY_MATCHING_EXCEL_DIR"):
        return Path(os.environ["CATEGORY_MATCHING_EXCEL_DIR"]).resolve()
    return get_base_dir() / "excel"


def get_output_dir() -> Path:
    """匹配结果输出目录，可自行修改为期望的写入路径。"""
    if os.environ.get("CATEGORY_MATCHING_OUTPUT_DIR"):
        return Path(os.environ["CATEGORY_MATCHING_OUTPUT_DIR"]).resolve()
    return get_base_dir() / "output"


def get_log_dir() -> Path:
    """日志文件所在目录（用于记录模型调用等）。"""
    if os.environ.get("CATEGORY_MATCHING_LOG_DIR"):
        return Path(os.environ["CATEGORY_MATCHING_LOG_DIR"]).resolve()
    return get_base_dir() / "logs"


def get_config_dir() -> Path:
    """配置文件目录（config）；委托 core.conf。"""
    from core.conf import get_config_dir as _get
    return _get()


def get_llm_config_path() -> Path | None:
    """大模型配置文件路径；委托 core.conf。"""
    from core.conf import get_llm_config_path as _get
    return _get()


def get_mcp_config_path() -> Path | None:
    """MCP 客户端配置文件路径；委托 core.conf。"""
    from core.conf import get_mcp_config_path as _get
    return _get()


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
