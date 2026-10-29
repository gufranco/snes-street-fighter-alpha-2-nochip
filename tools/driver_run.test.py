import contextlib
import importlib.util
import io
import sys
import tempfile
import types
import unittest
from pathlib import Path
from typing import Any, override

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import script

ROOT = Path(__file__).resolve().parent.parent


def load_module(name: str, where: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, where)
    assert spec is not None and spec.loader is not None, "no loader for that path"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


driver_run = load_module("driver_run", Path(__file__).resolve().parent / "driver_run.py")
spcfast = load_module("spcfast", ROOT / "spcfast.py")


PAYLOAD = bytes(range(0x30))

BLANK_BOOT_PROGRAM = bytes(0x40)

STOCK_BODY = 0x0200

TO_THE_STOCK_BODY = bytes([0x5F, 0x00, 0x02])

ONE_BYTE_RECEIVE = bytes(
    [0xE4, 0xF5, 0xD7, 0x14, 0xE4, 0xF4, 0xC4, 0xF4, 0xFC, 0x64, 0xF4, 0xF0, 0xFC, 0x5F, 0xC9, 0x0E]
)


def a_cartridge_with_the_driver_in_place() -> bytearray:
    rom = bytearray(driver_run.DRIVER_BASE + driver_run.IMAGE_BYTES)
    for at, want in spcfast.STOCK_PROBE:
        rom[at : at + len(want)] = want
    stock = driver_run.DRIVER_BASE + driver_run.STOCK_LOOP
    rom[stock : stock + len(TO_THE_STOCK_BODY)] = TO_THE_STOCK_BODY
    body = driver_run.DRIVER_BASE + STOCK_BODY
    rom[body : body + len(ONE_BYTE_RECEIVE)] = ONE_BYTE_RECEIVE
    return rom


def lend_a_blank_boot_program(case: unittest.TestCase) -> None:
    real = driver_run.ssmp
    case.addCleanup(setattr, driver_run, "ssmp", real)
    driver_run.ssmp = types.SimpleNamespace(
        Chip=lambda part: real.Chip(part, boot=BLANK_BOOT_PROGRAM)
    )


class PortsTest(unittest.TestCase):
    def test_the_first_triple_is_ready_before_anything_runs(self) -> None:
        ports = driver_run.Ports(bytes(range(6)))

        self.assertEqual([ports.read8(at) for at in range(0xF5, 0xF8)], [0, 1, 2])

    def test_the_counter_starts_where_the_driver_starts(self) -> None:
        ports = driver_run.Ports(bytes(range(6)))

        self.assertEqual(ports.read8(0xF4), 0)

    def test_an_echo_advances_to_the_next_triple(self) -> None:
        ports = driver_run.Ports(bytes(range(6)))

        ports.write8(0xF4, 0)

        self.assertEqual([ports.read8(at) for at in range(0xF5, 0xF8)], [3, 4, 5])

    def test_and_moves_the_counter_on_with_it(self) -> None:
        ports = driver_run.Ports(bytes(range(6)))

        ports.write8(0xF4, 0)

        self.assertEqual(ports.read8(0xF4), 1)

    def test_the_counter_wraps_at_a_byte(self) -> None:
        ports = driver_run.Ports(bytes(3 * 300))
        for step in range(300):
            ports.write8(0xF4, step & 0xFF)

        self.assertEqual(ports.read8(0xF4), 300 & 0xFF)

    def test_a_payload_that_runs_out_says_so(self) -> None:
        ports = driver_run.Ports(bytes(3))

        ports.write8(0xF4, 0)

        self.assertTrue(ports.spent)

    def test_and_one_that_has_not_says_that_instead(self) -> None:
        ports = driver_run.Ports(bytes(6))

        ports.write8(0xF4, 0)

        self.assertFalse(ports.spent)

    def test_a_payload_shorter_than_a_triple_is_padded_rather_than_read_past(self) -> None:
        ports = driver_run.Ports(bytes([9]))

        self.assertEqual([ports.read8(at) for at in range(0xF5, 0xF8)], [9, 0, 0])

    def test_everything_outside_the_ports_is_ordinary_memory(self) -> None:
        ports = driver_run.Ports(bytes(3))

        ports.write8(0x0200, 0x5A)

        self.assertEqual(ports.read8(0x0200), 0x5A)

    def test_and_the_driver_echo_is_remembered_for_the_caller_to_read(self) -> None:
        ports = driver_run.Ports(bytes(6))

        ports.write8(0xF5, 0x77)

        self.assertEqual(ports.echoed[1], 0x77)

    def test_an_echo_on_a_port_that_is_not_the_first_does_not_advance_anything(self) -> None:
        ports = driver_run.Ports(bytes(6))

        ports.write8(0xF6, 0x11)

        self.assertEqual(ports.handshakes, 0)


