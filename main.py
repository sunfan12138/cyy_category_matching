"""品类匹配：从 excel 目录解析原子品类关键词规则，输入门店后按规则匹配原子分类。"""

import sys
from pathlib import Path

from parser import (
    CategoryRule,
    load_rules,
    load_verified_brands,
    match_by_similarity,
    match_store,
)

SIMILARITY_THRESHOLD = 0.97


def match_store_categories(
    store_text: str,
) -> tuple[list[CategoryRule], bool]:
    """
    将门店名称/描述作为参数，加载规则并匹配，返回 (该门店对应的原子分类规则列表, 是否由相似度匹配).
    若规则无结果，则用相似度与已校验品牌比对，相似度 >= 0.97 时归入该品牌原子品类。
    """
    excel_dir = Path(__file__).resolve().parent / "excel"
    rules_path = excel_dir / "原子品类关键词.xlsx"
    verified_path = excel_dir / "校验过的品牌对应原子品类.xlsx"

    _, rules = load_rules(rules_path)
    matched = match_store(store_text.strip(), rules)
    from_similarity = False

    if not matched and verified_path.exists():
        verified_brands = load_verified_brands(verified_path)
        matched = match_by_similarity(
            store_text, verified_brands, threshold=SIMILARITY_THRESHOLD
        )
        from_similarity = bool(matched)
    return matched, from_similarity


def main() -> None:
    if len(sys.argv) > 1:
        store_text = " ".join(sys.argv[1:])
    else:
        store_text = input("请输入门店名称或描述: ").strip()

    if not store_text:
        print("未输入门店，退出。")
        return

    matched, from_similarity = match_store_categories(store_text)

    if not matched:
        print(f"未匹配到任何原子分类。门店: {store_text!r}")
        return

    print(f"门店: {store_text!r}")
    if from_similarity:
        print("（通过相似度匹配已知品牌）")
    print(f"匹配到 {len(matched)} 个原子分类:")
    for r in matched:
        print(f"  - {r.level1_category} | {r.category_code} | {r.atomic_category}")


if __name__ == "__main__":
    main()
