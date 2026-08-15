"""Output formatting for terminal display.

ANSI colour is a constructor flag rather than an ambient decision, so the
formatter stays deterministic under test and the caller (`cli.py`) can gate it
on `sys.stdout.isatty()`. Escape sequences in a redirected file or a pipe would
corrupt it, so colour is emitted only to a terminal (DEV-44).

See: LLD-06 §6 (Display Formatting)
"""

from typing import Any

# LLD-06 §6.1, as ANSI SGR codes rather than colour names.
STATUS_COLORS: dict[str, str] = {
    "pending_review": "33",
    "approved": "32",
    "rejected": "31",
    "ambiguous": "35",
    "out_of_scope": "36",
    "pending": "33",
    "resolved": "32",
}

STATUS_GLYPH = "■"
_RESET = "\x1b[0m"
_RULE = "─" * 62


class DisplayFormatter:
    """Format tool responses for terminal output (LLD-06 §6)."""

    def __init__(self, color: bool = False) -> None:
        self._color = color

    def _status(self, status: Any) -> str:
        """Render a status with its glyph, coloured only when enabled."""
        if status is None:
            return ""
        text = f"{STATUS_GLYPH} {status}"
        code = STATUS_COLORS.get(str(status))
        if self._color and code is not None:
            return f"\x1b[{code}m{text}{_RESET}"
        return text

    @staticmethod
    def _label(record: dict[str, Any]) -> str:
        """A record's display name.

        `PortConnections` has no `name` column and uses `description` instead
        (LLD-01 §4.13), so the two are tried in order.
        """
        return str(record.get("name") or record.get("description") or "")

    def format_list(self, response: dict[str, Any], table: str) -> str:
        """One header line, a rule, then one row per record."""
        if "error" in response:
            return self.format_result(response)
        records: list[dict[str, Any]] = response["result"]["records"]
        lines = [f"{table} ({len(records)} records)", _RULE]
        if not records:
            return "\n".join(lines)
        lines.append(f"{'UUID':<38}{'Name':<24}Status")
        for record in records:
            key = str(record.get("unique_key", ""))
            lines.append(
                f"{key:<38}{self._label(record):<24}{self._status(record.get('status'))}"
            )
        return "\n".join(lines)

    def format_detail(self, response: dict[str, Any]) -> str:
        """A single record's fields, with its children nested underneath."""
        if "error" in response:
            return self.format_result(response)
        payload = response["result"]
        record: dict[str, Any] = payload.get("record", {})
        lines = [f"{payload.get('table', '')}  {payload.get('unique_key', '')}", _RULE]
        for name, value in record.items():
            if name == "id":
                continue
            rendered = self._status(value) if name == "status" else str(value)
            lines.append(f"  {name + ':':<24}{rendered}")

        children: list[dict[str, Any]] = payload.get("children", [])
        if children:
            lines.extend(["", f"  Children: {len(children)} records", f"  {_RULE}"])
            for index, child in enumerate(children, start=1):
                body = child["record"]
                lines.append(
                    f"  {index:<4}{child['table']:<26}{self._label(body):<24}"
                    f"{self._status(body.get('status'))}"
                )
        return "\n".join(lines)

    def format_stats(self, stats: dict[str, Any]) -> str:
        """Totals and status breakdown, one block per table."""
        lines = ["Database statistics", _RULE]
        for table in sorted(stats):
            entry = stats[table]
            lines.append(f"{table:<32}{entry['total']:>6}")
            for status in sorted(entry["by_status"]):
                lines.append(f"    {status:<28}{entry['by_status'][status]:>6}")
        return "\n".join(lines)

    def format_result(self, response: dict[str, Any]) -> str:
        """A command outcome: a structured error, or a success summary."""
        if "error" in response:
            error = response["error"]
            parts = [f"✗ {error['operation']}: {error['reason']}"]
            if error.get("field"):
                parts.append(f"  field: {error['field']}")
            if error.get("affected_key"):
                parts.append(f"  key:   {error['affected_key']}")
            return "\n".join(parts)

        result: dict[str, Any] = response.get("result", {})
        lines = [f"✓ {result.get('unique_key', '')}"]
        if result.get("table"):
            lines[0] += f"  ({result['table']})"
        if result.get("status") is not None:
            lines.append(f"  status: {self._status(result['status'])}")
        for key, label in (("demoted", "parent auto-demoted"), ("warnings", "warning")):
            for item in result.get(key, []):
                lines.append(f"  ⚠ {label}: {item}")
        return "\n".join(lines)
