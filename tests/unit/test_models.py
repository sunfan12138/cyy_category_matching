"""core.models 单元测试。"""

from __future__ import annotations

import pytest

from domain.category import CategoryRule, RuleSheetMeta, VerifiedBrand


def test_category_rule_defaults() -> None:
    r = CategoryRule()
    assert r.level1_category == ""
    assert r.atomic_category == ""
    assert r.keyword_group_1 == []
    assert r.must_not_contain == []


def test_category_rule_with_values() -> None:
    r = CategoryRule(
        level1_category="餐饮",
        atomic_category="奶茶",
        keyword_group_1=["奶茶", "茶饮"],
    )
    assert r.level1_category == "餐饮"
    assert r.atomic_category == "奶茶"
    assert r.keyword_group_1 == ["奶茶", "茶饮"]


def test_verified_brand_defaults() -> None:
    vb = VerifiedBrand()
    assert vb.brand_name == ""
    assert vb.embedding is None


def test_rule_sheet_meta() -> None:
    meta = RuleSheetMeta(logic_descriptions=["a"], field_descriptions=["b"])
    assert meta.logic_descriptions == ["a"]
    assert meta.field_descriptions == ["b"]
