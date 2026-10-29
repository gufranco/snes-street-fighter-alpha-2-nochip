import importlib.util
import tempfile
import unittest
from pathlib import Path
from typing import Any, ClassVar, override

import hardware
import script

ROOT = Path(__file__).resolve().parent


dump = hardware.load("romimage").dump


JP = ROOT / "roms" / "sfz2-jp-final.sfc"


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


@unittest.skipUnless(USA.exists() and JP.exists(), "the retail ROMs are not present")
class RetailRomTest(unittest.TestCase):
    jp: ClassVar[Any]
    usa: ClassVar[Any]

    @classmethod
    @override
    def setUpClass(cls) -> None:
        cls.usa = dump.read(USA)
        cls.jp = dump.read(JP)

    def test_the_gate_is_present_exactly_once_in_each_region(self) -> None:
        self.assertEqual(shinakuma.find_gate(self.usa), 0x00EC6E)
        self.assertEqual(shinakuma.find_gate(self.jp), 0x00ECA0)

    def test_the_gate_is_byte_identical_across_regions(self) -> None:
        usa = shinakuma.find_gate(self.usa)
        jp = shinakuma.find_gate(self.jp)

        self.assertEqual(
            self.usa[usa : usa + len(shinakuma.GATE)],
            self.jp[jp : jp + len(shinakuma.GATE)],
        )

    def test_patching_touches_only_the_branch_and_the_checksum(self) -> None:
        patched = shinakuma.apply(self.usa)
        changed = {i for i in range(len(patched)) if patched[i] != self.usa[i]}
        site = 0x00EC6E + shinakuma.PRECONDITION
        allowed = {site, site + 1} | set(
            range(shinakuma.spcfast.CHECKSUM_FIELD, shinakuma.spcfast.CHECKSUM_FIELD + 4)
        )

        self.assertTrue(changed.issubset(allowed))
        self.assertIn(site, changed)
        self.assertIn(site + 1, changed)

    def test_the_substitution_handler_is_untouched(self) -> None:
        patched = shinakuma.apply(self.usa)

        self.assertEqual(patched[0x00CA7F:0x00CAD0], self.usa[0x00CA7F:0x00CAD0])

    def test_both_regions_patch_at_their_own_offset(self) -> None:
        for rom, offset in ((self.usa, 0x00EC6E), (self.jp, 0x00ECA0)):
            patched = shinakuma.apply(rom)
            site = offset + shinakuma.PRECONDITION

            self.assertEqual(patched[site : site + 2], shinakuma.BRANCH)


script.entry(__name__, unittest.main, verbosity=2)
