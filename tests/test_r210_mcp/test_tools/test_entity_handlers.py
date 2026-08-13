"""Development tests for the interface, prototype, connection and issue tools.

See: LLD-02 §7.3-7.6, §10.3
"""

from typing import Any

import pytest

from r210_mcp.errors import McpValidationError
from r210_mcp.tools.context import ToolContext, build_context
from r210_mcp.tools.port_connections import (
    handle_create_port_connection,
    handle_create_port_connection_member,
    handle_update_port_connection_member,
)
from r210_mcp.tools.port_interfaces import (
    handle_create_client_server_operation,
    handle_create_interface_data_element,
    handle_create_operation_argument,
    handle_create_port_interface,
    handle_query_port_interfaces,
    handle_update_port_interface,
)
from r210_mcp.tools.port_prototypes import (
    handle_create_port_prototype,
    handle_create_port_prototype_function,
    handle_query_port_prototypes,
    handle_update_port_prototype,
)
from r210_mcp.tools.review_issues import (
    handle_create_review_issue,
    handle_query_review_issues,
    handle_update_review_issue,
)

PROTOTYPE = {"name": "SpeedPort", "direction": "provider", "component_reference": "ECU_Main"}
ISSUE = {"issue_type": "ambiguous", "message": "Unclear wording"}


def _key(response: dict[str, Any]) -> str:
    return str(response["result"]["unique_key"])


def _interface(ctx: ToolContext, name: str, interface_type: str) -> str:
    return _key(handle_create_port_interface(ctx, {"name": name, "interface_type": interface_type}))


def _prototype(ctx: ToolContext, name: str, direction: str) -> str:
    return _key(
        handle_create_port_prototype(
            ctx, {"name": name, "direction": direction, "component_reference": "ECU"}
        )
    )


class TestPortInterface:
    def test_creates_with_an_interface_type(self, initialized_db: str) -> None:
        """SRS-052 — interface_type is sender_receiver or client_server."""
        ctx = build_context(initialized_db, "review")
        response = handle_create_port_interface(
            ctx, {"name": "Speed", "interface_type": "sender_receiver"}
        )
        assert response["result"]["interface_type"] == "sender_receiver"

    def test_rejects_an_unknown_interface_type(self, initialized_db: str) -> None:
        ctx = build_context(initialized_db, "review")
        with pytest.raises(McpValidationError) as caught:
            handle_create_port_interface(ctx, {"name": "X", "interface_type": "broadcast"})
        assert caught.value.error.field == "interface_type"

    def test_query_filters_by_interface_type(self, initialized_db: str) -> None:
        ctx = build_context(initialized_db, "review")
        _interface(ctx, "A", "sender_receiver")
        _interface(ctx, "B", "client_server")
        response = handle_query_port_interfaces(ctx, {"interface_type": "client_server"})
        assert [record["name"] for record in response["result"]["records"]] == ["B"]

    def test_update_rejects_status(self, initialized_db: str) -> None:
        """SRS-091a — status only through set_review_status."""
        ctx = build_context(initialized_db, "review")
        key = _interface(ctx, "A", "sender_receiver")
        with pytest.raises(McpValidationError):
            handle_update_port_interface(ctx, {"unique_key": key, "status": "approved"})


