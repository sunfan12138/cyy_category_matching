"""公共工具：Excel 读写、相似度计算、文件读取等。"""

from .excel_io import cell_value, open_excel_read, write_sheet
from .similarity import (
    DEFAULT_BGE_WEIGHT,
    jaro_winkler_similarity,
    weighted_combined,
)

__all__ = [
    "cell_value",
    "open_excel_read",
    "write_sheet",
    "DEFAULT_BGE_WEIGHT",
    "jaro_winkler_similarity",
    "weighted_combined",
]
