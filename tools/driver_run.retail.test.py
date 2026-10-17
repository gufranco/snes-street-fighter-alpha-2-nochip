import importlib.util
import sys
import unittest
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ROOT = Path(__file__).resolve().parent.parent


def load_module(name: str, where: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, where)
    assert spec is not None and spec.loader is not None, "no loader for that path"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


driver_run = load_module("driver_run", Path(__file__).resolve().parent / "driver_run.py")
spcfast = load_module("spcfast", ROOT / "spcfast.py")

USA = ROOT / "roms" / "sfa2-usa-final.sfc"

NEEDS_A_DUMP = unittest.skipUnless(
    USA.exists(), "the retail dump is not on this machine, and nothing here ships one"
)


def _unit_builds() -> bool:
    try:
        driver_run.ssmp.Chip("s-smp")
    except (
        driver_run.ssmp.NoBootRom,
        driver_run.ssmp.Corrupt,
        OSError,
    ):
        return False
    return True


NEEDS_THE_BOOT_ROM = unittest.skipUnless(
    _unit_builds(),
    "the audio unit needs Sony's boot program, which nobody may distribute",
)

PAYLOAD = bytes(range(0x30))


@NEEDS_A_DUMP
@NEEDS_THE_BOOT_ROM
class ComposedTest(unittest.TestCase):
    def images(self) -> tuple[bytes, bytes]:
        rom = bytearray(USA.read_bytes())
        return driver_run.image_of(rom), driver_run.image_of(spcfast.apply(bytearray(rom)))

    def unit(self, payload: bytes | bytearray = PAYLOAD) -> Any:
        _stock, fast = self.images()
        return driver_run.on_hardware(fast, payload, driver_run.DESTINATION)

    def test_the_unit_carries_the_three_streams_the_stand_in_carries(self) -> None:
        # Arrange
        payload = PAYLOAD

        # Act
        found = self.unit(payload)

        # Assert
        self.assertEqual(found.streams, (PAYLOAD[0::3], PAYLOAD[1::3], PAYLOAD[2::3]))

    def test_it_reaches_the_same_bytes_as_the_stand_in(self) -> None:
        # Arrange
        _stock, fast = self.images()

        # Act
        found = driver_run.on_hardware(fast, PAYLOAD, driver_run.DESTINATION)

        # Assert
        self.assertEqual(
            found.streams, driver_run.deliver(fast, PAYLOAD, driver_run.DESTINATION).streams
        )

    def test_and_takes_the_same_number_of_handshakes_getting_there(self) -> None:
        # Arrange
        _stock, fast = self.images()

        # Act
        found = driver_run.on_hardware(fast, PAYLOAD, driver_run.DESTINATION)

        # Assert
        self.assertEqual(
            found.handshakes, driver_run.deliver(fast, PAYLOAD, driver_run.DESTINATION).handshakes
        )

    def test_and_the_same_number_of_instructions(self) -> None:
        # Arrange
        _stock, fast = self.images()

        # Act
        found = driver_run.on_hardware(fast, PAYLOAD, driver_run.DESTINATION)

        # Assert
        self.assertEqual(
            found.steps, driver_run.deliver(fast, PAYLOAD, driver_run.DESTINATION).steps
        )

    def test_only_the_unit_reports_cycles_at_all(self) -> None:
        # Arrange
        _stock, fast = self.images()
        stand_in = driver_run.deliver(fast, PAYLOAD, driver_run.DESTINATION)

        # Act
        found = self.unit()

        # Assert
        self.assertIsNone(stand_in.cycles)
        self.assertGreater(found.cycles, 0)

    def test_the_stock_loop_runs_on_the_unit_too(self) -> None:
        # Arrange
        stock, _fast = self.images()

        # Act
        found = driver_run.on_hardware(
            stock, driver_run.spread(PAYLOAD), driver_run.DESTINATION, entry=driver_run.STOCK_LOOP
        )

        # Assert
        self.assertEqual(found.handshakes, len(PAYLOAD))

    def test_and_costs_more_cycles_than_the_patched_one_for_the_same_bytes(self) -> None:
        # Arrange
        stock, _fast = self.images()

        # Act
        slow = driver_run.on_hardware(
            stock, driver_run.spread(PAYLOAD), driver_run.DESTINATION, entry=driver_run.STOCK_LOOP
        )

        # Assert
        self.assertGreater(slow.cycles, self.unit().cycles * 3)

    def test_a_counter_that_does_not_start_where_the_driver_expects_runs_away(self) -> None:
        # Arrange
        _stock, fast = self.images()

        # Act
        with self.assertRaises(driver_run.RunLimit) as caught:
            driver_run.on_hardware(fast, PAYLOAD, driver_run.DESTINATION, counter=1)

        # Assert
        self.assertIn("gave up after", str(caught.exception))

    def test_without_the_seeded_latch_the_first_acknowledgement_is_lost(self) -> None:
        # Arrange
        _stock, fast = self.images()

        # Act
        with self.assertRaises(driver_run.RunLimit) as caught:
            driver_run.on_hardware(fast, PAYLOAD, driver_run.DESTINATION, unechoed=0x00)

        # Assert
        self.assertIn("gave up after", str(caught.exception))

    def test_leaving_the_boot_window_on_changes_nothing_for_this_driver(self) -> None:
        # Arrange
        _stock, fast = self.images()
        hidden = self.unit()

        # Act
        found = driver_run.on_hardware(fast, PAYLOAD, driver_run.DESTINATION, control=0x80)

        # Assert
        self.assertEqual((found.streams, found.cycles), (hidden.streams, hidden.cycles))

    def test_because_the_driver_never_reads_what_the_window_covers(self) -> None:
        # Arrange
        _stock, fast = self.images()

        # Act
        shown = driver_run.on_hardware(fast, PAYLOAD, driver_run.DESTINATION, control=0x80)

        # Assert
        self.assertEqual(shown.handshakes, len(PAYLOAD) // 3)

    def test_a_payload_longer_than_a_page_carries_over_on_the_unit_too(self) -> None:
        # Arrange
        payload = bytes(range(256)) * 3

        # Act
        found = self.unit(payload)

        # Assert
        self.assertEqual(found.streams[0], payload[0::3])


@NEEDS_THE_BOOT_ROM
class ConsoleTest(unittest.TestCase):
    def build(self, payload: bytes | bytearray) -> tuple[Any, Any]:
        chip = driver_run.ssmp.Chip("s-smp")
        chip.reset()
        chip.space.write8(driver_run.PORT_BASE, driver_run.UNECHOED)
        console = driver_run.Console(chip, payload)
        console.offer()
        return chip, console

    def test_the_first_triple_is_where_the_driver_will_look_for_it(self) -> None:
        # Arrange
        payload = bytes(range(6))

        # Act
        chip, _console = self.build(payload)

        # Assert
        self.assertEqual([chip.space.read8(at) for at in range(0xF5, 0xF8)], [0, 1, 2])

    def test_the_counter_starts_where_the_driver_expects_it(self) -> None:
        # Arrange
        payload = bytes(range(6))

        # Act
        chip, _console = self.build(payload)

        # Assert
        self.assertEqual(chip.space.read8(0xF4), driver_run.FIRST_COUNTER)

    def test_an_acknowledgement_advances_to_the_next_triple(self) -> None:
        # Arrange
        chip, console = self.build(bytes(range(6)))
        chip.space.write8(0xF4, 0x00)

        # Act
        console.watch()

        # Assert
        self.assertEqual([chip.space.read8(at) for at in range(0xF5, 0xF8)], [3, 4, 5])

    def test_a_latch_that_has_not_changed_is_not_an_acknowledgement(self) -> None:
        # Arrange
        _chip, console = self.build(bytes(range(6)))

        # Act
        acknowledged = console.watch()

        # Assert
        self.assertFalse(acknowledged)
        self.assertEqual(console.handshakes, 0)

    def test_a_payload_shorter_than_a_triple_is_padded_rather_than_read_past(self) -> None:
        # Arrange
        payload = bytes([9])

        # Act
        chip, _console = self.build(payload)

        # Assert
        self.assertEqual([chip.space.read8(at) for at in range(0xF5, 0xF8)], [9, 0, 0])

    def test_a_payload_that_runs_out_says_so(self) -> None:
        # Arrange
        chip, console = self.build(bytes(3))
        chip.space.write8(0xF4, 0x00)

        # Act
        console.watch()

        # Assert
        self.assertTrue(console.spent)

    def test_the_counter_wraps_at_a_byte(self) -> None:
        # Arrange
        chip, console = self.build(bytes(3 * 300))

        # Act
        for step in range(300):
            chip.space.write8(0xF4, step & 0xFF)
            console.watch()

        # Assert
        self.assertEqual(chip.space.read8(0xF4), 300 & 0xFF)

    def test_the_driver_cannot_read_its_own_acknowledgement(self) -> None:
        # Arrange
        chip, _console = self.build(bytes(range(6)))

        # Act
        chip.space.write8(0xF4, 0x9E)

        # Assert
        self.assertEqual(chip.space.read8(0xF4), driver_run.FIRST_COUNTER)


class EntryTest(unittest.TestCase):
    @NEEDS_A_DUMP
    @NEEDS_THE_BOOT_ROM
    def test_a_run_from_the_command_line_reports_what_it_measured(self) -> None:
        # Arrange
        argv = [str(USA)]

        # Act
        code = driver_run.main(argv)

        # Assert
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
