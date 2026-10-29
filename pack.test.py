import contextlib
import importlib.util
import shutil
import subprocess
import tempfile
import unittest
from collections.abc import Iterator
from pathlib import Path
from typing import Any, override

import script

ROOT = Path(__file__).resolve().parent


def load_module(name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, ROOT / f"{name}.py")
    assert spec is not None and spec.loader is not None, "no loader for that path"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


pack = load_module("pack")
version = load_module("version")


class RegionTest(unittest.TestCase):
    def test_both_cartridges_are_covered(self) -> None:
        self.assertEqual(sorted(pack.REGIONS), ["jp", "usa"])

    def test_each_region_names_its_retail_dump_and_its_patch(self) -> None:
        for region in pack.REGIONS.values():
            self.assertTrue(region.retail.name.endswith(".sfc"))
            self.assertTrue(region.bypass.endswith(".asm"))

    def test_the_two_regions_use_different_sources(self) -> None:
        self.assertNotEqual(pack.REGIONS["usa"].retail, pack.REGIONS["jp"].retail)


class NameTest(unittest.TestCase):
    def test_the_output_carries_the_region_and_the_version(self) -> None:
        name = pack.output_name("usa", "1.4.2")

        self.assertEqual(name, "sfa2-usa-nochip-v1.4.2.sfc")

    def test_the_japanese_output_uses_its_own_title(self) -> None:
        self.assertEqual(pack.output_name("jp", "1.4.2"), "sfz2-jp-nochip-v1.4.2.sfc")

    def test_an_unreleased_build_says_so(self) -> None:
        self.assertIn("-dev", pack.output_name("usa", version.UNRELEASED))

    def test_an_unknown_region_is_rejected(self) -> None:
        with self.assertRaises(KeyError):
            pack.output_name("eu", "1.0.0")


class ManifestTest(unittest.TestCase):
    def test_a_manifest_line_pairs_the_digest_with_the_name(self) -> None:
        line = pack.manifest_line("name.sfc", b"abc")

        self.assertTrue(line.endswith("  name.sfc"))
        self.assertEqual(len(line.split("  ")[0]), 64)

    def test_the_digest_is_of_the_image_and_not_the_name(self) -> None:
        first = pack.manifest_line("a.sfc", b"same")
        second = pack.manifest_line("b.sfc", b"same")

        self.assertEqual(first.split("  ")[0], second.split("  ")[0])


class AssemblyFailureTest(unittest.TestCase):
    @staticmethod
    def result(returncode: int = 1, stdout: str = "", stderr: str = "") -> Any:
        return subprocess.CompletedProcess(
            args=["python3", "build.py"], returncode=returncode, stdout=stdout, stderr=stderr
        )

    def test_the_message_names_the_region_and_the_exit_code(self) -> None:
        message = pack.assembly_failure("jp", self.result(returncode=3))

        self.assertIn("jp", message)
        self.assertIn("3", message)

    def test_what_the_assembler_said_is_carried_and_not_discarded(self) -> None:
        # Arrange
        done = self.result(stdout="staged the rom", stderr="asar is not in this environment")

        # Act
        message = pack.assembly_failure("usa", done)

        # Assert
        self.assertIn("asar is not in this environment", message)
        self.assertIn("staged the rom", message)

    def test_an_empty_stream_adds_no_heading(self) -> None:
        message = pack.assembly_failure("jp", self.result(stderr="only this"))

        self.assertNotIn("stdout", message)
        self.assertIn("stderr", message)

    def test_the_message_points_at_the_launcher(self) -> None:
        # Arrange
        done = self.result()

        # Act
        message = pack.assembly_failure("jp", done)

        # Assert
        self.assertIn("pack.py through the launcher: ./run.sh pack.py", message)

    def test_a_failure_is_raised_as_its_own_kind_of_error(self) -> None:
        self.assertTrue(issubclass(pack.AssemblyFailed, Exception))


class LoadingTest(unittest.TestCase):
    def test_the_model_it_loads_is_the_image_handling_one(self) -> None:
        self.assertTrue(hasattr(pack.load_images(), "dump"))

    def test_a_tree_without_it_stops_with_what_the_loader_said(self) -> None:
        def absent(_name: str) -> Any:
            raise pack.hardware.ModelMissing("run git submodule update")

        with self.assertRaises(SystemExit) as raised:
            pack.load_images(absent)

        self.assertIn("git submodule update", str(raised.exception))


