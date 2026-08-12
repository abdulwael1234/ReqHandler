"""Tests that the created schema enforces the constraints specified in LLD-01 §3.

Requirement coverage: SRS-027, SRS-029, SRS-030, SRS-032, SRS-035, SRS-035a,
SRS-036, SRS-037, SRS-038a, SRS-038b, SRS-038c, SRS-040, SRS-041, SRS-043,
SRS-052, SRS-059, SRS-061, SRS-063, SRS-070, SRS-074, SRS-075, SRS-076.
"""

import sqlite3

import pytest


def _new_source_requirement(conn: sqlite3.Connection, key: str = "src-1") -> int:
    cur = conn.execute(
        "INSERT INTO SourceRequirements (unique_key, source_reference) VALUES (?, 'DOC-001')",
        (key,),
    )
    return cur.lastrowid


def _new_type(conn: sqlite3.Connection, key: str, kind: str = "simple_typedef") -> int:
    cur = conn.execute(
        "INSERT INTO TypeDefinitions (unique_key, name, kind) VALUES (?, ?, ?)",
        (key, f"T_{key}", kind),
    )
    return cur.lastrowid


def _new_interface(conn: sqlite3.Connection, key: str, interface_type: str) -> int:
    cur = conn.execute(
        "INSERT INTO PortInterfaces (unique_key, name, interface_type) VALUES (?, ?, ?)",
        (key, f"IF_{key}", interface_type),
    )
    return cur.lastrowid


def _new_prototype(conn: sqlite3.Connection, key: str, direction: str = "provider") -> int:
    cur = conn.execute(
        "INSERT INTO PortPrototypes (unique_key, name, direction, component_reference) "
        "VALUES (?, ?, ?, 'SWC_A')",
        (key, f"PP_{key}", direction),
    )
    return cur.lastrowid


def _new_connection(conn: sqlite3.Connection, key: str = "conn-1") -> int:
    cur = conn.execute("INSERT INTO PortConnections (unique_key) VALUES (?)", (key,))
    return cur.lastrowid


class TestUniqueKeys:
    """SRS-027: unique_key is constrained to be unique on every referable record."""

    @pytest.mark.parametrize(
        ("table", "columns", "values"),
        [
            ("SourceRequirements", "unique_key, source_reference", ("dup", "DOC-1")),
            ("TypeDefinitions", "unique_key, name, kind", ("dup", "T", "struct")),
            ("PortInterfaces", "unique_key, name, interface_type", ("dup", "I", "client_server")),
            ("PortConnections", "unique_key", ("dup",)),
        ],
    )
    def test_duplicate_unique_key_is_rejected(
        self, conn: sqlite3.Connection, table: str, columns: str, values: tuple
    ) -> None:
        placeholders = ", ".join("?" * len(values))
        sql = f"INSERT INTO {table} ({columns}) VALUES ({placeholders})"
        conn.execute(sql, values)

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(sql, values)


class TestStatusConstraints:
    """SRS-035 / SRS-035a: the five review states, defaulting to pending_review."""

    def test_rejects_status_outside_the_five_review_states(self, conn: sqlite3.Connection) -> None:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO SourceRequirements (unique_key, source_reference, status) "
                "VALUES ('s', 'DOC-1', 'almost_approved')"
            )

    @pytest.mark.parametrize(
        "status", ["pending_review", "approved", "rejected", "ambiguous", "out_of_scope"]
    )
    def test_accepts_each_of_the_five_review_states(
        self, conn: sqlite3.Connection, status: str
    ) -> None:
        conn.execute(
            "INSERT INTO SourceRequirements (unique_key, source_reference, status) "
            "VALUES (?, 'DOC-1', ?)",
            (status, status),
        )

        stored = conn.execute(
            "SELECT status FROM SourceRequirements WHERE unique_key = ?", (status,)
        ).fetchone()[0]
        assert stored == status

    def test_new_records_default_to_pending_review(self, conn: sqlite3.Connection) -> None:
        _new_type(conn, "t1", "struct")

        status = conn.execute(
            "SELECT status FROM TypeDefinitions WHERE unique_key = 't1'"
        ).fetchone()[0]
        assert status == "pending_review"

    def test_structural_subtype_tables_carry_no_status_column(
        self, conn: sqlite3.Connection
    ) -> None:
        """SRS-035a: SimpleTypeDefinitions/ArrayTypeDefinitions are not reviewable."""
        for table in ("SimpleTypeDefinitions", "ArrayTypeDefinitions"):
            columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
            assert "status" not in columns


