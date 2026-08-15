"""The skill file must describe the tool surface that actually exists.

PHASE4_SCOPE §9 names this as the mitigation for its own risk: "The Gemini
skill drifts from the implemented tool surface — skill fails at runtime, long
after writing." A prose document cannot be type-checked, so this test does the
cross-check instead, against `TOOL_HANDLERS` and the SRS-015a allowlist.
"""

import pathlib
import re

import pytest

from r210_mcp.projection import GEMINI_ALLOWED_FIELDS
from r210_mcp.tools.registry import TOOL_HANDLERS

SKILL_PATH = pathlib.Path(__file__).parents[2] / "src" / "gemini_skill" / "r210_extraction.md"


@pytest.fixture(scope="module")
def skill_text() -> str:
    """The skill file as written."""
    return SKILL_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def referenced_tools(skill_text: str) -> set[str]:
    """Every backticked identifier that looks like a tool name."""
    candidates = set(re.findall(r"`([a-z_][a-z0-9_]*)`", skill_text))
    verbs = ("create_", "update_", "query_", "set_", "resolve_", "trigger_")
    return {name for name in candidates if name.startswith(verbs)}


class TestToolCoverage:
    """LLD-03 §10: the quick reference covers all 35 tools."""

    def test_every_tool_is_documented(self, referenced_tools: set[str]) -> None:
        """LLD-03 §10: a tool the skill never mentions cannot be used."""
        missing = set(TOOL_HANDLERS) - referenced_tools
        assert missing == set(), f"tools absent from the skill: {sorted(missing)}"

    def test_no_invented_tools(self, referenced_tools: set[str]) -> None:
        """SRS-082: a tool the skill invents fails at runtime, not at review."""
        invented = referenced_tools - set(TOOL_HANDLERS)
        assert invented == set(), f"skill names tools that do not exist: {sorted(invented)}"

    def test_thirty_five_tools(self) -> None:
        """LLD-02 §9: the surface is 35 tools; the skill's count must match."""
        assert len(TOOL_HANDLERS) == 35


class TestBehaviouralRules:
    """LLD-03 §4: every behavioural rule is present, with its SRS."""

    @pytest.mark.parametrize(
        "srs",
        [
            "SRS-015",   # §4.0 synthetic-mode gate
            "SRS-077",   # §4.1 no invention
            "SRS-078",   # §4.2 query-first
            "SRS-079",   # §4.3 stable UUID
            "SRS-080",   # §4.4 issue recording
            "SRS-082a",  # §4.5 no approval authority
            "SRS-082",   # §4.6 no direct database access
            "SRS-015a",  # §4.7 data minimization
        ],
    )
    def test_rule_is_present(self, skill_text: str, srs: str) -> None:
        """LLD-03 §4: each rule cites the requirement it implements."""
        assert srs in skill_text

    def test_never_instructs_approval(self, skill_text: str) -> None:
        """SRS-082a: the skill must bind caller to extraction, not review."""
        assert 'caller: "extraction"' in skill_text or 'caller="extraction"' in skill_text
        assert 'caller="review"' not in skill_text

    def test_states_the_create_response_shape(self, skill_text: str) -> None:
        """DEV-38: a skill that reads fields back from a create will not work."""
        assert "returns only the new `unique_key`" in skill_text

    def test_states_table_hint_is_optional(self, skill_text: str) -> None:
        """DEV-35: set_review_status resolves the table itself."""
        assert "`table_hint` is optional" in skill_text


class TestIssueTypes:
    """LLD-03 §7.1 / SRS-080: the five issue types are all documented."""

    @pytest.mark.parametrize(
        "issue_type",
        ["incomplete", "unresolved_reference", "ambiguous", "unsupported", "out_of_scope"],
    )
    def test_issue_type_present(self, skill_text: str, issue_type: str) -> None:
        """SRS-080: an undocumented issue type will never be produced."""
        assert issue_type in skill_text


class TestDataBoundary:
    """LLD-03 §11 / SRS-015a: the allowlist in prose matches the code."""

    def test_every_allowed_field_is_listed(self, skill_text: str) -> None:
        """SRS-015a §11.1: the skill lists exactly what it can receive."""
        boundary = skill_text[skill_text.index("### 11.1") : skill_text.index("### 11.2")]
        missing = {field for field in GEMINI_ALLOWED_FIELDS if f"`{field}`" not in boundary}
        assert missing == set(), f"allowlisted fields not documented: {sorted(missing)}"

    def test_withheld_fields_are_listed(self, skill_text: str) -> None:
        """SRS-015a §11.2: the withheld fields are named explicitly."""
        withheld = skill_text[skill_text.index("### 11.2") :]
        for field in ("source_text", "review_note", "resolution", "description"):
            assert f"`{field}`" in withheld

    def test_no_longer_a_stub(self, skill_text: str) -> None:
        """LLD-03: the file described itself as a stub until Phase 4."""
        assert "Status: Stub" not in skill_text
        assert "TODO" not in skill_text
