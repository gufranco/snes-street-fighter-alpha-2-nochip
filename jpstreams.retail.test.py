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


script.entry(__name__, unittest.main)
