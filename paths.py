"""
model、excel、output 目录路径：支持脚本运行与打包后运行，支持环境变量覆盖。

- 未打包：以 main.py 所在目录为基准，model/excel/output 在其下。
- 打包后（PyInstaller 等）：以 exe 所在目录为基准。
- 环境变量（可选）：
  - CATEGORY_MATCHING_BASE_DIR：覆盖基准目录
  - CATEGORY_MATCHING_MODEL_DIR：覆盖 model 目录
  - CATEGORY_MATCHING_EXCEL_DIR：覆盖 excel 目录
  - CATEGORY_MATCHING_OUTPUT_DIR：覆盖 output 目录
"""

import os
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
