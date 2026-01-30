"""品类匹配：从 excel 目录解析原子品类关键词规则，输入门店后按规则匹配原子分类。"""

import sys
from pathlib import Path

from parser import CategoryRule, load_rules, match_store


def match_store_categories(store_text: str) -> list[CategoryRule]:
    """
    将门店名称/描述作为参数，加载规则并匹配，返回该门店对应的原子分类规则列表。
    """
    excel_dir = Path(__file__).resolve().parent / "excel"
    excel_path = excel_dir / "原子品类关键词.xlsx"
    _, rules = load_rules(excel_path)
    return match_store(store_text.strip(), rules)


def main() -> None:
    if len(sys.argv) > 1:
        store_text = " ".join(sys.argv[1:])
    else:
        store_text = input("请输入门店名称或描述: ").strip()

    if not store_text:
        print("未输入门店，退出。")
        return

    matched = match_store_categories(store_text)

    if not matched:
        print(f"未匹配到任何原子分类。门店: {store_text!r}")
        return

    print(f"门店: {store_text!r}")
    print(f"匹配到 {len(matched)} 个原子分类:")
    for r in matched:
        print(f"  - {r.level1_category} | {r.category_code} | {r.atomic_category}")


if __name__ == "__main__":
    main()