class TestChildTypeMatching:
    def test_data_element_requires_sender_receiver(self, initialized_db: str) -> None:
        """SRS-055 — a data element cannot hang off a client_server interface."""
        ctx = build_context(initialized_db, "review")
        key = _interface(ctx, "Ops", "client_server")
        with pytest.raises(McpValidationError) as caught:
            handle_create_interface_data_element(
                ctx, {"port_interface_key": key, "name": "value", "position": 1}
            )
        assert caught.value.error.field == "port_interface_key"

    def test_operation_requires_client_server(self, initialized_db: str) -> None:
        """SRS-055 — an operation cannot hang off a sender_receiver interface."""
        ctx = build_context(initialized_db, "review")
        key = _interface(ctx, "Data", "sender_receiver")
        with pytest.raises(McpValidationError):
            handle_create_client_server_operation(
                ctx, {"port_interface_key": key, "name": "Get", "position": 1}
            )

    def test_valid_children_are_created(self, initialized_db: str) -> None:
        ctx = build_context(initialized_db, "review")
        sr_key = _interface(ctx, "Data", "sender_receiver")
        cs_key = _interface(ctx, "Ops", "client_server")
        element = handle_create_interface_data_element(
            ctx, {"port_interface_key": sr_key, "name": "value", "position": 1}
        )
        operation = handle_create_client_server_operation(
            ctx, {"port_interface_key": cs_key, "name": "Get", "position": 1}
        )
        assert element["result"]["name"] == "value"
        assert operation["result"]["name"] == "Get"


class TestOperationArgument:
    def _operation(self, ctx: ToolContext) -> str:
        iface = _interface(ctx, "Ops", "client_server")
        return _key(
            handle_create_client_server_operation(
                ctx, {"port_interface_key": iface, "name": "Get", "position": 1}
            )
        )

    def test_creates_with_a_direction(self, initialized_db: str) -> None:
        """SRS-059 — direction is input, output or input_output."""
        ctx = build_context(initialized_db, "review")
        response = handle_create_operation_argument(
            ctx,
            {
                "operation_key": self._operation(ctx),
                "name": "value",
                "direction": "input",
                "position": 1,
            },
        )
        assert response["result"]["direction"] == "input"

    def test_rejects_an_unknown_direction(self, initialized_db: str) -> None:
        ctx = build_context(initialized_db, "review")
        with pytest.raises(McpValidationError) as caught:
            handle_create_operation_argument(
                ctx,
                {
                    "operation_key": self._operation(ctx),
                    "name": "v",
                    "direction": "sideways",
                    "position": 1,
                },
            )
        assert caught.value.error.field == "direction"

    def test_unresolved_type_reference_creates_an_issue(self, initialized_db: str) -> None:
        """SRS-036a — an unresolved type_definition_id is recorded."""
        ctx = build_context(initialized_db, "review")
        key = _key(
            handle_create_operation_argument(
                ctx,
                {
                    "operation_key": self._operation(ctx),
                    "name": "value",
                    "direction": "input",
                    "position": 1,
                },
            )
        )
        with ctx.db.read_only() as conn:
            issues = ctx.dal.query_review_issues(conn, {"artifact_unique_key": key})
        assert issues[0].issue_type == "unresolved_reference"
        assert issues[0].artifact_type == "operation_argument"


class TestPortPrototype:
    def test_creates_with_a_direction(self, initialized_db: str) -> None:
        """SRS-061 — direction is provider or requester."""
        ctx = build_context(initialized_db, "review")
        response = handle_create_port_prototype(ctx, dict(PROTOTYPE))
        assert response["result"]["direction"] == "provider"
        assert response["result"]["component_reference"] == "ECU_Main"

    def test_rejects_an_unknown_direction(self, initialized_db: str) -> None:
        ctx = build_context(initialized_db, "review")
        with pytest.raises(McpValidationError) as caught:
            handle_create_port_prototype(ctx, dict(PROTOTYPE, direction="both"))
        assert caught.value.error.field == "direction"

    def test_requires_a_component_reference(self, initialized_db: str) -> None:
        """SRS-062 — component_reference is NOT NULL in the schema."""
        ctx = build_context(initialized_db, "review")
        with pytest.raises(McpValidationError) as caught:
            handle_create_port_prototype(ctx, {"name": "P", "direction": "provider"})
        assert caught.value.error.field == "component_reference"

    def test_port_interface_key_may_stay_unresolved(self, initialized_db: str) -> None:
        """SRS-036 — a missing optional relationship is stored as NULL."""
        ctx = build_context(initialized_db, "review")
        key = _key(handle_create_port_prototype(ctx, dict(PROTOTYPE)))
        with ctx.db.read_only() as conn:
            record = ctx.dal.get_port_prototype_by_key(conn, key)
            issues = ctx.dal.query_review_issues(conn, {"artifact_unique_key": key})
        assert record.port_interface_id is None
        assert issues == []

    def test_query_filters_by_direction(self, initialized_db: str) -> None:
        ctx = build_context(initialized_db, "review")
        handle_create_port_prototype(ctx, dict(PROTOTYPE))
        handle_create_port_prototype(ctx, dict(PROTOTYPE, name="Other", direction="requester"))
        response = handle_query_port_prototypes(ctx, {"direction": "requester"})
        assert [record["name"] for record in response["result"]["records"]] == ["Other"]

    def test_update_rejects_status(self, initialized_db: str) -> None:
        """SRS-091a."""
        ctx = build_context(initialized_db, "review")
        key = _key(handle_create_port_prototype(ctx, dict(PROTOTYPE)))
        with pytest.raises(McpValidationError):
            handle_update_port_prototype(ctx, {"unique_key": key, "status": "approved"})