class EntriesTest(unittest.TestCase):
    def test_the_usa_table_becomes_entries(self) -> None:
        self.assertTrue(pack.entries_for("usa"))

    def test_and_the_japanese_one_becomes_different_entries(self) -> None:
        self.assertNotEqual(pack.entries_for("jp"), pack.entries_for("usa"))


class ShellingOutTest(unittest.TestCase):
    def test_the_real_path_runs_the_command_it_was_given(self) -> None:
        self.assertEqual(pack._shell_out(["true"]).returncode, 0)


class AssembleTest(unittest.TestCase):
    def test_the_command_names_the_patch_and_where_the_output_goes(self) -> None:
        found = pack.assemble_command("usa", pack.ROOT / "dist" / "x.sfc", "usa-bypass.sfc")

        self.assertIn("build.py", found)
        self.assertIn("usa-bypass.sfc", found)

    def _under_root(self) -> Path:
        where = Path(tempfile.mkdtemp(dir=pack.ROOT))
        self.addCleanup(shutil.rmtree, where, True)
        return where

    def test_an_assembler_that_fails_carries_what_it_said(self) -> None:
        failed = type("Done", (), {"returncode": 1, "stdout": "out", "stderr": "asar said no"})

        with self.assertRaises(pack.AssemblyFailed) as raised:
            pack.assemble_bypass("usa", b"\x00" * 16, self._under_root(), lambda _a: failed)

        self.assertIn("asar said no", str(raised.exception))

    def test_and_says_to_start_through_the_launcher(self) -> None:
        # Arrange
        failed = type("Done", (), {"returncode": 1, "stdout": "", "stderr": ""})

        # Act
        with self.assertRaises(pack.AssemblyFailed) as raised:
            pack.assemble_bypass("usa", b"\x00" * 16, self._under_root(), lambda _a: failed)

        # Assert
        self.assertIn("./run.sh pack.py", str(raised.exception))

    def test_an_assembler_that_succeeds_hands_back_the_image_it_wrote(self) -> None:
        done = type("Done", (), {"returncode": 0, "stdout": "", "stderr": ""})
        produced = pack.ROOT / "asm" / "usa-bypass.sfc"
        produced.write_bytes(b"\xab" * 32)
        self.addCleanup(lambda: produced.unlink() if produced.exists() else None)

        found = pack.assemble_bypass("usa", b"\x00" * 16, self._under_root(), lambda _a: done)

        self.assertEqual(found, b"\xab" * 32)


@contextlib.contextmanager
def a_dump_in_place(region: str = "usa") -> Iterator[Path]:
    original = pack.REGIONS[region]
    with tempfile.TemporaryDirectory() as where:
        stand_in = Path(where) / "stand-in.sfc"
        stand_in.write_bytes(b"\x00")
        pack.REGIONS[region] = original._replace(retail=stand_in)
        try:
            yield stand_in
        finally:
            pack.REGIONS[region] = original


