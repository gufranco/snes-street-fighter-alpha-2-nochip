import importlib.util
import tempfile
import unittest
from pathlib import Path
from typing import Any

import hardware

wdc65816 = hardware.load("mos65xx")

ROOT = Path(__file__).resolve().parent


def load_module(name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, ROOT / f"{name}.py")
    assert spec is not None and spec.loader is not None, "no loader for that path"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


prefight = load_module("prefight")


class TableTest(unittest.TestCase):
    def test_the_table_is_the_size_the_builder_writes(self) -> None:
        self.assertEqual(len(prefight.table()), prefight.TABLE_SIZE)

    def test_the_table_is_the_same_every_time_it_is_built(self) -> None:
        self.assertEqual(prefight.table(), prefight.table())

    def test_the_first_entry_is_the_high_word_of_the_starting_value(self) -> None:
        self.assertEqual(prefight.table()[:2], bytes([0x4B, 0x00]))

    def test_every_entry_is_a_word(self) -> None:
        self.assertEqual(prefight.TABLE_SIZE % 2, 0)

    def test_the_table_fits_inside_one_bank_half(self) -> None:
        self.assertLess(prefight.TABLE_SIZE, 0x8000)


class RoutineTest(unittest.TestCase):
    def test_the_routine_ends_in_a_long_return(self) -> None:
        self.assertEqual(prefight.routine()[-1], 0x6B)

    def test_the_routine_starts_by_saving_the_flags(self) -> None:
        self.assertEqual(prefight.routine()[0], 0x08)

    def test_every_hardware_store_is_long_addressed(self) -> None:
        emitted = prefight.routine()
        listing = [
            ins
            for ins in wdc65816.disassemble(emitted, 0, prefight.ROUTINE_ADDRESS, m=True, x=True)
            if ins.address - prefight.ROUTINE_ADDRESS < len(emitted)
        ]
        stores = [ins for ins in listing if ins.mnemonic == "sta"]

        self.assertEqual(len(stores), 8)
        for store in stores:
            self.assertEqual(emitted[store.address - prefight.ROUTINE_ADDRESS], 0x8F)

    def test_the_routine_names_the_table_address_it_reads(self) -> None:
        emitted = prefight.routine()

        self.assertIn(bytes([prefight.TABLE_ADDRESS >> 16]), emitted)

    def test_the_routine_matches_what_the_assembler_emits(self) -> None:
        assembled = ROOT / "asm" / "prefight-out.sfc"
        if not assembled.exists():
            raise unittest.SkipTest("assemble asm/prefight-table.asm first")

        produced = assembled.read_bytes()  # pragma: no cover

        self.assertEqual(  # pragma: no cover
            produced[prefight.FILLER_FILE : prefight.FILLER_FILE + len(prefight.ROUTINE)],
            prefight.ROUTINE,
        )

    def test_the_routine_fits_the_filler_it_is_written_into(self) -> None:
        self.assertLess(len(prefight.routine()), prefight.FILLER_SIZE)


class LocationTest(unittest.TestCase):
    def test_a_rom_without_the_builder_reports_nothing(self) -> None:
        self.assertIsNone(prefight.find_builder(b"\x00" * 0x1000))


class ApplyTest(unittest.TestCase):
    def test_a_rom_without_the_builder_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            prefight.apply(b"\x00" * 0x1000)


def synthetic(builder: int = 0x030000, callers: tuple[int, ...] = (0x020000,)) -> bytearray:
    rom = bytearray(0x400000)
    rom[builder : builder + len(prefight.BUILDER_SIGNATURE)] = prefight.BUILDER_SIGNATURE
    rom[prefight.FILLER_FILE : prefight.FILLER_END] = b"\xff" * prefight.FILLER_SIZE
    window = prefight.WINDOW_FIRST_BANK + (builder >> 16)
    call = prefight.call_to((window << 16) | (builder & 0xFFFF))
    for site in callers:
        rom[site : site + len(call)] = call
    return rom


