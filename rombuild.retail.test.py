import importlib.util
import itertools
import sys
import unittest
from pathlib import Path
from typing import Any, ClassVar, override

import script

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hardware

sdd1 = hardware.load("sdd1")

mapper = hardware.load("mapper")

dump = hardware.load("romimage").dump

ROOT = Path(__file__).resolve().parent


def load_module(name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, ROOT / f"{name}.py")
    assert spec is not None and spec.loader is not None, "no loader for that path"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


rombuild = load_module("rombuild")

PATCHED = ROOT / "build" / "sfa2-usa-patched.sfc"

TAGGED = ROOT / "roms" / "sfa2-usa-vc-sound-restored.sfc"


def key_slot(image: bytes | bytearray, source: int) -> int | None:
    bank = 0xC0 + (source >> 16)
    slots = (((source & 0xFFFF) + step) & 0xFFFF for step in range(0x10000))
    return next(
        (
            slot
            for slot in slots
            if image[mapper.snes_to_file(rombuild.TABLE_BANK, slot, rombuild.IMAGE_BANKS)] == bank
        ),
        None,
    )


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


@unittest.skipUnless(PATCHED.exists() and TAGGED.exists(), "the patched rom is not built")
class ImageTest(unittest.TestCase):
    entries: ClassVar[Any]
    result: ClassVar[Any]
    rom: ClassVar[Any]

    @classmethod
    @override
    def setUpClass(cls) -> None:
        cls.rom = dump.read(PATCHED)
        cls.entries = rombuild.load_entries(dump.read(TAGGED))
        cls.result = rombuild.build(cls.rom, cls.entries)

    def test_the_image_is_the_declared_size(self) -> None:
        self.assertEqual(len(self.result.image), rombuild.IMAGE_SIZE)
        self.assertEqual(mapper.bank_count(len(self.result.image)), rombuild.IMAGE_BANKS)

    def test_the_lorom_view_returns_the_original(self) -> None:
        for bank in (0x00, 0x01, 0x25, 0x35, 0x3F):
            offset = mapper.address_to_file(bank, 0x8000, rombuild.IMAGE_BANKS)
            got = self.result.image[offset : offset + 0x8000]

            self.assertEqual(got, self.rom[bank * 0x8000 : bank * 0x8000 + 0x8000])

    def occupied(self) -> dict[int, list[tuple[int, int]]]:
        spans: dict[int, list[tuple[int, int]]] = {}
        for entry in self.entries:
            destination = self.result.destinations[entry.index]
            spans.setdefault(destination >> 16, []).append(
                (destination & 0xFFFF, (destination & 0xFFFF) + entry.length)
            )
        return spans

    def test_the_window_view_returns_the_original_where_nothing_was_reclaimed(self) -> None:
        spans = self.occupied()
        checked = 0

        for n in (0x00, 0x1A, 0x25, 0x3F):
            taken = spans.get(0xC0 + n, [])
            for addr in range(0x0000, 0x10000, 0x400):
                if any(start < addr + 0x400 and end > addr for start, end in taken):
                    continue
                got = read_snes(self.result.image, ((0xC0 + n) << 16) | addr, 0x400)

                self.assertEqual(got, self.rom[n * 0x10000 + addr :][:0x400])
                checked += 1

        self.assertGreater(checked, 100)

    def test_the_patch_routine_is_reachable_at_its_assembled_address(self) -> None:
        offset = mapper.address_to_file(0x35, 0xCD84, rombuild.IMAGE_BANKS)

        self.assertEqual(self.result.image[offset], 0x08)

    def test_every_stream_can_be_read_at_the_address_the_table_gives(self) -> None:
        for entry in self.entries[:400]:
            destination = self.result.destinations[entry.index]
            expected = sdd1.decompress(self.rom, entry.source, entry.length).data

            got = read_snes(self.result.image, destination, entry.length)

            self.assertEqual(got, expected, f"stream {entry.index}")

    def test_a_stream_spanning_the_half_boundary_still_reads_back(self) -> None:
        crossing = [
            e
            for e in self.entries
            if (self.result.destinations[e.index] & 0xFFFF) < mapper.HALF
            and (self.result.destinations[e.index] & 0xFFFF) + e.length > mapper.HALF
        ]

        self.assertGreater(len(crossing), 0)
        for entry in crossing[:20]:
            expected = sdd1.decompress(self.rom, entry.source, entry.length).data

            got = read_snes(self.result.image, self.result.destinations[entry.index], entry.length)

            self.assertEqual(got, expected, f"stream {entry.index}")

    def test_most_streams_stay_adjacent_in_map_order(self) -> None:
        adjacent = 0
        for entry, following in itertools.pairwise(self.entries):
            here = self.result.destinations[entry.index]
            nxt = self.result.destinations[following.index]
            if here + entry.length == nxt:
                adjacent += 1

        self.assertGreater(adjacent / (len(self.entries) - 1), 0.8)

    def test_no_stream_crosses_a_bank_boundary(self) -> None:
        for entry in self.entries:
            start = self.result.destinations[entry.index]

            self.assertEqual(start >> 16, (start + entry.length - 1) >> 16)

    def test_the_tables_land_in_their_declared_banks(self) -> None:
        parts = (
            self.result.tables.key,
            self.result.tables.dest_low,
            self.result.tables.dest_high,
            self.result.tables.dest_bank,
        )

        for index, part in enumerate(parts):
            got = read_snes(self.result.image, (rombuild.TABLE_BANK + index) << 16, mapper.BANK)

            self.assertEqual(got, part, f"table bank ${rombuild.TABLE_BANK + index:02X}")

    def test_the_final_stream_gets_a_length_so_it_has_a_table_entry(self) -> None:
        self.assertIsNotNone(self.entries[-1].length)
        self.assertEqual(self.entries[-1].length, rombuild.FINAL_STREAM_LENGTH)
        self.assertIn(self.entries[-1].index, self.result.destinations)

    def test_every_mapped_stream_has_a_table_entry_so_the_scan_terminates(self) -> None:
        # Arrange
        image = self.result.image

        # Act
        keyed = {entry.index: key_slot(image, entry.source) for entry in self.entries}

        # Assert
        self.assertEqual([at for at, slot in keyed.items() if slot is None], [])

    def test_a_stream_reads_back_through_its_own_table_entry(self) -> None:
        image = self.result.image
        banks = rombuild.IMAGE_BANKS

        def table_byte(bank: int, index: int) -> int:
            at = mapper.address_to_file(bank, index, banks)
            assert isinstance(at, int)
            found: int = image[at]
            return found

        for entry in self.entries[:200]:
            source_bank = 0xC0 + (entry.source >> 16)
            slot = entry.source & 0xFFFF
            while table_byte(rombuild.TABLE_BANK, slot) != source_bank:
                slot = (slot + 1) & 0xFFFF
            destination = (
                table_byte(rombuild.TABLE_BANK + 3, slot) << 16
                | table_byte(rombuild.TABLE_BANK + 2, slot) << 8
                | table_byte(rombuild.TABLE_BANK + 1, slot)
            )

            self.assertEqual(destination, self.result.destinations[entry.index])


script.entry(__name__, unittest.main)
