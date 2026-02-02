"""uv run -m core.config encrypt <明文key> 或 uv run -m core.config <明文key>"""

from . import main_encrypt

if __name__ == "__main__":
    main_encrypt()