class TestEnumeratedColumns:
    """CHECK constraints on the classification columns."""

    def test_type_definition_kind_is_restricted(self, conn: sqlite3.Connection) -> None:
        """SRS-043."""
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO TypeDefinitions (unique_key, name, kind) VALUES ('k', 'n', 'union')"
            )

    @pytest.mark.parametrize("kind", ["simple_typedef", "array", "struct", "enum"])
    def test_type_definition_accepts_each_supported_kind(
        self, conn: sqlite3.Connection, kind: str
    ) -> None:
        _new_type(conn, kind, kind)

    def test_interface_type_is_restricted(self, conn: sqlite3.Connection) -> None:
        """SRS-052."""
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO PortInterfaces (unique_key, name, interface_type) "
                "VALUES ('k', 'n', 'mode_switch')"
            )

    def test_port_prototype_direction_is_restricted(self, conn: sqlite3.Connection) -> None:
        """SRS-061."""
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO PortPrototypes (unique_key, name, direction, component_reference) "
                "VALUES ('k', 'n', 'bidirectional', 'SWC')"
            )

    def test_operation_argument_direction_is_restricted(self, conn: sqlite3.Connection) -> None:
        """SRS-059: input, output, input_output — the slash form is not stored."""
        interface_id = _new_interface(conn, "if-cs", "client_server")
        op = conn.execute(
            "INSERT INTO ClientServerOperations (unique_key, port_interface_id, name, position) "
            "VALUES ('op-1', ?, 'Op', 1)",
            (interface_id,),
        ).lastrowid
        type_id = _new_type(conn, "arg-type")

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO OperationArguments "
                "(unique_key, operation_id, name, type_definition_id, direction, position) "
                "VALUES ('a', ?, 'arg', ?, 'input/output', 1)",
                (op, type_id),
            )

    def test_port_prototype_function_relationship_type_is_restricted(
        self, conn: sqlite3.Connection
    ) -> None:
        """SRS-063."""
        prototype_id = _new_prototype(conn, "pp-1")

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO PortPrototypeFunctions "
                "(unique_key, port_prototype_id, function_name, relationship_type) "
                "VALUES ('f', ?, 'Rte_Read', 'server_call_point')",
                (prototype_id,),
            )

    def test_review_issue_type_is_restricted(self, conn: sqlite3.Connection) -> None:
        """SRS-075."""
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO ReviewIssues (unique_key, issue_type, message) "
                "VALUES ('i', 'confusing', 'msg')"
            )

    def test_review_issue_status_is_restricted(self, conn: sqlite3.Connection) -> None:
        """SRS-076: pending, resolved, rejected — not the five artifact states."""
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO ReviewIssues (unique_key, issue_type, message, status) "
                "VALUES ('i', 'ambiguous', 'msg', 'pending_review')"
            )

    def test_review_issue_defaults_to_pending(self, conn: sqlite3.Connection) -> None:
        """SRS-035b: initial review-issue status is pending."""
        conn.execute(
            "INSERT INTO ReviewIssues (unique_key, issue_type, message) "
            "VALUES ('i', 'ambiguous', 'msg')"
        )

        status = conn.execute(
            "SELECT status FROM ReviewIssues WHERE unique_key = 'i'"
        ).fetchone()[0]
        assert status == "pending"