class TestPortPrototypeFunction:
    def test_creates_with_a_relationship_type(self, initialized_db: str) -> None:
        """SRS-063 — relationship_type is access_point or trigger."""
        ctx = build_context(initialized_db, "review")
        parent = _key(handle_create_port_prototype(ctx, dict(PROTOTYPE)))
        response = handle_create_port_prototype_function(
            ctx,
            {
                "port_prototype_key": parent,
                "function_name": "ReadSpeed",
                "relationship_type": "access_point",
            },
        )
        assert response["result"]["relationship_type"] == "access_point"

    def test_rejects_an_unknown_relationship_type(self, initialized_db: str) -> None:
        ctx = build_context(initialized_db, "review")
        parent = _key(handle_create_port_prototype(ctx, dict(PROTOTYPE)))
        with pytest.raises(McpValidationError) as caught:
            handle_create_port_prototype_function(
                ctx,
                {
                    "port_prototype_key": parent,
                    "function_name": "ReadSpeed",
                    "relationship_type": "callback",
                },
            )
        assert caught.value.error.field == "relationship_type"

    def test_demotes_an_approved_parent(self, initialized_db: str) -> None:
        """SRS-035c — a new pending child invalidates the parent's approval."""
        ctx = build_context(initialized_db, "review")
        parent = _key(handle_create_port_prototype(ctx, dict(PROTOTYPE)))
        with ctx.db.transaction() as conn:
            record = ctx.dal.get_port_prototype_by_key(conn, parent)
            ctx.dal.update_status(conn, "PortPrototypes", record.id, "approved")
        response = handle_create_port_prototype_function(
            ctx,
            {
                "port_prototype_key": parent,
                "function_name": "ReadSpeed",
                "relationship_type": "trigger",
            },
        )
        assert response["result"]["demoted"] == [parent]


