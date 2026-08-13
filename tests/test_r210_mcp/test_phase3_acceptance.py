"""End-to-end acceptance tests for the Phase 3 MCP tool surface.

Independent acceptance suite, written against the specification rather than the
implementation. The eleven currently-failing cases are defects D-01 to D-03,
recorded in `docs/PHASE3_IMPLEMENTED_REQUIREMENTS.md` §11 and scheduled for
remediation in Phase 4 (`docs/PHASE4_SCOPE.md` §3.0).

Verifies: SRS-036a, SRS-069, SRS-070, SRS-072, SRS-074, SRS-084, SRS-122.

See: LLD-02 §7.2 (type definition update), §7.5 (port connection tools),
§7.6 (review issue tools)
"""

from typing import Any
from uuid import uuid4

import pytest

from r210_mcp.tools.context import ToolContext, build_context
from r210_mcp.tools.registry import (
    TOOL_HANDLERS,
    dispatch,
    get_children_for_display,
    query_by_table,
)


def _dispatch_success(
    ctx: ToolContext, tool_name: str, arguments: dict[str, Any]
) -> dict[str, Any]:
    response = dispatch(ctx, tool_name, arguments)
    assert "error" not in response, response
    return response["result"]


def _create_prototype(ctx: ToolContext, name: str, direction: str) -> str:
    result = _dispatch_success(
        ctx,
        "create_port_prototype",
        {
            "name": name,
            "direction": direction,
            "component_reference": "ECU_Main",
        },
    )
    return str(result["unique_key"])


def _create_complete_connection(ctx: ToolContext) -> tuple[str, str, str]:
    provider_key = _create_prototype(ctx, "ProvidedSpeed", "provider")
    requester_key = _create_prototype(ctx, "RequiredSpeed", "requester")
    result = _dispatch_success(
        ctx,
        "create_port_connection",
        {
            "description": "Speed signal",
            "members": [
                {"port_prototype_key": provider_key, "position": 1},
                {"port_prototype_key": requester_key, "position": 2},
            ],
        },
    )
    return str(result["unique_key"]), provider_key, requester_key


def _query_issue(ctx: ToolContext, artifact_key: str) -> dict[str, Any]:
    result = _dispatch_success(
        ctx,
        "query_review_issues",
        {"artifact_unique_key": artifact_key},
    )
    assert result["count"] == 1
    return result["records"][0]


