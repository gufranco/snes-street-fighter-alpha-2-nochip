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


spcfast = load_module("spcfast")

USA = ROOT / "roms" / "sfa2-usa-final.sfc"


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
        code = spcfast.main(
            ["spcfast.py", str(source), str(source)],
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
        code = spcfast.main(["spcfast.py", str(source), str(output)], say=said.append)

        # Assert
        self.assertEqual(code, 0)
        self.assertTrue(output.exists())
        self.assertTrue(said)


if __name__ == "__main__":
    unittest.main(verbosity=2)