class TestPortConnection:
    """A connection is created whole (LLD-02 §7.5) — never empty then filled."""

    def _complete(self, ctx: ToolContext, suffix: str = "") -> tuple[str, str, str]:
        provider = _prototype(ctx, f"P{suffix}", "provider")
        requester = _prototype(ctx, f"R{suffix}", "requester")
        connection = _key(
            handle_create_port_connection(
                ctx,
                {
                    "description": "link",
                    "members": [
                        {"port_prototype_key": provider, "position": 1},
                        {"port_prototype_key": requester, "position": 2},
                    ],
                },
            )
        )
        return connection, provider, requester

    def test_creates_with_members_and_records_the_compatibility_issue(
        self, initialized_db: str
    ) -> None:
        """SRS-125 — compatibility is unverified, so an issue is created."""
        ctx = build_context(initialized_db, "review")
        connection, _provider, _requester = self._complete(ctx)
        with ctx.db.read_only() as conn:
            issues = ctx.dal.query_review_issues(conn, {"artifact_unique_key": connection})
            record = ctx.dal.get_port_connection_by_key(conn, connection)
            members = ctx.dal.get_children(
                conn, "PortConnectionMembers", "port_connection_id", record.id
            )
        assert len(issues) == 1
        assert issues[0].issue_type == "incomplete"
        assert [member.position for member in members] == [1, 2]

    def test_rejects_a_connection_without_members(self, initialized_db: str) -> None:
        """SRS-072 — an empty connection is invalid and must not persist."""
        ctx = build_context(initialized_db, "review")
        with pytest.raises(McpValidationError) as caught:
            handle_create_port_connection(ctx, {"members": []})
        assert caught.value.error.field == "members"
        with ctx.db.read_only() as conn:
            assert ctx.dal.query_port_connections(conn) == []

    def test_rejects_a_connection_without_a_requester(self, initialized_db: str) -> None:
        """SRS-072 — at least one provider and one requester."""
        ctx = build_context(initialized_db, "review")
        provider = _prototype(ctx, "OnlyP", "provider")
        with pytest.raises(McpValidationError) as caught:
            handle_create_port_connection(
                ctx, {"members": [{"port_prototype_key": provider, "position": 1}]}
            )
        assert "requester" in caught.value.error.reason
        with ctx.db.read_only() as conn:
            assert ctx.dal.query_port_connections(conn) == []

    def test_adds_a_further_member_to_a_valid_connection(self, initialized_db: str) -> None:
        """SRS-122 — a member that keeps the connection valid is accepted."""
        ctx = build_context(initialized_db, "review")
        connection, _provider, _requester = self._complete(ctx)
        second_requester = _prototype(ctx, "R2", "requester")
        response = handle_create_port_connection_member(
            ctx,
            {
                "port_connection_key": connection,
                "port_prototype_key": second_requester,
                "position": 3,
            },
        )
        assert response["result"]["position"] == 3

    def test_update_revalidates_the_whole_connection(self, initialized_db: str) -> None:
        """SRS-122 — a member change revalidates the connection transactionally."""
        ctx = build_context(initialized_db, "review")
        connection, _provider, requester = self._complete(ctx)
        second_provider = _prototype(ctx, "P2", "provider")

        # Repointing the only requester at a second provider leaves no
        # requester: the update must be rejected and rolled back.
        with ctx.db.read_only() as conn:
            member = ctx.dal.get_children(
                conn,
                "PortConnectionMembers",
                "port_connection_id",
                ctx.dal.get_port_connection_by_key(conn, connection).id,
            )[1]
        with pytest.raises(McpValidationError) as caught:
            handle_update_port_connection_member(
                ctx, {"unique_key": member.unique_key, "port_prototype_key": second_provider}
            )
        assert "requester" in caught.value.error.reason

        with ctx.db.read_only() as conn:
            unchanged = ctx.dal.get_port_connection_member_by_key(conn, member.unique_key)
            target = ctx.dal.get_port_prototype_by_key(conn, requester)
        assert unchanged.port_prototype_id == target.id

    def test_valid_member_update_is_applied(self, initialized_db: str) -> None:
        ctx = build_context(initialized_db, "review")
        connection, _provider, _requester = self._complete(ctx)
        other = _prototype(ctx, "R2", "requester")
        with ctx.db.read_only() as conn:
            member = ctx.dal.get_children(
                conn,
                "PortConnectionMembers",
                "port_connection_id",
                ctx.dal.get_port_connection_by_key(conn, connection).id,
            )[1]
        handle_update_port_connection_member(
            ctx, {"unique_key": member.unique_key, "port_prototype_key": other}
        )
        with ctx.db.read_only() as conn:
            updated = ctx.dal.get_port_connection_member_by_key(conn, member.unique_key)
            target = ctx.dal.get_port_prototype_by_key(conn, other)
        assert updated.port_prototype_id == target.id

    def test_member_update_rejects_status(self, initialized_db: str) -> None:
        """SRS-091a."""
        ctx = build_context(initialized_db, "review")
        connection, _provider, _requester = self._complete(ctx)
        with ctx.db.read_only() as conn:
            member = ctx.dal.get_children(
                conn,
                "PortConnectionMembers",
                "port_connection_id",
                ctx.dal.get_port_connection_by_key(conn, connection).id,
            )[0]
        with pytest.raises(McpValidationError) as caught:
            handle_update_port_connection_member(
                ctx, {"unique_key": member.unique_key, "status": "approved"}
            )
        assert caught.value.error.field == "status"


