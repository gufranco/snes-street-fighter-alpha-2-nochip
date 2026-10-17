import importlib.util
import tempfile
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent


def load_module(name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, ROOT / f"{name}.py")
    assert spec is not None and spec.loader is not None, "no loader for that path"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


repeatload = load_module("repeatload")
spcfast = load_module("spcfast")

USA = ROOT / "roms" / "sfa2-usa-final.sfc"
JP = ROOT / "roms" / "sfz2-jp-final.sfc"


def retail(path: Path) -> bytes:
    if not path.exists():
        raise unittest.SkipTest(f"{path} is not present")
    return path.read_bytes()


class SiteTest(unittest.TestCase):
    def test_the_hook_site_carries_the_expected_instruction_in_both_regions(self) -> None:
        # Arrange
        roms = [retail(path) for path in (USA, JP)]

        # Act
        sites = [
            rom[repeatload.HOOK_FILE : repeatload.HOOK_FILE + len(repeatload.REPLACED)]
            for rom in roms
        ]

        # Assert
        self.assertEqual(sites, [repeatload.REPLACED, repeatload.REPLACED])

    def test_the_filler_is_free_in_both_regions(self) -> None:
        # Arrange
        roms = [retail(path) for path in (USA, JP)]

        # Act
        windows = [
            set(rom[repeatload.FILLER_FILE : repeatload.FILLER_FILE + repeatload.FILLER_SIZE])
            for rom in roms
        ]

        # Assert
        self.assertEqual(windows, [{0xFF}, {0xFF}])


class ApplyTest(unittest.TestCase):
    def test_applying_installs_the_hook_and_the_routine(self) -> None:
        # Arrange
        roms = [retail(path) for path in (USA, JP)]

        # Act
        patched = [repeatload.apply(rom) for rom in roms]

        # Assert
        self.assertEqual(
            [image[repeatload.HOOK_FILE : repeatload.HOOK_FILE + 3] for image in patched],
            [repeatload.hook(), repeatload.hook()],
        )
        self.assertEqual(
            [
                image[repeatload.FILLER_FILE : repeatload.FILLER_FILE + len(repeatload.ROUTINE)]
                for image in patched
            ],
            [repeatload.ROUTINE, repeatload.ROUTINE],
        )

    def test_applying_twice_changes_nothing_the_second_time(self) -> None:
        # Arrange
        once = repeatload.apply(retail(USA))

        # Act
        twice = repeatload.apply(once)

        # Assert
        self.assertEqual(twice, once)

    def test_nothing_outside_the_hook_and_the_routine_moves(self) -> None:
        # Arrange
        rom = retail(USA)

        # Act
        patched = repeatload.apply(rom)

        # Assert
        allowed = set(range(repeatload.HOOK_FILE, repeatload.HOOK_FILE + 3))
        allowed.update(
            range(repeatload.FILLER_FILE, repeatload.FILLER_FILE + len(repeatload.ROUTINE))
        )
        allowed.update(range(spcfast.CHECKSUM_FIELD, spcfast.CHECKSUM_FIELD + 4))
        moved = {at for at, (a, b) in enumerate(zip(rom, patched, strict=True)) if a != b}
        self.assertTrue(moved <= allowed, sorted(moved - allowed)[:8])


class EntryTest(unittest.TestCase):
    def _paths(self) -> tuple[Path, Path]:
        where = Path(tempfile.mkdtemp())
        source = where / "in.sfc"
        source.write_bytes(USA.read_bytes())
        return source, where / "out.sfc"

    @unittest.skipUnless(USA.exists(), "the retail dump is supplied by the builder")
    def test_patching_the_source_in_place_is_refused(self) -> None:
        # Arrange
        source, _ = self._paths()
        complained: list[Any] = []

        # Act
        code = repeatload.main(
            ["repeatload.py", str(source), str(source)],
            say=lambda _l: None,
            complain=complained.append,
        )

        # Assert
        self.assertEqual(code, 1)
        self.assertIn("in place", complained[0])

    @unittest.skipUnless(USA.exists(), "the retail dump is supplied by the builder")
    def test_a_run_writes_the_patched_image_and_says_what_it_did(self) -> None:
        # Arrange
        source, output = self._paths()
        said: list[Any] = []

        # Act
        code = repeatload.main(["repeatload.py", str(source), str(output)], say=said.append)

        # Assert
        self.assertEqual(code, 0)
        self.assertTrue(output.exists())
        self.assertTrue(said)


if __name__ == "__main__":
    unittest.main()
