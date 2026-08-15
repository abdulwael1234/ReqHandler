"""R210 template application — routes artifacts to their template functions.

Everything in this module is independent of what the templates *say*: dispatch,
the artifact sort order, child ordering, and rejected-child exclusion are all
structural rules that LLD-04 §6.2-§6.5 fixes. They are implemented and tested
here against an injected `TemplateSet`, so the pipeline is finished before the
work-specific template bodies exist (DEV-47).

See: LLD-04 §6.2 (Rendering Pipeline), §6.3 (Artifact Ordering),
     §6.4 (Child Ordering), §6.5 (Rejected Child Exclusion)
"""

from typing import TYPE_CHECKING, Any

from .templates import TemplateSet

if TYPE_CHECKING:  # pragma: no cover - import cycle guard
    from ..models import ArtifactTree, DatabaseSnapshot, GeneratorConfig, R210File

# LLD-04 §6.3. Primary sort key per artifact type; the secondary key is the
# sort *field*, which is `name` everywhere except PortConnections, and the
# tertiary key is `id`.
TYPE_SORT_KEYS: dict[tuple[str, str | None], int] = {
    ("TypeDefinitions", "simple_typedef"): 1,
    ("TypeDefinitions", "array"): 2,
    ("TypeDefinitions", "struct"): 3,
    ("TypeDefinitions", "enum"): 4,
    ("PortInterfaces", "sender_receiver"): 5,
    ("PortInterfaces", "client_server"): 6,
    ("PortPrototypes", None): 7,
    ("PortConnections", None): 8,
}


def type_sort_key(tree: "ArtifactTree") -> int:
    """The §6.3 primary sort key for one tree."""
    discriminator = getattr(tree.record, "kind", None) or getattr(
        tree.record, "interface_type", None
    )
    return TYPE_SORT_KEYS[(tree.table, discriminator)]


def sort_children(children: tuple[tuple[str, Any], ...]) -> list[tuple[str, Any]]:
    """Order child records by `(position, id)` (LLD-04 §6.4, SRS-108).

    A child table without a `position` column falls back to `id` alone rather
    than failing; only ordered children have one.
    """
    return sorted(children, key=lambda pair: (getattr(pair[1], "position", 0), pair[1].id))


def sort_trees(trees: list["ArtifactTree"]) -> list["ArtifactTree"]:
    """Order artifacts for output (LLD-04 §6.3, SRS-101).

    `label` may be empty — PortConnections.description is nullable — so the
    secondary key is lowercased defensively, per LLD-04 v1.2's H-06 fix.
    """
    return sorted(trees, key=lambda t: (type_sort_key(t), t.label.lower(), t.record.id))


class Renderer:
    """Apply templates to validated trees (LLD-04 §6.2)."""

    def __init__(self, config: "GeneratorConfig") -> None:
        self._config = config

    def _template_for(self, tree: "ArtifactTree", templates: TemplateSet) -> Any:
        """Pick the render callable for one artifact type."""
        if tree.table == "TypeDefinitions":
            return {
                "simple_typedef": templates.simple_typedef,
                "array": templates.array_type,
                "struct": templates.struct_type,
                "enum": templates.enum_type,
            }[tree.record.kind]
        if tree.table == "PortInterfaces":
            return (
                templates.sender_receiver
                if tree.record.interface_type == "sender_receiver"
                else templates.client_server
            )
        if tree.table == "PortPrototypes":
            return templates.port_prototype
        return templates.port_connection

    def render(
        self, trees: list["ArtifactTree"], snapshot: "DatabaseSnapshot"
    ) -> list["R210File"]:
        """Render every validated tree, in output order.

        Children reach a template already ordered and already stripped of
        rejected records, so no template repeats §6.4 or §6.5.
        """
        from ..models import R210File

        files: list[R210File] = []
        for tree in sort_trees(trees):
            template = self._template_for(tree, self._config.templates)
            content = template(
                tree.record,
                sort_children(tree.active_children),
                snapshot,
                self._config,
            )
            path = self._config.naming.file_path(tree.table, tree.record, self._config)
            files.append(R210File(path=path, content=content))
        return files
