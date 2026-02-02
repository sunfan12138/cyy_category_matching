"""文件读写：品类列表读取、匹配结果写入 Excel。"""

from pathlib import Path

from core.utils.excel_io import write_sheet

# 匹配成功：关键词匹配到、相似度匹配到、搜索大模型后匹配到；其余为匹配失败
MATCH_SUCCESS_METHODS = ("规则", "相似度", "搜索后匹配")

# 7 列：(输入品类, 一级原子品类, 品类编码, 原子品类, 匹配方式, 相似度匹配结果, 大模型描述)
ResultRow = tuple[str, str, str, str, str, str, str]

HEADERS = (
    "输入品类",
    "一级原子品类",
    "品类编码",
    "原子品类",
    "匹配方式",
    "相似度匹配结果",
    "大模型描述",
)


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


def write_result_excel(rows: list[ResultRow], output_path: Path) -> None:
    """将结果写入 Excel，未匹配行标红。"""
    write_sheet(
        output_path,
        "匹配结果",
        HEADERS,
        rows,
        failed_row_predicate=lambda row: len(row) > 4 and row[4] not in MATCH_SUCCESS_METHODS,
    )
