"""大模型配置：api_key（明文/加密）、base_url、model；加解密与脱敏。"""

from __future__ import annotations

import base64
import json
import logging
import os
from pathlib import Path

from . import paths as _paths

logger = logging.getLogger(__name__)

_FERNET_SALT = b"category_matching_llm_salt_v1"
_KEY_PASSPHRASE = "category_matching_llm_key_v1"
_DEFAULT_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
_DEFAULT_MODEL = "qwen-plus"


def mask_key(key: str | None) -> str:
    """脱敏展示：不可直接展示明文 key。"""
    if not key or not key.strip():
        return ""
    k = key.strip()
    if len(k) <= 8:
        return "***"
    if k.startswith("sk-"):
        return f"{k[:6]}***{k[-4:]}" if len(k) > 10 else "sk-***"
    return f"{k[:2]}***{k[-2:]}" if len(k) > 4 else "***"


def _fernet_key_from_passphrase(passphrase: str) -> bytes:
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives.hashes import SHA256

    kdf = PBKDF2HMAC(
        algorithm=SHA256(),
        length=32,
        salt=_FERNET_SALT,
        iterations=100000,
        backend=default_backend(),
    )
    return base64.urlsafe_b64encode(kdf.derive(passphrase.encode("utf-8")))


def encrypt_key(plain_key: str, passphrase: str = _KEY_PASSPHRASE) -> str:
    """将明文 API Key 加密为 base64 字符串，可写入 llm_config.json。"""
    from cryptography.fernet import Fernet
    f = Fernet(_fernet_key_from_passphrase(passphrase))
    return f.encrypt(plain_key.encode("utf-8")).decode("ascii")


def decrypt_key(encrypted_b64: str, passphrase: str = _KEY_PASSPHRASE) -> str | None:
    """从配置文件中的加密字符串解密出明文 API Key。"""
    from cryptography.fernet import Fernet, InvalidToken
    try:
        f = Fernet(_fernet_key_from_passphrase(passphrase))
        return f.decrypt(encrypted_b64.encode("ascii")).decode("utf-8")
    except (InvalidToken, Exception):
        return None


def load_llm_config() -> tuple[str | None, str, str]:
    """
    加载大模型配置：(api_key, base_url, model)。
    key 优先从 llm_config.json（明文或 api_key_encrypted），否则环境变量 OPENAI_API_KEY。
    """
    base_url = _DEFAULT_URL
    model = _DEFAULT_MODEL
    api_key: str | None = None

    config_path = _paths.get_llm_config_path_raw()
    if not config_path:
        logger.warning("未找到 llm_config.json（已尝试 config 目录），大模型将不调用；可设置环境变量 CATEGORY_MATCHING_LLM_CONFIG 或 CATEGORY_MATCHING_CONFIG_DIR 指定路径")
    else:
        logger.info("大模型配置文件: %s", config_path)
        try:
            raw = config_path.read_text(encoding="utf-8")
            data = json.loads(raw)
        except Exception as e:
            logger.warning("读取 llm_config.json 失败: %s", e)
            data = {}
        base_url = (data.get("base_url") or _DEFAULT_URL).strip().rstrip("/")
        model = (data.get("model") or _DEFAULT_MODEL).strip()
        plain_in_config = (data.get("api_key") or "").strip()
        if plain_in_config:
            api_key = plain_in_config
            logger.info("大模型配置已加载（api_key 明文），base_url=%s, model=%s", base_url, model)
        else:
            enc = (data.get("api_key_encrypted") or "").strip()
            if enc:
                dec = decrypt_key(enc)
                if dec:
                    api_key = dec
                    logger.info("大模型配置已加载（api_key_encrypted 解密成功），base_url=%s, model=%s", base_url, model)
                else:
                    logger.warning("api_key_encrypted 解密失败，请确认是用本项目 uv run -m llm.llm_config <明文key> 生成的密文；大模型将不调用")

    if api_key is None:
        api_key = os.environ.get("OPENAI_API_KEY", "").strip() or None
        if api_key:
            logger.info("大模型 API Key 来自环境变量 OPENAI_API_KEY")

    if api_key is None:
        logger.warning("未配置大模型 API Key（config/llm_config.json 或环境变量 OPENAI_API_KEY），大模型将不调用")

    base_url = base_url.rstrip("/") if base_url else _DEFAULT_URL
    model = model or _DEFAULT_MODEL
    return (api_key, base_url, model)
