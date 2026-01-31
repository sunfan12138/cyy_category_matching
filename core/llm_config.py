"""
大模型配置：key/url/model 可配置；key 支持加密存储，展示时脱敏。

- key 优先级：默认取环境变量 OPEN_AI_KEY（明文，不需解密）；若 llm_config.json 里配置了 key，则用配置的（api_key 明文 或 api_key_encrypted 需解密）。
- 配置文件：llm_config.json 可配 api_key（明文）、api_key_encrypted（加密，解密口令写死在代码中）、base_url、model。
- base_url/model：仅从配置文件取，未配置则用默认值。
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path

# 解密用盐（固定，与加密脚本一致）
_FERNET_SALT = b"category_matching_llm_salt_v1"
# api_key_encrypted 加解密口令（写死，与加密脚本一致）
_KEY_PASSPHRASE = "category_matching_llm_key_v1"
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
    key 默认取环境变量 OPEN_AI_KEY（明文，不需解密）；若 llm_config.json 里配置了 api_key 或 api_key_encrypted，则用配置的（加密项用写死的口令解密）。
    base_url/model：仅从配置文件取，未配置则用默认值。
    返回的 api_key 仅用于调用，不可写入日志或界面；展示请用 mask_key(api_key)。
    """
    from paths import get_llm_config_path

    base_url = _DEFAULT_URL
    model = _DEFAULT_MODEL
    api_key: str | None = None

    config_path = get_llm_config_path()
    if config_path:
        try:
            raw = config_path.read_text(encoding="utf-8")
            data = json.loads(raw)
        except Exception:
            data = {}
        base_url = (data.get("base_url") or _DEFAULT_URL).strip().rstrip("/")
        model = (data.get("model") or _DEFAULT_MODEL).strip()
        # 配置里配了 key 则用配置的（明文直接取，加密需解密）
        plain_in_config = (data.get("api_key") or "").strip()
        if plain_in_config:
            api_key = plain_in_config
        else:
            enc = (data.get("api_key_encrypted") or "").strip()
            if enc:
                dec = decrypt_key(enc, _KEY_PASSPHRASE)
                if dec:
                    api_key = dec

    if api_key is None:
        api_key = os.environ.get("OPEN_AI_KEY", "").strip() or None

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
    """命令行：将明文 key 加密后输出，用于写入 llm_config.json。用法：uv run -m core.llm_config <明文key>（口令写死在代码中）"""
    import sys

    if len(sys.argv) < 2:
        print("用法: uv run -m core.llm_config <明文API_Key>")
        print("输出加密后的字符串，填入 llm_config.json 的 api_key_encrypted。")
        sys.exit(1)
    plain = sys.argv[1].strip()
    enc = encrypt_key(plain, _KEY_PASSPHRASE)
    print("将下面一行填入 llm_config.json 的 api_key_encrypted：")
    print(enc)


if __name__ == "__main__":
    _main_encrypt()
