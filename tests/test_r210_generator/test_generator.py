"""Generator orchestration end to end (SRS-090, SRS-101, SRS-104)."""

from pathlib import Path

import pytest

from r210_generator.generator import Generator
from r210_generator.models import GENERATION_MODES, GeneratorConfig

from .test_renderer import synthetic_config


class TestModes:
    """LLD-04 §3.2 / SRS-090: three generation modes."""

    def test_rejects_an_unknown_mode(self, populated_db: str, tmp_path: Path) -> None:
        """SRS-090: an unknown mode is a wiring fault, not caller input."""
        generator = Generator(populated_db, GeneratorConfig(output_dir=str(tmp_path)))
        with pytest.raises(ValueError, match="mode must be one of"):
            generator.generate("everything")

    def test_three_modes(self) -> None:
        """LLD-04 §3.2: exactly r210_only, report_only and both."""
        assert GENERATION_MODES == {"r210_only", "report_only", "both"}


class TestReportOnly:
    """SRS-104: the report is producible independently of R210 generation."""

    def test_writes_a_report(self, populated_db: str, tmp_path: Path) -> None:
        """SRS-104: report_only produces a file and no R210 output."""
        result = Generator(populated_db, GeneratorConfig(output_dir=str(tmp_path))).generate(
            "report_only"
        )
        assert result.report_file is not None
        assert Path(result.report_file).exists()
        assert result.r210_files == []

    def test_succeeds_on_an_empty_database(self, initialized_db: str, tmp_path: Path) -> None:
        """SRS-104: the report is generated even with no approved artifacts."""
        result = Generator(initialized_db, GeneratorConfig(output_dir=str(tmp_path))).generate(
            "report_only"
        )
        assert result.report_file is not None
        assert result.success

    def test_report_does_not_claim_approved_tree_was_generated(
        self, populated_db: str, tmp_path: Path
    ) -> None:
        """SRS-104(a): report_only leaves the generated-artifact section empty."""
        result = Generator(populated_db, GeneratorConfig(output_dir=str(tmp_path))).generate(
            "report_only"
        )
        assert result.report_file is not None
        content = Path(result.report_file).read_text(encoding="utf-8")
        generated_section = content[
            content.index("## (a) Approved and Generated") : content.index(
                "## (a2) Excluded - Unresolved References"
            )
        ]
        assert "No artifacts were approved and generated." in generated_section
        assert "SensorData" not in generated_section

    def test_report_only_needs_no_work_configuration(
        self, populated_db: str, tmp_path: Path
    ) -> None:
        """PHASE4_SCOPE §3.2: the report has no template precondition."""
        result = Generator(populated_db, GeneratorConfig(output_dir=str(tmp_path))).generate(
            "report_only"
        )
        assert result.unconfigured == []


class TestUnconfiguredR210Modes:
    """SRS-019(c), SRS-064: rendering needs values this copy does not have."""

    @pytest.mark.parametrize("mode", ["r210_only", "both"])
    def test_reports_unmet_entry_criteria(
        self, populated_db: str, tmp_path: Path, mode: str
    ) -> None:
        """PHASE5_SCOPE §2: the open criteria are named, not merely failed."""
        result = Generator(populated_db, GeneratorConfig(output_dir=str(tmp_path))).generate(mode)
        assert result.unconfigured == ["SRS-019(c)", "SRS-019(d)", "SRS-019", "SRS-064"]
        assert not result.success

    def test_reports_criteria_even_with_nothing_to_render(
        self, initialized_db: str, tmp_path: Path
    ) -> None:
        """DEV-47: an empty database must not look like a configured success."""
        result = Generator(initialized_db, GeneratorConfig(output_dir=str(tmp_path))).generate(
            "r210_only"
        )
        assert result.unconfigured != []

    def test_both_mode_still_writes_the_report(self, populated_db: str, tmp_path: Path) -> None:
        """SRS-104: missing templates must not cost the reviewer their report."""
        result = Generator(populated_db, GeneratorConfig(output_dir=str(tmp_path))).generate(
            "both"
        )
        assert result.report_file is not None
        assert Path(result.report_file).exists()