class TestPortConnectionAcceptance:
    def test_complete_connection_is_created_with_all_members_atomically(
        self, initialized_db: str
    ) -> None:
        """SRS-069, SRS-072, SRS-122 — create a complete connection atomically."""
        ctx = build_context(initialized_db, "review")
        connection_key, provider_key, requester_key = _create_complete_connection(ctx)

        connections = query_by_table(
            ctx, "PortConnections", {"unique_key": connection_key}
        )
        assert len(connections) == 1

        children = get_children_for_display(ctx, "PortConnections", connections[0]["id"])
        assert [child["record"]["position"] for child in children] == [1, 2]
        assert {
            child["record"]["port_prototype_id"] for child in children
        } == {
            prototype["id"]
            for prototype in query_by_table(ctx, "PortPrototypes")
            if prototype["unique_key"] in {provider_key, requester_key}
        }

    @pytest.mark.parametrize(
        ("members", "reason_fragment"),
        [
            ([], "must not be empty"),
            (
                [{"port_prototype_key": "provider", "position": 1}],
                "requester",
            ),
        ],
    )
    def test_invalid_connection_is_rejected_without_persisting_its_parent(
        self,
        initialized_db: str,
        members: list[dict[str, Any]],
        reason_fragment: str,
    ) -> None:
        """SRS-072, SRS-122 — invalid partial connections never persist."""
        ctx = build_context(initialized_db, "review")
        if members:
            members[0]["port_prototype_key"] = _create_prototype(ctx, "OnlyProvider", "provider")

        response = dispatch(ctx, "create_port_connection", {"members": members})

        assert response["error"]["field"] == "members"
        assert reason_fragment in response["error"]["reason"]
        assert query_by_table(ctx, "PortConnections") == []

    def test_duplicate_member_is_rejected_without_persisting_the_connection(
        self, initialized_db: str
    ) -> None:
        """SRS-070, SRS-122 — one prototype cannot appear twice in a connection."""
        ctx = build_context(initialized_db, "review")
        provider_key = _create_prototype(ctx, "Provider", "provider")

        response = dispatch(
            ctx,
            "create_port_connection",
            {
                "members": [
                    {"port_prototype_key": provider_key, "position": 1},
                    {"port_prototype_key": provider_key, "position": 2},
                ]
            },
        )

        assert response["error"]["field"] == "members"
        assert "duplicate" in response["error"]["reason"].lower()
        assert query_by_table(ctx, "PortConnections") == []

    def test_duplicate_position_is_rejected_without_persisting_the_connection(
        self, initialized_db: str
    ) -> None:
        """SRS-037, SRS-122 — member positions are unique within a connection."""
        ctx = build_context(initialized_db, "review")
        provider_key = _create_prototype(ctx, "Provider", "provider")
        requester_key = _create_prototype(ctx, "Requester", "requester")

        response = dispatch(
            ctx,
            "create_port_connection",
            {
                "members": [
                    {"port_prototype_key": provider_key, "position": 1},
                    {"port_prototype_key": requester_key, "position": 1},
                ]
            },
        )

        assert response["error"]["field"] == "members"
        assert "position" in response["error"]["reason"].lower()
        assert query_by_table(ctx, "PortConnections") == []

    def test_unknown_member_reference_rolls_back_the_whole_connection(
        self, initialized_db: str
    ) -> None:
        """SRS-069, SRS-084 — every member resolves inside the create transaction."""
        ctx = build_context(initialized_db, "review")
        provider_key = _create_prototype(ctx, "Provider", "provider")

        response = dispatch(
            ctx,
            "create_port_connection",
            {
                "members": [
                    {"port_prototype_key": provider_key, "position": 1},
                    {"port_prototype_key": str(uuid4()), "position": 2},
                ]
            },
        )

        assert "does not resolve" in response["error"]["reason"]
        assert query_by_table(ctx, "PortConnections") == []

    def test_adding_a_duplicate_member_rolls_back_only_that_mutation(
        self, initialized_db: str
    ) -> None:
        """SRS-070, SRS-122 — member create revalidates the complete connection."""
        ctx = build_context(initialized_db, "review")
        connection_key, provider_key, _ = _create_complete_connection(ctx)

        response = dispatch(
            ctx,
            "create_port_connection_member",
            {
                "port_connection_key": connection_key,
                "port_prototype_key": provider_key,
                "position": 3,
            },
        )

        assert "error" in response
        connection = query_by_table(ctx, "PortConnections", {"unique_key": connection_key})[0]
        children = get_children_for_display(ctx, "PortConnections", connection["id"])
        assert len(children) == 2


