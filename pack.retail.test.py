import importlib.util
import shutil
import tempfile
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent


def load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None, "no loader for that path"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


pack = load_module("pack", ROOT / "pack.py")

USA = pack.REGIONS["usa"].retail


@unittest.skipUnless(USA.exists(), "the retail dump is supplied by the builder")  # pragma: no cover
class BuildTest(unittest.TestCase):
    def _workdir(self) -> Path:
        where = Path(tempfile.mkdtemp(dir=pack.ROOT))
        self.addCleanup(shutil.rmtree, where, True)
        return where

    def test_the_whole_pipeline_produces_an_image_larger_than_the_dump(self) -> None:
        image = pack.build("usa", self._workdir())

        self.assertGreater(len(image), len(USA.read_bytes()))

    def test_and_it_is_the_size_the_build_declares(self) -> None:
        image = pack.build("usa", self._workdir())

        self.assertEqual(len(image), pack.rombuild.IMAGE_SIZE)

    def test_the_same_dump_twice_produces_the_same_image(self) -> None:
        first = pack.build("usa", self._workdir())
        second = pack.build("usa", self._workdir())

        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
