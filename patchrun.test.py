import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

import script

sys.path.insert(0, str(Path(__file__).resolve().parent))


ROOT = Path(__file__).resolve().parent


def load_module(name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, ROOT / f"{name}.py")
    assert spec is not None and spec.loader is not None, "no loader for that path"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


patchrun = load_module("patchrun")
rombuild = load_module("rombuild")


class EntryTest(unittest.TestCase):
    def test_too_few_arguments_are_refused_with_the_usage(self) -> None:
        complained: list[Any] = []

        code = patchrun.main(["patchrun.py"], say=lambda _l: None, complain=complained.append)

        self.assertEqual(code, 2)
        self.assertIn("usage", complained[0])


class MemoryTest(unittest.TestCase):
    def memory(self) -> Any:
        return patchrun.SnesMemory(bytes(rombuild.IMAGE_SIZE))

    def test_a_work_ram_bank_reads_from_ram(self) -> None:
        memory = self.memory()
        memory.write8(0x7E1234, 0xAB)

        self.assertEqual(memory.read8(0x7E1234), 0xAB)

    def test_the_second_work_ram_bank_does_too(self) -> None:
        memory = self.memory()
        memory.write8(0x7F1234, 0xCD)

        self.assertEqual(memory.read8(0x7F1234), 0xCD)

    def test_a_work_ram_address_never_written_reads_as_zero(self) -> None:
        self.assertEqual(self.memory().read8(0x7E1234), 0x00)

    def test_the_low_half_of_a_low_bank_is_ram_rather_than_cartridge(self) -> None:
        memory = self.memory()
        memory.write8(0x001234, 0xEF)

        self.assertEqual(memory.read8(0x001234), 0xEF)

    def test_the_high_half_of_a_low_bank_is_cartridge(self) -> None:
        self.assertEqual(self.memory().read8(0x008000), 0x00)


class WalkTest(unittest.TestCase):
    class Entry:
        def __init__(self, index: int, source: int) -> None:
            self.index, self.source = index, source

    def walk_with(
        self, outcomes: dict[int, tuple[int, int]], want: dict[int, int]
    ) -> tuple[list[str], int]:
        said: list[str] = []
        entries = [self.Entry(index, 0x100000 + index) for index in want]

        def _translate(_memory: Any, source: int) -> Any:
            destination, dmap = outcomes[source - 0x100000]
            return patchrun.Outcome(destination, dmap, None)

        return said, patchrun.walk(None, entries, want, said.append, _translate)

    def test_a_stream_that_lands_where_it_was_allocated_is_not_a_failure(self) -> None:
        said, failures = self.walk_with({0: (0x0C4000, 0x00)}, {0: 0x0C4000})

        self.assertEqual((failures, said), (0, []))

    def test_a_stream_that_lands_elsewhere_is_reported(self) -> None:
        said, failures = self.walk_with({0: (0x0C5000, 0x00)}, {0: 0x0C4000})

        self.assertEqual((failures, "got 0x0c5000" in said[0]), (1, True))

    def test_a_stream_that_kept_the_fixed_address_bit_is_reported(self) -> None:
        said, failures = self.walk_with({0: (0x0C4000, patchrun.FIXED_ADDRESS_BIT)}, {0: 0x0C4000})

        self.assertEqual((failures, "fixed-address bit" in said[0]), (1, True))

    def test_only_the_first_few_wrong_destinations_are_named(self) -> None:
        count = patchrun.EXAMPLE_LIMIT + 3
        outcomes = dict.fromkeys(range(count), (806912, 0))
        want = dict.fromkeys(range(count), 0x0C4000)

        said, failures = self.walk_with(outcomes, want)

        self.assertEqual((failures, len(said)), (count, patchrun.EXAMPLE_LIMIT))


ENTRY_FILE = 0x1ACD84
RETURN_AT_ONCE = bytes.fromhex("6b")
REWRITE_BANK_AND_CONTROL = bytes.fromhex("a90c8f044300a9018f0043006b")


def image_with(routine: bytes) -> bytes:
    image = bytearray(rombuild.IMAGE_SIZE)
    image[ENTRY_FILE : ENTRY_FILE + len(routine)] = routine
    return bytes(image)


