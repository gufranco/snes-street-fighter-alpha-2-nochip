import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

import script

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hardware

mapper = hardware.load("mapper")


ROOT = Path(__file__).resolve().parent


def load_module(name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, ROOT / f"{name}.py")
    assert spec is not None and spec.loader is not None, "no loader for that path"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


rombuild = load_module("rombuild")
sdd1map = load_module("sdd1map")


def region(bank: int, start: int, end: int) -> Any:
    return rombuild.Region(bank=bank, start=start, end=end)


def read_snes(
    image: bytes | bytearray, address: int, length: int, banks: int = rombuild.IMAGE_BANKS
) -> bytes:
    out = bytearray()
    bank, addr = address >> 16, address & 0xFFFF
    while length:
        edge = mapper.HALF if addr < mapper.HALF else mapper.BANK
        chunk = min(length, edge - addr)
        offset = mapper.address_to_file(bank, addr, banks)
        out += image[offset : offset + chunk]
        addr += chunk
        length -= chunk
    return bytes(out)


class RegionTest(unittest.TestCase):
    def test_the_wram_banks_are_never_offered(self) -> None:
        banks = {r.bank for r in rombuild.data_bank_regions()}

        self.assertNotIn(0x7E, banks)
        self.assertNotIn(0x7F, banks)

    def test_the_table_banks_are_reserved(self) -> None:
        banks = {r.bank for r in rombuild.data_bank_regions()}

        for bank in range(rombuild.TABLE_BANK, rombuild.TABLE_BANK + 4):
            self.assertNotIn(bank, banks)

    def test_a_data_bank_is_offered_whole(self) -> None:
        found = [r for r in rombuild.data_bank_regions() if r.bank == 0x41]

        self.assertEqual(found, [region(0x41, 0x0000, 0x10000)])

    def test_a_region_never_spans_two_banks(self) -> None:
        for r in rombuild.data_bank_regions():
            self.assertGreater(r.end, r.start)
            self.assertLessEqual(r.end, 0x10000)


class AllocationTest(unittest.TestCase):
    def test_a_stream_is_placed_inside_one_bank(self) -> None:
        regions = [region(0x41, 0x0000, 0x10000)]

        placed = rombuild.allocate([(0, 0x2000)], regions)

        bank = placed[0] >> 16
        self.assertEqual(bank, 0x41)
        self.assertEqual((placed[0] + 0x2000 - 1) >> 16, bank)

    def test_two_streams_do_not_overlap(self) -> None:
        regions = [region(0x41, 0x0000, 0x10000)]

        placed = rombuild.allocate([(0, 0x8000), (1, 0x8000)], regions)

        self.assertNotEqual(placed[0], placed[1])
        self.assertEqual(abs(placed[0] - placed[1]), 0x8000)

    def test_a_stream_too_large_for_any_region_is_reported(self) -> None:
        regions = [region(0x41, 0x0000, 0x1000)]

        with self.assertRaises(rombuild.AllocationError):
            rombuild.allocate([(0, 0x2000)], regions)

    def test_a_small_region_is_used_before_it_is_wasted(self) -> None:
        regions = [region(0x41, 0x0000, 0x0400), region(0x42, 0x0000, 0x10000)]

        placed = rombuild.allocate([(0, 0x0400)], regions)

        self.assertEqual(placed[0] >> 16, 0x41)


class ReservationTest(unittest.TestCase):
    def test_a_reserved_span_is_removed_from_its_bank(self) -> None:
        regions = [rombuild.Region(0x5F, 0x0000, 0x10000)]
        taken = rombuild.spans_of([(0x5F0000, b"x" * 0x100)])

        left = rombuild.subtract(regions, taken)

        self.assertEqual(left, [rombuild.Region(0x5F, 0x0100, 0x10000)])

    def test_a_reservation_in_the_middle_leaves_two_pieces(self) -> None:
        regions = [rombuild.Region(0x5F, 0x0000, 0x1000)]
        taken = rombuild.spans_of([(0x5F0400, b"x" * 0x100)])

        left = rombuild.subtract(regions, taken)

        self.assertEqual(
            left, [rombuild.Region(0x5F, 0x0000, 0x0400), rombuild.Region(0x5F, 0x0500, 0x1000)]
        )

    def test_a_reservation_leaves_other_banks_alone(self) -> None:
        regions = [rombuild.Region(0x41, 0x0000, 0x10000)]
        taken = rombuild.spans_of([(0x5F0000, b"x" * 0x100)])

        self.assertEqual(rombuild.subtract(regions, taken), regions)

    def test_a_reservation_covering_a_whole_region_removes_it(self) -> None:
        regions = [rombuild.Region(0x5F, 0x0000, 0x0100)]
        taken = rombuild.spans_of([(0x5F0000, b"x" * 0x100)])

        self.assertEqual(rombuild.subtract(regions, taken), [])

    def test_a_span_names_the_bank_and_length_of_its_payload(self) -> None:
        spans = rombuild.spans_of([(0x5F0000, b"x" * 0x6080)])

        self.assertEqual(spans, [rombuild.Region(0x5F, 0x0000, 0x6080)])


