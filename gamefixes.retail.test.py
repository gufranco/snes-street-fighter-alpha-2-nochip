import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

import script

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hardware

sdd1 = hardware.load("sdd1")


ROOT = Path(__file__).resolve().parent


def load_module(name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, ROOT / f"{name}.py")
    assert spec is not None and spec.loader is not None, "no loader for that path"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gamefixes = load_module("gamefixes")
spcfast = load_module("spcfast")

USA = ROOT / "roms" / "sfa2-usa-final.sfc"
JP = ROOT / "roms" / "sfz2-jp-final.sfc"
REGIONS = ((USA, "usa"), (JP, "jp"))


def retail(path: Path) -> bytes:
    script.skip_unless(path.exists(), f"{path} is not present")
    return path.read_bytes()


class RetailTest(unittest.TestCase):
    def test_every_empty_call_is_retired_in_both_regions(self) -> None:
        # Arrange
        roms = [retail(path) for path, _ in REGIONS]

        # Act
        counts = [len(gamefixes.empty_call_sites(rom, gamefixes.EMPTY_CALLS[0])) for rom in roms]

        # Assert
        self.assertEqual(counts, [42, 42])

    def test_every_empty_call_target_is_a_bare_return(self) -> None:
        # Arrange
        rom = retail(USA)

        # Act
        targets = {
            call.name: rom[gamefixes.long_to_file(call.target)] for call in gamefixes.EMPTY_CALLS
        }

        # Assert
        self.assertEqual(targets, {call.name: gamefixes.RTL for call in gamefixes.EMPTY_CALLS})

    def test_the_three_routines_together_reach_forty_five_sites(self) -> None:
        # Arrange
        rom = retail(USA)

        # Act
        sites = sum(len(gamefixes.empty_call_sites(rom, call)) for call in gamefixes.EMPTY_CALLS)

        # Assert
        self.assertEqual(sites, 45)

    def test_every_fix_that_claims_usa_is_present_in_the_usa_rom(self) -> None:
        # Arrange
        rom = retail(USA)

        # Act
        found = gamefixes.survey(rom)

        # Assert
        for fix in gamefixes.FIXES:
            expected = "applied" if "usa" in fix.regions else "already"
            self.assertEqual(found[fix.name], expected, fix.name)

    def test_every_fix_that_claims_jp_is_present_in_the_jp_rom(self) -> None:
        # Arrange
        rom = retail(JP)

        # Act
        found = gamefixes.survey(rom)

        # Assert
        for fix in gamefixes.FIXES:
            if "jp" in fix.regions:
                self.assertEqual(found[fix.name], "applied", fix.name)
            else:
                self.assertIn(found[fix.name], ("already", "absent"), fix.name)

    def outside_the_checksum(self, rom: bytes | bytearray, patched: bytes | bytearray) -> int:
        field = range(spcfast.CHECKSUM_FIELD, spcfast.CHECKSUM_FIELD + 4)
        return sum(
            1
            for at, (before, after) in enumerate(zip(rom, patched, strict=True))
            if before != after and at not in field
        )

    def test_the_usa_rom_changes_by_exactly_the_declared_bytes(self) -> None:
        # Arrange
        rom = retail(USA)

        # Act
        patched = gamefixes.apply(rom)

        # Assert
        self.assertEqual(self.outside_the_checksum(rom, patched), gamefixes.changed_bytes(rom))

    def test_the_jp_rom_changes_by_exactly_the_declared_bytes(self) -> None:
        # Arrange
        rom = retail(JP)

        # Act
        patched = gamefixes.apply(rom)

        # Assert
        self.assertEqual(self.outside_the_checksum(rom, patched), gamefixes.changed_bytes(rom))

    def test_the_usa_rom_changes_more_bytes_than_the_jp_one(self) -> None:
        # Arrange
        usa, jp = retail(USA), retail(JP)

        # Act
        counts = (gamefixes.changed_bytes(usa), gamefixes.changed_bytes(jp))

        # Assert
        self.assertEqual(counts, (214, 56))

    def test_the_patched_rom_carries_a_consistent_checksum(self) -> None:
        # Arrange
        rom = retail(USA)

        # Act
        patched = gamefixes.apply(rom)

        # Assert
        self.assertEqual(patched, spcfast.write_checksum(patched))

    def test_applying_to_an_already_patched_usa_rom_is_a_no_op(self) -> None:
        # Arrange
        rom = retail(USA)
        once = gamefixes.apply(rom)

        # Act
        twice = gamefixes.apply(once)

        # Assert
        self.assertEqual(twice, once)

    def occurrences(self, rom: bytes | bytearray, run: bytes) -> int:
        found, at = 0, rom.find(run)
        while at != -1:
            found += 1
            at = rom.find(run, at + 1)
        return found

    def test_a_fix_names_a_run_that_appears_once_in_every_region_it_claims(self) -> None:
        # Arrange
        roms = [(path, region, retail(path)) for path, region in REGIONS]

        # Act
        counts = {
            f"{fix.name} in {path.name}": (
                self.occurrences(rom, fix.stock),
                self.occurrences(rom, fix.patched),
            )
            for path, region, rom in roms
            for fix in gamefixes.FIXES
            if region in fix.regions
        }

        # Assert
        for where, count in counts.items():
            self.assertEqual(count, (1, 0), where)

    def test_a_region_a_fix_does_not_claim_never_carries_the_stock_run(self) -> None:
        # Arrange
        roms = [(path, region, retail(path)) for path, region in REGIONS]

        # Act
        counts = {
            f"{fix.name} in {path.name}": self.occurrences(rom, fix.stock)
            for path, region, rom in roms
            for fix in gamefixes.FIXES
            if region not in fix.regions
        }

        # Assert
        for where, count in counts.items():
            self.assertEqual(count, 0, where)

    def test_the_japanese_rom_already_reads_right_where_it_shares_the_run(self) -> None:
        # Arrange
        rom = retail(JP)

        # Act
        found = gamefixes.survey(rom)

        # Assert
        already = sorted(name for name, state in found.items() if state == "already")
        absent = sorted(name for name, state in found.items() if state == "absent")
        self.assertEqual(
            already,
            [
                "sodom name on the life bar",
                "sodom name on the select screen",
                "sodom name on the vs screen",
            ],
        )
        self.assertEqual(absent, ["sodom name on the vs results screen"])

    def test_the_vs_results_fix_only_turns_katana_into_sodom(self) -> None:
        # Arrange
        rom = bytearray(retail(USA))
        fix = next(f for f in gamefixes.FIXES if f.name == "sodom name on the vs results screen")
        at = gamefixes.locate(bytes(rom), fix.stock)
        before = sdd1.decompress(bytes(rom), at, gamefixes.VS_RESULTS_LENGTH).data
        rom[at : at + len(fix.patched)] = fix.patched

        # Act
        after = sdd1.decompress(bytes(rom), at, gamefixes.VS_RESULTS_LENGTH).data

        # Assert
        self.assertEqual(len(after), gamefixes.VS_RESULTS_LENGTH)
        moved = [i for i in range(len(before)) if before[i] != after[i]]
        self.assertEqual(moved, list(range(0x35A, 0x366, 2)))
        self.assertEqual(bytes(before[i] for i in moved), b"KATANA")
        self.assertEqual(bytes(after[i] for i in moved), b"SODOM ")

    def starts_inside(self, starts: list[int], at: int, length: int) -> list[int]:
        return [start for start in starts if at < start < at + length]

    def test_no_fix_writes_over_the_start_of_a_neighbouring_stream(self) -> None:
        # Arrange
        usastreams = load_module("usastreams")
        rom = retail(USA)
        starts = sorted(start for start, _ in usastreams.STREAMS)

        # Act
        reached = {
            fix.name: self.starts_inside(starts, gamefixes.locate(rom, fix.stock), len(fix.stock))
            for fix in gamefixes.FIXES
            if "usa" in fix.regions
        }

        # Assert
        self.assertEqual(reached, {name: [] for name in reached})

    def test_the_vs_results_fix_stops_where_the_next_stream_begins(self) -> None:
        # Arrange
        usastreams = load_module("usastreams")
        rom = retail(USA)
        fix = next(f for f in gamefixes.FIXES if f.name == "sodom name on the vs results screen")
        at = gamefixes.locate(rom, fix.stock)

        # Act
        following = min(start for start, _ in usastreams.STREAMS if start > at)

        # Assert
        self.assertEqual(at + len(fix.stock), following)


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
        code = gamefixes.main(
            ["gamefixes.py", str(source), str(source)],
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
        code = gamefixes.main(["gamefixes.py", str(source), str(output)], say=said.append)

        # Assert
        self.assertEqual(code, 0)
        self.assertTrue(output.exists())
        self.assertTrue(said)


script.entry(__name__, unittest.main)
