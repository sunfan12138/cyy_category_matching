"""大模型配置：api_key（明文/加密）、base_url、model；加解密与脱敏。"""

from __future__ import annotations

import base64
import json
import logging
import os

from pydantic import ValidationError

from models.schemas import LlmConfigResult, LlmConfigSchema

from . import paths as _paths

logger = logging.getLogger(__name__)

_FERNET_SALT = b"category_matching_llm_salt_v1"
_KEY_PASSPHRASE = "category_matching_llm_key_v1"
_DEFAULT_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
_DEFAULT_MODEL = "qwen-plus"


def build_llm_config_result(schema: LlmConfigSchema) -> LlmConfigResult:
    """
    从 LlmConfigSchema（YAML/JSON 中的 llm 节）解析出 LlmConfigResult。
    优先 api_key 明文，否则 api_key_encrypted 解密，否则环境变量 OPENAI_API_KEY。
    """
    base_url = (schema.base_url or _DEFAULT_URL).rstrip("/")
    model = schema.model or _DEFAULT_MODEL
    api_key: str | None = None
    if schema.api_key and schema.api_key.strip():
        api_key = schema.api_key.strip()
        logger.info("大模型配置已加载（api_key 明文），base_url=%s, model=%s", base_url, model)
    elif schema.api_key_encrypted and schema.api_key_encrypted.strip():
        dec = decrypt_key(schema.api_key_encrypted.strip())
        if dec:
            api_key = dec
            logger.info("大模型配置已加载（api_key_encrypted 解密成功），base_url=%s, model=%s", base_url, model)
        else:
            logger.warning("api_key_encrypted 解密失败，请确认使用 uv run -m core.config <明文key> 生成")
    if api_key is None:
        api_key = os.environ.get("OPENAI_API_KEY", "").strip() or None
        if api_key:
            logger.info("大模型 API Key 来自环境变量 OPENAI_API_KEY")
    if api_key is None:
        logger.warning("未配置大模型 API Key（app_config.yaml 或环境变量 OPENAI_API_KEY），大模型将不调用")
    return LlmConfigResult(api_key=api_key, base_url=base_url, model=model)


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


def load_llm_config(schema: LlmConfigSchema | None = None) -> LlmConfigResult:
    """
    加载大模型配置：返回 LlmConfigResult(api_key, base_url, model)。
    若传入 schema（来自 app_config.yaml 的 llm 节），则直接使用；否则由调用方从 loader 提供。
    """
    if schema is not None:
        return build_llm_config_result(schema)
    # 兼容：无统一配置时从旧版 llm_config.json 读
    config_path = _paths.get_llm_config_path_raw()
    if not config_path:
        logger.warning("未找到 llm_config.json，使用默认 base_url/model")
        return build_llm_config_result(LlmConfigSchema())
    try:
        raw = config_path.read_text(encoding="utf-8")
        data = json.loads(raw)
        cfg = LlmConfigSchema.model_validate(data)
    except (ValidationError, json.JSONDecodeError) as e:
        logger.warning("读取或解析 llm_config.json 失败: %s", e)
        cfg = LlmConfigSchema()
    return build_llm_config_result(cfg)
