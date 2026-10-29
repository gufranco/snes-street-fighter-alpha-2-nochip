import importlib.util
import sys
import unittest
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import script

ROOT = Path(__file__).resolve().parent.parent


def load_module(name: str, where: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, where)
    assert spec is not None and spec.loader is not None, "no loader for that path"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


tile_shape = load_module("tile_shape", Path(__file__).resolve().parent / "tile_shape.py")

USA = ROOT / "roms" / "sfa2-usa-final.sfc"

NEEDS_A_DUMP = unittest.skipUnless(
    USA.exists(), "the retail dump is not on this machine, and nothing here ships one"
)


@NEEDS_A_DUMP
class AgainstTheCartridgeTest(unittest.TestCase):
    def measured(self) -> Any:
        return tile_shape.against(USA, limit=200)

    def test_most_streams_are_a_whole_number_of_tiles(self) -> None:
        found = self.measured()

        self.assertGreater(found.aligned, found.unaligned)

    def test_the_decompressed_output_repeats_tiles(self) -> None:
        self.assertGreater(self.measured().meanReuse, 0.05)

    def test_and_random_bytes_of_the_same_lengths_repeat_none(self) -> None:
        self.assertEqual(self.measured().meanReuseOfNoise, 0.0)

    def test_which_is_the_whole_claim(self) -> None:
        found = self.measured()

        self.assertGreater(found.withAnyRepeat, found.noiseWithAnyRepeat)


@NEEDS_A_DUMP
class ExhaustedTableTest(unittest.TestCase):
    def test_a_table_shorter_than_the_limit_is_measured_whole(self) -> None:
        table = list(tile_shape.table_for(USA))[:3]

        found = tile_shape.against(USA, limit=100, table=table)

        self.assertEqual(found.aligned + found.unaligned, len(table))

    def test_a_table_with_no_stream_big_enough_measures_nothing(self) -> None:
        found = tile_shape.against(USA, table=[(0x100000, tile_shape.SMALLEST - 1)])

        self.assertEqual(found.aligned + found.unaligned, 0)


@NEEDS_A_DUMP
class EntryAgainstTheCartridgeTest(unittest.TestCase):
    def test_a_run_from_the_command_line_reports_what_it_measured(self) -> None:
        # Arrange
        arguments = [str(USA), "60"]

        # Act
        code = tile_shape.main(arguments)

        # Assert
        self.assertEqual(code, 0)


script.entry(__name__, unittest.main)
