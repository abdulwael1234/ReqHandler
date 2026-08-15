"""Deterministic file output.

Byte-identical output for identical input is a hard requirement (SRS-101), and
the differences that break it are all incidental: platform line endings, a BOM,
a missing or doubled trailing newline. Centralising them in one writer is what
keeps every output path — the review report now, R210 files on the work
computer — free of them.

The module lives under `r210/` because LLD-04 §2 puts it there, but §8's rules
serve both outputs. It is delivered with Phase 4 rather than moved, so Phase 5
inherits it unchanged.

See: LLD-04 §8 (Deterministic File Output)
"""

import os


class DeterministicFileWriter:
    """Write files with strict determinism guarantees (LLD-04 §8.2)."""

    def __init__(self, output_dir: str) -> None:
        self._output_dir = output_dir

    @property
    def output_dir(self) -> str:
        return self._output_dir

    @staticmethod
    def normalize(content: str) -> str:
        """Apply LLD-04 §8.1's content rules: LF endings, one trailing newline.

        Exposed separately from `write_file` so a caller can compare rendered
        content without touching the filesystem.
        """
        content = content.replace("\r\n", "\n").replace("\r", "\n")
        if not content.endswith("\n"):
            content += "\n"
        return content

    def write_file(self, relative_path: str, content: str) -> str:
        """Write one file and return its absolute path.

        `newline=""` stops Python translating `\\n` to the platform ending on
        write; without it this produces CRLF on Windows and the same database
        yields different bytes on different machines.
        """
        full_path = os.path.join(self._output_dir, relative_path)
        parent = os.path.dirname(full_path)
        if parent:
            os.makedirs(parent, exist_ok=True)

        with open(full_path, "w", encoding="utf-8", newline="") as handle:
            handle.write(self.normalize(content))
        return os.path.abspath(full_path)
