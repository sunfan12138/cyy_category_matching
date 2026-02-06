"""统一配置加载：从 app_config.yaml 读取并校验。支持整文件 ${VAR_NAME} 环境变量占位。"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from models.schemas import AppConfigSchema

from . import paths as _paths

logger = logging.getLogger(__name__)

APP_CONFIG_FILENAME = "app_config.yaml"
_ENV_PLACEHOLDER = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def _substitute_env_vars(content: str) -> str:
    """将原始文本中的 ${VAR_NAME} 替换为环境变量值；未定义则替换为空。"""
    return _ENV_PLACEHOLDER.sub(lambda m: os.environ.get(m.group(1), ""), content)


def get_app_config_path() -> Path:
    """app_config.yaml 路径（config 目录下）。"""
    return _paths.get_config_dir_raw() / APP_CONFIG_FILENAME


def _load_yaml(path: Path) -> dict[str, Any] | None:
    """读取 YAML 文件，先解析 ${VAR_NAME} 再交给 PyYAML；解析失败返回 None。"""
    if not path.exists():
        return None
    try:
        file_content = path.read_text(encoding="utf-8")
        content_with_env_resolved = _substitute_env_vars(file_content)
        return yaml.safe_load(content_with_env_resolved) or {}
    except (yaml.YAMLError, OSError) as error:
        logger.warning("读取 YAML 失败 %s: %s", path, error)
        return None


def load_app_config_yaml() -> AppConfigSchema:
    """
    从 config/app_config.yaml 加载统一配置；若不存在或解析失败则使用默认值。
    返回 AppConfigSchema，各节均有默认值。
    """
    yaml_path = get_app_config_path()
    config_data: dict[str, Any] = _load_yaml(yaml_path) or {}
    try:
        return AppConfigSchema.model_validate(config_data)
    except ValidationError as error:
        logger.warning("配置校验失败，使用默认配置: %s", error)
        return AppConfigSchema.model_validate({})
