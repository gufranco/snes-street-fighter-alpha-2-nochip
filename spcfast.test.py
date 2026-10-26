import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, ClassVar, override

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hardware

spc700 = hardware.load("spc700")
dump = hardware.load("romimage").dump


ROOT = Path(__file__).resolve().parent


def load_module(name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, ROOT / f"{name}.py")
    assert spec is not None and spec.loader is not None, "no loader for that path"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


spcfast = load_module("spcfast")

USA = ROOT / "roms" / "sfa2-usa-final.sfc"
JP = ROOT / "roms" / "sfz2-jp-final.sfc"


class PatchShapeTest(unittest.TestCase):
    def test_the_patch_is_not_empty(self) -> None:
        self.assertGreater(len(spcfast.PATCH), 0)

    def test_the_runs_are_ordered_and_disjoint(self) -> None:
        end = -1
        for at, data in spcfast.PATCH:
            self.assertGreater(at, end)
            end = at + len(data) - 1

    def test_no_run_touches_the_checksum_field(self) -> None:
        for at, data in spcfast.PATCH:
            self.assertFalse(at <= spcfast.CHECKSUM_FIELD < at + len(data))

    def test_every_run_stays_inside_a_four_megabyte_rom(self) -> None:
        for at, data in spcfast.PATCH:
            self.assertLessEqual(at + len(data), 0x400000)

    def test_the_patch_reaches_the_sound_bank(self) -> None:
        self.assertIn(0x07, {at >> 16 for at, _ in spcfast.PATCH})

    def test_the_blank_gate_is_the_documented_sequence(self) -> None:
        self.assertEqual(spcfast.BLANK_GATE.hex(), "af12420029c0f0f8")


class DriverTest(unittest.TestCase):
    def run_covering(self, offset: int) -> tuple[int, bytes]:
        for at, data in spcfast.PATCH:
            if at <= offset < at + len(data):
                return at, data
        raise AssertionError(  # pragma: no cover
            f"{offset:#08x} is not covered by the patch"
        )

    def test_the_receive_loop_is_inside_the_patch(self) -> None:
        at, data = self.run_covering(spcfast.DRIVER_BASE + spcfast.RECEIVE_LOOP)

        self.assertLessEqual(at, spcfast.DRIVER_BASE + spcfast.RECEIVE_LOOP)
        self.assertGreater(len(data), 0)

    def test_the_block_header_parse_is_inside_the_patch(self) -> None:
        at, _ = self.run_covering(spcfast.DRIVER_BASE + spcfast.BLOCK_HEADER)

        self.assertLessEqual(at, spcfast.DRIVER_BASE + spcfast.BLOCK_HEADER)

    def test_the_processor_posts_the_three_byte_kind(self) -> None:
        at, data = self.run_covering(0x07046D)

        self.assertEqual(data[0x07046D - at], 0x03)


class ChecksumTest(unittest.TestCase):
    def test_the_stamped_field_is_a_complement_pair(self) -> None:
        stamped = spcfast.write_checksum(bytes(0x10000))
        complement = stamped[0x7FDC] | (stamped[0x7FDD] << 8)
        value = stamped[0x7FDE] | (stamped[0x7FDF] << 8)

        self.assertEqual(complement ^ value, 0xFFFF)

    def test_stamping_is_idempotent(self) -> None:
        once = spcfast.write_checksum(bytes(0x10000))

        self.assertEqual(spcfast.write_checksum(once), once)


class ApplyTest(unittest.TestCase):
    def make_rom(self) -> bytes:
        rom = bytearray(0x400000)
        for at, want in spcfast.STOCK_PROBE:
            rom[at : at + len(want)] = want
        return bytes(rom)

    def test_a_stock_rom_is_recognised(self) -> None:
        self.assertTrue(spcfast.is_stock(self.make_rom()))

    def test_every_run_is_written(self) -> None:
        patched = spcfast.apply(self.make_rom())

        for at, data in spcfast.PATCH:
            self.assertEqual(patched[at : at + len(data)], data)

    def test_the_result_reports_as_patched(self) -> None:
        self.assertTrue(spcfast.is_patched(spcfast.apply(self.make_rom())))

    def test_applying_twice_changes_nothing_further(self) -> None:
        once = spcfast.apply(self.make_rom())

        self.assertEqual(spcfast.apply(once), once)

    def test_the_source_rom_is_not_modified(self) -> None:
        rom = self.make_rom()

        spcfast.apply(rom)

        self.assertEqual(rom[0x07046D], 0x01)

    def test_a_rom_that_is_not_stock_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            spcfast.apply(bytes(0x400000))


