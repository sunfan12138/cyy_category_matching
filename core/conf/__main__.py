"""uv run -m core.conf encrypt <明文key> 或 uv run -m core.conf <明文key>"""

from . import main_encrypt

if __name__ == "__main__":
    main_encrypt()