class TestReviewIssueArtifactReference:
    """SRS-074: the typed polymorphic artifact reference."""

    def test_artifact_type_is_restricted(self, conn: sqlite3.Connection) -> None:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO ReviewIssues (unique_key, artifact_type, issue_type, message) "
                "VALUES ('i', 'software_component', 'ambiguous', 'msg')"
            )

    def test_artifact_unique_key_requires_artifact_type(self, conn: sqlite3.Connection) -> None:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO ReviewIssues (unique_key, artifact_unique_key, issue_type, message) "
                "VALUES ('i', 'some-uuid', 'ambiguous', 'msg')"
            )

    def test_both_reference_fields_may_be_null(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            "INSERT INTO ReviewIssues (unique_key, issue_type, message) "
            "VALUES ('i', 'unsupported', 'no artifact yet')"
        )

    def test_artifact_type_without_unique_key_is_allowed(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            "INSERT INTO ReviewIssues (unique_key, artifact_type, issue_type, message) "
            "VALUES ('i', 'port_interface', 'incomplete', 'no key yet')"
        )


class TestPositionConstraints:
    """SRS-037 / SRS-038b: position is >= 1 and unique within its parent."""

    def test_position_must_be_positive(self, conn: sqlite3.Connection) -> None:
        struct_id = _new_type(conn, "s1", "struct")
        element_type = _new_type(conn, "e1")

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO StructElements "
                "(unique_key, struct_type_id, name, element_type_id, position) "
                "VALUES ('se', ?, 'field', ?, 0)",
                (struct_id, element_type),
            )

    def test_position_is_unique_within_parent(self, conn: sqlite3.Connection) -> None:
        struct_id = _new_type(conn, "s1", "struct")
        element_type = _new_type(conn, "e1")
        conn.execute(
            "INSERT INTO StructElements "
            "(unique_key, struct_type_id, name, element_type_id, position) "
            "VALUES ('se1', ?, 'first', ?, 1)",
            (struct_id, element_type),
        )

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO StructElements "
                "(unique_key, struct_type_id, name, element_type_id, position) "
                "VALUES ('se2', ?, 'second', ?, 1)",
                (struct_id, element_type),
            )

    def test_same_position_is_allowed_under_different_parents(
        self, conn: sqlite3.Connection
    ) -> None:
        first = _new_type(conn, "s1", "struct")
        second = _new_type(conn, "s2", "struct")
        element_type = _new_type(conn, "e1")

        conn.execute(
            "INSERT INTO StructElements "
            "(unique_key, struct_type_id, name, element_type_id, position) "
            "VALUES ('se1', ?, 'field', ?, 1)",
            (first, element_type),
        )
        conn.execute(
            "INSERT INTO StructElements "
            "(unique_key, struct_type_id, name, element_type_id, position) "
            "VALUES ('se2', ?, 'field', ?, 1)",
            (second, element_type),
        )

    def test_array_size_must_be_positive(self, conn: sqlite3.Connection) -> None:
        """SRS-038b."""
        array_id = _new_type(conn, "a1", "array")
        element_type = _new_type(conn, "e1")

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO ArrayTypeDefinitions "
                "(unique_key, type_definition_id, element_type_id, array_size) "
                "VALUES ('at', ?, ?, 0)",
                (array_id, element_type),
            )


class TestChildNameUniqueness:
    """SRS-038c: element and enum-value names are unique within their parent."""

    def test_struct_element_names_are_unique_within_struct(self, conn: sqlite3.Connection) -> None:
        struct_id = _new_type(conn, "s1", "struct")
        element_type = _new_type(conn, "e1")
        conn.execute(
            "INSERT INTO StructElements "
            "(unique_key, struct_type_id, name, element_type_id, position) "
            "VALUES ('se1', ?, 'speed', ?, 1)",
            (struct_id, element_type),
        )

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO StructElements "
                "(unique_key, struct_type_id, name, element_type_id, position) "
                "VALUES ('se2', ?, 'speed', ?, 2)",
                (struct_id, element_type),
            )

    def test_enum_value_names_are_unique_within_enum(self, conn: sqlite3.Connection) -> None:
        enum_id = _new_type(conn, "en1", "enum")
        conn.execute(
            "INSERT INTO EnumValues (unique_key, enum_type_id, name, position) "
            "VALUES ('ev1', ?, 'IDLE', 1)",
            (enum_id,),
        )

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO EnumValues (unique_key, enum_type_id, name, position) "
                "VALUES ('ev2', ?, 'IDLE', 2)",
                (enum_id,),
            )


