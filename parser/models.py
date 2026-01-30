"""品类匹配相关数据模型。"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CategoryRule:
    """单条品类匹配规则。"""

    level1_category: str = ""  # 一级原子品类
    category_code: str | int = ""  # 品类编码
    atomic_category: str = ""  # 原子品类
    sequence_no: int = 0  # 序号
    # 关键词组1-4：单元格需同时包含以下关键词（可断开）
    keyword_group_1: list[str] = field(default_factory=list)
    keyword_group_2: list[str] = field(default_factory=list)
    keyword_group_3: list[str] = field(default_factory=list)
    keyword_group_4: list[str] = field(default_factory=list)
    # 关键词组5：单元格可任意包含其中一个关键词即可
    keyword_group_5: list[str] = field(default_factory=list)
    # 一定不包含（且）
    must_not_contain: list[str] = field(default_factory=list)


@dataclass
class RuleSheetMeta:
    """表头元数据：第1行判断逻辑、第2行字段解释。"""

    logic_descriptions: list[str] = field(default_factory=list)
    field_descriptions: list[str] = field(default_factory=list)


@dataclass
class VerifiedBrand:
    """已校验过的品牌及其对应原子品类（与「校验过的品牌对应原子品类.xlsx」列一致）。"""

    brand_code: str | int = ""  # 品牌编码
    brand_name: str = ""  # 品牌名称
    brand_keywords: str = ""  # 品牌关键词（，表示同时包含）
    atomic_category: str = ""  # 原子品类
