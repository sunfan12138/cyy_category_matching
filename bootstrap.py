"""
依赖组装：为 CLI 与批处理提供统一入口，仅做依赖汇集，不包含业务逻辑与算法。
"""

from __future__ import annotations

from application.use_cases.batch_match import run_batch_match
from core import (
    ensure_model_loaded,
    fill_brand_embeddings,
    load_rules,
    load_verified_brands,
)
from core.config import inject, load_app_config, AppConfig
from domain.category import CategoryRule, VerifiedBrand
from infrastructure.config.paths import (
    get_excel_dir,
    get_log_dir,
    get_output_dir,
    normalize_input_path,
)
from infrastructure.io.file_io import (
    MATCH_SUCCESS_METHODS,
    append_result_rows,
    read_categories_from_file,
    start_result_excel,
    write_result_excel,
)
from models.schemas import RunConfigSchema

__all__ = [
    "AppConfig",
    "CategoryRule",
    "MATCH_SUCCESS_METHODS",
    "RunConfigSchema",
    "VerifiedBrand",
    "append_result_rows",
    "ensure_model_loaded",
    "fill_brand_embeddings",
    "get_excel_dir",
    "get_log_dir",
    "get_output_dir",
    "inject",
    "load_app_config",
    "load_rules",
    "load_verified_brands",
    "normalize_input_path",
    "read_categories_from_file",
    "run_batch_match",
    "start_result_excel",
    "write_result_excel",
]
