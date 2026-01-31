"""
大模型配置：key/url/model 可配置；key 支持加密存储，展示时脱敏。

- 配置来源：llm_config.json（或环境变量 CATEGORY_MATCHING_LLM_CONFIG 指定路径）> 环境变量
- key：配置文件内为加密值（api_key_encrypted），解密需环境变量 CATEGORY_MATCHING_LLM_KEY_PASSPHRASE；或直接用环境变量 CATEGORY_MATCHING_LLM_API_KEY（明文，不展示）
- url/model：配置文件 base_url、model，或环境变量 CATEGORY_MATCHING_LLM_API_URL、CATEGORY_MATCHING_LLM_MODEL
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path

# 解密用盐（固定，与加密脚本一致）
_FERNET_SALT = b"category_matching_llm_salt_v1"
_DEFAULT_URL = "https://api.openai.com/v1"
_DEFAULT_MODEL = "gpt-3.5-turbo"


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
    """从口令派生 Fernet 所需 32 字节 key（base64url）。"""
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
    key_bytes = kdf.derive(passphrase.encode("utf-8"))
    return base64.urlsafe_b64encode(key_bytes)


def encrypt_key(plain_key: str, passphrase: str) -> str:
    """将明文 API Key 加密为 base64 字符串，可写入配置文件。"""
    from cryptography.fernet import Fernet

    f = Fernet(_fernet_key_from_passphrase(passphrase))
    return f.encrypt(plain_key.encode("utf-8")).decode("ascii")


def decrypt_key(encrypted_b64: str, passphrase: str) -> str | None:
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
    api_key 优先：配置文件中的 api_key_encrypted（需 PASSPHRASE 解密）> 环境变量 CATEGORY_MATCHING_LLM_API_KEY。
    base_url/model：配置文件 > 环境变量 > 默认值。
    返回的 api_key 仅用于调用，不可写入日志或界面；展示请用 mask_key(api_key)。
    """
    from paths import get_llm_config_path

    base_url = os.environ.get("CATEGORY_MATCHING_LLM_API_URL", "").strip() or _DEFAULT_URL
    model = os.environ.get("CATEGORY_MATCHING_LLM_MODEL", "").strip() or _DEFAULT_MODEL
    api_key = os.environ.get("CATEGORY_MATCHING_LLM_API_KEY", "").strip() or None

    config_path = get_llm_config_path()
    if config_path:
        try:
            raw = config_path.read_text(encoding="utf-8")
            data = json.loads(raw)
        except Exception:
            data = {}
        base_url = (data.get("base_url") or base_url or _DEFAULT_URL).strip().rstrip("/")
        model = (data.get("model") or model or _DEFAULT_MODEL).strip()
        enc = data.get("api_key_encrypted", "").strip()
        if enc:
            passphrase = os.environ.get("CATEGORY_MATCHING_LLM_KEY_PASSPHRASE", "").strip()
            if passphrase:
                dec = decrypt_key(enc, passphrase)
                if dec:
                    api_key = dec

    base_url = base_url.rstrip("/") if base_url else _DEFAULT_URL
    model = model or _DEFAULT_MODEL
    return (api_key, base_url, model)


def get_config_display() -> dict[str, str]:
    """用于界面/日志的配置展示：base_url、model、key 脱敏。不包含明文 key。"""
    api_key, base_url, model = load_llm_config()
    return {
        "base_url": base_url,
        "model": model,
        "api_key_masked": mask_key(api_key),
        "configured": "是" if api_key else "否",
    }


def _main_encrypt() -> None:
    """命令行：将明文 key 加密后输出，用于写入 llm_config.json。用法：uv run -m core.llm_config <明文key>"""
    import sys

    if len(sys.argv) < 2:
        print("用法: uv run -m core.llm_config <明文API_Key>")
        print("将提示输入口令（或设置环境变量 CATEGORY_MATCHING_LLM_KEY_PASSPHRASE），输出加密后的字符串，填入 llm_config.json 的 api_key_encrypted。")
        sys.exit(1)
    plain = sys.argv[1].strip()
    passphrase = os.environ.get("CATEGORY_MATCHING_LLM_KEY_PASSPHRASE", "").strip()
    if not passphrase:
        import getpass
        passphrase = getpass.getpass("请输入加密/解密口令（将用于解密时）：").strip()
    if not passphrase:
        print("口令不能为空")
        sys.exit(1)
    enc = encrypt_key(plain, passphrase)
    print("将下面一行填入 llm_config.json 的 api_key_encrypted：")
    print(enc)


if __name__ == "__main__":
    _main_encrypt()
