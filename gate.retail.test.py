import importlib.util
import unittest
from pathlib import Path
from typing import Any

import script

ROOT = Path(__file__).resolve().parent


def load_module(name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, ROOT / f"{name}.py")
    assert spec is not None and spec.loader is not None, "no loader for that path"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gate = load_module("gate")

jpstreams = load_module("jpstreams")

JP_ROM = ROOT / "roms" / "sfz2-jp-final.sfc"


@unittest.skipUnless(JP_ROM.exists(), "the Japanese ROM is absent")
class ShippedTableTest(unittest.TestCase):
    def test_the_shipped_table_passes_every_gate(self) -> None:
        findings = gate.check("jp")

        self.assertEqual(findings, [])

    def test_the_recorded_requests_are_a_subset_of_the_table(self) -> None:
        sources = {source for source, _ in jpstreams.STREAMS}

        for address in gate.requests("jp"):
            self.assertIn(address, sources)


script.entry(__name__, unittest.main)
