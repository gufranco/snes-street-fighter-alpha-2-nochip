import importlib.util
import tempfile
import unittest
from collections.abc import Sequence
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


gamefixes = load_module("gamefixes")


def carrier(fix: Any, filler: bytes = b"\x00" * 64) -> bytes:
    made: bytes = filler + fix.stock + filler
    return made


class TableTest(unittest.TestCase):
    def test_every_fix_replaces_a_run_of_its_own_length(self) -> None:
        for fix in gamefixes.FIXES:
            self.assertEqual(len(fix.stock), len(fix.patched), fix.name)

    def test_every_fix_actually_changes_something(self) -> None:
        for fix in gamefixes.FIXES:
            self.assertNotEqual(fix.stock, fix.patched, fix.name)

    def test_every_fix_names_the_regions_it_reaches(self) -> None:
        for fix in gamefixes.FIXES:
            self.assertTrue(fix.regions, fix.name)
            for region in fix.regions:
                self.assertIn(region, ("usa", "jp"), fix.name)

    def test_the_names_are_unique(self) -> None:
        names = [fix.name for fix in gamefixes.FIXES]

        self.assertEqual(len(names), len(set(names)))


class LocationTest(unittest.TestCase):
    def test_a_run_present_once_is_found(self) -> None:
        fix = gamefixes.FIXES[0]

        self.assertEqual(gamefixes.locate(carrier(fix), fix.stock), 64)

    def test_a_run_that_is_absent_reports_nothing(self) -> None:
        self.assertIsNone(gamefixes.locate(b"\x00" * 64, b"\xaa\xbb"))

    def test_a_run_present_twice_is_refused(self) -> None:
        fix = gamefixes.FIXES[0]
        twice = carrier(fix) + carrier(fix)

        with self.assertRaises(ValueError):
            gamefixes.locate(twice, fix.stock)


class ApplyTest(unittest.TestCase):
    def test_a_stock_run_becomes_the_patched_run(self) -> None:
        fix = gamefixes.FIXES[0]

        patched = gamefixes.apply(carrier(fix))

        self.assertEqual(patched[64 : 64 + len(fix.patched)], fix.patched)

    def test_applying_twice_changes_nothing_the_second_time(self) -> None:
        fix = gamefixes.FIXES[0]

        once = gamefixes.apply(carrier(fix))
        twice = gamefixes.apply(once)

        self.assertEqual(once, twice)

    def test_a_rom_carrying_no_fix_at_all_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            gamefixes.apply(b"\x00" * 4096)

    def test_the_report_names_every_fix_and_its_state(self) -> None:
        fix = gamefixes.FIXES[0]

        found = gamefixes.survey(carrier(fix))

        self.assertEqual(found[fix.name], "applied")
        for other in gamefixes.FIXES[1:]:
            self.assertEqual(found[other.name], "absent")


class EmptyCallTest(unittest.TestCase):
    def rom_with(self, call: Any, sites: Sequence[int], filler: bytes = b"\x00" * 32) -> bytes:
        rom = bytearray(b"\x00" * 0x400000)
        rom[gamefixes.long_to_file(call.target)] = gamefixes.RTL
        run = gamefixes.call_run(call.target)
        for at in sites:
            rom[at : at + len(run)] = run
        return bytes(rom)

    def test_every_call_followed_by_a_return_is_found(self) -> None:
        call = gamefixes.EMPTY_CALLS[0]

        rom = self.rom_with(call, (0x1000, 0x2000))

        self.assertEqual(gamefixes.empty_call_sites(rom, call), [0x1000, 0x2000])

    def test_a_call_not_followed_by_a_return_is_left_alone(self) -> None:
        call = gamefixes.EMPTY_CALLS[0]
        rom = bytearray(self.rom_with(call, (0x1000,)))
        rom[0x1004] = 0xEA

        self.assertEqual(gamefixes.empty_call_sites(bytes(rom), call), [])

    def test_a_target_that_is_not_a_bare_return_is_refused(self) -> None:
        call = gamefixes.EMPTY_CALLS[0]
        rom = bytearray(self.rom_with(call, (0x1000,)))
        rom[gamefixes.long_to_file(call.target)] = 0xEA

        with self.assertRaises(ValueError):
            gamefixes.empty_call_sites(bytes(rom), call)

    def test_applying_turns_the_call_opcode_into_a_return(self) -> None:
        call = gamefixes.EMPTY_CALLS[0]
        rom = self.rom_with(call, (0x1000,))

        patched = gamefixes.apply(rom)

        self.assertEqual(patched[0x1000], gamefixes.RTS)
        self.assertEqual(patched[0x1001:0x1005], rom[0x1001:0x1005])

    def test_a_retired_site_is_reported_as_already_done(self) -> None:
        call = gamefixes.EMPTY_CALLS[0]
        rom = self.rom_with(call, (0x1000,))

        patched = gamefixes.apply(rom)

        self.assertEqual(gamefixes.empty_call_sites(patched, call), [])
        self.assertEqual(gamefixes.retired_sites(patched, call), [0x1000])

    def test_a_long_address_maps_to_its_window_offset(self) -> None:
        self.assertEqual(gamefixes.long_to_file(0xFFFF4D), 0x3FFF4D)
        self.assertEqual(gamefixes.long_to_file(0xC00000), 0x000000)


