import importlib.util
import unittest
from pathlib import Path
from typing import Any

import script

ROOT = Path(__file__).resolve().parent

ROM_BYTES = 0x400000


def load_module(name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, ROOT / f"{name}.py")
    assert spec is not None and spec.loader is not None, "no loader for that path"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


jpstreams = load_module("jpstreams")
usastreams = load_module("usastreams")


class ShapeTest(unittest.TestCase):
    def test_every_entry_is_a_source_and_a_length(self) -> None:
        for entry in jpstreams.STREAMS:
            self.assertEqual(len(entry), 2)

    def test_sources_are_unique(self) -> None:
        sources = [source for source, _ in jpstreams.STREAMS]

        self.assertEqual(len(sources), len(set(sources)))

    def test_sources_are_ordered(self) -> None:
        sources = [source for source, _ in jpstreams.STREAMS]

        self.assertEqual(sources, sorted(sources))

    def test_every_length_is_positive(self) -> None:
        for source, length in jpstreams.STREAMS:
            self.assertGreater(length, 0, f"{source:#08x}")

    def test_every_source_lies_inside_a_four_megabyte_rom(self) -> None:
        for source, _ in jpstreams.STREAMS:
            self.assertLess(source, ROM_BYTES, f"{source:#08x}")

    def test_no_stream_runs_past_the_end_of_the_rom(self) -> None:
        for source, length in jpstreams.STREAMS:
            self.assertLessEqual(source, ROM_BYTES, f"{source:#08x} + {length}")

    def test_the_two_regions_are_different_tables(self) -> None:
        self.assertNotEqual(set(jpstreams.STREAMS), set(usastreams.STREAMS))

    def test_the_table_is_not_empty(self) -> None:
        self.assertGreater(len(jpstreams.STREAMS), 0)


class CoverageTest(unittest.TestCase):
    def test_the_run_of_704_byte_streams_holds_all_nineteen_members(self) -> None:
        # Arrange
        run = range(0x1AB500, 0x1AC800)

        # Act
        members = [
            source for source, length in jpstreams.STREAMS if source in run and length == 704
        ]

        # Assert
        self.assertEqual(len(members), 19)

    def test_the_streams_no_recorded_run_reached_are_listed(self) -> None:
        # Arrange
        missed = {0x1A3E45, 0x1A7EA0, 0x1AB17F, 0x1AB575, 0x1AB740, 0x1ABFF4, 0x1AC6AD, 0x1AC794}

        # Act
        listed = missed & {source for source, _ in jpstreams.STREAMS}

        # Assert
        self.assertEqual(listed, missed)

    def test_two_streams_cover_their_compressed_bytes_up_to_the_next_stream(self) -> None:
        # Arrange
        table = dict(jpstreams.STREAMS)

        # Act
        lengths = (table[0x14EC85], table[0x17DD54])

        # Assert
        self.assertEqual(lengths, (16256, 8352))


script.entry(__name__, unittest.main)
