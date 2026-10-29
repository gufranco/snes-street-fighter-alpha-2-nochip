import importlib.util
import sys
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import hardware  # noqa: E402
import script  # noqa: E402

dump = hardware.load("romimage").dump


def load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None, "no loader for that path"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


harvest_jp = load_module("harvest_jp", ROOT / "tools" / "harvest_jp.py")
recipes = load_module("harvest_jp.retail", ROOT / "tools" / "harvest_jp.retail.py")
repeatload = load_module("repeatload", ROOT / "repeatload.py")


@unittest.skipUnless(harvest_jp.RETAIL.exists(), "the retail cartridge is not present")
class VariantAgainstTheCartridgeTest(unittest.TestCase):
    def test_the_harvest_builds_four_variants_and_none_of_them_twice(self) -> None:
        # Arrange
        retail = dump.read(harvest_jp.RETAIL)

        # Act
        variants = recipes.variants(retail)

        # Assert
        self.assertEqual(sorted(variants), ["base", "both", "sa", "spc"])
        self.assertEqual(len(set(variants.values())), 4)

    def test_the_harvest_variants_carry_no_skip_patch(self) -> None:
        # Arrange
        retail = dump.read(harvest_jp.RETAIL)

        # Act
        variants = recipes.variants(retail)

        # Assert
        patched = [name for name, image in variants.items() if repeatload.is_patched(image)]
        self.assertEqual(patched, [])


script.entry(__name__, unittest.main)