class TestReviewIssues:
    def test_creates_a_pending_issue(self, initialized_db: str) -> None:
        """SRS-088, SRS-035b — issues start pending."""
        ctx = build_context(initialized_db, "review")
        assert handle_create_review_issue(ctx, dict(ISSUE))["result"]["status"] == "pending"

    def test_rejects_an_unknown_issue_type(self, initialized_db: str) -> None:
        ctx = build_context(initialized_db, "review")
        with pytest.raises(McpValidationError) as caught:
            handle_create_review_issue(ctx, dict(ISSUE, issue_type="confusing"))
        assert caught.value.error.field == "issue_type"

    def test_rejects_an_unknown_artifact_type(self, initialized_db: str) -> None:
        """SRS-074 — artifact_type is one of eleven values."""
        ctx = build_context(initialized_db, "review")
        with pytest.raises(McpValidationError) as caught:
            handle_create_review_issue(
                ctx, dict(ISSUE, artifact_type="widget", artifact_unique_key="k")
            )
        assert caught.value.error.field == "artifact_type"

    def test_rejects_an_artifact_key_without_a_type(self, initialized_db: str) -> None:
        """SRS-074 — the schema CHECK requires the type alongside the key."""
        ctx = build_context(initialized_db, "review")
        with pytest.raises(McpValidationError) as caught:
            handle_create_review_issue(ctx, dict(ISSUE, artifact_unique_key="k"))
        assert caught.value.error.field == "artifact_type"

    def test_resolves_an_issue(self, initialized_db: str) -> None:
        """SRS-119 — issue status changes through update_review_issue."""
        ctx = build_context(initialized_db, "review")
        key = _key(handle_create_review_issue(ctx, dict(ISSUE)))
        response = handle_update_review_issue(
            ctx, {"unique_key": key, "status": "resolved", "resolution": "Clarified"}
        )
        assert response["result"]["status"] == "resolved"
        assert response["result"]["resolution"] == "Clarified"

    def test_rejects_a_forbidden_transition(self, initialized_db: str) -> None:
        """SRS-035b — resolved may only return to pending."""
        ctx = build_context(initialized_db, "review")
        key = _key(handle_create_review_issue(ctx, dict(ISSUE)))
        handle_update_review_issue(ctx, {"unique_key": key, "status": "resolved"})
        with pytest.raises(McpValidationError) as caught:
            handle_update_review_issue(ctx, {"unique_key": key, "status": "rejected"})
        assert caught.value.error.field == "status"

    def test_reopening_is_permitted(self, initialized_db: str) -> None:
        ctx = build_context(initialized_db, "review")
        key = _key(handle_create_review_issue(ctx, dict(ISSUE)))
        handle_update_review_issue(ctx, {"unique_key": key, "status": "resolved"})
        response = handle_update_review_issue(ctx, {"unique_key": key, "status": "pending"})
        assert response["result"]["status"] == "pending"

    def test_query_filters_by_issue_type(self, initialized_db: str) -> None:
        ctx = build_context(initialized_db, "review")
        handle_create_review_issue(ctx, dict(ISSUE))
        handle_create_review_issue(ctx, dict(ISSUE, issue_type="incomplete"))
        assert handle_query_review_issues(ctx, {"issue_type": "incomplete"})["result"]["count"] == 1
