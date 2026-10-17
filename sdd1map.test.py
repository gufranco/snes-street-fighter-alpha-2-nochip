import importlib.util
import itertools
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, ClassVar, override

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hardware

sdd1 = hardware.load("sdd1")
dump = hardware.load("romimage").dump


ROOT = Path(__file__).resolve().parent


def load_module(name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, ROOT / f"{name}.py")
    assert spec is not None and spec.loader is not None, "no loader for that path"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sdd1map = load_module("sdd1map")

TAGGED = ROOT / "roms" / "sfa2-usa-vc-sound-restored.sfc"
RETAIL = ROOT / "roms" / "sfa2-usa-final.sfc"
EXPECTED_STREAMS = 2815
EXPECTED_GFX_BYTES = 4947202
FIRST_SOURCE = 0x7890


def tagged_blob(markers: list[tuple[int, int]], size: int = 8192) -> bytes:
    blob = bytearray(size)
    for position, target in markers:
        blob[position : position + 4] = sdd1map.MARKER
        blob[position + 4 : position + 8] = target.to_bytes(4, "little")
    return bytes(blob)


class MarkerTest(unittest.TestCase):
    def test_markers_are_reported_in_rom_order(self) -> None:
        blob = tagged_blob([(100, 0), (300, 64), (700, 192)])

        markers = sdd1map.find_markers(blob)

        self.assertEqual(markers, [(100, 0), (300, 64), (700, 192)])

    def test_a_blob_without_markers_yields_nothing(self) -> None:
        self.assertEqual(sdd1map.find_markers(bytes(4096)), [])


class BuildMapTest(unittest.TestCase):
    def test_lengths_come_from_the_gap_between_consecutive_targets(self) -> None:
        blob = tagged_blob([(100, 0), (300, 64), (700, 192)])

        entries = sdd1map.build_map(blob)

        self.assertEqual([e.length for e in entries[:2]], [64, 128])

    def test_sources_are_the_marker_positions(self) -> None:
        blob = tagged_blob([(100, 0), (300, 64)])

        entries = sdd1map.build_map(blob)

        self.assertEqual([e.source for e in entries], [100, 300])

    def test_the_final_length_is_unknown_without_a_declared_total(self) -> None:
        blob = tagged_blob([(100, 0), (300, 64)])

        entries = sdd1map.build_map(blob)

        self.assertIsNone(entries[-1].length)

    def test_a_declared_total_resolves_the_final_length(self) -> None:
        blob = tagged_blob([(100, 0), (300, 64)])

        entries = sdd1map.build_map(blob, gfx_size=200)

        self.assertEqual(entries[-1].length, 136)

    def test_targets_that_move_backwards_are_rejected(self) -> None:
        blob = tagged_blob([(100, 64), (300, 0)])

        with self.assertRaises(ValueError):
            sdd1map.build_map(blob)

    def test_a_total_below_the_last_target_is_rejected(self) -> None:
        blob = tagged_blob([(100, 0), (300, 64)])

        with self.assertRaises(ValueError):
            sdd1map.build_map(blob, gfx_size=32)


