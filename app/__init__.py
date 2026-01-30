"""应用层：路径/文件 IO、批量匹配、结果输出。"""

from .batch import run_batch_match
from .file_io import read_categories_from_file
from .output import write_result_excel
from .path_utils import normalize_input_path

__all__ = [
    "normalize_input_path",
    "read_categories_from_file",
    "run_batch_match",
    "write_result_excel",
]
