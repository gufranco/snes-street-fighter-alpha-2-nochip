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


prefight = load_module("prefight")

USA = ROOT / "roms" / "sfa2-usa-final.sfc"
JP = ROOT / "roms" / "sfz2-jp-final.sfc"


def retail(path: Path) -> bytes:
    script.skip_unless(path.exists(), f"{path} is not present")
    return path.read_bytes()


class LocationTest(unittest.TestCase):
    def test_the_builder_is_found_once_in_each_region(self) -> None:
        # Arrange
        roms = [(path, retail(path)) for path in (USA, JP)]

        # Act
        found = {str(path): prefight.find_builder(rom) for path, rom in roms}

        # Assert
        for where, at in found.items():
            self.assertIsNotNone(at, where)

    def test_both_callers_are_found_in_each_region(self) -> None:
        # Arrange
        roms = [(path, retail(path)) for path in (USA, JP)]

        # Act
        counts = {str(path): len(prefight.find_callers(rom)) for path, rom in roms}

        # Assert
        self.assertEqual(counts, {str(USA): 2, str(JP): 2})

    def test_the_filler_is_free_in_each_region(self) -> None:
        # Arrange
        roms = [(path, retail(path)) for path in (USA, JP)]

        # Act
        windows = {
            str(path): set(rom[prefight.FILLER_FILE : prefight.FILLER_FILE + prefight.FILLER_SIZE])
            for path, rom in roms
        }

        # Assert
        self.assertEqual(windows, {str(USA): {0xFF}, str(JP): {0xFF}})


class ApplyTest(unittest.TestCase):
    def test_every_caller_is_redirected_to_the_routine(self) -> None:
        # Arrange
        roms = [(path, retail(path)) for path in (USA, JP)]

        # Act
        patched = [(path, rom, prefight.apply(rom)) for path, rom in roms]

        # Assert
        for path, rom, result in patched:
            for at in prefight.find_callers(rom):
                self.assertEqual(result[at], 0x22, str(path))
                target = int.from_bytes(result[at + 1 : at + 4], "little")
                self.assertEqual(target, prefight.ROUTINE_ADDRESS, str(path))

    def test_the_routine_lands_in_the_filler(self) -> None:
        # Arrange
        rom = retail(USA)

        # Act
        patched = prefight.apply(rom)

        # Assert
        emitted = prefight.routine()
        self.assertEqual(
            patched[prefight.FILLER_FILE : prefight.FILLER_FILE + len(emitted)], emitted
        )

    def test_applying_twice_changes_nothing_the_second_time(self) -> None:
        # Arrange
        rom = retail(USA)
        once = prefight.apply(rom)

        # Act
        twice = prefight.apply(once)

        # Assert
        self.assertEqual(twice, once)

    def test_the_builder_itself_is_left_in_place(self) -> None:
        # Arrange
        rom = retail(USA)
        at = prefight.find_builder(rom)

        # Act
        patched = prefight.apply(rom)

        # Assert
        self.assertEqual(patched[at : at + 32], rom[at : at + 32])

    def test_nothing_outside_the_callers_and_the_filler_moves(self) -> None:
        # Arrange
        rom = retail(USA)

        # Act
        patched = prefight.apply(rom)

        # Assert
        allowed: set[int] = set()
        for at in prefight.find_callers(rom):
            allowed.update(range(at, at + 4))
        allowed.update(range(prefight.FILLER_FILE, prefight.FILLER_FILE + len(prefight.routine())))
        moved = {at for at, (a, b) in enumerate(zip(rom, patched, strict=True)) if a != b}
        self.assertTrue(moved <= allowed, sorted(moved - allowed)[:8])


script.entry(__name__, unittest.main)
