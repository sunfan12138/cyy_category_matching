"""core.matching 单元测试（规则匹配逻辑，不依赖 embedding 模型）。"""

from __future__ import annotations

import pytest

from core.models import CategoryRule, VerifiedBrand
from core.matching import match_rule, match_store


def test_match_rule_empty_text() -> None:
    r = CategoryRule(keyword_group_1=["奶茶"], keyword_group_5=[], must_not_contain=[])
    assert match_rule("", r) is False


def test_match_rule_must_not_contain() -> None:
    r = CategoryRule(must_not_contain=["咖啡"], keyword_group_1=["奶茶"], keyword_group_5=[])
    assert match_rule("奶茶店", r) is True
    assert match_rule("咖啡奶茶", r) is False


def test_match_rule_keyword_group_1() -> None:
    r = CategoryRule(
        keyword_group_1=["奶茶", "茶饮"],
        keyword_group_2=[],
        keyword_group_3=[],
        keyword_group_4=[],
        keyword_group_5=[],
        must_not_contain=[],
    )
    assert match_rule("奶茶茶饮", r) is True
    assert match_rule("奶茶", r) is False  # 需同时包含奶茶和茶饮


def test_match_store() -> None:
    r1 = CategoryRule(atomic_category="A", keyword_group_1=["a"], keyword_group_5=[], must_not_contain=[])
    r2 = CategoryRule(atomic_category="B", keyword_group_1=["b"], keyword_group_5=[], must_not_contain=[])
    rules = [r1, r2]
    assert len(match_store("a", rules)) == 1
    assert match_store("a", rules)[0].atomic_category == "A"
    assert len(match_store("b", rules)) == 1
    assert len(match_store("x", rules)) == 0