@unittest.skipUnless(
    TAGGED.exists() and RETAIL.exists(), "roms are not present"
)  # pragma: no cover
class RealMapTest(unittest.TestCase):
    entries: ClassVar[Any]
    retail: ClassVar[Any]
    tagged: ClassVar[Any]

    @classmethod
    @override
    def setUpClass(cls) -> None:
        cls.tagged = dump.read(TAGGED)
        cls.retail = dump.read(RETAIL)
        cls.entries = sdd1map.build_map(cls.tagged)

    def test_the_patched_rom_carries_one_marker_per_stream(self) -> None:
        self.assertEqual(len(self.entries), EXPECTED_STREAMS)

    def test_the_map_starts_at_the_first_compressed_stream(self) -> None:
        self.assertEqual(self.entries[0].source, FIRST_SOURCE)
        self.assertEqual(self.entries[0].target, 0)

    def test_the_declared_output_accounts_for_every_byte_of_the_graphics_blob(self) -> None:
        measured = sum(e.length for e in self.entries[:-1])

        self.assertEqual(measured, EXPECTED_GFX_BYTES)
        self.assertEqual(self.entries[-1].target, EXPECTED_GFX_BYTES)

    def test_targets_tile_the_graphics_blob_without_gaps(self) -> None:
        for previous, entry in itertools.pairwise(self.entries):
            self.assertEqual(previous.target + previous.length, entry.target)

    def test_every_stream_decompresses_from_the_untagged_rom(self) -> None:
        for entry in self.entries[:200]:
            stream = sdd1.decompress(self.retail, entry.source, entry.length)

            self.assertEqual(len(stream.data), entry.length)

    def test_most_streams_are_packed_end_to_end_in_the_rom(self) -> None:
        report = sdd1map.audit(self.retail, self.entries)

        self.assertGreater(report["packed"] / report["measured"], 0.9)

    def test_rebuilding_places_each_stream_at_its_declared_target(self) -> None:
        entries = self.entries[:64]
        total = entries[-1].target + entries[-1].length

        blob = sdd1map.rebuild(self.retail, entries, gfx_size=total)

        self.assertEqual(len(blob), total)
        for entry in entries:
            expected = sdd1.decompress(self.retail, entry.source, entry.length).data
            self.assertEqual(blob[entry.target : entry.target + entry.length], expected)

    def test_rebuilding_refuses_an_entry_of_unknown_length(self) -> None:
        with self.assertRaises(ValueError):
            sdd1map.rebuild(self.retail, self.entries[-1:])

    def test_rebuilding_refuses_a_blob_too_small_to_hold_a_stream(self) -> None:
        entries = self.entries[:4]

        with self.assertRaises(ValueError):
            sdd1map.rebuild(self.retail, entries, gfx_size=64)


ZERO_ROM = bytes(0x10000)


def audit_of(following_source: int, length: int | None = 64) -> dict[str, int]:
    entries = [
        sdd1map.Entry(0, 0x100, 0, length),
        sdd1map.Entry(1, following_source, 64, None),
    ]
    report: dict[str, int] = sdd1map.audit(ZERO_ROM, entries)
    return report


class AuditTest(unittest.TestCase):
    def test_a_stream_of_unknown_length_is_skipped(self) -> None:
        # Arrange
        following = 0x300

        # Act
        report = audit_of(following, length=None)

        # Assert
        self.assertEqual(
            report, {"measured": 0, "packed": 0, "padded": 0, "overrun": 0, "skipped": 1}
        )

    def test_a_neighbour_a_whole_bank_away_is_skipped(self) -> None:
        # Arrange
        following = 0x100 + sdd1map.BANK_SIZE

        # Act
        report = audit_of(following)

        # Assert
        self.assertEqual(
            report, {"measured": 0, "packed": 0, "padded": 0, "overrun": 0, "skipped": 1}
        )

    def test_a_neighbour_starting_where_the_stream_ends_is_packed(self) -> None:
        # Arrange
        following = sdd1.decompress(ZERO_ROM, 0x100, 64).end

        # Act
        report = audit_of(following)

        # Assert
        self.assertEqual(
            report, {"measured": 1, "packed": 1, "padded": 0, "overrun": 0, "skipped": 0}
        )

    def test_a_neighbour_starting_before_the_stream_ends_is_an_overrun(self) -> None:
        # Arrange
        following = sdd1.decompress(ZERO_ROM, 0x100, 64).end - 2

        # Act
        report = audit_of(following)

        # Assert
        self.assertEqual(
            report, {"measured": 1, "packed": 0, "padded": 0, "overrun": 1, "skipped": 0}
        )


