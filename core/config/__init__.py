"""
core.config：整合路径、统一 YAML 配置 app_config.yaml 及加载。

- 配置：config/app_config.yaml（含 llm、mcp、matching、app、embedding、llm_client、prompt）。
- 路径：config 目录及 model/excel/output/logs（见 .paths）
- 统一加载：load_app_config() 启动时调用一次；配置通过 inject(Annotated 类型) 获取。
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Annotated, Any

from models.schemas import (
    AppConfigSchema,
    ConfigDisplay,
    EmbeddingSection,
    LlmConfigResult,
    LlmClientSection,
    MatchingSection,
    PromptSection,
)

from . import deps as _deps
from . import llm as _llm
from . import loader as _loader
from . import mcp as _mcp
from . import paths as _paths

Depends = _deps.Depends
inject = _deps.inject
logger = logging.getLogger(__name__)

# ----- 路径（直接转发） -----

get_config_dir_raw = _paths.get_config_dir_raw
get_llm_config_path_raw = _paths.get_llm_config_path_raw
get_mcp_config_path_raw = _paths.get_mcp_config_path_raw
get_app_config_path = _loader.get_app_config_path
get_base_dir = _paths.get_base_dir
get_model_dir = _paths.get_model_dir
get_excel_dir = _paths.get_excel_dir
get_output_dir = _paths.get_output_dir
get_log_dir = _paths.get_log_dir
normalize_input_path = _paths.normalize_input_path

# ----- LLM（直接转发） -----

mask_key = _llm.mask_key
encrypt_key = _llm.encrypt_key
decrypt_key = _llm.decrypt_key
load_llm_config = _llm.load_llm_config

# ----- MCP（直接转发） -----

ServerConfig = _mcp.ServerConfig
load_mcp_config = _mcp.load_mcp_config

# ----- 统一加载与缓存 -----

_loaded = False
_config_dir: Path | None = None
_app_config_path: Path | None = None
_llm_config: LlmConfigResult | None = None
_mcp_config: list[Any] | None = None
_app_config: AppConfigSchema | None = None


def _ensure_loaded() -> None:
    """确保配置已加载，未加载时执行一次 load_app_config()。"""
    if not _loaded:
        load_app_config()


def load_app_config() -> None:
    """加载全部配置：从 config/app_config.yaml 读取并缓存。"""
    global _loaded, _config_dir, _app_config_path, _llm_config, _mcp_config, _app_config

    if _loaded:
        return

    _config_dir = get_config_dir_raw()
    _app_config = _loader.load_app_config_yaml()
    _app_config_path = get_app_config_path()

    _llm_config = load_llm_config(_app_config.llm)
    _mcp_config = [server for server in _app_config.mcp.servers if server.name]

    _loaded = True
    logger.debug(
        "公用配置已加载: config_dir=%s, config_file=%s",
        _config_dir,
        _app_config_path,
    )


def _resolve_app_config() -> AppConfigSchema:
    _ensure_loaded()
    assert _app_config is not None
    return _app_config


def _resolve_config_dir() -> Path:
    _ensure_loaded()
    assert _config_dir is not None
    return _config_dir


def _resolve_app_config_path() -> Path:
    _ensure_loaded()
    assert _app_config_path is not None
    return _app_config_path


def _resolve_llm_config() -> LlmConfigResult:
    _ensure_loaded()
    assert _llm_config is not None
    return _llm_config


def _resolve_mcp_config() -> list[Any]:
    _ensure_loaded()
    assert _mcp_config is not None
    return _mcp_config


# ----- 依赖注入：Annotated 类型别名（供 inject() 使用） -----

AppConfig = Annotated[AppConfigSchema, Depends(_resolve_app_config)]
LlmConfig = Annotated[LlmConfigResult, Depends(_resolve_llm_config)]
McpConfigList = Annotated[list[Any], Depends(_resolve_mcp_config)]
ConfigDirPath = Annotated[Path, Depends(_resolve_config_dir)]
AppConfigFilePath = Annotated[Path, Depends(_resolve_app_config_path)]


def _get_matching_config() -> MatchingSection:
    return _resolve_app_config().matching


def _get_embedding_config() -> EmbeddingSection:
    return _resolve_app_config().embedding


def _get_llm_client_config() -> LlmClientSection:
    return _resolve_app_config().llm_client


def _get_prompt_config() -> PromptSection:
    return _resolve_app_config().prompt


MatchingConfig = Annotated[MatchingSection, Depends(_get_matching_config)]
EmbeddingConfig = Annotated[EmbeddingSection, Depends(_get_embedding_config)]
LlmClientConfig = Annotated[LlmClientSection, Depends(_get_llm_client_config)]
PromptConfig = Annotated[PromptSection, Depends(_get_prompt_config)]


def get_config_display() -> dict[str, str]:
    """用于界面/日志的配置展示：base_url、model、key 脱敏。"""
    llm_config = inject(LlmConfig)
    display = ConfigDisplay(
        base_url=llm_config.base_url,
        model=llm_config.model,
        api_key_masked=mask_key(llm_config.api_key),
        configured="是" if llm_config.api_key else "否",
    )
    return display.model_dump()


# ----- CLI：加密 key -----


def _parse_plain_key_from_argv() -> str:
    """从命令行参数解析待加密的明文 API Key。"""
    if len(sys.argv) >= 3 and sys.argv[1] == "encrypt":
        return sys.argv[2].strip()
    return sys.argv[1].strip()


def main_encrypt() -> None:
    """命令行：uv run -m core.config encrypt <明文key> 或 uv run -m core.config <明文key>"""
    if len(sys.argv) < 2:
        print("用法: uv run -m core.config encrypt <明文API_Key>  或  uv run -m core.config <明文API_Key>")
        print("输出加密后的字符串，填入 config/app_config.yaml 的 llm.api_key_encrypted。")
        sys.exit(1)
    plain_key = _parse_plain_key_from_argv()
    print("将下面一行填入 config/app_config.yaml 的 llm.api_key_encrypted：")
    print(encrypt_key(plain_key))


__all__ = [
    "load_app_config",
    "get_config_dir_raw",
    "get_llm_config_path_raw",
    "get_mcp_config_path_raw",
    "get_config_display",
    "load_llm_config",
    "mask_key",
    "encrypt_key",
    "decrypt_key",
    "ServerConfig",
    "load_mcp_config",
    "main_encrypt",
    "get_app_config_path",
    "get_base_dir",
    "get_model_dir",
    "get_excel_dir",
    "get_output_dir",
    "get_log_dir",
    "normalize_input_path",
    "Depends",
    "inject",
    "AppConfig",
    "LlmConfig",
    "McpConfigList",
    "ConfigDirPath",
    "AppConfigFilePath",
    "MatchingConfig",
    "EmbeddingConfig",
    "LlmClientConfig",
    "PromptConfig",
]
