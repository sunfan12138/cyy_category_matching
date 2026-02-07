"""大模型配置：api_key（明文/加密）、base_url、model；加解密与脱敏。"""

from __future__ import annotations

import base64
import logging

from models.schemas import LlmConfigResult, LlmConfigSchema

logger = logging.getLogger(__name__)

_FERNET_SALT = b"category_matching_llm_salt_v1"
_KEY_PASSPHRASE = "category_matching_llm_key_v1"
_DEFAULT_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
_DEFAULT_MODEL = "qwen-plus"


def _resolve_api_key(schema: LlmConfigSchema, base_url: str, model: str) -> str | None:
    """从 schema 解析出 api_key：优先明文，否则解密 api_key_encrypted。"""
    if schema.api_key and schema.api_key.strip():
        logger.info("大模型配置已加载（api_key），base_url=%s, model=%s", base_url, model)
        return schema.api_key.strip()
    if not (schema.api_key_encrypted and schema.api_key_encrypted.strip()):
        return None
    decrypted_key = decrypt_key(schema.api_key_encrypted.strip())
    if decrypted_key:
        logger.info("大模型配置已加载（api_key_encrypted 解密成功），base_url=%s, model=%s", base_url, model)
        return decrypted_key
    logger.warning("api_key_encrypted 解密失败，请确认使用 uv run -m core.config <明文key> 生成")
    return None


def build_llm_config_result(schema: LlmConfigSchema) -> LlmConfigResult:
    """
    从 LlmConfigSchema（YAML/JSON 中的 llm 节）解析出 LlmConfigResult。
    优先 api_key 明文，否则 api_key_encrypted 解密；环境变量请用 api_key: \"${VAR}\" 在 YAML 中配置。
    """
    base_url = (schema.base_url or _DEFAULT_URL).rstrip("/")
    model = schema.model or _DEFAULT_MODEL
    api_key = _resolve_api_key(schema, base_url, model)
    if api_key is None:
        logger.warning(
            "未配置大模型 API Key（请在 app_config.yaml 的 llm.api_key 中配置，"
            "或使用 api_key: \"${OPENAI_API_KEY}\" 引用环境变量）"
        )
    return LlmConfigResult(api_key=api_key, base_url=base_url, model=model)


def mask_key(key: str | None) -> str:
    """脱敏展示：不可直接展示明文 key。"""
    if not key or not key.strip():
        return ""
    key_trimmed = key.strip()
    if len(key_trimmed) <= 8:
        return "***"
    if key_trimmed.startswith("sk-"):
        return f"{key_trimmed[:6]}***{key_trimmed[-4:]}" if len(key_trimmed) > 10 else "sk-***"
    return f"{key_trimmed[:2]}***{key_trimmed[-2:]}" if len(key_trimmed) > 4 else "***"


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
    """将明文 API Key 加密为 base64 字符串，可写入 app_config.yaml 的 llm.api_key_encrypted。"""
    from cryptography.fernet import Fernet

    fernet = Fernet(_fernet_key_from_passphrase(passphrase))
    return fernet.encrypt(plain_key.encode("utf-8")).decode("ascii")


def decrypt_key(encrypted_b64: str, passphrase: str = _KEY_PASSPHRASE) -> str | None:
    """从配置文件中的加密字符串解密出明文 API Key。"""
    from cryptography.fernet import Fernet, InvalidToken

    try:
        fernet = Fernet(_fernet_key_from_passphrase(passphrase))
        return fernet.decrypt(encrypted_b64.encode("ascii")).decode("utf-8")
    except (InvalidToken, Exception):
        return None


def load_llm_config(schema: LlmConfigSchema | None = None) -> LlmConfigResult:
    """
    加载大模型配置：返回 LlmConfigResult(api_key, base_url, model)。
    若传入 schema（来自 app_config.yaml 的 llm 节），则直接使用；否则使用默认配置。
    """
    if schema is not None:
        return build_llm_config_result(schema)
    return build_llm_config_result(LlmConfigSchema())