class RebuildTest(unittest.TestCase):
    def test_an_entry_of_unknown_length_is_refused(self) -> None:
        # Arrange
        entries = [sdd1map.Entry(0, 0x100, 0, None)]

        # Act
        with self.assertRaises(ValueError) as caught:
            sdd1map.rebuild(ZERO_ROM, entries)

        # Assert
        self.assertEqual(str(caught.exception), "cannot rebuild while any stream length is unknown")

    def test_a_declared_size_too_small_for_a_stream_is_refused(self) -> None:
        # Arrange
        entries = [sdd1map.Entry(0, 0x100, 0, 64), sdd1map.Entry(1, 0x300, 64, 128)]

        # Act
        with self.assertRaises(ValueError) as caught:
            sdd1map.rebuild(ZERO_ROM, entries, gfx_size=64)

        # Assert
        self.assertEqual(str(caught.exception), "stream 1 runs past the end of a 64 byte blob")

    def test_a_declared_size_sets_the_length_of_the_blob(self) -> None:
        # Arrange
        entries = [sdd1map.Entry(0, 0x100, 0, 64)]

        # Act
        blob = sdd1map.rebuild(ZERO_ROM, entries, gfx_size=256)

        # Assert
        self.assertEqual(len(blob), 256)


class CommandTest(unittest.TestCase):
    ROM = bytes(0x400000)

    def run_with(self, argv: list[str], blob: bytes) -> tuple[int, list[str]]:
        said: list[str] = []

        def _read(where: Any) -> bytes:
            return blob if str(where) == argv[1] else self.ROM

        code = sdd1map.main(argv, read=_read, say=lambda *args, **_k: said.append(str(args[0])))
        return code, said

    def test_too_few_arguments_prints_the_usage(self) -> None:
        code, said = self.run_with(["sdd1map.py", "one"], b"")

        self.assertEqual((code, "usage" in said[0]), (2, True))

    def test_a_blob_with_no_markers_is_refused(self) -> None:
        code, said = self.run_with(["sdd1map.py", "tagged", "rom"], bytes(1024))

        self.assertEqual((code, "no S-DD1 markers" in said[0]), (1, True))

    def test_a_blob_with_markers_is_reported(self) -> None:
        blob = tagged_blob([(0x100, 0), (0x300, 64), (0x700, 192)])

        code, said = self.run_with(["sdd1map.py", "tagged", "rom"], blob)

        self.assertEqual((code, "streams" in said[0]), (0, True))

    def test_the_report_names_the_source_span(self) -> None:
        blob = tagged_blob([(0x100, 0), (0x300, 64), (0x700, 192)])

        _, said = self.run_with(["sdd1map.py", "tagged", "rom"], blob)

        self.assertIn("0x0000100", "\n".join(said))

    def test_it_counts_the_bitplane_mode_of_every_stream_but_the_last(self) -> None:
        blob = tagged_blob([(0x100, 0), (0x300, 64), (0x700, 192)])

        _, said = self.run_with(["sdd1map.py", "tagged", "rom"], blob)

        self.assertIn("bitplane modes", "\n".join(said))

    def test_a_third_argument_writes_the_rebuilt_graphics(self) -> None:
        blob = tagged_blob([(0x100, 0), (0x300, 64), (0x700, 192)])
        out = Path(tempfile.mkdtemp()) / "graphics.bin"

        code, _said = self.run_with(["sdd1map.py", "tagged", "rom", str(out)], blob)

        self.assertEqual((code, out.exists()), (0, True))

    def test_and_says_that_the_final_stream_is_not_in_it(self) -> None:
        blob = tagged_blob([(0x100, 0), (0x300, 64), (0x700, 192)])
        out = Path(tempfile.mkdtemp()) / "graphics.bin"

        _, said = self.run_with(["sdd1map.py", "tagged", "rom", str(out)], blob)

        self.assertIn("final stream is omitted", "\n".join(said))


if __name__ == "__main__":
    unittest.main(verbosity=2)