class EntryTest(unittest.TestCase):
    def test_a_region_nobody_knows_is_refused(self) -> None:
        complained: list[Any] = []

        code = pack.main(["pack.py", "mars"], say=lambda _l: None, complain=complained.append)

        self.assertEqual(code, 2)
        self.assertIn("unknown region", complained[0])

    def test_a_dump_that_is_not_here_is_named_rather_than_guessed_at(self) -> None:
        complained: list[Any] = []
        original = pack.REGIONS["usa"]
        pack.REGIONS["usa"] = original._replace(retail=Path("/nowhere/at/all.sfc"))
        try:
            code = pack.main(["pack.py", "usa"], say=lambda _l: None, complain=complained.append)
        finally:
            pack.REGIONS["usa"] = original

        self.assertEqual(code, 1)
        self.assertIn("not present", complained[0])
        self.assertIn("nowhere", " ".join(complained))

    def test_a_table_that_does_not_pass_the_gate_stops_the_build(self) -> None:
        complained: list[Any] = []

        with a_dump_in_place():
            code = pack.main(
                ["pack.py", "usa"],
                gate_check=lambda _region: ["a stream is missing"],
                say=lambda _l: None,
                complain=complained.append,
            )

        self.assertIn(code, (1,))
        self.assertIn("does not pass the gate", " ".join(complained))

    def test_a_patch_that_will_not_assemble_stops_it_too(self) -> None:
        def boom(_region: str, _workdir: Path) -> Any:
            raise pack.AssemblyFailed("asar said no")

        complained: list[Any] = []
        with tempfile.TemporaryDirectory() as tmp, a_dump_in_place():
            code = pack.main(
                ["pack.py", "usa"],
                make=boom,
                gate_check=lambda _region: [],
                say=lambda _l: None,
                complain=complained.append,
                dist=tmp,
            )

        self.assertEqual(code, 1)
        self.assertIn("asar said no", complained[0])

    def test_a_whole_run_writes_an_image_and_a_manifest(self) -> None:
        # Arrange
        said: list[Any] = []

        # Act
        with tempfile.TemporaryDirectory() as tmp, a_dump_in_place():
            code = pack.main(
                ["pack.py", "usa"],
                make=lambda _region, _workdir: b"\x00" * 64,
                gate_check=lambda _region: [],
                say=said.append,
                dist=tmp,
                forms=two_forms,
            )
            written = (Path(tmp) / pack.release_folder() / pack.MANIFEST).read_text()

        # Assert
        self.assertEqual(code, 0)
        self.assertIn(f"emulator/{pack.output_name('usa')}", written)
        self.assertIn("64 bytes", " ".join(said))

    def test_the_plain_image_lands_in_the_emulator_folder_of_the_release(self) -> None:
        # Arrange
        said: list[Any] = []

        # Act
        with tempfile.TemporaryDirectory() as tmp, a_dump_in_place():
            code = pack.main(
                ["pack.py", "usa"],
                make=lambda _region, _workdir: b"\x00" * 64,
                gate_check=lambda _region: [],
                say=said.append,
                dist=tmp,
                forms=two_forms,
            )
            release = Path(tmp) / pack.release_folder()
            plain = (release / "emulator" / pack.output_name("usa")).read_bytes()
            listed = (release / pack.MANIFEST).read_text().splitlines()

        # Assert
        self.assertEqual(code, 0)
        self.assertEqual(plain, b"\x00" * 64)
        self.assertEqual(len(listed), 2)
        self.assertIn("2 images", said[-1])

    def test_a_headed_form_lands_in_its_own_device_folder(self) -> None:
        # Arrange
        said: list[Any] = []

        # Act
        with tempfile.TemporaryDirectory() as tmp, a_dump_in_place():
            code = pack.main(
                ["pack.py", "usa"],
                make=lambda _region, _workdir: b"\x00" * 64,
                gate_check=lambda _region: [],
                say=said.append,
                dist=tmp,
                forms=two_forms,
            )
            release = Path(tmp) / pack.release_folder()
            headed = (release / "gamedoctor" / pack.headed_name("usa")).read_bytes()
            listed = (release / pack.MANIFEST).read_text().splitlines()

        # Assert
        self.assertEqual(code, 0)
        self.assertEqual(headed, b"\x01" * 16 + b"\x00" * 64)
        self.assertEqual(len(listed), 2)
        self.assertIn("80 bytes", " ".join(said))
        self.assertIn("2 images", said[-1])

    def test_an_option_from_before_every_device_was_written_is_refused(self) -> None:
        # Arrange
        complained: list[Any] = []

        # Act
        code = pack.main(
            ["pack.py", "usa", "--fxpak"], say=lambda _l: None, complain=complained.append
        )

        # Assert
        self.assertEqual(code, 2)
        self.assertIn("--fxpak", complained[0])
        self.assertIn("unknown region", complained[0])

    def test_no_region_named_builds_every_region(self) -> None:
        # Arrange
        built: list[str] = []

        def record(region: str, _workdir: Path) -> bytes:
            built.append(region)
            return b"\x00" * 64

        # Act
        with tempfile.TemporaryDirectory() as tmp, a_dump_in_place("usa"), a_dump_in_place("jp"):
            code = pack.main(
                ["pack.py"],
                make=record,
                gate_check=lambda _region: [],
                say=lambda _l: None,
                dist=tmp,
                forms=two_forms,
            )

        # Assert
        self.assertEqual(code, 0)
        self.assertEqual(built, ["jp", "usa"])