class SpreadTest(unittest.TestCase):
    def test_spreading_leaves_one_byte_per_triple(self) -> None:
        self.assertEqual(driver_run.spread(bytes([1, 2])), bytes([1, 0, 0, 2, 0, 0]))

    def test_and_nothing_at_all_stays_nothing(self) -> None:
        self.assertEqual(driver_run.spread(b""), b"")


class PatcherTest(unittest.TestCase):
    def test_the_patch_is_loaded_from_the_file_beside_the_tools(self) -> None:
        # Arrange
        wanted = ROOT / "spcfast.py"

        # Act
        found = driver_run.patcher()

        # Assert
        self.assertEqual(Path(found.__file__), wanted)


class SyntheticImageTest(unittest.TestCase):
    def test_the_driver_image_is_the_block_the_processor_is_handed(self) -> None:
        # Arrange
        rom = a_cartridge_with_the_driver_in_place()

        # Act
        image = driver_run.image_of(rom)

        # Assert
        self.assertEqual(len(image), 0x10000)

    def test_and_it_starts_at_the_driver_rather_than_the_start_of_the_cartridge(self) -> None:
        # Arrange
        rom = a_cartridge_with_the_driver_in_place()

        # Act
        image = driver_run.image_of(rom)

        # Assert
        self.assertEqual(
            image[0x0EBD:0x0EC5], bytes([0xEC, 0xF4, 0x00, 0x5E, 0xF4, 0x00, 0xD0, 0xF8])
        )


class SyntheticTransferTest(unittest.TestCase):
    @override
    def setUp(self) -> None:
        self.image = driver_run.image_of(spcfast.apply(a_cartridge_with_the_driver_in_place()))

    def test_the_published_patch_carries_three_streams_side_by_side(self) -> None:
        # Arrange
        payload = PAYLOAD

        # Act
        found = driver_run.deliver(self.image, payload, driver_run.DESTINATION)

        # Assert
        self.assertEqual(found.streams, (PAYLOAD[0::3], PAYLOAD[1::3], PAYLOAD[2::3]))

    def test_and_takes_one_handshake_for_every_three_bytes(self) -> None:
        # Arrange
        payload = PAYLOAD

        # Act
        found = driver_run.deliver(self.image, payload, driver_run.DESTINATION)

        # Assert
        self.assertEqual(found.handshakes, 16)

    def test_the_stand_in_counts_no_cycles(self) -> None:
        # Arrange
        payload = PAYLOAD

        # Act
        found = driver_run.deliver(self.image, payload, driver_run.DESTINATION)

        # Assert
        self.assertIsNone(found.cycles)


PATCHED_BYTE_LOOP = 0x0EC1

TORN_HANDSHAKE = 5

LOOKS_AHEAD = 0x40


class TornOnce:
    def __init__(self, payload: bytes | bytearray) -> None:
        self.inner = driver_run.Ports(payload)
        self.torn = False

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)

    def write8(self, address: int, value: int) -> None:
        self.inner.write8(address, value)

    def read8(self, address: int) -> int:
        found: int = self.inner.read8(address)
        if address != driver_run.PORT_BASE or self.torn or self.inner.handshakes != TORN_HANDSHAKE:
            return found
        self.torn = True
        return (found + LOOKS_AHEAD) & 0xFF


def with_one_torn_read(image: bytes | bytearray, payload: bytes | bytearray) -> TornOnce:
    ports = TornOnce(payload)
    for address, value in enumerate(image):
        ports.memory.write8(address, value)
    driver_run.point(ports, driver_run.POINTER, driver_run.DESTINATION)
    driver_run.point(ports, driver_run.SECOND_POINTER, driver_run.SECOND)
    driver_run.point(ports, driver_run.THIRD_POINTER, driver_run.THIRD)
    ports.offer()
    return ports


