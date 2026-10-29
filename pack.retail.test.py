import importlib.util
import shutil
import tempfile
import unittest
from pathlib import Path
from typing import Any

import script

ROOT = Path(__file__).resolve().parent


def load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None, "no loader for that path"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


pack = load_module("pack", ROOT / "pack.py")
release = load_module("pack.retail", ROOT / "pack.retail.py")

USA = pack.REGIONS["usa"].retail


@unittest.skipUnless(USA.exists(), "the retail dump is supplied by the builder")
class BuildTest(unittest.TestCase):
    def _workdir(self) -> Path:
        where = Path(tempfile.mkdtemp(dir=pack.ROOT))
        self.addCleanup(shutil.rmtree, where, True)
        return where

    def test_the_whole_pipeline_produces_an_image_larger_than_the_dump(self) -> None:
        image = release.build("usa", self._workdir())

        self.assertGreater(len(image), len(USA.read_bytes()))

    def test_and_it_is_the_size_the_build_declares(self) -> None:
        image = release.build("usa", self._workdir())

        self.assertEqual(len(image), pack.rombuild.IMAGE_SIZE)

    def test_all_six_header_copies_declare_no_chip_and_agree(self) -> None:
        # Arrange
        places = (0x7FC0, 0xFFC0, 0x407FC0, 0x40FFC0, 0x607FC0, 0xA07FC0)

        # Act
        image = release.build("usa", self._workdir())

        # Assert
        self.assertEqual([image[at + 0x16] for at in places], [0x00] * 6)
        self.assertEqual(len({image[at : at + 0x20] for at in places}), 1)

    def test_the_sd2snes_form_declares_the_chip_in_all_six_and_is_the_size_it_wants(self) -> None:
        # Arrange
        places = (0x7FC0, 0xFFC0, 0x407FC0, 0x40FFC0, 0x607FC0, 0xA07FC0)

        # Act
        derived = dict(pack.forms_of("usa", release.build("usa", self._workdir())))[
            f"{pack.SD2SNES}/{pack.headed_name('usa')}"
        ]

        # Assert
        self.assertEqual(len(derived), 0xC00200)
        self.assertEqual([derived[0x200 + at + 0x16] for at in places], [0x43] * 6)
        self.assertEqual(len({derived[0x200 + at : 0x200 + at + 0x20] for at in places}), 1)

    def test_the_same_dump_twice_produces_the_same_image(self) -> None:
        first = release.build("usa", self._workdir())
        second = release.build("usa", self._workdir())

        self.assertEqual(first, second)


script.entry(__name__, unittest.main)
