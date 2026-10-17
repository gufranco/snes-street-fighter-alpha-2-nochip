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

HOOK_LITERAL = bytes.fromhex("2000f6")


def free_site() -> bytearray:
    rom = bytearray(repeatload.FILLER_END + 0x100)
    rom[repeatload.HOOK_FILE : repeatload.HOOK_FILE + 3] = bytes.fromhex("a90015")
    rom[repeatload.FILLER_FILE : repeatload.FILLER_END] = b"\xff" * 0x100
    return rom


def patched_site() -> bytes:
    rom = free_site()
    rom[repeatload.HOOK_FILE : repeatload.HOOK_FILE + 3] = HOOK_LITERAL
    rom[repeatload.FILLER_FILE : repeatload.FILLER_FILE + len(repeatload.ROUTINE)] = (
        repeatload.ROUTINE
    )
    return bytes(rom)


class RoutineTest(unittest.TestCase):
    def test_the_routine_ends_in_a_return(self) -> None:
        self.assertEqual(repeatload.ROUTINE[-1], 0x60)

    def test_the_routine_restores_the_instruction_it_replaced(self) -> None:
        self.assertEqual(repeatload.ROUTINE[-4:-1], bytes([0xA9, 0x00, 0x15]))

    def test_every_marker_access_is_long_addressed(self) -> None:
        loads = repeatload.ROUTINE.count(0xAF)
        stores = repeatload.ROUTINE.count(0x8F)

        self.assertEqual(loads, 3)
        self.assertEqual(stores, 3)

    def test_the_routine_fits_the_filler_it_is_written_into(self) -> None:
        self.assertLess(len(repeatload.ROUTINE), repeatload.FILLER_SIZE)

    def test_the_hook_is_a_call_to_the_routine(self) -> None:
        self.assertEqual(repeatload.hook(), bytes([0x20, repeatload.ROUTINE_ADDRESS & 0xFF, 0xF6]))

    def test_the_hook_is_the_same_length_as_what_it_replaces(self) -> None:
        self.assertEqual(len(repeatload.hook()), len(repeatload.REPLACED))

    def test_the_routine_matches_what_the_assembler_emits(self) -> None:
        assembled = ROOT / "asm" / "repeat-out.sfc"
        if not assembled.exists():
            raise unittest.SkipTest("assemble asm/repeat-load.asm first")

        produced = assembled.read_bytes()  # pragma: no cover

        self.assertEqual(  # pragma: no cover
            produced[repeatload.FILLER_FILE : repeatload.FILLER_FILE + len(repeatload.ROUTINE)],
            repeatload.ROUTINE,
        )


class SiteTest(unittest.TestCase):
    def test_the_marker_sits_inside_the_run_no_write_was_seen_in(self) -> None:
        first, last = 0x7E5E70, 0x7EFE3F

        self.assertGreaterEqual(repeatload.MARKER, first)
        self.assertLessEqual(repeatload.MARKER + 3, last)

    def test_the_marker_is_not_in_the_page_the_game_keeps_variables_in(self) -> None:
        self.assertGreater(repeatload.MARKER & 0xFFFF, 0x2000)

    def test_every_address_the_routine_touches_is_the_marker(self) -> None:
        touched = set()
        for at in range(len(repeatload.ROUTINE) - 3):
            if repeatload.ROUTINE[at] in (0xAF, 0x8F):
                operand = repeatload.ROUTINE[at + 1 : at + 4]
                touched.add(int.from_bytes(operand, "little"))

        self.assertEqual(touched, {repeatload.MARKER, repeatload.MARKER + 1, repeatload.MARKER + 2})


class ApplyTest(unittest.TestCase):
    def test_a_rom_without_the_site_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            repeatload.apply(b"\x00" * 0x100000)

    def test_it_does_not_collide_with_the_pre_fight_routine(self) -> None:
        prefight = load_module("prefight")

        first = range(prefight.FILLER_FILE, prefight.FILLER_FILE + len(prefight.ROUTINE))
        second = range(repeatload.FILLER_FILE, repeatload.FILLER_FILE + len(repeatload.ROUTINE))

        self.assertFalse(set(first) & set(second))


