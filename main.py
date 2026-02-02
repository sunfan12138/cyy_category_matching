"""
品类匹配入口：加载配置与规则后，接受品类文件路径，执行批量匹配并输出到 output 目录。

流程拆分为：init_config -> load_data -> (循环) run_matching -> save_output，
便于单测与维护；支持可选命令行参数（--input、--no-loop）。
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

from app import (
    normalize_input_path,
    read_categories_from_file,
    run_batch_match,
    write_result_excel,
)
from app.file_io import MATCH_SUCCESS_METHODS
from paths import get_excel_dir, get_log_dir, get_output_dir
from core import (
    ensure_model_loaded,
    fill_brand_embeddings,
    load_rules,
    load_verified_brands,
)
from core.config import load_app_config, get_app_config
from core.models import CategoryRule, VerifiedBrand
from models.schemas import RunConfigSchema

# 7 列结果行类型（与 app.file_io.ResultRow 一致）
ResultRow = tuple[str, str, str, str, str, str, str]

# 向后兼容：运行时配置使用 Pydantic RunConfigSchema
RunConfig = RunConfigSchema


def init_config(
    *,
    excel_dir: Path | None = None,
    output_dir: Path | None = None,
    log_dir: Path | None = None,
) -> RunConfigSchema:
    """
    初始化配置与日志：加载应用配置、创建日志目录、配置 logging，返回 RunConfig。

    Args:
        excel_dir: 规则/已校验品牌目录，默认从 paths.get_excel_dir() 获取。
        output_dir: 结果输出目录，默认从 paths.get_output_dir() 获取。
        log_dir: 日志目录，默认从 paths.get_log_dir() 获取。

    Returns:
        RunConfigSchema: 运行时路径配置，用于后续 load_data / save_output。

    Raises:
        无显式异常；路径不存在时仅创建 log_dir，excel/output 由后续步骤校验。
    """
    load_app_config()
    app_cfg = get_app_config().app
    _config = RunConfigSchema(
        excel_dir=excel_dir or get_excel_dir(),
        output_dir=output_dir or get_output_dir(),
        log_dir=log_dir or get_log_dir(),
        rules_filename=app_cfg.rules_filename,
        verified_filename=app_cfg.verified_filename,
    )
    # 先配置日志再打印（配置已由 load_app_config 加载）
    _setup_logging(_config.log_dir)
    print(f"配置已加载: excel_dir={_config.excel_dir}, output_dir={_config.output_dir}")
    return _config


def _setup_logging(log_dir: Path) -> None:
    """
    将日志按日期写入 log_dir，文件名 category_matching_YYYYMMDD.log。
    若已存在指向当日日志文件的 FileHandler 则不再添加，避免重复。
    """
    log_dir.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y%m%d")
    log_file = log_dir / f"category_matching_{today}.log"
    log_path = str(log_file.resolve())
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    for h in root.handlers:
        if isinstance(h, logging.FileHandler) and getattr(h, "baseFilename", "") == log_path:
            return
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    handler = logging.FileHandler(log_file, mode="a", encoding="utf-8")
    handler.setFormatter(logging.Formatter(fmt))
    root.addHandler(handler)


def load_data(
    config: RunConfigSchema,
) -> tuple[list[CategoryRule], list[VerifiedBrand]]:
    """
    加载规则与已校验品牌数据。

    Args:
        config: 运行时配置，用于定位 rules_path、verified_path。

    Returns:
        (rules, verified_brands): 规则列表与已校验品牌列表。

    Raises:
        FileNotFoundError: 规则文件不存在。
        ValueError: 规则文件无有效工作表或解析失败。
    """
    rules_path = config.rules_path
    verified_path = config.verified_path

    if not rules_path.exists():
        raise FileNotFoundError(f"规则文件不存在: {rules_path}")

    try:
        _, rules = load_rules(rules_path)
    except Exception as e:
        raise ValueError(f"加载规则文件失败: {rules_path}") from e

    if not rules:
        print(f"规则文件为空或未解析到有效规则: {rules_path}")

    if not verified_path.exists():
        print(f"已校验品牌文件不存在，将使用空列表: {verified_path}")
        verified_brands: list[VerifiedBrand] = []
    else:
        try:
            verified_brands = load_verified_brands(verified_path)
        except Exception as e:
            print(f"加载已校验品牌文件失败，将使用空列表: {e}")
            verified_brands = []

    print(f"规则 {len(rules)} 条，已校验品牌 {len(verified_brands)} 条。")
    return rules, verified_brands


def run_matching(
    categories: list[str],
    rules: list[CategoryRule],
    verified_brands: list[VerifiedBrand],
) -> list[ResultRow]:
    """
    对品类列表执行批量匹配，返回 7 列结果行。

    Args:
        categories: 待匹配品类名称列表。
        rules: 规则列表（由 load_data 返回）。
        verified_brands: 已校验品牌列表（由 load_data 返回）。

    Returns:
        与 categories 顺序一致的 7 列结果行列表（见 app.io.ResultRow）。
    """
    if not categories:
        return []
    try:
        result = run_batch_match(categories, rules, verified_brands)
    except Exception as e:
        raise RuntimeError("批量匹配失败") from e
    return result


def save_output(
    result_rows: list[ResultRow],
    output_dir: Path,
    *,
    source_stem: str | None = None,
    ignore_stem: str | None = None,
) -> Path:
    """
    将匹配结果写入 Excel 并保存到 output_dir。

    Args:
        result_rows: 7 列结果行（run_matching 返回值）。
        output_dir: 输出目录，不存在时会创建。
        source_stem: 输入文件名（无后缀），用于生成输出文件名；为空时使用「匹配结果_时间戳」。
        ignore_stem: 当 source_stem 等于此值时视为未提供有意义文件名，按无 stem 处理。

    Returns:
        写入的 Excel 文件路径。

    Raises:
        RuntimeError: 写入 Excel 失败。
    """
    if ignore_stem is None:
        ignore_stem = get_app_config().app.input_stem_ignore
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if source_stem and source_stem != ignore_stem:
        output_filename = f"{source_stem}_匹配结果_{stamp}.xlsx"
    else:
        output_filename = f"匹配结果_{stamp}.xlsx"
    output_path = output_dir / output_filename
    try:
        write_result_excel(result_rows, output_path)
    except Exception as e:
        raise RuntimeError(f"写入结果文件失败: {output_path}") from e
    return output_path


def _ensure_model_and_embeddings(
    verified_brands: list[VerifiedBrand],
) -> None:
    """加载 BGE 模型并填充已校验品牌向量；无品牌时仅加载模型。"""
    ensure_model_loaded()
    if verified_brands:
        fill_brand_embeddings(verified_brands)


def _process_one_file(
    input_path: Path,
    config: RunConfigSchema,
    rules: list[CategoryRule],
    verified_brands: list[VerifiedBrand],
) -> Path | None:
    """
    处理单个品类文件：读取品类列表 -> 匹配 -> 写结果。
    返回结果文件路径；读取或匹配失败时返回 None 并已打日志。
    """
    try:
        categories = read_categories_from_file(input_path)
    except Exception as e:
        print(f"读取文件失败 {input_path}: {e}")
        return None

    if not categories:
        print(f"文件中没有有效品类行: {input_path}")
        return None

    try:
        result_rows = run_matching(categories, rules, verified_brands)
    except RuntimeError:
        return None

    unmatched = sum(1 for r in result_rows if r[4] not in MATCH_SUCCESS_METHODS)
    print(f"匹配成功 {len(result_rows) - unmatched} 条，匹配失败 {unmatched} 条（已标红）。")

    stem = input_path.stem if input_path.stem != get_app_config().app.input_stem_ignore else None
    try:
        out_path = save_output(result_rows, config.output_dir, source_stem=stem)
    except RuntimeError:
        return None
    print(f"已写入: {out_path}")
    return out_path


def _parse_args(args: list[str] | None = None) -> argparse.Namespace:
    """解析命令行参数；args 为 None 时使用 sys.argv，便于单测注入。"""
    parser = argparse.ArgumentParser(
        description="品类匹配：加载规则与已校验品牌，对输入品类文件执行匹配并输出 Excel。",
    )
    parser.add_argument(
        "input_file",
        nargs="?",
        default=None,
        help="待匹配品类文件路径（每行一个品类）；不指定则进入交互式输入。",
    )
    parser.add_argument(
        "--no-loop",
        action="store_true",
        help="指定 input_file 时仅处理该文件一次后退出，不进入交互循环。",
    )
    return parser.parse_args(args)


def main(args: list[str] | None = None) -> None:
    """
    入口：初始化配置 -> 加载数据 -> 加载模型与向量 -> 循环处理输入文件或处理单文件后退出。

    支持命令行：
      python main.py                    # 交互式输入文件路径
      python main.py 文件.txt          # 处理该文件后继续交互
      python main.py 文件.txt --no-loop # 仅处理该文件后退出
    """
    parsed = _parse_args(args)
    config = init_config()

    try:
        rules, verified_brands = load_data(config)
    except (FileNotFoundError, ValueError) as e:
        print(f"加载数据失败，退出: {e}")
        sys.exit(1)

    _ensure_model_and_embeddings(verified_brands)
    if not parsed.no_loop or not parsed.input_file:
        print("请拖动或输入待匹配品类文件路径（每行一个品类），输入 q 退出。\n")

    pending_path: str | None = parsed.input_file.strip() if parsed.input_file else None
    if pending_path:
        pending_path = pending_path.strip()

    while True:
        file_path_str = pending_path if pending_path else input("文件路径: ").strip()
        pending_path = None

        if not file_path_str:
            continue
        if file_path_str.lower() in ("q", "quit", "exit"):
            print("退出。")
            break

        path = normalize_input_path(file_path_str)
        if not path or not path.exists():
            print(f"文件不存在: {path}\n")
            continue

        _process_one_file(path, config, rules, verified_brands)
        print(f"已处理: {path}\n")

        if parsed.no_loop and parsed.input_file:
            break


if __name__ == "__main__":
    main()
