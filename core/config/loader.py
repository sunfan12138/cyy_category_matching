"""统一配置加载：从 app_config.yaml 读取并校验，兼容旧版 llm_config.json / mcp_client_config.json。"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from models.schemas import AppConfigSchema

from . import paths as _paths

logger = logging.getLogger(__name__)

# 默认配置文件名
APP_CONFIG_FILENAME = "app_config.yaml"
LEGACY_LLM_CONFIG_FILENAME = "llm_config.json"
LEGACY_MCP_CONFIG_FILENAME = "mcp_client_config.json"


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


def _load_json(path: Path) -> dict[str, Any] | None:
    """读取 JSON 文件，解析失败返回 None。"""
    if not path or not path.exists():
        return None
    try:
        raw = path.read_text(encoding="utf-8")
        return json.loads(raw) or {}
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("读取 JSON 失败 %s: %s", path, e)
        return None


def load_app_config_yaml() -> AppConfigSchema:
    """
    加载统一配置：优先 app_config.yaml；若不存在或某节缺失，使用默认 + 旧版 JSON 补充。
    返回 AppConfigSchema，各节均有默认值。
    """
    config_dir = _paths.get_config_dir_raw()
    yaml_path = config_dir / APP_CONFIG_FILENAME
    data: dict[str, Any] = _load_yaml(yaml_path) or {}

    # 若 YAML 无 llm 节，尝试旧版 llm_config.json
    if "llm" not in data or not data["llm"]:
        legacy_llm = config_dir / LEGACY_LLM_CONFIG_FILENAME
        legacy_data = _load_json(legacy_llm)
        if legacy_data:
            data["llm"] = legacy_data
            logger.info("从 %s 加载大模型配置（兼容旧版）", legacy_llm)

    # 若 YAML 无 mcp 节或 servers 为空，尝试旧版 mcp_client_config.json
    if "mcp" not in data or not data.get("mcp") or not data["mcp"].get("servers"):
        legacy_mcp = config_dir / LEGACY_MCP_CONFIG_FILENAME
        legacy_data = _load_json(legacy_mcp)
        if legacy_data and legacy_data.get("servers"):
            data["mcp"] = legacy_data
            logger.info("从 %s 加载 MCP 配置（兼容旧版）", legacy_mcp)

    try:
        return AppConfigSchema.model_validate(data)
    except ValidationError as e:
        logger.warning("配置校验失败，使用默认配置: %s", e)
        return AppConfigSchema.model_validate({})
