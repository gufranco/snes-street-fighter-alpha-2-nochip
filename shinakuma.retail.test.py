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


shinakuma = load_module("shinakuma")

USA = ROOT / "roms" / "sfa2-usa-final.sfc"


class EntryTest(unittest.TestCase):
    def _paths(self) -> tuple[Path, Path]:
        where = Path(tempfile.mkdtemp())
        source = where / "in.sfc"
        source.write_bytes(USA.read_bytes())
        return source, where / "out.sfc"

    @unittest.skipUnless(USA.exists(), "the retail dump is supplied by the builder")
    def test_running_it_again_on_its_own_output_reports_rather_than_raising(self) -> None:
        # Arrange
        source, output = self._paths()
        shinakuma.main(["shinakuma.py", str(source), str(output)], say=lambda _l: None)
        said: list[str] = []

        # Act
        code = shinakuma.main(
            ["shinakuma.py", str(output), str(output.parent / "third.sfc")], say=said.append
        )

        # Assert
        self.assertEqual(code, 0)
        self.assertIn("already", " ".join(said))

    @unittest.skipUnless(USA.exists(), "the retail dump is supplied by the builder")
    def test_and_leaves_the_image_it_was_given_unchanged(self) -> None:
        # Arrange
        source, output = self._paths()
        shinakuma.main(["shinakuma.py", str(source), str(output)], say=lambda _l: None)
        third = output.parent / "third.sfc"

        # Act
        shinakuma.main(["shinakuma.py", str(output), str(third)], say=lambda _l: None)

        # Assert
        self.assertEqual(third.read_bytes(), output.read_bytes())

    @unittest.skipUnless(USA.exists(), "the retail dump is supplied by the builder")
    def test_patching_the_source_in_place_is_refused(self) -> None:
        # Arrange
        source, _ = self._paths()
        complained: list[Any] = []

        # Act
        code = shinakuma.main(
            ["shinakuma.py", str(source), str(source)],
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
        code = shinakuma.main(["shinakuma.py", str(source), str(output)], say=said.append)

        # Assert
        self.assertEqual(code, 0)
        self.assertTrue(output.exists())
        self.assertTrue(said)


if __name__ == "__main__":
    unittest.main(verbosity=2)
