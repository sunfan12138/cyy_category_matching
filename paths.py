"""
路径与输入规范化：基准目录、model/excel/output、MCP 配置、用户路径解析。

- 未打包：以 main.py 所在目录为基准；打包后以 exe 所在目录为基准。
- 环境变量：CATEGORY_MATCHING_BASE_DIR / MODEL_DIR / EXCEL_DIR / OUTPUT_DIR / MCP_CONFIG
"""

import os
import re
import sys
from pathlib import Path


def get_base_dir() -> Path:
    """基准目录：打包后为 exe 所在目录，否则为 main.py 所在目录。"""
    if os.environ.get("CATEGORY_MATCHING_BASE_DIR"):
        return Path(os.environ["CATEGORY_MATCHING_BASE_DIR"]).resolve()
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
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


def get_mcp_config_path() -> Path | None:
    """MCP 客户端配置文件路径；未设置或文件不存在时返回 None。"""
    if os.environ.get("CATEGORY_MATCHING_MCP_CONFIG"):
        p = Path(os.environ["CATEGORY_MATCHING_MCP_CONFIG"]).resolve()
        return p if p.exists() else None
    p = get_base_dir() / "mcp_client_config.json"
    return p if p.exists() else None


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
