"""R210 templates for port interfaces (sender-receiver, client-server).

**Not implemented here, by requirement** — SRS-019(c), withheld from this
repository copy by `docs/WORK_MACHINE_CONFIGURATION.md`.

To supply them on the work computer:

    render_sender_receiver(interface, data_elements, type_definitions, config) -> str
    render_client_server(interface, operations, arguments_by_operation,
                         type_definitions, config) -> str

Children arrive ordered by `(position, id)` with rejected ones removed
(LLD-04 §6.4, §6.5).

See: LLD-04 §6.1 (Template Architecture)
"""

from . import UNCONFIGURED_TEMPLATES

render_sender_receiver = UNCONFIGURED_TEMPLATES.sender_receiver
render_client_server = UNCONFIGURED_TEMPLATES.client_server