class TestArrayReferenceAcceptance:
    def test_unresolved_array_reference_can_be_resolved_and_its_issue_closed(
        self, initialized_db: str
    ) -> None:
        """SRS-036a — updating an array reference resolves its tracking issue."""
        ctx = build_context(initialized_db, "review")
        element_key = str(
            _dispatch_success(
                ctx,
                "create_type_definition",
                {"name": "Byte", "kind": "simple_typedef", "subtype": {"base_type": "uint8"}},
            )["unique_key"]
        )
        array_key = str(
            _dispatch_success(
                ctx,
                "create_type_definition",
                {"name": "Buffer", "kind": "array", "subtype": {"array_size": 8}},
            )["unique_key"]
        )
        assert _query_issue(ctx, array_key)["status"] == "pending"

        _dispatch_success(
            ctx,
            "update_type_definition",
            {"unique_key": array_key, "subtype": {"element_type_key": element_key}},
        )

        assert _query_issue(ctx, array_key)["status"] == "resolved"

    def test_clearing_an_array_reference_reopens_its_tracking_issue(
        self, initialized_db: str
    ) -> None:
        """SRS-036a — changing a resolved array reference to unresolved reopens its issue."""
        ctx = build_context(initialized_db, "review")
        element_key = str(
            _dispatch_success(
                ctx,
                "create_type_definition",
                {"name": "Byte", "kind": "simple_typedef", "subtype": {"base_type": "uint8"}},
            )["unique_key"]
        )
        array_key = str(
            _dispatch_success(
                ctx,
                "create_type_definition",
                {
                    "name": "Buffer",
                    "kind": "array",
                    "subtype": {"array_size": 8, "element_type_key": element_key},
                },
            )["unique_key"]
        )

        _dispatch_success(
            ctx,
            "update_type_definition",
            {"unique_key": array_key, "subtype": {"element_type_key": None}},
        )

        assert _query_issue(ctx, array_key)["status"] == "pending"

    def test_resolved_array_can_pass_the_approval_gate(self, initialized_db: str) -> None:
        """SRS-036a, SRS-082a — a resolved array reference no longer blocks approval."""
        ctx = build_context(initialized_db, "review")
        element_key = str(
            _dispatch_success(
                ctx,
                "create_type_definition",
                {"name": "Byte", "kind": "simple_typedef", "subtype": {"base_type": "uint8"}},
            )["unique_key"]
        )
        array_key = str(
            _dispatch_success(
                ctx,
                "create_type_definition",
                {"name": "Buffer", "kind": "array", "subtype": {"array_size": 8}},
            )["unique_key"]
        )
        _dispatch_success(
            ctx,
            "update_type_definition",
            {"unique_key": array_key, "subtype": {"element_type_key": element_key}},
        )

        result = _dispatch_success(
            ctx,
            "set_review_status",
            {"unique_key": array_key, "new_status": "approved", "caller": "review"},
        )

        assert result["status"] == "approved"


class TestReviewIssueAcceptance:
    def test_artifact_type_without_artifact_key_is_rejected(self, initialized_db: str) -> None:
        """SRS-074 — artifact type and unique key must be provided together."""
        ctx = build_context(initialized_db, "review")

        response = dispatch(
            ctx,
            "create_review_issue",
            {
                "issue_type": "incomplete",
                "message": "Missing detail",
                "artifact_type": "type_definition",
            },
        )

        assert response["error"]["field"] == "artifact_unique_key"

    def test_paired_artifact_reference_is_preserved(self, initialized_db: str) -> None:
        """SRS-074, SRS-088 — a complete typed artifact reference is queryable."""
        ctx = build_context(initialized_db, "review")
        artifact_key = str(
            _dispatch_success(
                ctx,
                "create_type_definition",
                {"name": "Mode", "kind": "enum", "subtype": {"values": []}},
            )["unique_key"]
        )

        _dispatch_success(
            ctx,
            "create_review_issue",
            {
                "issue_type": "incomplete",
                "message": "Needs values",
                "artifact_type": "type_definition",
                "artifact_unique_key": artifact_key,
            },
        )

        issue = _query_issue(ctx, artifact_key)
        assert issue["artifact_type"] == "type_definition"
        assert issue["artifact_unique_key"] == artifact_key


class TestDispatchAcceptance:
    @pytest.mark.parametrize("tool_name", sorted(TOOL_HANDLERS))
    def test_every_registered_tool_returns_a_structured_response_for_empty_input(
        self, initialized_db: str, tool_name: str
    ) -> None:
        """SRS-083, SRS-109 — invalid input never escapes the dispatch error boundary."""
        ctx = build_context(initialized_db, "review")

        response = dispatch(ctx, tool_name, {})

        assert set(response) in ({"result"}, {"error"})
        if "error" in response:
            assert response["error"]["operation"] == tool_name

    @pytest.mark.parametrize(
        "tool_name",
        sorted(name for name in TOOL_HANDLERS if name.startswith("update_")),
    )
    def test_every_update_rejects_a_malformed_unique_key_structurally(
        self, initialized_db: str, tool_name: str
    ) -> None:
        """SRS-027, SRS-083, SRS-109 — update keys are validated as UUIDs."""
        ctx = build_context(initialized_db, "review")

        response = dispatch(ctx, tool_name, {"unique_key": "not-a-uuid"})

        assert response["error"]["operation"] == tool_name
        assert response["error"]["field"] == "unique_key"
