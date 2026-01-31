"""品类匹配入口：加载规则后循环接受文件路径，批量匹配并输出到 output 目录。"""

import sys
from datetime import datetime
from pathlib import Path

from app import (
    normalize_input_path,
    read_categories_from_file,
    run_batch_match,
    write_result_excel,
)
from paths import get_excel_dir, get_output_dir
from core import ensure_model_loaded, fill_brand_embeddings, load_rules, load_verified_brands


def main() -> None:
    excel_dir = get_excel_dir()
    output_dir = get_output_dir()
    rules_path = excel_dir / "原子品类关键词.xlsx"
    verified_path = excel_dir / "校验过的品牌对应原子品类.xlsx"

    ensure_model_loaded()
    # 解析规则与已校验品牌
    _, rules = load_rules(rules_path)
    verified_brands = load_verified_brands(verified_path)
    print(f"规则 {len(rules)} 条，已校验品牌 {len(verified_brands)} 条。")
    # 正在编码品牌名向量
    fill_brand_embeddings(verified_brands)
    print("请拖动或输入待匹配品类文件路径（每行一个品类），输入 q 退出。\n")

    pending_path = " ".join(sys.argv[1:]).strip() if len(sys.argv) > 1 else None

    while True:
        file_path_str = pending_path or input("文件路径: ").strip()
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

        try:
            categories = read_categories_from_file(path)
        except Exception as e:
            print(f"读取失败: {e}\n")
            continue
        if not categories:
            print("文件中没有有效品类行。\n")
            continue

        print(f"共 {len(categories)} 条品类，正在匹配...")
        result_rows = run_batch_match(categories, rules, verified_brands)
        unmatched = sum(1 for r in result_rows if r[4] == "未匹配")

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = output_dir / f"{path.stem}_匹配结果_{stamp}.xlsx"
        write_result_excel(result_rows, output_path)
        print(f"已写入: {output_path}")
        print(f"匹配 {len(result_rows) - unmatched} 条，未匹配 {unmatched} 条（已标红）。\n")


if __name__ == "__main__":
    main()
