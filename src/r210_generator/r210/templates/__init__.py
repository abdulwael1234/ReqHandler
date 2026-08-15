"""R210 output templates and the policies that surround them.

**None of the work-specific content lives in this repository copy.** The exact
template bodies (SRS-019c), file and artifact naming conventions (SRS-019d),
AUTOSAR package paths (SRS-019) and the `access_point` selection rule (SRS-064)
are recorded in `docs/WORK_MACHINE_CONFIGURATION.md` as values to be supplied
on the work computer, and inventing them here would mean writing code that must
be thrown away.

So the templates are **injected, not imported**. `TemplateSet` carries the eight
render callables LLD-04 §6.1 and §6.6 specify; `GeneratorConfig` holds one.
The default `UNCONFIGURED_TEMPLATES` raises `TemplateNotConfigured` naming the
criterion it needs. That keeps the rendering pipeline — dispatch, ordering,
rejected-child exclusion, byte-determinism — real, testable and finished, while
the part that genuinely cannot be written stays a declared plug-point (DEV-47).

LLD-04 §11 states the intent this serves: "template implementations are
pluggable — the generator framework is ready for any template content."

On the work computer, Phase 5 is: write one module returning a populated
`TemplateSet`, `NamingPolicy` and `AccessPointPolicy`, and pass it to
`GeneratorConfig`. No framework code changes.

See: LLD-04 §6.1 (Template Architecture), §6.7 (AUTOSAR Metamodel Mapping)
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, NoReturn

# The Phase 5 entry criteria of docs/PHASE5_SCOPE.md §2, by the SRS that owns
# each. Reported verbatim when rendering is attempted without configuration, so
# an operator is told what is missing rather than that something "failed".
ENTRY_CRITERIA: dict[str, str] = {
    "SRS-019(c)": "R210 output templates installed and approved",
    "SRS-019(d)": "File and artifact naming conventions and output paths defined",
    "SRS-019": "AUTOSAR package paths and metamodel/version identifiers defined",
    "SRS-064": (
        "access_point selection rule documented - which input selects "
        "DataReadAccess, DataWriteAccess or ServerCallPoint"
    ),
}


class TemplateNotConfigured(Exception):
    """Raised when rendering needs a work-computer value that is absent.

    Carries the unmet criteria so the generator can report them rather than
    surfacing a bare failure.
    """

    def __init__(self, criteria: tuple[str, ...]) -> None:
        self.criteria = criteria
        detail = "; ".join(f"{key}: {ENTRY_CRITERIA[key]}" for key in criteria)
        super().__init__(
            f"R210 rendering is not configured. Unmet entry criteria - {detail}. "
            "See docs/WORK_MACHINE_CONFIGURATION.md and docs/PHASE5_SCOPE.md §2."
        )


def _unconfigured_template(*_args: Any, **_kwargs: Any) -> NoReturn:
    """Stand in for a template body that only the work computer can supply."""
    raise TemplateNotConfigured(("SRS-019(c)", "SRS-019"))


def _unconfigured_path(*_args: Any, **_kwargs: Any) -> NoReturn:
    """Stand in for the naming convention that decides an output path."""
    raise TemplateNotConfigured(("SRS-019(d)",))


def _unconfigured_access_point(*_args: Any, **_kwargs: Any) -> NoReturn:
    """Stand in for the SRS-064 access_point selection rule."""
    raise TemplateNotConfigured(("SRS-064",))


# One render callable per artifact type. Signatures follow LLD-04 §6.1 and §6.6;
# they are typed loosely because a work template may need any subset of the
# record, its children and the config.
Renderer = Callable[..., str]


@dataclass(frozen=True)
class TemplateSet:
    """The eight R210 render functions (LLD-04 §6.1, §6.6)."""

    simple_typedef: Renderer
    array_type: Renderer
    struct_type: Renderer
    enum_type: Renderer
    sender_receiver: Renderer
    client_server: Renderer
    port_prototype: Renderer
    port_connection: Renderer

    @property
    def configured(self) -> bool:
        """Whether any real template has been supplied."""
        return self.simple_typedef is not _unconfigured_template


@dataclass(frozen=True)
class NamingPolicy:
    """Output file naming and artifact naming (SRS-019d)."""

    # (table, record, config) -> path relative to the output directory.
    file_path: Callable[..., str]

    @property
    def configured(self) -> bool:
        return self.file_path is not _unconfigured_path


@dataclass(frozen=True)
class AccessPointPolicy:
    """The SRS-064 mapping from a port function to an AUTOSAR element.

    `trigger` already has a fixed answer in LLD-04 §6.7
    (`ExternalTriggeringPoint`); only `access_point` needs the work-computer
    selection rule, which is why the two are represented differently.
    """

    trigger_element: str = "ExternalTriggeringPoint"
    # (function_record, prototype_record, interface_record) -> element name.
    access_point_element: Callable[..., str] = _unconfigured_access_point

    @property
    def configured(self) -> bool:
        return self.access_point_element is not _unconfigured_access_point


UNCONFIGURED_TEMPLATES = TemplateSet(
    simple_typedef=_unconfigured_template,
    array_type=_unconfigured_template,
    struct_type=_unconfigured_template,
    enum_type=_unconfigured_template,
    sender_receiver=_unconfigured_template,
    client_server=_unconfigured_template,
    port_prototype=_unconfigured_template,
    port_connection=_unconfigured_template,
)

UNCONFIGURED_NAMING = NamingPolicy(file_path=_unconfigured_path)

UNCONFIGURED_ACCESS_POINTS = AccessPointPolicy()


def unmet_criteria(
    templates: TemplateSet, naming: NamingPolicy, access_points: AccessPointPolicy
) -> tuple[str, ...]:
    """Which Phase 5 entry criteria are still open, in document order."""
    unmet: list[str] = []
    if not templates.configured:
        unmet.extend(["SRS-019(c)", "SRS-019"])
    if not naming.configured:
        unmet.append("SRS-019(d)")
    if not access_points.configured:
        unmet.append("SRS-064")
    return tuple(sorted(set(unmet), key=list(ENTRY_CRITERIA).index))
