"""Main generator orchestrator.

Implements the generation pipeline:
1. Load database snapshot (inside a read transaction for consistency)
2. Evaluate parent-child exportable trees (always — the report needs it too)
3. If R210 mode: validate FK completeness, render R210 files
4. If report mode: build review report
5. Write files deterministically
6. Return result

Step 2 runs before the mode check on purpose: LLD-04 §3.3 requires the report's
section (b) warnings even in `report_only` mode.

See: LLD-04 §3 (Generator Orchestrator — SRS-024, SRS-090, SRS-104)
"""

from typing import Any

from .loader import Loader
from .models import (
    GENERATION_MODES,
    ExportedArtifact,
    GenerationResult,
    GeneratorConfig,
)
from .r210.file_writer import DeterministicFileWriter
from .r210.renderer import Renderer, sort_trees
from .r210.templates import TemplateNotConfigured, unmet_criteria
from .report.builder import ReportBuilder
from .validator import evaluate_exportable_trees, validate_fk_completeness


class Generator:
    """Deterministic generator: R210 files and/or the review report."""

    def __init__(self, db_path: str, config: GeneratorConfig) -> None:
        self._db_path = db_path
        self._config = config
        self._loader = Loader()
        self._writer = DeterministicFileWriter(config.output_dir)
        self._report_builder = ReportBuilder()

    def generate(self, mode: str) -> GenerationResult:
        """Run the pipeline for one mode (SRS-090).

        `ValueError`, not a structured error: the mode is validated by the
        `trigger_generation` tool before it reaches here, so an invalid one is
        a wiring fault rather than caller input.
        """
        if mode not in GENERATION_MODES:
            raise ValueError(f"mode must be one of {sorted(GENERATION_MODES)}")

        snapshot = self._loader.load_all(self._db_path)
        result = GenerationResult()

        exportable = evaluate_exportable_trees(snapshot)
        result.r210_warnings = exportable.warnings
        result.exportable_trees = exportable.trees

        if mode in ("r210_only", "both"):
            validated = validate_fk_completeness(snapshot, exportable)
            result.r210_errors = validated.errors
            result.exportable_trees = validated.trees

            # Checked before rendering, not by catching a template raise: an
            # empty database calls no template at all, and reporting success
            # for an R210 mode that could never produce a file would be a lie
            # about the configuration rather than about the data (DEV-47).
            open_criteria = unmet_criteria(
                self._config.templates, self._config.naming, self._config.access_points
            )
            if open_criteria:
                result.unconfigured = list(open_criteria)
                return self._finish(snapshot, result, mode)

            # Sorted here, not just inside the renderer: `exported_artifacts`
            # is paired with the rendered files positionally, so both sides
            # must be in the same §6.3 output order.
            ordered = sort_trees(validated.trees)
            try:
                result.r210_files = Renderer(self._config).render(ordered, snapshot)
            except TemplateNotConfigured:  # pragma: no cover - guarded above
                result.unconfigured = list(
                    unmet_criteria(
                        self._config.templates, self._config.naming, self._config.access_points
                    )
                )
                result.r210_files = []
            else:
                result.exported_artifacts = [
                    ExportedArtifact(
                        table=tree.table,
                        unique_key=tree.unique_key,
                        label=tree.label,
                        path=rendered.path,
                    )
                    for tree, rendered in zip(ordered, result.r210_files, strict=True)
                ]

        return self._finish(snapshot, result, mode)

    def _finish(
        self, snapshot: Any, result: GenerationResult, mode: str
    ) -> GenerationResult:
        """Write whatever the pipeline produced, then the report.

        The report is written last so it can describe the R210 run in the same
        invocation, which is what `both` mode requires.
        """
        for rendered in result.r210_files:
            self._writer.write_file(rendered.path, rendered.content)

        if mode in ("report_only", "both"):
            content = self._report_builder.build(snapshot, result, self._config)
            result.report_file = self._writer.write_file(self._config.report_filename, content)

        return result