class RefusalTest(unittest.TestCase):
    def test_an_image_whose_filler_is_not_free_is_refused(self) -> None:
        rom = bytearray(repeatload.FILLER_END + 0x100)
        rom[repeatload.HOOK_FILE : repeatload.HOOK_FILE + len(repeatload.REPLACED)] = (
            repeatload.REPLACED
        )
        rom[repeatload.FILLER_FILE : repeatload.FILLER_END] = b"\xff" * (
            repeatload.FILLER_END - repeatload.FILLER_FILE
        )
        rom[repeatload.FILLER_FILE] = 0x00

        with self.assertRaises(ValueError) as raised:
            repeatload.apply(bytes(rom))

        self.assertIn("filler", str(raised.exception))

    def test_an_image_whose_allocator_setup_is_elsewhere_is_refused(self) -> None:
        rom = bytearray(repeatload.FILLER_END + 0x100)
        rom[repeatload.FILLER_FILE : repeatload.FILLER_END] = b"\xff" * (
            repeatload.FILLER_END - repeatload.FILLER_FILE
        )

        with self.assertRaises(ValueError) as raised:
            repeatload.apply(bytes(rom))

        self.assertIn("allocator setup", str(raised.exception))


class SyntheticApplyTest(unittest.TestCase):
    def test_applying_to_a_free_site_writes_the_call_to_the_routine(self) -> None:
        # Arrange
        rom = bytes(free_site())

        # Act
        patched = repeatload.apply(rom)

        # Assert
        self.assertEqual(patched[repeatload.HOOK_FILE : repeatload.HOOK_FILE + 3], HOOK_LITERAL)

    def test_applying_to_a_free_site_writes_the_routine_into_the_filler(self) -> None:
        # Arrange
        rom = bytes(free_site())

        # Act
        patched = repeatload.apply(rom)

        # Assert
        self.assertEqual(
            patched[repeatload.FILLER_FILE : repeatload.FILLER_FILE + len(repeatload.ROUTINE)],
            repeatload.ROUTINE,
        )

    def test_an_image_already_carrying_the_hook_and_routine_is_returned_unchanged(self) -> None:
        # Arrange
        rom = patched_site()

        # Act
        again = repeatload.apply(rom)

        # Assert
        self.assertEqual(again, rom)


class ReportTest(unittest.TestCase):
    def test_an_unpatched_image_is_reported_as_ready(self) -> None:
        # Arrange
        said: list[str] = []

        # Act
        repeatload.report(bytes(free_site()), said.append)

        # Assert
        self.assertEqual(
            said,
            [
                "  hook      $C7:0069  a9 00 15 -> 20 00 f6",
                "  routine   $C7:F600  61 bytes",
                "  marker    $7E9000  two byte magic and the last list id",
                "  state     ready",
            ],
        )

    def test_a_patched_image_is_reported_as_already_applied(self) -> None:
        # Arrange
        said: list[str] = []

        # Act
        repeatload.report(patched_site(), said.append)

        # Assert
        self.assertEqual(said[-1], "  state     already applied")


class EntryTest(unittest.TestCase):
    def _workdir(self) -> Path:
        where = tempfile.TemporaryDirectory()
        self.addCleanup(where.cleanup)
        return Path(where.name)

    def test_too_few_arguments_are_refused_with_the_usage(self) -> None:
        complained: list[Any] = []

        code = repeatload.main(["repeatload.py"], say=lambda _l: None, complain=complained.append)

        self.assertEqual(code, 2)
        self.assertIn("usage", complained[0])

    def test_naming_the_source_as_the_output_is_refused(self) -> None:
        # Arrange
        source = self._workdir() / "in.sfc"
        source.write_bytes(bytes(free_site()))
        complained: list[str] = []

        # Act
        code = repeatload.main(
            ["repeatload.py", str(source), str(source)],
            say=lambda _l: None,
            complain=complained.append,
        )

        # Assert
        self.assertEqual((code, complained), (1, ["refusing to patch the source ROM in place"]))

    def test_a_run_on_a_synthetic_image_writes_the_hook_to_the_output(self) -> None:
        # Arrange
        where = self._workdir()
        source, output = where / "in.sfc", where / "out.sfc"
        source.write_bytes(bytes(free_site()))

        # Act
        code = repeatload.main(["repeatload.py", str(source), str(output)], say=lambda _l: None)

        # Assert
        written = output.read_bytes()
        self.assertEqual(
            (code, written[repeatload.HOOK_FILE : repeatload.HOOK_FILE + 3]), (0, HOOK_LITERAL)
        )

    def test_a_run_ends_by_naming_the_output_and_its_size(self) -> None:
        # Arrange
        where = self._workdir()
        source, output = where / "in.sfc", where / "out.sfc"
        source.write_bytes(bytes(free_site()))
        said: list[str] = []

        # Act
        repeatload.main(["repeatload.py", str(source), str(output)], say=said.append)

        # Assert
        self.assertEqual(said[-1], f"[done] {output} (522,240 bytes)")


if __name__ == "__main__":
    unittest.main()
