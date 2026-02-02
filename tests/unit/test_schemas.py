"""models.schemas 单元测试：CategoryConfig、CategoryNode、MatchResult、RunConfigSchema。"""

from __future__ import annotations

from pathlib import Path

import pytest

from models.schemas import (
    CategoryConfig,
    CategoryNode,
    MatchResult,
    RunConfigSchema,
)


class TestCategoryConfig:
    def test_defaults(self) -> None:
        c = CategoryConfig()
        assert c.similarity_threshold == 0.0
        assert c.llm_fallback_threshold == 0.9
        assert c.rules_filename == "原子品类关键词.xlsx"

    def test_custom(self) -> None:
        c = CategoryConfig(similarity_threshold=0.97, rules_filename="rules.xlsx")
        assert c.similarity_threshold == 0.97
        assert c.rules_filename == "rules.xlsx"


class TestCategoryNode:
    def test_strip_strings(self) -> None:
        n = CategoryNode(id=" 1 ", name=" 餐饮 ", parent_id="")
        assert n.id == "1"
        assert n.name == "餐饮"
        assert n.level == 1


class TestMatchResult:
    def test_to_result_row(self) -> None:
        r = MatchResult(
            raw_text="奶茶店",
            level1_category="餐饮",
            category_code="101",
            atomic_category="奶茶",
            method="规则",
            similarity_detail="已使用关键词匹配到",
            llm_desc="",
        )
        row = r.to_result_row()
        assert len(row) == 7
        assert row[0] == "奶茶店"
        assert row[1] == "餐饮"
        assert row[4] == "规则"

    def test_from_result_row_roundtrip(self) -> None:
        row = ("输入", "一级", "编码", "原子", "相似度", "详情", "描述")
        r = MatchResult.from_result_row(row)
        assert r.raw_text == "输入"
        assert r.method == "相似度"
        assert r.to_result_row() == row


class TestRunConfigSchema:
    def test_rules_path_and_verified_path(self) -> None:
        config = RunConfigSchema(
            excel_dir=Path("/tmp/excel"),
            output_dir=Path("/out"),
            log_dir=Path("/log"),
        )
        assert config.rules_path == Path("/tmp/excel/原子品类关键词.xlsx")
        assert config.verified_path == Path("/tmp/excel/校验过的品牌对应原子品类.xlsx")