def tagged_blob(markers: list[tuple[int, int]], size: int = 8192) -> bytes:
    blob = bytearray(size)
    for position, target in markers:
        blob[position : position + 4] = sdd1map.MARKER
        blob[position + 4 : position + 8] = target.to_bytes(4, "little")
    return bytes(blob)


class LoadEntriesTest(unittest.TestCase):
    def test_a_blob_with_no_markers_yields_nothing(self) -> None:
        self.assertEqual(rombuild.load_entries(bytes(4096)), [])

    def test_the_final_stream_is_given_the_assumed_length(self) -> None:
        entries = rombuild.load_entries(tagged_blob([(0x100, 0), (0x300, 64)]))

        self.assertEqual(entries[-1].length, rombuild.FINAL_STREAM_LENGTH)

    def test_the_earlier_streams_keep_the_length_the_gap_gives_them(self) -> None:
        entries = rombuild.load_entries(tagged_blob([(0x100, 0), (0x300, 64)]))

        self.assertEqual(entries[0].length, 64)


class EntriesFromMapTest(unittest.TestCase):
    def test_entries_come_back_in_source_order(self) -> None:
        entries = rombuild.entries_from_map({"512": 16, "256": 32})

        self.assertEqual([one.source for one in entries], [256, 512])

    def test_each_entry_is_numbered_by_its_place_in_that_order(self) -> None:
        entries = rombuild.entries_from_map({"512": 16, "256": 32})

        self.assertEqual([one.index for one in entries], [0, 1])

    def test_no_entry_claims_a_destination_it_has_not_been_given(self) -> None:
        entries = rombuild.entries_from_map({"256": 32})

        self.assertIsNone(entries[0].target)


class CommandTest(unittest.TestCase):
    def test_too_few_arguments_prints_the_usage(self) -> None:
        said: list[str] = []

        code = rombuild.main(
            ["rombuild.py", "one"], say=lambda *args, **_k: said.append(str(args[0]))
        )

        self.assertEqual((code, "usage" in said[0]), (2, True))

    def build_with(self, markers: list[tuple[int, int]]) -> tuple[int, list[str], Path]:
        out = Path(tempfile.mkdtemp()) / "image.sfc"
        said: list[str] = []
        blob = tagged_blob(markers)

        code = rombuild.main(
            ["rombuild.py", "rom", "tagged", str(out)],
            read=lambda where: blob if str(where) == "tagged" else bytes(rombuild.ORIGINAL_SIZE),
            say=lambda *args, **_k: said.append(str(args[0])),
        )
        return code, said, out

    def test_a_build_writes_the_image_where_it_was_told(self) -> None:
        code, _, out = self.build_with([(0x100, 0), (0x300, 64)])

        self.assertEqual((code, out.exists()), (0, True))

    def test_the_image_is_the_declared_size(self) -> None:
        _, _, out = self.build_with([(0x100, 0), (0x300, 64)])

        self.assertEqual(len(out.read_bytes()), rombuild.IMAGE_SIZE)

    def test_it_counts_the_streams_it_placed(self) -> None:
        _, said, _ = self.build_with([(0x100, 0), (0x300, 64)])

        self.assertIn("streams   2", said[0])

    def test_it_reports_how_many_banks_the_graphics_landed_in(self) -> None:
        _, said, _ = self.build_with([(0x100, 0), (0x300, 64)])

        self.assertIn("banks", "\n".join(said))

    def test_a_cartridge_of_the_wrong_size_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            rombuild.build(bytes(1024), [])