class TestSubtypeCardinality:
    """SRS-038a: at most one subtype detail row per TypeDefinitions parent."""

    def test_simple_type_detail_is_one_to_one(self, conn: sqlite3.Connection) -> None:
        type_id = _new_type(conn, "t1", "simple_typedef")
        conn.execute(
            "INSERT INTO SimpleTypeDefinitions (unique_key, type_definition_id, base_type) "
            "VALUES ('st1', ?, 'uint8')",
            (type_id,),
        )

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO SimpleTypeDefinitions (unique_key, type_definition_id, base_type) "
                "VALUES ('st2', ?, 'uint16')",
                (type_id,),
            )

    def test_array_type_detail_is_one_to_one(self, conn: sqlite3.Connection) -> None:
        type_id = _new_type(conn, "t1", "array")
        element_type = _new_type(conn, "e1")
        conn.execute(
            "INSERT INTO ArrayTypeDefinitions "
            "(unique_key, type_definition_id, element_type_id, array_size) "
            "VALUES ('at1', ?, ?, 8)",
            (type_id, element_type),
        )

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO ArrayTypeDefinitions "
                "(unique_key, type_definition_id, element_type_id, array_size) "
                "VALUES ('at2', ?, ?, 16)",
                (type_id, element_type),
            )


class TestPortConnectionMembership:
    """SRS-070: a port prototype appears at most once per connection."""

    def test_duplicate_prototype_within_connection_is_rejected(
        self, conn: sqlite3.Connection
    ) -> None:
        connection_id = _new_connection(conn)
        prototype_id = _new_prototype(conn, "pp1")
        conn.execute(
            "INSERT INTO PortConnectionMembers "
            "(unique_key, port_connection_id, port_prototype_id, position) VALUES ('m1', ?, ?, 1)",
            (connection_id, prototype_id),
        )

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO PortConnectionMembers "
                "(unique_key, port_connection_id, port_prototype_id, position) "
                "VALUES ('m2', ?, ?, 2)",
                (connection_id, prototype_id),
            )

    def test_same_prototype_may_join_different_connections(self, conn: sqlite3.Connection) -> None:
        first = _new_connection(conn, "c1")
        second = _new_connection(conn, "c2")
        prototype_id = _new_prototype(conn, "pp1")

        conn.execute(
            "INSERT INTO PortConnectionMembers "
            "(unique_key, port_connection_id, port_prototype_id, position) VALUES ('m1', ?, ?, 1)",
            (first, prototype_id),
        )
        conn.execute(
            "INSERT INTO PortConnectionMembers "
            "(unique_key, port_connection_id, port_prototype_id, position) VALUES ('m2', ?, ?, 1)",
            (second, prototype_id),
        )

    def test_connection_members_carry_no_direction_column(self, conn: sqlite3.Connection) -> None:
        """SRS-068: direction lives only on PortPrototypes."""
        for table in ("PortConnections", "PortConnectionMembers"):
            columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
            assert "direction" not in columns