class TestConfiguredR210Modes:
    """SRS-103: with templates supplied, the pipeline produces files."""

    def test_renders_and_writes_files(self, populated_db: str, tmp_path: Path) -> None:
        """SRS-103: an approved tree becomes a written file."""
        result = Generator(populated_db, synthetic_config(str(tmp_path))).generate("r210_only")
        assert result.unconfigured == []
        assert len(result.r210_files) == 2
        for rendered in result.r210_files:
            assert (tmp_path / rendered.path).exists()

    def test_exported_artifacts_match_the_files(self, populated_db: str, tmp_path: Path) -> None:
        """SRS-090: the result reports what it actually exported.

        Regression: `exported_artifacts` is paired positionally with the
        rendered files, so it breaks if the two are not in the same order.
        """
        result = Generator(populated_db, synthetic_config(str(tmp_path))).generate("r210_only")
        for artifact, rendered in zip(result.exported_artifacts, result.r210_files, strict=True):
            assert artifact.path == rendered.path
            assert artifact.label in rendered.content

    def test_both_mode_produces_report_and_files(self, populated_db: str, tmp_path: Path) -> None:
        """SRS-090: `both` runs the whole pipeline."""
        result = Generator(populated_db, synthetic_config(str(tmp_path))).generate("both")
        assert result.r210_files and result.report_file is not None
        assert result.success

    def test_both_report_names_every_file_actually_generated(
        self, populated_db: str, tmp_path: Path
    ) -> None:
        """SRS-104(a): section (a) is an auditable manifest of R210 output."""
        result = Generator(populated_db, synthetic_config(str(tmp_path))).generate("both")
        assert result.report_file is not None
        report = Path(result.report_file).read_text(encoding="utf-8")
        generated_section = report[
            report.index("## (a) Approved and Generated") : report.index(
                "## (a2) Excluded - Unresolved References"
            )
        ]
        assert f"## (a) Approved and Generated - {len(result.r210_files)}" in generated_section
        for rendered in result.r210_files:
            assert f"file={rendered.path}" in generated_section


class TestDeterminism:
    """SRS-101: byte-identical output for identical database content."""

    def test_two_report_runs_are_byte_identical(
        self, populated_db: str, tmp_path: Path
    ) -> None:
        """SRS-101: compared as bytes, not strings.

        A string comparison would pass even if the two runs differed in
        encoding or line endings, which is exactly what SRS-101 forbids.
        """
        first_dir = tmp_path / "first"
        second_dir = tmp_path / "second"
        config_a = GeneratorConfig(output_dir=str(first_dir), generated_at="2026-08-15T00:00:00Z")
        config_b = GeneratorConfig(output_dir=str(second_dir), generated_at="2026-08-15T00:00:00Z")

        first = Generator(populated_db, config_a).generate("report_only")
        second = Generator(populated_db, config_b).generate("report_only")
        assert first.report_file and second.report_file
        assert Path(first.report_file).read_bytes() == Path(second.report_file).read_bytes()

    def test_two_r210_runs_are_byte_identical(self, populated_db: str, tmp_path: Path) -> None:
        """SRS-101: R210 output repeats exactly, with synthetic templates."""
        first_dir = tmp_path / "first"
        second_dir = tmp_path / "second"
        Generator(populated_db, synthetic_config(str(first_dir))).generate("r210_only")
        Generator(populated_db, synthetic_config(str(second_dir))).generate("r210_only")

        produced = sorted(p.relative_to(first_dir) for p in first_dir.rglob("*") if p.is_file())
        assert produced, "expected at least one rendered file"
        for relative in produced:
            assert (first_dir / relative).read_bytes() == (second_dir / relative).read_bytes()

    def test_report_bytes_use_lf(self, populated_db: str, tmp_path: Path) -> None:
        """SRS-101: the written report has LF endings even on Windows."""
        result = Generator(populated_db, GeneratorConfig(output_dir=str(tmp_path))).generate(
            "report_only"
        )
        assert result.report_file is not None
        assert b"\r\n" not in Path(result.report_file).read_bytes()

    def test_injected_timestamp_is_the_only_variable(
        self, populated_db: str, tmp_path: Path
    ) -> None:
        """DEV-46: two runs differ only where the caller made them differ."""
        one = Generator(
            populated_db,
            GeneratorConfig(output_dir=str(tmp_path / "a"), generated_at="2026-01-01T00:00:00Z"),
        ).generate("report_only")
        two = Generator(
            populated_db,
            GeneratorConfig(output_dir=str(tmp_path / "b"), generated_at="2026-12-31T00:00:00Z"),
        ).generate("report_only")
        assert one.report_file and two.report_file
        first_text = Path(one.report_file).read_text(encoding="utf-8")
        second_text = Path(two.report_file).read_text(encoding="utf-8")
        assert first_text != second_text
        assert first_text.replace("2026-01-01", "2026-12-31") == second_text