def two_forms(region: str, image: bytes) -> list[tuple[str, bytes]]:
    return [
        (f"emulator/{pack.output_name(region)}", image),
        (f"gamedoctor/{pack.headed_name(region)}", b"\x01" * 16 + image),
    ]


def headed_image() -> bytearray:
    image = bytearray(0x10000)
    for anchor in (0x7FC0, 0xFFC0):
        image[anchor : anchor + 21] = b"SYNTHETIC SD2SNES IMG"
        image[anchor + pack.rewrite.MAP_MODE] = 0x32
        image[anchor + pack.rewrite.ROM_SIZE] = 0x06
    return image


def with_a_stale_copy() -> bytearray:
    image = headed_image()
    image[0xFFC0 + 0x16] = 0x43
    image[0xFFC0 + 0x17] = 0x0C
    image[0xFFC0 + 0x1C : 0xFFC0 + 0x20] = b"\x66\x24\x99\xdb"
    return image


class UnifyHeadersTest(unittest.TestCase):
    def test_a_copy_differing_only_past_the_map_byte_is_found(self) -> None:
        # Arrange
        image = with_a_stale_copy()

        # Act
        copies = pack.header_copies(image)

        # Assert
        self.assertEqual(copies, [0x7FC0, 0xFFC0])

    def test_every_copy_ends_up_carrying_the_same_header(self) -> None:
        # Arrange
        image = with_a_stale_copy()

        # Act
        unified = pack.unify_headers(image)

        # Assert
        self.assertEqual(unified[0x7FC0:0x7FE0], unified[0xFFC0:0xFFE0])

    def test_so_the_rewrite_then_reaches_both_of_them(self) -> None:
        # Arrange
        image = with_a_stale_copy()

        # Act
        declared = pack.rewrite.declare_rom_only(pack.unify_headers(image))

        # Assert
        self.assertEqual([declared[at + 0x16] for at in (0x7FC0, 0xFFC0)], [0x00, 0x00])

    def test_a_title_away_from_a_bank_end_is_not_a_header(self) -> None:
        # Arrange
        image = with_a_stale_copy()
        image[0x1234 : 0x1234 + 22] = image[0x7FC0 : 0x7FC0 + 22]

        # Act
        copies = pack.header_copies(image)

        # Assert
        self.assertEqual(copies, [0x7FC0, 0xFFC0])

    def test_an_image_with_no_header_is_left_alone(self) -> None:
        # Arrange
        image = bytes(0x10000)

        # Act
        unified = pack.unify_headers(image)

        # Assert
        self.assertEqual(unified, image)


class HeadedNameTest(unittest.TestCase):
    def test_a_form_with_a_copier_header_keeps_the_name_and_says_smc(self) -> None:
        # Arrange
        release = "1.6.0"

        # Act
        name = pack.headed_name("usa", release)

        # Assert
        self.assertEqual(name, "sfa2-usa-nochip-v1.6.0.smc")

    def test_the_release_folder_is_the_version(self) -> None:
        # Arrange
        release = "1.6.0"

        # Act
        folder = pack.release_folder(release)

        # Assert
        self.assertEqual(folder, "v1.6.0")

    def test_an_unreleased_folder_says_so(self) -> None:
        # Arrange
        release = version.UNRELEASED

        # Act
        folder = pack.release_folder(release)

        # Assert
        self.assertEqual(folder, "v0.0.0-dev")


def chip_free_image() -> bytes:
    image = bytearray(0xC00000)
    for anchor in (0x7FC0, 0xFFC0):
        image[anchor : anchor + 21] = b"SYNTHETIC CHIP FREE  "
        image[anchor + pack.rewrite.MAP_MODE] = 0x32
        image[anchor + 0x1A] = 0x33
        image[anchor + 0x3C : anchor + 0x3E] = b"\x00\x80"
    declared: bytes = pack.rewrite.declare_rom_only(image)
    return declared


