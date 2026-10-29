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


sites = load_module("sdd1sites")

sdd1map = load_module("sdd1map")

RETAIL = ROOT / "roms" / "sfa2-usa-final.sfc"

TAGGED = ROOT / "roms" / "sfa2-usa-vc-sound-restored.sfc"

EXPECTED_ARM_SITES = 7

KNOWN_ARM_OFFSETS = (
    0x000482,
    0x00085A,
    0x000881,
    0x0077BF,
    0x12BBD3,
    0x1AE002,
    0x1AE131,
)


@unittest.skipUnless(RETAIL.exists() and TAGGED.exists(), "roms are not present")
class RealRomTest(unittest.TestCase):
    found: ClassVar[Any]
    mask: ClassVar[Any]
    rom: ClassVar[Any]

    @classmethod
    @override
    def setUpClass(cls) -> None:
        cls.rom = dump.read(RETAIL)
        entries = sdd1map.build_map(dump.read(TAGGED))
        cls.mask = sites.compressed_mask(cls.rom, entries)
        cls.found = sites.find_register_writes(cls.rom, cls.mask)

    def test_the_arm_register_is_written_from_exactly_seven_places(self) -> None:
        arms = [f for f in self.found if f.register == sites.ARM_REGISTER]

        self.assertEqual(len(arms), EXPECTED_ARM_SITES)
        self.assertEqual(tuple(f.offset for f in arms), KNOWN_ARM_OFFSETS)

    def test_no_register_write_hides_inside_compressed_data(self) -> None:
        for found in self.found:
            self.assertFalse(self.mask[found.offset])

    def test_every_arm_site_is_followed_by_a_dma_start(self) -> None:
        for offset in KNOWN_ARM_OFFSETS:
            listing = sites.window(self.rom, offset, forward=16)
            after = [i for i in listing if i.offset > offset]

            self.assertTrue(
                any(i.text == "sta $420b" for i in after[:4]),
                f"no dma start after {offset:#x}",
            )

    def test_the_window_resynchronises_onto_the_site(self) -> None:
        listing = sites.window(self.rom, KNOWN_ARM_OFFSETS[0])

        self.assertIn(KNOWN_ARM_OFFSETS[0], [i.offset for i in listing])

    def test_every_arm_site_sits_in_a_bank_reachable_as_lorom_code(self) -> None:
        for offset in KNOWN_ARM_OFFSETS:
            address = sites.lorom_address(offset)

            self.assertLess(address >> 16, 0x80)
            self.assertGreaterEqual(address & 0xFFFF, 0x8000)


script.entry(__name__, unittest.main)
