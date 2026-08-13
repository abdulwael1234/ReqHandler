"""Development tests for the common validators (LLD-02 §6.1)."""

import pytest

from r210_mcp.errors import McpValidationError
from r210_mcp.validation.common import (
    normalize_name,
    validate_artifact_type,
    validate_choice,
    validate_not_empty,
    validate_position,
    validate_positive_int,
    validate_uuid_format,
)

VALID_UUID = "3f2504e0-4f89-41d3-9a0c-0305e82c3301"


class TestValidateNotEmpty:
    def test_accepts_a_non_empty_string(self) -> None:
        validate_not_empty("x", "name", operation="create_type_definition")

    @pytest.mark.parametrize("value", [None, "", "   "])
    def test_rejects_empty_values(self, value: object) -> None:
        """SRS-083 — invalid input names the field and the reason."""
        with pytest.raises(McpValidationError) as caught:
            validate_not_empty(value, "name", operation="create_type_definition")
        assert caught.value.error.field == "name"
        assert caught.value.error.operation == "create_type_definition"


class TestValidateUuidFormat:
    def test_accepts_a_uuid(self) -> None:
        validate_uuid_format(VALID_UUID, "unique_key", operation="update_source_requirement")

    @pytest.mark.parametrize("value", ["not-a-uuid", "", None, 42])
    def test_rejects_a_non_uuid(self, value: object) -> None:
        """SRS-027, SRS-083 — keys are UUIDs and malformed keys are rejected."""
        with pytest.raises(McpValidationError):
            validate_uuid_format(value, "unique_key", operation="update_source_requirement")


class TestValidateChoice:
    def test_accepts_a_permitted_value(self) -> None:
        validate_choice("struct", frozenset({"struct", "enum"}), "kind", operation="t")

    def test_rejects_and_lists_the_permitted_values(self) -> None:
        """SRS-083 — the reason tells the caller what was permitted."""
        with pytest.raises(McpValidationError) as caught:
            validate_choice("bogus", frozenset({"struct", "enum"}), "kind", operation="t")
        assert "enum" in caught.value.error.reason
        assert "struct" in caught.value.error.reason


class TestValidatePosition:
    @pytest.mark.parametrize("value", [1, 2, 100])
    def test_accepts_a_positive_integer(self, value: int) -> None:
        validate_position(value, "position", operation="create_enum_value")

    @pytest.mark.parametrize("value", [0, -1, "1", 1.5, None, True])
    def test_rejects_anything_else(self, value: object) -> None:
        """SRS-038b — position is an integer >= 1. bool is not an int here."""
        with pytest.raises(McpValidationError):
            validate_position(value, "position", operation="create_enum_value")


class TestValidatePositiveInt:
    def test_accepts_one(self) -> None:
        validate_positive_int(1, "array_size", operation="create_type_definition")

    @pytest.mark.parametrize("value", [0, -3, None, "2"])
    def test_rejects_anything_else(self, value: object) -> None:
        """SRS-038b — array_size is an integer >= 1."""
        with pytest.raises(McpValidationError):
            validate_positive_int(value, "array_size", operation="create_type_definition")


class TestValidateArtifactType:
    def test_accepts_none(self) -> None:
        validate_artifact_type(None, "artifact_type", operation="create_review_issue")

    def test_accepts_each_permitted_type(self) -> None:
        """SRS-074 — the eleven typed artifact references."""
        for value in ["type_definition", "enum_value", "port_connection_member"]:
            validate_artifact_type(value, "artifact_type", operation="create_review_issue")

    def test_rejects_an_unknown_type(self) -> None:
        with pytest.raises(McpValidationError):
            validate_artifact_type("widget", "artifact_type", operation="create_review_issue")


class TestNormalizeName:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("  Speed  ", "speed"),
            ("Vehicle   Speed", "vehicle speed"),
            ("VEHICLE\tSPEED", "vehicle speed"),
            ("Vehicle\n Speed", "vehicle speed"),
            ("speed", "speed"),
        ],
    )
    def test_trims_collapses_and_lowercases(self, raw: str, expected: str) -> None:
        """SRS-034 — trim, collapse internal whitespace, compare case-insensitively."""
        assert normalize_name(raw) == expected