class TornReadTest(unittest.TestCase):
    @override
    def setUp(self) -> None:
        self.image = driver_run.image_of(spcfast.apply(a_cartridge_with_the_driver_in_place()))

    def test_a_torn_counter_read_does_not_end_a_three_byte_block(self) -> None:
        # Arrange
        ports = with_one_torn_read(self.image, PAYLOAD)

        # Act
        found = driver_run.run(ports, driver_run.FAST_LOOP, PAYLOAD, driver_run.DESTINATION)

        # Assert
        self.assertTrue(ports.torn)
        self.assertEqual(found.streams, (PAYLOAD[0::3], PAYLOAD[1::3], PAYLOAD[2::3]))
        self.assertEqual(found.handshakes, 16)

    def test_nor_a_one_byte_block(self) -> None:
        # Arrange
        ports = with_one_torn_read(self.image, driver_run.spread(PAYLOAD))

        # Act
        found = driver_run.run(ports, PATCHED_BYTE_LOOP, PAYLOAD, driver_run.DESTINATION)

        # Assert
        landed = bytes(
            ports.memory.read8(driver_run.DESTINATION + step) for step in range(len(PAYLOAD))
        )
        self.assertTrue(ports.torn)
        self.assertEqual(landed, PAYLOAD)
        self.assertEqual(found.handshakes, len(PAYLOAD))


class SyntheticStockTest(unittest.TestCase):
    @override
    def setUp(self) -> None:
        self.image = driver_run.image_of(a_cartridge_with_the_driver_in_place())

    def test_a_one_byte_receive_loop_takes_a_handshake_for_every_byte(self) -> None:
        # Arrange
        payload = PAYLOAD

        # Act
        found = driver_run.deliver_one_at_a_time(self.image, payload, driver_run.DESTINATION)

        # Assert
        self.assertEqual(found.handshakes, 48)

    def test_and_lands_the_bytes_one_after_another_in_the_first_stream(self) -> None:
        # Arrange
        payload = PAYLOAD

        # Act
        found = driver_run.deliver_one_at_a_time(self.image, payload, driver_run.DESTINATION)

        # Assert
        self.assertEqual(found.streams[0], bytes(range(16)))


class SyntheticUnitTest(unittest.TestCase):
    @override
    def setUp(self) -> None:
        lend_a_blank_boot_program(self)
        rom = a_cartridge_with_the_driver_in_place()
        self.stock = driver_run.image_of(rom)
        self.fast = driver_run.image_of(spcfast.apply(rom))

    def test_the_unit_carries_the_three_streams_side_by_side(self) -> None:
        # Arrange
        payload = PAYLOAD

        # Act
        found = driver_run.on_hardware(self.fast, payload, driver_run.DESTINATION)

        # Assert
        self.assertEqual(found.streams, (PAYLOAD[0::3], PAYLOAD[1::3], PAYLOAD[2::3]))

    def test_and_counts_one_acknowledgement_for_every_three_bytes(self) -> None:
        # Arrange
        payload = PAYLOAD

        # Act
        found = driver_run.on_hardware(self.fast, payload, driver_run.DESTINATION)

        # Assert
        self.assertEqual(found.handshakes, 16)

    def test_the_stock_loop_runs_on_the_unit_one_byte_per_acknowledgement(self) -> None:
        # Arrange
        payload = driver_run.spread(PAYLOAD)

        # Act
        found = driver_run.on_hardware(
            self.stock, payload, driver_run.DESTINATION, entry=driver_run.STOCK_LOOP
        )

        # Assert
        self.assertEqual((found.handshakes, found.streams[0][:48]), (48, PAYLOAD))

    def test_without_the_seeded_latch_the_first_acknowledgement_is_lost(self) -> None:
        # Arrange
        unechoed = 0x00

        # Act
        with self.assertRaises(driver_run.RunLimit) as caught:
            driver_run.on_hardware(self.fast, PAYLOAD, driver_run.DESTINATION, unechoed=unechoed)

        # Assert
        self.assertIn("gave up after", str(caught.exception))


class EntryTest(unittest.TestCase):
    def test_a_cartridge_with_the_driver_in_place_runs_both_models_to_agreement(self) -> None:
        # Arrange
        lend_a_blank_boot_program(self)
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        where = Path(folder.name) / "synthetic.sfc"
        where.write_bytes(a_cartridge_with_the_driver_in_place())
        printed = io.StringIO()

        # Act
        with contextlib.redirect_stdout(printed):
            code = driver_run.main([str(where)])

        # Assert
        self.assertEqual(
            (code, printed.getvalue().splitlines()[-1]),
            (0, "  stand-in and unit agree on every byte: True"),
        )

    def test_a_rom_it_cannot_read_is_reported_rather_than_raised(self) -> None:
        self.assertEqual(driver_run.main([str(ROOT / "roms" / "nothing-here.sfc")]), 2)

    def test_and_so_is_a_missing_argument(self) -> None:
        self.assertEqual(driver_run.main([]), 2)


script.entry(__name__, unittest.main)
