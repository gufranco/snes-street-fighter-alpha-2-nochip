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


tables = load_module("sdd1tables")

sdd1map = load_module("sdd1map")

TAGGED = ROOT / "roms" / "sfa2-usa-vc-sound-restored.sfc"


@unittest.skipUnless(TAGGED.exists(), "the tagged rom is not present")
class RealMapTest(unittest.TestCase):
    entries: ClassVar[Any]

    @classmethod
    @override
    def setUpClass(cls) -> None:
        cls.entries = [e for e in sdd1map.build_map(dump.read(TAGGED)) if e.length]

    def test_every_real_stream_places_and_verifies(self) -> None:
        keys = [tables.source_key(e.source) for e in self.entries]

        placed = tables.allocate(keys)

        tables.verify(keys, placed)
        self.assertEqual(len(placed), len(self.entries))

    def test_the_real_map_fits_with_room_to_spare(self) -> None:
        keys = [tables.source_key(e.source) for e in self.entries]

        placed = tables.allocate(keys)

        self.assertLess(len(set(placed)), tables.SLOTS // 8)
        self.assertEqual(len(set(placed)), len(placed))

    def test_most_streams_land_on_their_own_address_without_probing(self) -> None:
        keys = [tables.source_key(e.source) for e in self.entries]

        placed = tables.allocate(keys)
        exact = sum(1 for (_, addr), slot in zip(keys, placed, strict=True) if addr == slot)

        self.assertGreater(exact / len(placed), 0.9)


script.entry(__name__, unittest.main)
