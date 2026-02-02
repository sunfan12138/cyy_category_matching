"""统一配置加载：从 app_config.yaml 读取并校验。"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from models.schemas import AppConfigSchema

from . import paths as _paths

logger = logging.getLogger(__name__)

APP_CONFIG_FILENAME = "app_config.yaml"


def get_app_config_path() -> Path:
    """app_config.yaml 路径（config 目录下）。"""
    return _paths.get_config_dir_raw() / APP_CONFIG_FILENAME


def _load_yaml(path: Path) -> dict[str, Any] | None:
    """读取 YAML 文件，解析失败返回 None。"""
    if not path.exists():
        return None
    try:
        raw = path.read_text(encoding="utf-8")
        return yaml.safe_load(raw) or {}
    except (yaml.YAMLError, OSError) as e:
        logger.warning("读取 YAML 失败 %s: %s", path, e)
        return None


def load_app_config_yaml() -> AppConfigSchema:
    """
    从 config/app_config.yaml 加载统一配置；若不存在或解析失败则使用默认值。
    返回 AppConfigSchema，各节均有默认值。
    """
    yaml_path = get_app_config_path()
    data: dict[str, Any] = _load_yaml(yaml_path) or {}
    try:
        return AppConfigSchema.model_validate(data)
    except ValidationError as e:
        logger.warning("配置校验失败，使用默认配置: %s", e)
        return AppConfigSchema.model_validate({})