class SyntheticLocationTest(unittest.TestCase):
    def test_a_cartridge_without_the_builder_has_none(self) -> None:
        self.assertIsNone(prefight.find_builder(bytes(0x400000)))

    def test_a_builder_appearing_twice_is_refused(self) -> None:
        rom = synthetic()
        rom[0x050000 : 0x050000 + len(prefight.BUILDER_SIGNATURE)] = prefight.BUILDER_SIGNATURE

        with self.assertRaises(ValueError):
            prefight.find_builder(rom)

    def test_the_builder_is_found_where_it_was_put(self) -> None:
        self.assertEqual(prefight.find_builder(synthetic()), 0x030000)

    def test_a_cartridge_without_the_builder_has_no_callers(self) -> None:
        self.assertEqual(prefight.find_callers(bytes(0x400000)), [])

    def test_every_caller_is_found(self) -> None:
        rom = synthetic(callers=(0x020000, 0x021000, 0x022000))

        self.assertEqual(prefight.find_callers(rom), [0x020000, 0x021000, 0x022000])


class SyntheticApplyTest(unittest.TestCase):
    def test_a_cartridge_without_the_builder_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            prefight.apply(bytes(0x400000))

    def test_a_builder_nobody_calls_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            prefight.apply(synthetic(callers=()))

    def test_filler_that_is_not_free_is_refused(self) -> None:
        rom = synthetic()
        rom[prefight.FILLER_FILE] = 0x00

        with self.assertRaises(ValueError):
            prefight.apply(rom)

    def test_the_routine_lands_in_the_filler_of_a_stand_in(self) -> None:
        patched = prefight.apply(synthetic())

        emitted = prefight.routine()
        self.assertEqual(
            patched[prefight.FILLER_FILE : prefight.FILLER_FILE + len(emitted)], emitted
        )

    def test_the_caller_is_redirected(self) -> None:
        patched = prefight.apply(synthetic())

        self.assertEqual(
            patched[0x020000 : 0x020000 + 4], prefight.call_to(prefight.ROUTINE_ADDRESS)
        )

    def test_a_patched_cartridge_is_recognised_as_patched(self) -> None:
        self.assertTrue(prefight.is_patched(prefight.apply(synthetic())))

    def test_an_unpatched_cartridge_is_not(self) -> None:
        self.assertFalse(prefight.is_patched(synthetic()))

    def test_applying_twice_to_a_stand_in_changes_nothing(self) -> None:
        once = prefight.apply(synthetic())

        self.assertEqual(prefight.apply(once), once)


class ReportTest(unittest.TestCase):
    def test_a_cartridge_without_the_builder_is_said_to_have_none(self) -> None:
        said: list[str] = []

        prefight.report(bytes(0x400000), said.append)

        self.assertIn("no pre-fight table builder", said[0])

    def test_a_cartridge_with_one_has_it_named_with_its_bank(self) -> None:
        said: list[str] = []

        prefight.report(synthetic(), said.append)

        self.assertIn("$C3:0000", said[0])

    def test_every_caller_is_named(self) -> None:
        said: list[str] = []

        prefight.report(synthetic(callers=(0x020000, 0x021000)), said.append)

        self.assertEqual(len([one for one in said if "caller" in one]), 2)

    def test_the_table_it_will_build_is_named_with_its_size(self) -> None:
        said: list[str] = []

        prefight.report(synthetic(), said.append)

        self.assertIn(f"{prefight.TABLE_SIZE:,} bytes", said[-1])


class CommandTest(unittest.TestCase):
    def test_the_wrong_number_of_arguments_prints_the_usage(self) -> None:
        said: list[str] = []

        code = prefight.main(["prefight.py"], say=said.append)

        self.assertEqual((code, "usage" in said[0]), (2, True))

    def test_patching_a_cartridge_over_itself_is_refused(self) -> None:
        where = Path(tempfile.mkdtemp()) / "rom.sfc"
        where.write_bytes(bytes(synthetic()))
        said: list[str] = []

        code = prefight.main(["prefight.py", str(where), str(where)], say=said.append)

        self.assertEqual((code, "in place" in said[0]), (1, True))

    def test_a_run_writes_the_patched_cartridge(self) -> None:
        where = Path(tempfile.mkdtemp())
        source, output = where / "in.sfc", where / "out.sfc"
        source.write_bytes(bytes(synthetic()))

        code = prefight.main(["prefight.py", str(source), str(output)], say=lambda _l: None)

        self.assertEqual((code, prefight.is_patched(output.read_bytes())), (0, True))

    def test_and_says_how_big_the_result_is(self) -> None:
        where = Path(tempfile.mkdtemp())
        source, output = where / "in.sfc", where / "out.sfc"
        source.write_bytes(bytes(synthetic()))
        said: list[str] = []

        prefight.main(["prefight.py", str(source), str(output)], say=said.append)

        self.assertIn("[done]", said[-1])


if __name__ == "__main__":
    unittest.main()
