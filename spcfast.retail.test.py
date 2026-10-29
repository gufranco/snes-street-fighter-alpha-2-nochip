import importlib.util
import tempfile
import unittest
from pathlib import Path
from typing import Any, ClassVar, override

import hardware
import script

ROOT = Path(__file__).resolve().parent


spc700 = hardware.load("spc700")


dump = hardware.load("romimage").dump


JP = ROOT / "roms" / "sfz2-jp-final.sfc"


def load_module(name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, ROOT / f"{name}.py")
    assert spec is not None and spec.loader is not None, "no loader for that path"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


spcfast = load_module("spcfast")

USA = ROOT / "roms" / "sfa2-usa-final.sfc"


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
        code = spcfast.main(
            ["spcfast.py", str(source), str(source)],
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
        code = spcfast.main(["spcfast.py", str(source), str(output)], say=said.append)

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


script.entry(__name__, unittest.main, verbosity=2)
