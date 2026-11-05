import importlib.util
import math
import unittest
from collections import Counter
from pathlib import Path
from typing import Any

import script

ROOT = Path(__file__).resolve().parent

JP_ROM = ROOT / "roms" / "sfz2-jp-final.sfc"

USA_ROM = ROOT / "roms" / "sfa2-usa-final.sfc"

COMPRESSED_AREA = 0x130000

SHORTEST_RUN = 32

WINDOW = 256

STEP = 32

COMPRESSED_ENTROPY = 6.9


def load_module(name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, ROOT / f"{name}.py")
    assert spec is not None and spec.loader is not None, "no loader for that path"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gate = load_module("gate")
jpstreams = load_module("jpstreams")
usastreams = load_module("usastreams")

LOAD_LISTS = (0x1F0000, 0x200000)

LIST_END = 0xFF

LIST_RECORD = 7

LIST_LONGEST = 0x8000

TILE = 32

WINDOW_BANKS = range(0x80, 0xC0)

CHARACTER_TABLES = {
    "usa": ((0x003F2E, 8, 21), (0x00D9FB, 5, 40)),
    "jp": ((0x003F16, 8, 21), (0x00DA27, 5, 40)),
}


def retail(path: Path) -> bytes:
    script.skip_unless(path.exists(), f"{path} is not present")
    found: bytes = gate.dump.read(path)
    return found


def covered(rom: bytes, table: tuple[tuple[int, int], ...]) -> bytearray:
    mask = bytearray(len(rom))
    for source, length in table:
        end = min(gate.sdd1.decompress(rom, source, length).end, len(rom))
        mask[source:end] = b"\x01" * (end - source)
    return mask


def entropy(window: bytes) -> float:
    counts = Counter(window)
    return -sum(n / len(window) * math.log2(n / len(window)) for n in counts.values())


def unexplained_runs(jp: bytes, usa: bytes, mask: bytearray) -> list[tuple[int, int]]:
    runs: list[tuple[int, int]] = []
    start = None
    for at in range(COMPRESSED_AREA, len(jp) + 1):
        odd = at < len(jp) and not mask[at] and jp[at] != usa[at]
        if odd and start is None:
            start = at
        if not odd and start is not None:
            if at - start >= SHORTEST_RUN:
                runs.append((start, at))
            start = None
    return runs


def dense(jp: bytes, run: tuple[int, int]) -> bool:
    first, last = run
    lows = range(
        max(0, first - WINDOW // 2), max(first - WINDOW // 2 + 1, last - WINDOW // 2), STEP
    )
    return any(entropy(jp[low : low + WINDOW]) >= COMPRESSED_ENTROPY for low in lows)


def source_at(rom: bytes, at: int) -> int:
    return (rom[at + 2] & 0x3F) << 16 | rom[at + 1] << 8 | rom[at]


def list_record(rom: bytes, at: int) -> int | None:
    length = rom[at] | rom[at + 1] << 8
    source = source_at(rom, at + 4)
    named = (
        rom[at + 6] in WINDOW_BANKS
        and 0 < length <= LIST_LONGEST
        and length % TILE == 0
        and source >= COMPRESSED_AREA
    )
    return source if named else None


def one_list(rom: bytes, start: int) -> list[int]:
    found: list[int] = []
    at = start
    while (source := list_record(rom, at)) is not None:
        found.append(source)
        at += LIST_RECORD
    return found if rom[at] == LIST_END else []


def unlisted(rom: bytes, table: tuple[tuple[int, int], ...]) -> set[int]:
    low, high = LOAD_LISTS
    named = {
        source
        for start in range(low, high)
        if rom[start - 1] == LIST_END
        for source in one_list(rom, start)
    }
    return named - {source for source, _ in table}


def unnamed_characters(rom: bytes, region: str, table: tuple[tuple[int, int], ...]) -> set[int]:
    named = {
        source_at(rom, start + slot * stride)
        for start, stride, count in CHARACTER_TABLES[region]
        for slot in range(count)
    }
    return named - {source for source, _ in table}


def without(table: tuple[tuple[int, int], ...], source: int) -> tuple[tuple[int, int], ...]:
    return tuple(entry for entry in table if entry[0] != source)


def stray(table: tuple[tuple[int, int], ...]) -> list[int]:
    jp = retail(JP_ROM)
    usa = retail(USA_ROM)
    mask = covered(jp, table)
    return [first for first, last in unexplained_runs(jp, usa, mask) if dense(jp, (first, last))]


class CompressedByteCoverageTest(unittest.TestCase):
    def test_no_japanese_bytes_at_compressed_data_density_lie_outside_the_table(self) -> None:
        # Arrange
        table = jpstreams.STREAMS

        # Act
        found = stray(table)

        # Assert
        self.assertEqual(found, [])

    def test_a_table_missing_a_listed_stream_leaves_dense_bytes_uncovered(self) -> None:
        # Arrange
        table = tuple(entry for entry in jpstreams.STREAMS if entry[0] != 0x1AB740)

        # Act
        found = stray(table)

        # Assert
        self.assertEqual(
            (len(found) > 0, [at for at in found if not 0x1AB740 <= at < 0x1AB840]), (True, [])
        )

    def test_the_entropy_of_a_window_holding_one_value_is_zero(self) -> None:
        # Arrange
        window = bytes(WINDOW)

        # Act
        found = entropy(window)

        # Assert
        self.assertEqual(found, 0.0)


class LoadListTest(unittest.TestCase):
    def test_the_japanese_table_leaves_out_only_what_the_tagged_usa_table_leaves_out(
        self,
    ) -> None:
        # Arrange
        jp, usa = retail(JP_ROM), retail(USA_ROM)

        # Act
        found = (unlisted(jp, jpstreams.STREAMS), unlisted(usa, usastreams.STREAMS))

        # Assert
        self.assertEqual(found[0], found[1])

    def test_a_table_missing_an_ending_glyph_leaves_its_load_list_entry_unlisted(self) -> None:
        # Arrange
        jp, usa = retail(JP_ROM), retail(USA_ROM)
        table = without(jpstreams.STREAMS, 0x1B1C43)

        # Act
        found = unlisted(jp, table) - unlisted(usa, usastreams.STREAMS)

        # Assert
        self.assertEqual(found, {0x1B1C43})


class CharacterTableTest(unittest.TestCase):
    def test_every_stream_a_per_character_table_names_is_in_its_regions_table(self) -> None:
        # Arrange
        roms = {"usa": retail(USA_ROM), "jp": retail(JP_ROM)}
        tables = {"usa": usastreams.STREAMS, "jp": jpstreams.STREAMS}

        # Act
        found = {
            region: unnamed_characters(roms[region], region, tables[region]) for region in roms
        }

        # Assert
        self.assertEqual(found, {"usa": set(), "jp": set()})

    def test_a_table_missing_shin_akumas_portrait_leaves_his_slot_unnamed(self) -> None:
        # Arrange
        jp = retail(JP_ROM)
        table = without(jpstreams.STREAMS, 0x1947F1)

        # Act
        found = unnamed_characters(jp, "jp", table)

        # Assert
        self.assertEqual(found, {0x1947F1})


script.entry(__name__, unittest.main)
