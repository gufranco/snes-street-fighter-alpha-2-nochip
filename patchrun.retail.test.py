import importlib.util
import sys
import unittest
from pathlib import Path
from typing import Any, ClassVar, override

import script

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hardware

dump = hardware.load("romimage").dump

cpu = hardware.load("mos65xx")

ROOT = Path(__file__).resolve().parent


def load_module(name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, ROOT / f"{name}.py")
    assert spec is not None and spec.loader is not None, "no loader for that path"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


patchrun = load_module("patchrun")

rombuild = load_module("rombuild")

IMAGE = ROOT / "build" / "sfa2-usa-nochip.sfc"

PATCHED = ROOT / "build" / "sfa2-usa-patched.sfc"

TAGGED = ROOT / "roms" / "sfa2-usa-vc-sound-restored.sfc"

STAR_OCEAN = ROOT / "roms" / "star-ocean-jp-nochip-96mbit.sfc"

STAR_OCEAN_BANKS = 192

NEVIKSTI_ROUTINE = 0x00F063

STAR_OCEAN_STREAMS = (
    (0x0D5C85, 0x010000),
    (0x0E0000, 0x018000),
    (0x0DB2FD, 0x050000),
    (0x137EA8, 0x078000),
    (0x14C11B, 0x088000),
    (0x18D178, 0x0E6000),
    (0x134327, 0x168000),
    (0x16FB45, 0x14E000),
)


@unittest.skipUnless(
    IMAGE.exists() and PATCHED.exists() and TAGGED.exists(),
    "the built image is not present",
)
class TranslationTest(unittest.TestCase):
    entries: ClassVar[Any]
    expected: ClassVar[Any]
    image: ClassVar[Any]
    memory: ClassVar[Any]

    @classmethod
    @override
    def setUpClass(cls) -> None:
        cls.image = dump.read(IMAGE)
        cls.entries = rombuild.load_entries(dump.read(TAGGED))
        cls.expected = rombuild.build(dump.read(PATCHED), cls.entries).destinations
        cls.memory = patchrun.SnesMemory(cls.image)

    def test_every_stream_translates_to_its_allocated_address(self) -> None:
        # Arrange
        entries = self.entries

        # Act
        landed = {entry.index: patchrun.translate(self.memory, entry.source) for entry in entries}

        # Assert
        wrong = [at for at, one in landed.items() if one.destination != self.expected[at]]
        self.assertEqual(wrong, [])

    def test_every_stream_leaves_the_fixed_address_bit_clear(self) -> None:
        for entry in self.entries[:600]:
            outcome = patchrun.translate(self.memory, entry.source)

            self.assertFalse(outcome.dmap & patchrun.FIXED_ADDRESS_BIT)

    def test_the_rest_of_the_dmap_byte_is_untouched(self) -> None:
        outcome = patchrun.translate(self.memory, self.entries[0].source, dmap=0xF9)

        self.assertEqual(outcome.dmap, 0xF9 & ~patchrun.FIXED_ADDRESS_BIT)

    def test_the_other_fixed_channels_translate_the_same_way(self) -> None:
        for channel in (0x10, 0x70):
            for entry in self.entries[:200]:
                outcome = patchrun.translate(self.memory, entry.source, channel=channel)

                self.assertEqual(
                    outcome.destination,
                    self.expected[entry.index],
                    f"channel {channel:#04x}",
                )
                self.assertFalse(outcome.dmap & patchrun.FIXED_ADDRESS_BIT)

    def test_the_variable_channel_entry_reads_its_offset_from_y(self) -> None:
        for channel in (0x00, 0x10, 0x70):
            for entry in self.entries[:100]:
                outcome = patchrun.translate(
                    self.memory,
                    entry.source,
                    channel=channel,
                    entry=patchrun.VARIABLE_ENTRY,
                    y=channel,
                )

                self.assertEqual(
                    outcome.destination, self.expected[entry.index], f"y={channel:#04x}"
                )
                self.assertFalse(outcome.dmap & patchrun.FIXED_ADDRESS_BIT)

    def test_an_eight_bit_callers_registers_come_back_untouched(self) -> None:
        for entry in self.entries[:300]:
            outcome = patchrun.translate(
                self.memory, entry.source, a=0x0001, x=0x0034, y=0x0078, c=True
            )

            self.assertEqual(outcome.cpu.a & 0xFF, 0x01)
            self.assertEqual(outcome.cpu.x, 0x34)
            self.assertEqual(outcome.cpu.y, 0x78)
            self.assertTrue(outcome.cpu.c)

    def test_a_sixteen_bit_callers_registers_come_back_untouched(self) -> None:
        for entry in self.entries[:300]:
            outcome = patchrun.translate(
                self.memory,
                entry.source,
                m8=False,
                x8=False,
                a=0x1001,
                x=0x1234,
                y=0x5678,
                c=True,
            )

            self.assertEqual(outcome.cpu.a, 0x1001)
            self.assertEqual(outcome.cpu.x, 0x1234)
            self.assertEqual(outcome.cpu.y, 0x5678)
            self.assertTrue(outcome.cpu.c)

    def test_a_narrow_caller_gets_back_only_what_it_could_hold(self) -> None:
        outcome = patchrun.translate(
            self.memory, self.entries[0].source, a=0x0001, x=0x1234, y=0x5678
        )

        self.assertEqual(outcome.cpu.x, 0x34)
        self.assertEqual(outcome.cpu.y, 0x78)

    def test_the_stack_is_balanced_on_return(self) -> None:
        for entry in self.entries[:300]:
            outcome = patchrun.translate(self.memory, entry.source)

            self.assertEqual(outcome.cpu.s, patchrun.STACK_TOP)

    def test_the_widths_the_caller_had_are_restored(self) -> None:
        outcome = patchrun.translate(self.memory, self.entries[0].source)

        self.assertTrue(outcome.cpu.m8)
        self.assertTrue(outcome.cpu.x8)

    def test_the_variable_channel_entry_also_balances_its_stack(self) -> None:
        for entry in self.entries[:200]:
            outcome = patchrun.translate(
                self.memory,
                entry.source,
                channel=0x70,
                entry=patchrun.VARIABLE_ENTRY,
                y=0x70,
            )

            self.assertEqual(outcome.cpu.s, patchrun.STACK_TOP)
            self.assertEqual(outcome.cpu.y, 0x70)


