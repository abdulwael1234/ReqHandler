"""Deterministic file output (SRS-101)."""

from pathlib import Path

from r210_generator.r210.file_writer import DeterministicFileWriter


class TestNormalize:
    """LLD-04 §8.1: LF endings and exactly one trailing newline."""

    def test_crlf_becomes_lf(self) -> None:
        """SRS-101: platform line endings must not reach the file."""
        assert DeterministicFileWriter.normalize("a\r\nb") == "a\nb\n"

    def test_lone_cr_becomes_lf(self) -> None:
        """SRS-101: old-Mac endings normalise too."""
        assert DeterministicFileWriter.normalize("a\rb") == "a\nb\n"

    def test_trailing_newline_added_once(self) -> None:
        """LLD-04 §8.1: a single trailing newline, never two."""
        assert DeterministicFileWriter.normalize("a") == "a\n"
        assert DeterministicFileWriter.normalize("a\n") == "a\n"


class TestWriteFile:
    """LLD-04 §8.2: UTF-8 without BOM, LF on disk, directories created."""

    def test_bytes_on_disk_use_lf(self, tmp_path: Path) -> None:
        """SRS-101: the file must be LF even on Windows.

        Asserted on bytes, not on read-back text: Python's text mode would
        translate the endings and hide exactly the bug this guards.
        """
        writer = DeterministicFileWriter(str(tmp_path))
        path = writer.write_file("out.txt", "first\nsecond")
        assert Path(path).read_bytes() == b"first\nsecond\n"

    def test_no_bom(self, tmp_path: Path) -> None:
        """LLD-04 §8.1: UTF-8 without BOM."""
        writer = DeterministicFileWriter(str(tmp_path))
        path = writer.write_file("out.txt", "plain")
        assert not Path(path).read_bytes().startswith(b"\xef\xbb\xbf")

    def test_non_ascii_round_trips(self, tmp_path: Path) -> None:
        """LLD-04 §8.1: UTF-8 encodes the characters the report uses."""
        writer = DeterministicFileWriter(str(tmp_path))
        path = writer.write_file("out.txt", "façade — ok")
        assert Path(path).read_text(encoding="utf-8") == "façade — ok\n"

    def test_nested_directories_created(self, tmp_path: Path) -> None:
        """LLD-04 §8.1: output directories are created before writing."""
        writer = DeterministicFileWriter(str(tmp_path))
        path = writer.write_file("a/b/c.txt", "deep")
        assert Path(path).exists()

    def test_two_writes_are_byte_identical(self, tmp_path: Path) -> None:
        """SRS-101: writing the same content twice yields the same bytes."""
        writer = DeterministicFileWriter(str(tmp_path))
        first = Path(writer.write_file("a.txt", "same")).read_bytes()
        second = Path(writer.write_file("b.txt", "same")).read_bytes()
        assert first == second