@unittest.skipUnless(
    USA.exists() and JP.exists(), "the retail ROMs are not present"
)  # pragma: no cover
class RetailRomTest(unittest.TestCase):
    jp: ClassVar[Any]
    usa: ClassVar[Any]

    @classmethod
    @override
    def setUpClass(cls) -> None:
        cls.usa = dump.read(USA)
        cls.jp = dump.read(JP)

    def test_both_regions_are_recognised_as_stock(self) -> None:
        self.assertTrue(spcfast.is_stock(self.usa))
        self.assertTrue(spcfast.is_stock(self.jp))

    def test_every_patched_region_is_identical_across_regions(self) -> None:
        for at, data in spcfast.PATCH:
            self.assertEqual(
                self.usa[at : at + len(data)],
                self.jp[at : at + len(data)],
                f"regions differ at {at:#08x}",
            )

    def test_both_regions_have_seventeen_blank_gates(self) -> None:
        self.assertEqual(len(spcfast.find_blank_gates(self.usa)), 17)
        self.assertEqual(len(spcfast.find_blank_gates(self.jp)), 17)

    def test_patching_touches_only_the_patch_and_the_checksum(self) -> None:
        patched = spcfast.apply(self.usa)
        changed = {i for i in range(len(patched)) if patched[i] != self.usa[i]}
        allowed = set(range(spcfast.CHECKSUM_FIELD, spcfast.CHECKSUM_FIELD + 4))
        for at, data in spcfast.PATCH:
            allowed.update(range(at, at + len(data)))

        self.assertTrue(changed.issubset(allowed))

    def listing_at(self, start: int, count: int) -> list[str]:
        patched = spcfast.apply(self.usa)
        base = spcfast.DRIVER_BASE
        return [
            i.text
            for i in spc700.disassemble(patched[base : base + 0x10000], start, start, count=count)
        ]

    def test_the_patched_block_start_waits_for_a_zero_counter(self) -> None:
        # Arrange
        start = spcfast.RECEIVE_LOOP

        # Act
        listing = self.listing_at(start, 3)

        # Assert
        self.assertEqual(listing, ["mov y,$0f4", "bne $0ebd", "cmp y,$0f4"])

    def test_the_header_parse_selects_the_wait_on_the_kind_byte(self) -> None:
        # Arrange
        start = 0x0F0B

        # Act
        listing = self.listing_at(start, 3)

        # Assert
        self.assertEqual(listing, ["beq $0f28", "cmp a,#$03", "bne $0ebd"])

    def test_the_driver_echoes_only_after_reading_every_port(self) -> None:
        # Arrange
        start = 0x0EDD

        # Act
        listing = self.listing_at(start, 6)

        # Assert
        self.assertEqual(listing[2:5], ["mov x,$0f6", "mov a,$0f7", "mov $0f4,y"])

    def test_the_one_byte_loop_reads_the_counter_again_before_a_new_block(self) -> None:
        # Arrange
        start = 0x0ED2

        # Act
        listing = self.listing_at(start, 4)

        # Assert
        self.assertEqual(listing, ["bpl $0ec1", "cmp y,$0f4", "bpl $0ec1", "bra $0eff"])

    def test_and_so_does_the_three_byte_loop(self) -> None:
        # Arrange
        start = 0x0EF5

        # Act
        listing = self.listing_at(start, 5)

        # Assert
        self.assertEqual(
            listing, ["cmp y,$0f4", "beq $0edd", "bpl $0ef5", "cmp y,$0f4", "bpl $0ef5"]
        )

    def test_the_three_byte_loop_ends_exactly_where_the_header_parse_begins(self) -> None:
        # Arrange
        patched = spcfast.apply(self.usa)
        base = spcfast.DRIVER_BASE

        # Act
        walked = list(spc700.disassemble(patched[base : base + 0x10000], 0x0EF5, 0x0EF5, count=5))

        # Assert
        self.assertEqual(walked[-1].address + walked[-1].size, spcfast.BLOCK_HEADER)

    def test_the_transfer_leaves_only_the_length_on_the_caller_stack(self) -> None:
        patched = spcfast.apply(self.usa)
        entry = 0x0704EB

        self.assertEqual(patched[entry : entry + 3].hex(), "c230da")

    def test_the_transfer_switches_to_its_own_stack_before_doing_anything(self) -> None:
        patched = spcfast.apply(self.usa)
        entry = 0x0704EB

        self.assertEqual(patched[entry + 3 : entry + 9].hex(), "3ba2e01f9a48")

    def test_the_stock_driver_tail_is_untouched(self) -> None:
        patched = spcfast.apply(self.usa)
        tail = spcfast.DRIVER_BASE + 0x0F28

        self.assertEqual(patched[tail : tail + 0x18], self.usa[tail : tail + 0x18])

    def test_the_checksum_is_restamped(self) -> None:
        patched = spcfast.apply(self.usa)

        self.assertEqual(patched[0x7FDE] | (patched[0x7FDF] << 8), spcfast.checksum(patched))


