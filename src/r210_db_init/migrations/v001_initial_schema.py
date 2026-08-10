"""V001: Initial schema — creates all 16 tables defined in LLD-01 §3.

Tables created:
- SourceRequirements, TypeDefinitions, SimpleTypeDefinitions,
  ArrayTypeDefinitions, StructElements, EnumValues, PortInterfaces,
  InterfaceDataElements, ClientServerOperations, OperationArguments,
  PortPrototypes, PortPrototypeFunctions, PortConnections,
  PortConnectionMembers, ReviewIssues
- (schema_version is created by the initializer itself)

See: LLD-05 §5.2 (Initial Schema Migration)
"""

from .base import Migration


class V001InitialSchema(Migration):
    """Migration: version 0 → 1. Creates all tables from LLD-01."""

    @property
    def description(self) -> str:
        return "Initial schema — all 16 tables per LLD-01 v1.0"

    def up(self, conn):
        # TODO: Implement all CREATE TABLE IF NOT EXISTS statements
        #       from LLD-01 §3 and LLD-05 §5.2
        pass
