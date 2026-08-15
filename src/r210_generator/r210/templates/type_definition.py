"""R210 templates for type definitions (simple, array, struct, enum).

**Not implemented here, by requirement.** The template bodies are SRS-019(c)
values that `docs/WORK_MACHINE_CONFIGURATION.md` deliberately withholds from
this repository copy.

To supply them on the work computer, write four functions with these
signatures and pass them in a `TemplateSet` (see `templates/__init__.py`):

    render_simple_typedef(typedef, detail, config) -> str
    render_array_type(typedef, detail, element_type, config) -> str
    render_struct_type(typedef, elements, element_types, config) -> str
    render_enum_type(typedef, values, config) -> str

`elements` and `values` arrive already ordered by `(position, id)` and already
stripped of rejected children (LLD-04 §6.4, §6.5), so a template never repeats
that logic.

See: LLD-04 §6.1 (Template Architecture)
"""

from . import UNCONFIGURED_TEMPLATES

# Re-exported so the unconfigured behaviour is reachable by module path, the
# way LLD-04 §2 lays the package out.
render_simple_typedef = UNCONFIGURED_TEMPLATES.simple_typedef
render_array_type = UNCONFIGURED_TEMPLATES.array_type
render_struct_type = UNCONFIGURED_TEMPLATES.struct_type
render_enum_type = UNCONFIGURED_TEMPLATES.enum_type
