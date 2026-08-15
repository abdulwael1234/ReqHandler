"""R210 template for port prototypes.

**Not implemented here, by requirement** — SRS-019(c), withheld from this
repository copy by `docs/WORK_MACHINE_CONFIGURATION.md`.

To supply it on the work computer:

    render_port_prototype(prototype, functions, interface, config) -> str

`functions` are `PortPrototypeFunctions` rows. Mapping each one to an AUTOSAR
element is `config.access_points`' job, not the template's: `trigger` maps to
`ExternalTriggeringPoint`, while `access_point` needs the SRS-064 selection
rule that chooses between `DataReadAccess`, `DataWriteAccess` and
`ServerCallPoint`.

See: LLD-04 §6.1 (Template Architecture), §6.7 (AUTOSAR Metamodel Mapping)
"""

from . import UNCONFIGURED_TEMPLATES

render_port_prototype = UNCONFIGURED_TEMPLATES.port_prototype