class AllocationRefusalTest(unittest.TestCase):
    def test_no_regions_at_all_is_refused(self) -> None:
        with self.assertRaises(rombuild.AllocationError):
            rombuild.allocate([(0, 16)], [])


class SubtractTest(unittest.TestCase):
    def test_a_hole_that_misses_a_region_leaves_it_whole(self) -> None:
        found = rombuild.subtract([region(0x40, 0x0000, 0x1000)], [region(0x40, 0x2000, 0x3000)])

        self.assertEqual(found, [region(0x40, 0x0000, 0x1000)])

    def test_a_hole_in_the_middle_splits_the_region_in_two(self) -> None:
        found = rombuild.subtract([region(0x40, 0x0000, 0x3000)], [region(0x40, 0x1000, 0x2000)])

        self.assertEqual(found, [region(0x40, 0x0000, 0x1000), region(0x40, 0x2000, 0x3000)])

    def test_a_hole_covering_the_region_removes_it(self) -> None:
        found = rombuild.subtract([region(0x40, 0x1000, 0x2000)], [region(0x40, 0x0000, 0x3000)])

        self.assertEqual(found, [])

    def test_a_hole_in_another_bank_does_not_touch_this_one(self) -> None:
        found = rombuild.subtract([region(0x40, 0x0000, 0x1000)], [region(0x41, 0x0000, 0x1000)])

        self.assertEqual(found, [region(0x40, 0x0000, 0x1000)])


class ReclaimTest(unittest.TestCase):
    ROM = bytes(rombuild.ORIGINAL_SIZE)

    def test_a_stream_of_unknown_length_reclaims_nothing(self) -> None:
        entry = sdd1map.Entry(index=0, source=0x100000, target=None, length=None)

        self.assertEqual(rombuild.reclaimed_regions(self.ROM, [entry]), [])

    def test_a_stream_too_short_to_free_a_byte_reclaims_nothing(self) -> None:
        entry = sdd1map.Entry(index=0, source=0x100000, target=None, length=1)

        self.assertEqual(rombuild.reclaimed_regions(self.ROM, [entry]), [])

    def test_a_stream_that_consumed_nothing_reclaims_nothing(self) -> None:
        entry = sdd1map.Entry(index=0, source=0x100000, target=None, length=4096)

        class Consumed:
            end = 0x100000

        found = rombuild.reclaimed_regions(self.ROM, [entry], lambda *_a: Consumed())

        self.assertEqual(found, [])

    def test_a_stream_long_enough_reclaims_the_span_it_occupied(self) -> None:
        entry = sdd1map.Entry(index=0, source=0x100000, target=None, length=4096)

        class Consumed:
            end = 0x100000 + rombuild.MIN_REGION + 1

        found = rombuild.reclaimed_regions(self.ROM, [entry], lambda *_a: Consumed())

        self.assertEqual(found[0].bank, rombuild.WINDOW_BASE + 0x10)

    def test_a_span_shorter_than_the_smallest_usable_region_is_dropped(self) -> None:
        entry = sdd1map.Entry(index=0, source=0x100000, target=None, length=4096)

        class Consumed:
            end = 0x100000 + rombuild.MIN_REGION - 1

        self.assertEqual(rombuild.reclaimed_regions(self.ROM, [entry], lambda *_a: Consumed()), [])


class MergeTest(unittest.TestCase):
    def test_two_overlapping_regions_in_one_bank_become_one(self) -> None:
        # Arrange
        regions = [region(0x41, 0x0080, 0x0200), region(0x41, 0x0000, 0x0100)]

        # Act
        merged = rombuild.merge(regions)

        # Assert
        self.assertEqual(merged, [region(0x41, 0x0000, 0x0200)])

    def test_a_region_inside_another_leaves_the_outer_end(self) -> None:
        # Arrange
        regions = [region(0x41, 0x0000, 0x0400), region(0x41, 0x0100, 0x0200)]

        # Act
        merged = rombuild.merge(regions)

        # Assert
        self.assertEqual(merged, [region(0x41, 0x0000, 0x0400)])


class ExtraPlacementTest(unittest.TestCase):
    def test_it_lands_where_the_caller_named(self) -> None:
        payload = bytes(range(16))
        at = 0x5F0000

        result = rombuild.build(bytes(rombuild.ORIGINAL_SIZE), [], extra=((at, payload),))

        self.assertEqual(read_snes(result.image, at, len(payload)), payload)


script.entry(__name__, unittest.main, verbosity=2)
