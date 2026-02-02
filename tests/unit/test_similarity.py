"""core.utils.similarity 单元测试（纯函数，无模型依赖）。"""

from __future__ import annotations

import pytest

from core.utils.similarity import (
    DEFAULT_BGE_WEIGHT,
    jaro_winkler_similarity,
    weighted_combined,
)


def test_jaro_winkler_empty() -> None:
    assert jaro_winkler_similarity("", "abc") == 0.0
    assert jaro_winkler_similarity("a", "") == 0.0


def test_jaro_winkler_identical() -> None:
    assert jaro_winkler_similarity("奶茶", "奶茶") == 1.0


def test_jaro_winkler_similar() -> None:
    s = jaro_winkler_similarity("奶茶", "奶荼")
    assert 0 < s < 1.0


def test_weighted_combined() -> None:
    assert weighted_combined(1.0, 1.0, 0.5) == 1.0
    assert weighted_combined(0.0, 0.0, 0.5) == 0.0
    assert weighted_combined(1.0, 0.0, DEFAULT_BGE_WEIGHT) == pytest.approx(0.5)
    assert weighted_combined(0.0, 1.0, DEFAULT_BGE_WEIGHT) == pytest.approx(0.5)
