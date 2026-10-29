import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, override

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


class TilesTest(unittest.TestCase):
    def test_a_run_that_is_a_whole_number_of_tiles_is_cut_into_them(self) -> None:
        found = tile_shape.tiles(bytes(64))

        self.assertEqual(len(found), 2)

    def test_a_run_that_is_not_is_refused_rather_than_padded(self) -> None:
        self.assertIsNone(tile_shape.tiles(bytes(40)))

    def test_and_nothing_at_all_is_refused_too(self) -> None:
        self.assertIsNone(tile_shape.tiles(b""))

    def test_the_model_decides_what_a_tile_is_rather_than_this_file(self) -> None:
        found = tile_shape.tiles(bytes(tile_shape.TILE_BYTES))

        self.assertEqual(len(found), 1)

    def test_and_the_size_named_here_agrees_with_what_the_model_cuts(self) -> None:
        found = tile_shape.tiles(bytes(tile_shape.TILE_BYTES * 5))

        self.assertEqual(len(found), 5)


class ReuseTest(unittest.TestCase):
    def test_a_sheet_of_identical_tiles_is_all_reuse_but_one(self) -> None:
        found = tile_shape.reuse(bytes(32 * 4))

        self.assertEqual(found, 0.75)

    def test_a_sheet_with_no_tile_twice_reuses_nothing(self) -> None:
        sheet = b"".join(bytes([n]) * 32 for n in range(4))

        self.assertEqual(tile_shape.reuse(sheet), 0.0)

    def test_a_run_that_is_not_whole_tiles_has_no_reuse_to_report(self) -> None:
        self.assertIsNone(tile_shape.reuse(bytes(40)))


class ControlTest(unittest.TestCase):
    def test_random_bytes_repeat_no_tile_at_all(self) -> None:
        found = [tile_shape.reuse(tile_shape.noise(32 * 64)) for _ in range(8)]

        self.assertEqual(max(found), 0.0)

    def test_which_is_what_makes_a_nonzero_reading_mean_something(self) -> None:
        sheet = bytes(32) + bytes(32) + b"\x01" * 32

        self.assertGreater(tile_shape.reuse(sheet), tile_shape.reuse(tile_shape.noise(96)))


class SurveyTest(unittest.TestCase):
    def test_a_survey_of_nothing_reports_nothing_rather_than_dividing_by_zero(self) -> None:
        found = tile_shape.survey([])

        self.assertEqual((found.aligned, found.meanReuse), (0, 0.0))

    def test_an_aligned_run_is_counted_as_aligned(self) -> None:
        found = tile_shape.survey([bytes(32 * 3)])

        self.assertEqual((found.aligned, found.unaligned), (1, 0))

    def test_and_one_that_is_not_is_counted_apart(self) -> None:
        found = tile_shape.survey([bytes(40)])

        self.assertEqual((found.aligned, found.unaligned), (0, 1))

    def test_the_control_is_measured_beside_every_real_run(self) -> None:
        found = tile_shape.survey([bytes(32 * 3)])

        self.assertEqual(found.meanReuseOfNoise, 0.0)

    def test_a_survey_of_real_sheets_reuses_more_than_its_own_control(self) -> None:
        found = tile_shape.survey([bytes(32 * 8)] * 4)

        self.assertGreater(found.meanReuse, found.meanReuseOfNoise)

    def test_how_many_sheets_repeated_anything_is_reported(self) -> None:
        found = tile_shape.survey([bytes(32 * 2), b"".join(bytes([n]) * 32 for n in range(2))])

        self.assertEqual((found.withAnyRepeat, found.noiseWithAnyRepeat), (1, 0))


def a_cartridge_on_disk(case: unittest.TestCase, name: str, size: int) -> Path:
    folder = tempfile.TemporaryDirectory()
    case.addCleanup(folder.cleanup)
    where = Path(folder.name) / name
    where.write_bytes(bytes(size))
    return where


class TableTest(unittest.TestCase):
    def test_a_dump_named_for_the_usa_is_measured_against_the_usa_table(self) -> None:
        # Arrange
        wanted = load_module("usastreams", ROOT / "usastreams.py").STREAMS

        # Act
        found = tile_shape.table_for(Path("sfa2-usa-final.sfc"))

        # Assert
        self.assertEqual(found, wanted)

    def test_any_other_name_is_measured_against_the_japanese_table(self) -> None:
        # Arrange
        wanted = load_module("jpstreams", ROOT / "jpstreams.py").STREAMS

        # Act
        found = tile_shape.table_for("sfz2-jp-final.sfc")

        # Assert
        self.assertEqual(found, wanted)


class AgainstASyntheticCartridgeTest(unittest.TestCase):
    @override
    def setUp(self) -> None:
        self.where = a_cartridge_on_disk(self, "synthetic.sfc", 4096)

    def test_a_stream_of_whole_tiles_and_one_that_is_not_are_counted_apart(self) -> None:
        # Arrange
        table = [(0, 512), (0, 520)]

        # Act
        found = tile_shape.against(self.where, table=table)

        # Assert
        self.assertEqual((found.aligned, found.unaligned), (1, 1))

    def test_a_stream_smaller_than_the_smallest_sheet_is_not_measured(self) -> None:
        # Arrange
        table = [(0, 511)]

        # Act
        found = tile_shape.against(self.where, table=table)

        # Assert
        self.assertEqual((found.aligned, found.unaligned), (0, 0))

    def test_the_limit_stops_the_survey_once_that_many_streams_are_measured(self) -> None:
        # Arrange
        table = [(0, 512), (0, 512), (0, 512)]

        # Act
        found = tile_shape.against(self.where, limit=2, table=table)

        # Assert
        self.assertEqual((found.aligned, found.unaligned), (2, 0))


class EntryTest(unittest.TestCase):
    def test_a_run_over_a_cartridge_reports_how_many_streams_are_whole_tiles(self) -> None:
        # Arrange
        where = a_cartridge_on_disk(self, "synthetic.sfc", 0x8000)
        said: list[str] = []

        # Act
        code = tile_shape.main([str(where), "1"], say=said.append)

        # Assert
        self.assertEqual((code, said[0]), (0, "  1 streams are a whole number of 32 byte tiles"))

    def test_a_rom_it_cannot_read_is_reported_rather_than_raised(self) -> None:
        self.assertEqual(tile_shape.main([str(ROOT / "roms" / "nothing-here.sfc")]), 2)

    def test_and_so_is_a_missing_argument(self) -> None:
        self.assertEqual(tile_shape.main([]), 2)


script.entry(__name__, unittest.main)
