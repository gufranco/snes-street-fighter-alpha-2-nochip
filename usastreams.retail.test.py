import importlib.util
import sys
import unittest
from pathlib import Path
from typing import Any

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


usastreams = load_module("usastreams")

rombuild = load_module("rombuild")

TAGGED_ROM = ROOT / "roms" / "sfa2-usa-vc-sound-restored.sfc"


@unittest.skipUnless(TAGGED_ROM.exists(), "the tagged ROM is not present")
class RegenerationTest(unittest.TestCase):
    def test_the_frozen_table_matches_what_the_tags_say(self) -> None:
        entries = rombuild.load_entries(dump.read(TAGGED_ROM))
        extracted = tuple((entry.source, entry.length) for entry in entries if entry.length)

        self.assertEqual(extracted, usastreams.TAGGED)


script.entry(__name__, unittest.main)