class LoadingTest(unittest.TestCase):
    def test_a_module_beside_this_one_is_loaded_by_path(self) -> None:
        self.assertTrue(hasattr(spcfast._load("sdd1tables"), "__name__"))


class FrameHookTest(unittest.TestCase):
    def test_no_hook_is_placed_while_there_is_no_hook_to_place(self) -> None:
        self.assertEqual(spcfast.FRAME_HOOK, b"")

    def test_so_the_runs_are_the_patch_and_nothing_else(self) -> None:
        self.assertEqual(spcfast.runs_for(bytes(0x400000)), spcfast.PATCH)

    def test_and_the_two_sites_it_would_look_at_are_still_named(self) -> None:
        self.assertEqual(len(spcfast.FRAME_HOOK_SITES), 2)


def stock_rom() -> bytes:
    rom = bytearray(0x400000)
    for at, want in spcfast.STOCK_PROBE:
        rom[at : at + len(want)] = want
    return bytes(rom)


class PatchSizeTest(unittest.TestCase):
    def test_the_patch_is_the_four_hundred_and_twenty_bytes_the_readme_states(self) -> None:
        # Arrange
        expected = 420

        # Act
        size = spcfast.patch_bytes()

        # Assert
        self.assertEqual(size, expected)


class BlankGateTest(unittest.TestCase):
    def test_only_gates_inside_the_sound_bank_are_found(self) -> None:
        # Arrange
        rom = bytearray(0x090000)
        for at in (0x060000, 0x070100, 0x075000, 0x080000):
            rom[at : at + 8] = bytes.fromhex("af12420029c0f0f8")

        # Act
        found = spcfast.find_blank_gates(bytes(rom))

        # Assert
        self.assertEqual(found, [0x070100, 0x075000])

    def test_an_image_with_no_gate_has_none(self) -> None:
        # Arrange
        rom = bytes(0x080000)

        # Act
        found = spcfast.find_blank_gates(rom)

        # Assert
        self.assertEqual(found, [])


class EntryTest(unittest.TestCase):
    def _workdir(self) -> Path:
        where = tempfile.TemporaryDirectory()
        self.addCleanup(where.cleanup)
        return Path(where.name)

    def test_too_few_arguments_are_refused_with_the_usage(self) -> None:
        complained: list[Any] = []

        code = spcfast.main(["spcfast.py"], say=lambda _l: None, complain=complained.append)

        self.assertEqual(code, 2)
        self.assertIn("usage", complained[0])

    def test_naming_the_source_as_the_output_is_refused(self) -> None:
        # Arrange
        source = self._workdir() / "in.sfc"
        source.write_bytes(stock_rom())
        complained: list[str] = []

        # Act
        code = spcfast.main(
            ["spcfast.py", str(source), str(source)],
            say=lambda _l: None,
            complain=complained.append,
        )

        # Assert
        self.assertEqual((code, complained), (1, ["refusing to patch the source ROM in place"]))

    def test_a_run_on_a_synthetic_stock_image_posts_the_three_byte_kind(self) -> None:
        # Arrange
        where = self._workdir()
        source, output = where / "in.sfc", where / "out.sfc"
        source.write_bytes(stock_rom())

        # Act
        code = spcfast.main(["spcfast.py", str(source), str(output)], say=lambda _l: None)

        # Assert
        self.assertEqual((code, output.read_bytes()[0x07046D]), (0, 0x03))

    def test_a_run_says_where_the_driver_is_and_what_it_retired(self) -> None:
        # Arrange
        where = self._workdir()
        source, output = where / "in.sfc", where / "out.sfc"
        source.write_bytes(stock_rom())
        said: list[str] = []

        # Act
        spcfast.main(["spcfast.py", str(source), str(output)], say=said.append)

        # Assert
        self.assertEqual(
            said,
            [
                "  driver        0x072b13  three bytes per handshake",
                "  blank gates   1 sites retired",
                "  patch         420 bytes in 21 runs",
                f"[done] {output} (4,194,304 bytes)",
            ],
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
