"""R210 template for port connections.

**Not implemented here, by requirement** — SRS-019(c), withheld from this
repository copy by `docs/WORK_MACHINE_CONFIGURATION.md`.

To supply it on the work computer:

    render_port_connection(connection, members, prototypes, config) -> str

SRS-073 is binding on whatever body is written: a connection renders as one
global multi-port connection with every member inside a single block. The
generator does **not** expand a connection into pairwise provider/requester
combinations, and a template must not either.

`PortConnections` has no `name` column and is labelled by `description`
(LLD-01 §4.13).

See: LLD-04 §6.6 (Port Connection Rendering)
"""

from . import UNCONFIGURED_TEMPLATES

render_port_connection = UNCONFIGURED_TEMPLATES.port_connection