@unittest.skipUnless(STAR_OCEAN.exists(), "the star ocean build is not present")
class ReferenceBuildTest(unittest.TestCase):
    image: ClassVar[Any]

    @classmethod
    @override
    def setUpClass(cls) -> None:
        cls.image = dump.read(STAR_OCEAN)

    def run_reference(self, source: int) -> Any:
        memory = patchrun.SnesMemory(self.image, banks=STAR_OCEAN_BANKS)
        memory.ram[patchrun.DMA_BASE] = patchrun.ARMED_DMAP
        memory.ram[patchrun.DMA_BASE + 2] = source & 0xFF
        memory.ram[patchrun.DMA_BASE + 3] = (source >> 8) & 0xFF
        memory.ram[patchrun.DMA_BASE + 4] = patchrun.WINDOW_BASE + (source >> 16)

        cpu = patchrun.emu65816.Cpu("65816", memory)
        cpu.s = patchrun.STACK_TOP
        cpu.m8 = True
        cpu.x8 = False
        cpu.call(NEVIKSTI_ROUTINE)
        return memory

    def test_the_reference_routine_reaches_the_known_output_of_each_stream(self) -> None:
        for source, expected_file in STAR_OCEAN_STREAMS:
            memory = self.run_reference(source)
            destination = patchrun.dma_source(memory.triggered)

            landed = patchrun.mapper.snes_to_file(
                destination >> 16, destination & 0xFFFF, STAR_OCEAN_BANKS
            )

            self.assertEqual(landed, expected_file, f"source {source:#08x}")

    def test_the_reference_routine_also_clears_the_fixed_address_bit(self) -> None:
        for source, _ in STAR_OCEAN_STREAMS:
            memory = self.run_reference(source)

            self.assertFalse(memory.triggered[patchrun.DMA_BASE] & patchrun.FIXED_ADDRESS_BIT)

    def test_the_reference_routine_starts_a_transfer(self) -> None:
        memory = self.run_reference(STAR_OCEAN_STREAMS[0][0])

        self.assertIsNotNone(memory.triggered)


@unittest.skipUnless(
    IMAGE.exists() and PATCHED.exists() and TAGGED.exists(),
    "the built image is not present",
)
class EntryAgainstTheImageTest(unittest.TestCase):
    def test_a_whole_run_reports_how_many_streams_it_executed(self) -> None:
        # Arrange
        said: list[Any] = []

        # Act
        code = patchrun.main(
            ["patchrun.py", str(IMAGE), str(PATCHED), str(TAGGED)], say=said.append
        )

        # Assert
        self.assertEqual(code, 0)
        self.assertIn("executed", said[-1])


script.entry(__name__, unittest.main)
