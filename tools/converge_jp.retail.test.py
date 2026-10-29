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


converge = load_module("converge_jp", ROOT / "tools" / "converge_jp.py")
recipes = load_module("converge_jp.retail", ROOT / "tools" / "converge_jp.retail.py")
spcfast = load_module("spcfast", ROOT / "spcfast.py")
shinakuma = load_module("shinakuma", ROOT / "shinakuma.py")


@unittest.skipUnless(converge.RETAIL.exists(), "the retail cartridge is not present")
class VariantAgainstTheCartridgeTest(unittest.TestCase):
    def test_the_base_variant_is_the_cartridge_untouched(self) -> None:
        # Arrange
        retail = dump.read(converge.RETAIL)

        # Act
        variants = recipes.variants(retail)

        # Assert
        self.assertEqual(sorted(variants), ["base", "both", "spc"])
        self.assertEqual(variants["base"], retail)

    def test_each_variant_carries_only_the_patches_its_name_promises(self) -> None:
        # Arrange
        retail = dump.read(converge.RETAIL)

        # Act
        variants = recipes.variants(retail)

        # Assert
        carried = {
            name: (spcfast.is_patched(image), shinakuma.is_patched(image))
            for name, image in variants.items()
        }
        self.assertEqual(
            carried, {"base": (False, False), "spc": (True, False), "both": (True, True)}
        )


script.entry(__name__, unittest.main)
