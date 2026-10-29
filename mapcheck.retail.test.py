import importlib.util
import sys
import unittest
from pathlib import Path
from typing import Any, ClassVar, override

import script

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hardware

dump = hardware.load("romimage").dump

ROOT = Path(__file__).resolve().parent


def load_module(name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, ROOT / f"{name}.py")
    assert spec is not None and spec.loader is not None, "no loader for that path"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


mapcheck = load_module("mapcheck")

JP_ROM = ROOT / "roms" / "sfz2-jp-final.sfc"


@unittest.skipUnless(JP_ROM.exists(), "the Japanese ROM is absent")
class JapaneseMapTest(unittest.TestCase):
    entries: ClassVar[Any]
    rom: ClassVar[Any]

    @classmethod
    @override
    def setUpClass(cls) -> None:
        cls.rom = dump.read(JP_ROM)
        cls.entries = mapcheck.load()

    def test_the_map_holds_the_streams_the_build_needs(self) -> None:
        self.assertGreaterEqual(len(self.entries), 2816)

    def test_no_source_appears_twice(self) -> None:
        self.assertEqual(mapcheck.duplicate_sources(self.entries), [])

    def test_every_stream_decompresses(self) -> None:
        self.assertEqual(mapcheck.undecodable(self.rom, self.entries), [])

    def test_every_stream_stays_inside_the_rom(self) -> None:
        for source, _ in self.entries:
            self.assertLess(source, len(self.rom))

    def test_the_lookup_stays_cheap_to_scan(self) -> None:
        _, worst = mapcheck.scan_cost(self.entries)

        self.assertLessEqual(worst, mapcheck.SCAN_BUDGET)

    def test_the_streams_recovered_by_harvesting_are_present(self) -> None:
        sources = {source for source, _ in self.entries}

        for recovered in mapcheck.RECOVERED_JP:
            self.assertIn(recovered, sources)


script.entry(__name__, unittest.main)