class TriggerTest(unittest.TestCase):
    def test_writing_the_trigger_snapshots_what_the_channel_registers_hold(self) -> None:
        # Arrange
        memory = patchrun.SnesMemory(bytes(rombuild.IMAGE_SIZE))
        memory.write8(0x4302, 0x56)

        # Act
        memory.write8(0x420B, 0x01)

        # Assert
        self.assertEqual((len(memory.triggered), memory.triggered[0x4302]), (0x80, 0x56))

    def test_a_write_elsewhere_takes_no_snapshot(self) -> None:
        # Arrange
        memory = patchrun.SnesMemory(bytes(rombuild.IMAGE_SIZE))

        # Act
        memory.write8(0x4302, 0x56)

        # Assert
        self.assertIsNone(memory.triggered)


class DmaSourceTest(unittest.TestCase):
    def test_the_source_is_read_as_low_high_and_bank(self) -> None:
        # Arrange
        snapshot = {0x4302: 0x56, 0x4303: 0x34, 0x4304: 0xD2}

        # Act
        source = patchrun.dma_source(snapshot)

        # Assert
        self.assertEqual(source, 0xD23456)

    def test_another_channel_is_read_from_its_own_registers(self) -> None:
        # Arrange
        snapshot = {0x4312: 0x78, 0x4313: 0x9A, 0x4314: 0xC1}

        # Act
        source = patchrun.dma_source(snapshot, channel=0x10)

        # Assert
        self.assertEqual(source, 0xC19A78)


class SyntheticTranslationTest(unittest.TestCase):
    def test_a_routine_that_returns_at_once_leaves_the_source_in_its_window(self) -> None:
        # Arrange
        memory = patchrun.SnesMemory(image_with(RETURN_AT_ONCE))

        # Act
        outcome = patchrun.translate(memory, 0x123456)

        # Assert
        self.assertEqual((outcome.destination, outcome.dmap), (0xD23456, 0x09))

    def test_the_destination_is_what_the_routine_leaves_in_the_source_registers(self) -> None:
        # Arrange
        memory = patchrun.SnesMemory(image_with(REWRITE_BANK_AND_CONTROL))

        # Act
        outcome = patchrun.translate(memory, 0x123456)

        # Assert
        self.assertEqual(outcome.destination, 0x0C3456)

    def test_the_control_byte_is_what_the_routine_leaves_in_it(self) -> None:
        # Arrange
        memory = patchrun.SnesMemory(image_with(REWRITE_BANK_AND_CONTROL))

        # Act
        outcome = patchrun.translate(memory, 0x123456)

        # Assert
        self.assertEqual(outcome.dmap, 0x01)

    def test_a_register_the_caller_names_is_set_before_the_routine_runs(self) -> None:
        # Arrange
        memory = patchrun.SnesMemory(image_with(RETURN_AT_ONCE))

        # Act
        outcome = patchrun.translate(memory, 0x123456, y=0x70)

        # Assert
        self.assertEqual(outcome.cpu.y, 0x70)


class SyntheticRunTest(unittest.TestCase):
    def run_on(self, workdir: Path) -> tuple[int, list[str]]:
        tagged = bytearray(8192)
        for position, target in ((0x100, 0), (0x300, 64)):
            tagged[position : position + 4] = b"SDD1"
            tagged[position + 4 : position + 8] = target.to_bytes(4, "little")
        paths = [workdir / "image.sfc", workdir / "patched.sfc", workdir / "tagged.sfc"]
        paths[0].write_bytes(image_with(RETURN_AT_ONCE))
        paths[1].write_bytes(bytes(rombuild.ORIGINAL_SIZE))
        paths[2].write_bytes(bytes(tagged))
        said: list[str] = []
        code = patchrun.main(["patchrun.py", *map(str, paths)], say=said.append)
        return code, said

    def test_a_routine_that_moves_nothing_fails_every_stream(self) -> None:
        # Arrange
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)

        # Act
        code, said = self.run_on(Path(directory.name))

        # Assert
        self.assertEqual((code, said[-1]), (1, "  executed 2 streams, 2 failures"))


script.entry(__name__, unittest.main, verbosity=2)