class DeviceFormTest(unittest.TestCase):
    image: bytes
    forms: dict[str, bytes]

    @classmethod
    @override
    def setUpClass(cls) -> None:
        cls.image = chip_free_image()
        cls.forms = dict(pack.forms_of("usa", cls.image))

    def sd2snes(self) -> bytes:
        return self.forms[f"sd2snes/{pack.headed_name('usa')}"]

    def test_every_device_gets_its_own_folder(self) -> None:
        # Arrange
        expected = list(pack.DEVICES)

        # Act
        folders = [name.split("/")[0] for name in self.forms]

        # Assert
        self.assertEqual(folders, expected)

    def test_an_emulator_and_a_super_everdrive_take_the_image_as_built(self) -> None:
        # Arrange
        name = pack.output_name("usa")

        # Act
        plain = (self.forms[f"emulator/{name}"], self.forms[f"supereverdrive/{name}"])

        # Assert
        self.assertEqual(plain, (self.image, self.image))

    def test_the_sd2snes_and_the_fxpak_get_the_same_file(self) -> None:
        # Arrange
        name = pack.headed_name("usa")

        # Act
        fxpak = self.forms[f"fxpak/{name}"]

        # Assert
        self.assertEqual(fxpak, self.sd2snes())

    def test_a_512_byte_empty_copier_header_comes_first(self) -> None:
        # Arrange
        expected = 0xC00000 + 512

        # Act
        written = self.sd2snes()

        # Assert
        self.assertEqual(len(written), expected)
        self.assertEqual(written[:512], bytes(512))

    def test_every_header_copy_declares_the_chip_the_firmware_keys_on(self) -> None:
        # Arrange
        copies = (0x7FC0, 0xFFC0)

        # Act
        body = self.sd2snes()[512:]

        # Assert
        self.assertEqual([body[at + 0x16] for at in copies], [0x43, 0x43])

    def test_the_map_byte_is_left_as_it_was(self) -> None:
        # Arrange
        copies = (0x7FC0, 0xFFC0)

        # Act
        body = self.sd2snes()[512:]

        # Assert
        self.assertEqual([body[at + 0x15] for at in copies], [0x32, 0x32])

    def test_every_copy_carries_a_checksum_that_matches_the_bytes(self) -> None:
        # Arrange
        copies = (0x7FC0, 0xFFC0)

        # Act
        body = self.sd2snes()[512:]

        # Assert
        for at in copies:
            complement = body[at + 0x1C] | body[at + 0x1D] << 8
            value = body[at + 0x1E] | body[at + 0x1F] << 8
            self.assertEqual(value, pack.rewrite.checksum(body, list(copies)))
            self.assertEqual(complement ^ value, 0xFFFF)

    def test_nothing_outside_the_chip_and_checksum_fields_changes(self) -> None:
        # Arrange
        touched = {
            at + offset for at in (0x7FC0, 0xFFC0) for offset in (0x16, 0x1C, 0x1D, 0x1E, 0x1F)
        }

        # Act
        body = self.sd2snes()[512:]

        # Assert
        moved = {at for at in range(0x10000) if body[at] != self.image[at]}
        self.assertLessEqual(moved, touched)
        self.assertEqual(body[0x10000:], self.image[0x10000:])

    def test_the_game_doctor_file_maps_all_twenty_four_chunks_in_order(self) -> None:
        # Arrange
        name = pack.headed_name("usa")

        # Act
        written = self.forms[f"gamedoctor/{name}"]

        # Assert
        self.assertEqual(
            (written[:16], written[0x11:0x29], written[0x200:]),
            (b"GAME DOCTOR SF 3", bytes(range(0x20, 0x38)), self.image),
        )

    def test_an_image_with_no_header_is_refused(self) -> None:
        # Arrange
        image = bytes(0xC00000)

        # Act
        with self.assertRaises(pack.rewrite.NoHeader) as raised:
            pack.forms_of("usa", image)

        # Assert
        self.assertIn("no cartridge header", str(raised.exception))


script.entry(__name__, unittest.main, verbosity=2)
