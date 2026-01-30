"""从文件按行读取品类列表。"""

from pathlib import Path


def read_categories_from_file(file_path: Path) -> list[str]:
    """读取文件，每行一个品类，去空行、去首尾空白。"""
    try:
        text = file_path.read_text(encoding="utf-8")
    except Exception as e:
        try:
            text = file_path.read_text(encoding="utf-8-sig")
        except Exception:
            raise RuntimeError(f"无法读取文件 {file_path}: {e}") from e
    return [line.strip() for line in text.splitlines() if line.strip()]