class RetailTest(unittest.TestCase):
    def test_every_sodom_plate_is_confined_to_one_region(self) -> None:
        confined = [fix.name for fix in gamefixes.FIXES if set(fix.regions) != {"usa", "jp"}]

        self.assertEqual(
            confined,
            [
                "sodom name on the life bar",
                "sodom name on the select screen",
                "sodom name on the vs screen",
                "sodom name on the vs results screen",
            ],
        )

    def test_the_rename_reaches_every_screen_that_shows_the_name(self) -> None:
        plates = [fix.name for fix in gamefixes.FIXES if fix.name.startswith("sodom name")]

        self.assertEqual(len(plates), 4)

    def test_the_vs_results_fix_zero_fills_the_bytes_the_shorter_stream_leaves(self) -> None:
        fix = next(f for f in gamefixes.FIXES if f.name == "sodom name on the vs results screen")

        self.assertEqual(len(fix.patched), len(fix.stock))
        self.assertEqual(fix.patched[-6:], b"\x00" * 6)

    def test_the_akuma_pose_fixes_reach_both_regions(self) -> None:
        poses = [fix for fix in gamefixes.FIXES if fix.name.startswith("akuma")]

        self.assertEqual(len(poses), 2)
        for fix in poses:
            self.assertEqual(set(fix.regions), {"usa", "jp"}, fix.name)

    def test_the_reorder_puts_the_taunt_first_and_drops_the_dead_entry(self) -> None:
        fix = next(f for f in gamefixes.FIXES if f.name == "akuma win pose order")

        def words(run: bytes) -> list[int]:
            return [run[i] | (run[i + 1] << 8) for i in range(0, len(run), 2)]

        self.assertEqual(words(fix.stock), [0x390, 0x39E, 0x3C4, 0x3DA])
        self.assertEqual(words(fix.patched), [0x426, 0x390, 0x39E, 0x3DA])

    def test_the_index_moves_with_the_pose_it_names(self) -> None:
        fix = next(f for f in gamefixes.FIXES if f.name == "akuma silent win pose index")

        moved = [(a, b) for a, b in zip(fix.stock, fix.patched, strict=True) if a != b]

        self.assertEqual(moved, [(0x01, 0x02)])

    def test_the_silent_pose_index_matches_where_the_reorder_puts_it(self) -> None:
        order = next(f for f in gamefixes.FIXES if f.name == "akuma win pose order")
        index = next(f for f in gamefixes.FIXES if f.name == "akuma silent win pose index")

        def words(run: bytes) -> list[int]:
            return [run[i] | (run[i + 1] << 8) for i in range(0, len(run), 2)]

        silent = 0x39E
        self.assertEqual(words(order.stock).index(silent), index.stock[3])
        self.assertEqual(words(order.patched).index(silent), index.patched[3])

    def test_the_object_table_fix_reaches_both_regions(self) -> None:
        fix = next(f for f in gamefixes.FIXES if f.name == "object table overflow")

        self.assertEqual(set(fix.regions), {"usa", "jp"})

    def test_the_object_table_fix_trades_a_store_for_a_decrement(self) -> None:
        fix = next(f for f in gamefixes.FIXES if f.name == "object table overflow")

        moved = [
            (i, a, b) for i, (a, b) in enumerate(zip(fix.stock, fix.patched, strict=True)) if a != b
        ]

        self.assertEqual(moved, [(5, 0x84, 0xD6), (6, 0x20, 0x87), (10, 0x05, 0x03)])

    def test_the_object_table_fix_keeps_the_run_the_same_length(self) -> None:
        fix = next(f for f in gamefixes.FIXES if f.name == "object table overflow")

        self.assertEqual(len(fix.stock), 16)
        self.assertEqual(len(fix.patched), 16)

    def test_no_fix_changes_how_a_stage_animates(self) -> None:
        names = [fix.name for fix in gamefixes.FIXES]

        self.assertNotIn("stage animation frame gate", names)
        self.assertEqual([name for name in names if name.endswith("stage lights")], [])

    def test_no_fix_claims_a_scene_that_cannot_be_driven(self) -> None:
        names = [fix.name for fix in gamefixes.FIXES]

        self.assertNotIn("akuma jump frame", names)


