"""
main 入口流程单元测试：对 init_config、load_data、run_matching、save_output 做 mock 调用验证。

不依赖真实规则文件、模型或 MCP，仅验证流程函数可被单独调用且行为符合预期。
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from main import (
    RunConfig,
    init_config,
    load_data,
    run_matching,
    save_output,
    _parse_args,
)


class TestRunConfig:
    """RunConfig 数据类与路径属性。"""

    def test_rules_path_and_verified_path(self) -> None:
        excel = Path("/tmp/excel")
        config = RunConfig(excel_dir=excel, output_dir=Path("/out"), log_dir=Path("/log"))
        assert config.rules_path == excel / "原子品类关键词.xlsx"
        assert config.verified_path == excel / "校验过的品牌对应原子品类.xlsx"

    def test_custom_filenames(self) -> None:
        excel = Path("/tmp/excel")
        config = RunConfig(
            excel_dir=excel,
            output_dir=Path("/out"),
            log_dir=Path("/log"),
            rules_filename="rules.xlsx",
            verified_filename="brands.xlsx",
        )
        assert config.rules_path == excel / "rules.xlsx"
        assert config.verified_path == excel / "brands.xlsx"


class TestParseArgs:
    """命令行解析。"""

    def test_no_args(self) -> None:
        p = _parse_args([])
        assert p.input_file is None
        assert p.no_loop is False

    def test_input_file_only(self) -> None:
        p = _parse_args(["foo.txt"])
        assert p.input_file == "foo.txt"
        assert p.no_loop is False

    def test_input_file_and_no_loop(self) -> None:
        p = _parse_args(["foo.txt", "--no-loop"])
        assert p.input_file == "foo.txt"
        assert p.no_loop is True


class TestInitConfig:
    """init_config：依赖 load_app_config，通过 mock 避免加载真实配置。"""

    @patch("main.load_app_config")
    def test_returns_run_config_with_injected_dirs(self, mock_load_app: MagicMock) -> None:
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            excel = base / "excel"
            out = base / "out"
            log = base / "log"
            excel.mkdir()
            out.mkdir()
            log.mkdir()

            config = init_config(excel_dir=excel, output_dir=out, log_dir=log)

            assert config.excel_dir == excel
            assert config.output_dir == out
            assert config.log_dir == log
            mock_load_app.assert_called_once()


class TestLoadData:
    """load_data：依赖 load_rules、load_verified_brands，通过 mock 返回样例数据。"""

    def test_rules_file_missing_raises(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            excel = Path(d)
            (excel / "校验过的品牌对应原子品类.xlsx").touch()
            config = RunConfig(excel_dir=excel, output_dir=Path(d), log_dir=Path(d))
            assert not config.rules_path.exists()

            with pytest.raises(FileNotFoundError, match="规则文件不存在"):
                load_data(config)

    @patch("main.load_verified_brands")
    @patch("main.load_rules")
    def test_returns_rules_and_brands(
        self,
        mock_load_rules: MagicMock,
        mock_load_brands: MagicMock,
    ) -> None:
        from core.models import CategoryRule, RuleSheetMeta, VerifiedBrand

        meta = RuleSheetMeta(logic_descriptions=[], field_descriptions=[])
        rules = [CategoryRule(atomic_category="奶茶")]
        brands = [VerifiedBrand(brand_name="A", atomic_category="奶茶")]
        mock_load_rules.return_value = (meta, rules)
        mock_load_brands.return_value = brands

        with tempfile.TemporaryDirectory() as d:
            excel = Path(d)
            (excel / "原子品类关键词.xlsx").touch()
            (excel / "校验过的品牌对应原子品类.xlsx").touch()
            config = RunConfig(excel_dir=excel, output_dir=Path(d), log_dir=Path(d))

            r, b = load_data(config)

        assert len(r) == 1
        assert r[0].atomic_category == "奶茶"
        assert len(b) == 1
        assert b[0].brand_name == "A"


class TestRunMatching:
    """run_matching：依赖 run_batch_match，通过 mock 返回假结果。"""

    @patch("main.run_batch_match")
    def test_returns_result_rows(self, mock_batch: MagicMock) -> None:
        from core.models import CategoryRule, VerifiedBrand

        mock_batch.return_value = [
            ("品类A", "一级", "code1", "原子A", "规则", "", ""),
        ]
        rules: list[CategoryRule] = []
        brands: list[VerifiedBrand] = []

        rows = run_matching(["品类A"], rules, brands)

        assert len(rows) == 1
        assert rows[0][0] == "品类A"
        assert rows[0][4] == "规则"
        mock_batch.assert_called_once_with(["品类A"], rules, brands)

    @patch("main.run_batch_match")
    def test_empty_categories_returns_empty(self, mock_batch: MagicMock) -> None:
        mock_batch.return_value = []
        rows = run_matching([], [], [])
        assert rows == []
        mock_batch.assert_not_called()


class TestSaveOutput:
    """save_output：依赖 write_result_excel，使用临时目录。"""

    @patch("main.write_result_excel")
    def test_returns_output_path_and_calls_write(
        self,
        mock_write: MagicMock,
    ) -> None:
        result_rows: list[tuple[str, str, str, str, str, str, str]] = [
            ("a", "b", "c", "d", "规则", "e", "f"),
        ]
        with tempfile.TemporaryDirectory() as d:
            out_dir = Path(d)
            path = save_output(result_rows, out_dir, source_stem="test")
            assert path.parent == out_dir
            assert path.suffix == ".xlsx"
            assert "test" in path.name
            mock_write.assert_called_once()
            assert mock_write.call_args[0][1] == path
