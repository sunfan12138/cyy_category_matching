"""
大模型配置：从 core.config 统一 re-export，保持原有调用方式兼容。
命令行加密：uv run -m llm.llm_config <明文key>
"""

from __future__ import annotations

import sys

from core.config import (
    decrypt_key,
    encrypt_key,
    get_config_display,
    load_llm_config,
    mask_key,
)

__all__ = [
    "load_llm_config",
    "get_config_display",
    "mask_key",
    "encrypt_key",
    "decrypt_key",
]


def _main_encrypt() -> None:
    """命令行：uv run -m llm.llm_config <明文key>"""
    if len(sys.argv) < 2:
        print("用法: uv run -m llm.llm_config <明文API_Key>")
        print("输出加密后的字符串，填入 app_config.yaml 的 llm.api_key_encrypted。")
        sys.exit(1)
    enc = encrypt_key(sys.argv[1].strip())
    print("将下面一行填入 app_config.yaml 的 llm.api_key_encrypted：")
    print(enc)


if __name__ == "__main__":
    _main_encrypt()