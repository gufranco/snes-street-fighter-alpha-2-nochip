import importlib.util
import random
import sys
import unittest
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hardware

sdd1 = hardware.load("sdd1")
dump = hardware.load("romimage").dump


ROOT = Path(__file__).resolve().parent


def load_module(name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, ROOT / f"{name}.py")
    assert spec is not None and spec.loader is not None, "no loader for that path"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ref = load_module("sdd1ref")

STAR_OCEAN = ROOT / "roms" / "star-ocean-jp-original.sfc"
ALPHA2 = ROOT / "roms" / "sfa2-usa-final.sfc"


@unittest.skipUnless(ref.reference_available(), "sdd1ref runs inside ./run.sh")
@unittest.skipUnless(STAR_OCEAN.exists() and ALPHA2.exists(), "reference roms are not present")
class DifferentialTest(unittest.TestCase):
    def mismatches(self, rom: bytes | bytearray, cases: list[tuple[int, int]]) -> list[int]:
        expected = ref.reference_outputs(rom, cases)
        return [
            offset
            for (offset, length), want in zip(cases, expected, strict=True)
            if sdd1.decompress(rom, offset, length).data != want
        ]

    def test_it_agrees_with_the_c_reference_on_arbitrary_star_ocean_offsets(self) -> None:
        # Arrange
        rom = dump.read(STAR_OCEAN)
        rng = random.Random(20260813)
        cases = [
            (rng.randrange(len(rom) - 65536), rng.choice([1, 2, 15, 64, 832, 4096]))
            for _ in range(400)
        ]

        # Act
        found = self.mismatches(rom, cases)

        # Assert
        self.assertEqual(found, [])

    def test_it_agrees_with_the_c_reference_on_every_header_configuration(self) -> None:
        # Arrange
        rom = bytearray(dump.read(ALPHA2)[:262144])
        cases = []
        for index in range(16):
            offset = 4096 * (index + 1)
            rom[offset] = (index & 0x0F) << 4
            cases.append((offset, 2048))

        # Act
        found = self.mismatches(bytes(rom), cases)

        # Assert
        self.assertEqual(found, [])

    def test_it_agrees_with_the_c_reference_on_a_full_64k_block(self) -> None:
        # Arrange
        rom = dump.read(STAR_OCEAN)

        # Act
        found = self.mismatches(rom, [(0x101010, 0)])

        # Assert
        self.assertEqual(found, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
