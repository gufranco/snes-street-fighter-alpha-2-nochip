import importlib.util
import itertools
import unittest
from pathlib import Path
from typing import Any

import script

ROOT = Path(__file__).resolve().parent

ORIGINAL_SIZE = 0x400000

BORDER_TILE = (0x1A2203, 64)


def load_module(name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, ROOT / f"{name}.py")
    assert spec is not None and spec.loader is not None, "no loader for that path"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


rawreads = load_module("rawreads")


def overlapping(spans: tuple[tuple[int, int], ...]) -> list[int]:
    return [
        later[0]
        for earlier, later in itertools.pairwise(spans)
        if later[0] < earlier[0] + earlier[1]
    ]


class ShapeTest(unittest.TestCase):
    def test_the_record_holds_both_regions(self) -> None:
        # Arrange
        regions = rawreads.READS

        # Act
        found = sorted(regions)

        # Assert
        self.assertEqual(found, ["jp", "usa"])

    def test_every_span_is_sorted_and_apart_from_the_next(self) -> None:
        # Arrange
        regions = rawreads.READS

        # Act
        found = {
            region: (list(spans) == sorted(spans), overlapping(spans))
            for region, spans in regions.items()
        }

        # Assert
        self.assertEqual(found, {"jp": (True, []), "usa": (True, [])})

    def test_every_span_has_a_length_and_lies_inside_the_cartridge(self) -> None:
        # Arrange
        spans = rawreads.USA + rawreads.JP

        # Act
        outside = [
            source for source, length in spans if length <= 0 or source + length > ORIGINAL_SIZE
        ]

        # Assert
        self.assertEqual(outside, [])

    def test_the_japanese_dialogue_border_tile_is_recorded(self) -> None:
        # Arrange
        source, length = BORDER_TILE

        # Act
        found = [
            (start, size)
            for start, size in rawreads.JP
            if start <= source and source + length <= start + size
        ]

        # Assert
        self.assertEqual(len(found), 1)

    def test_overlapping_finds_a_span_that_starts_inside_the_previous_one(self) -> None:
        # Arrange
        spans = ((0x100, 0x10), (0x108, 0x10), (0x200, 0x10))

        # Act
        found = overlapping(spans)

        # Assert
        self.assertEqual(found, [0x108])


script.entry(__name__, unittest.main)