class TestNullability:
    """SRS-030, SRS-036, SRS-040, SRS-041: optional relationships stored as NULL."""

    def test_source_text_may_be_null(self, conn: sqlite3.Connection) -> None:
        """SRS-040."""
        conn.execute(
            "INSERT INTO SourceRequirements (unique_key, source_reference, source_text) "
            "VALUES ('s', 'DOC-1', NULL)"
        )

        stored = conn.execute(
            "SELECT source_text FROM SourceRequirements WHERE unique_key = 's'"
        ).fetchone()[0]
        assert stored is None

    def test_source_requirement_id_may_be_null(self, conn: sqlite3.Connection) -> None:
        """SRS-041: NULL when the source is not known."""
        _new_type(conn, "t1", "struct")

        stored = conn.execute(
            "SELECT source_requirement_id FROM TypeDefinitions WHERE unique_key = 't1'"
        ).fetchone()[0]
        assert stored is None

    def test_port_prototype_interface_may_be_null_while_unresolved(
        self, conn: sqlite3.Connection
    ) -> None:
        """SRS-036."""
        _new_prototype(conn, "pp1")

        stored = conn.execute(
            "SELECT port_interface_id FROM PortPrototypes WHERE unique_key = 'pp1'"
        ).fetchone()[0]
        assert stored is None

    def test_struct_element_type_reference_may_be_null_while_unresolved(
        self, conn: sqlite3.Connection
    ) -> None:
        """SRS-036a: unresolved cross-artifact type references may be NULL."""
        struct_id = _new_type(conn, "s1", "struct")

        conn.execute(
            "INSERT INTO StructElements "
            "(unique_key, struct_type_id, name, element_type_id, position) "
            "VALUES ('se', ?, 'field', NULL, 1)",
            (struct_id,),
        )

        stored = conn.execute(
            "SELECT element_type_id FROM StructElements WHERE unique_key = 'se'"
        ).fetchone()[0]
        assert stored is None

    def test_other_cross_artifact_type_references_may_be_null(
        self, conn: sqlite3.Connection
    ) -> None:
        array_type_id = _new_type(conn, "array", "array")
        sender_receiver_id = _new_interface(conn, "sr", "sender_receiver")
        client_server_id = _new_interface(conn, "cs", "client_server")
        operation_id = conn.execute(
            "INSERT INTO ClientServerOperations "
            "(unique_key, port_interface_id, name, position) "
            "VALUES ('op', ?, 'Operation', 1)",
            (client_server_id,),
        ).lastrowid

        conn.execute(
            "INSERT INTO ArrayTypeDefinitions "
            "(unique_key, type_definition_id, element_type_id, array_size) "
            "VALUES ('array-detail', ?, NULL, 4)",
            (array_type_id,),
        )
        conn.execute(
            "INSERT INTO InterfaceDataElements "
            "(unique_key, port_interface_id, name, type_definition_id, position) "
            "VALUES ('data-element', ?, 'Value', NULL, 1)",
            (sender_receiver_id,),
        )
        conn.execute(
            "INSERT INTO OperationArguments "
            "(unique_key, operation_id, name, type_definition_id, direction, position) "
            "VALUES ('argument', ?, 'Value', NULL, 'input', 1)",
            (operation_id,),
        )

        assert conn.execute(
            "SELECT element_type_id FROM ArrayTypeDefinitions "
            "WHERE unique_key = 'array-detail'"
        ).fetchone()[0] is None
        assert conn.execute(
            "SELECT type_definition_id FROM InterfaceDataElements "
            "WHERE unique_key = 'data-element'"
        ).fetchone()[0] is None
        assert conn.execute(
            "SELECT type_definition_id FROM OperationArguments "
            "WHERE unique_key = 'argument'"
        ).fetchone()[0] is None


class TestReferentialIntegrity:
    """SRS-029 / SRS-032: relationships use foreign keys that are enforced."""

    def test_child_row_referencing_missing_parent_is_rejected(
        self, conn: sqlite3.Connection
    ) -> None:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO PortConnectionMembers "
                "(unique_key, port_connection_id, port_prototype_id, position) "
                "VALUES ('m', 4242, 4243, 1)"
            )

    def test_valid_source_requirement_reference_is_accepted(self, conn: sqlite3.Connection) -> None:
        source_id = _new_source_requirement(conn)

        conn.execute(
            "INSERT INTO TypeDefinitions (unique_key, name, kind, source_requirement_id) "
            "VALUES ('t', 'T', 'struct', ?)",
            (source_id,),
        )

        stored = conn.execute(
            "SELECT source_requirement_id FROM TypeDefinitions WHERE unique_key = 't'"
        ).fetchone()[0]
        assert stored == source_id