class EntryTest(unittest.TestCase):
    def test_too_few_arguments_are_refused_with_the_usage(self) -> None:
        complained: list[Any] = []

        code = gamefixes.main(["gamefixes.py"], say=lambda _l: None, complain=complained.append)

        self.assertEqual(code, 2)
        self.assertIn("usage", complained[0])

    def _workdir(self) -> Path:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        return Path(directory.name)

    def _source(self) -> Path:
        rom = bytearray(0x8000)
        rom[0x100 : 0x100 + len(gamefixes.FIXES[0].stock)] = gamefixes.FIXES[0].stock
        source = self._workdir() / "in.sfc"
        source.write_bytes(bytes(rom))
        return source

    def test_patching_a_rom_over_itself_is_refused(self) -> None:
        # Arrange
        source = self._source()
        complained: list[str] = []

        # Act
        code = gamefixes.main(
            ["gamefixes.py", str(source), str(source)],
            say=lambda _l: None,
            complain=complained.append,
        )

        # Assert
        self.assertEqual((code, complained), (1, ["refusing to patch the source ROM in place"]))

    def test_a_run_writes_the_patched_run_into_the_output(self) -> None:
        # Arrange
        source = self._source()
        output = source.parent / "out.sfc"

        # Act
        code = gamefixes.main(["gamefixes.py", str(source), str(output)], say=lambda _l: None)

        # Assert
        self.assertEqual((code, output.read_bytes()[0x100:0x11C]), (0, gamefixes.FIXES[0].patched))

    def test_a_run_ends_by_naming_the_output_and_its_size(self) -> None:
        # Arrange
        source = self._source()
        output = source.parent / "out.sfc"
        said: list[str] = []

        # Act
        gamefixes.main(["gamefixes.py", str(source), str(output)], say=said.append)

        # Assert
        self.assertEqual(said[-1], f"[done] {output} (32,768 bytes)")


class ChangedBytesTest(unittest.TestCase):
    def test_a_present_fix_counts_only_the_bytes_it_alters(self) -> None:
        # Arrange
        rom = carrier(gamefixes.FIXES[0])

        # Act
        changed = gamefixes.changed_bytes(rom)

        # Assert
        self.assertEqual(changed, 3)

    def test_each_empty_call_site_counts_as_one_byte(self) -> None:
        # Arrange
        rom = bytearray(0x400000)
        rom[0x3FFF4D] = 0x6B
        rom[0x1000:0x1005] = bytes.fromhex("224dffff60")
        rom[0x2000:0x2005] = bytes.fromhex("224dffff60")

        # Act
        changed = gamefixes.changed_bytes(bytes(rom))

        # Assert
        self.assertEqual(changed, 2)


class SurveyRetiredTest(unittest.TestCase):
    def test_a_rom_carrying_only_retired_calls_reads_as_already_done(self) -> None:
        # Arrange
        rom = bytes(32) + bytes.fromhex("604dffff60") + bytes(32)

        # Act
        found = gamefixes.survey(rom)

        # Assert
        self.assertEqual(found["empty routine at $FF:FF4D"], "already")


class ReportTest(unittest.TestCase):
    def test_a_present_fix_is_named_with_its_state_and_file_offset(self) -> None:
        # Arrange
        said: list[str] = []

        # Act
        gamefixes.report(carrier(gamefixes.FIXES[0]), said.append)

        # Assert
        self.assertEqual(
            said[0], "  thrown father sprite" + " " * 12 + " applied  0x000040  regions usa, jp"
        )

    def test_an_absent_fix_is_said_to_be_not_present(self) -> None:
        # Arrange
        said: list[str] = []

        # Act
        gamefixes.report(carrier(gamefixes.FIXES[0]), said.append)

        # Assert
        self.assertEqual(
            said[1], "  sodom name on the life bar" + " " * 6 + " absent   not present  regions usa"
        )

    def test_an_absent_empty_call_is_named_with_no_call_sites(self) -> None:
        # Arrange
        said: list[str] = []

        # Act
        gamefixes.report(carrier(gamefixes.FIXES[0]), said.append)

        # Assert
        self.assertEqual(
            said[8], "  empty routine at $FF:FF4D" + " " * 7 + " absent   0 call sites"
        )

    def test_the_summary_counts_the_bytes_to_change_and_every_entry(self) -> None:
        # Arrange
        said: list[str] = []

        # Act
        gamefixes.report(carrier(gamefixes.FIXES[0]), said.append)

        # Assert
        self.assertEqual(said[-1], "  3 bytes to change across 11 entries")


class VanishedRunTest(unittest.TestCase):
    def test_a_run_that_is_no_longer_there_is_refused(self) -> None:
        claimed = {fix.name: gamefixes.APPLIED for fix in gamefixes.FIXES}

        with self.assertRaises(ValueError) as refusal:
            gamefixes.apply(bytes(0x400000), claimed)

        self.assertIn("was there at survey", str(refusal.exception))

    def test_the_refusal_names_the_fix_that_went_missing(self) -> None:
        claimed = {fix.name: gamefixes.APPLIED for fix in gamefixes.FIXES}

        with self.assertRaises(ValueError) as refusal:
            gamefixes.apply(bytes(0x400000), claimed)

        self.assertIn(gamefixes.FIXES[0].name, str(refusal.exception))


script.entry(__name__, unittest.main)
