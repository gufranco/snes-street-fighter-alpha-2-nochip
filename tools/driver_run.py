import importlib.util
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import hardware

spc700 = hardware.load("spc700")

ssmp = hardware.load("ssmp")

PORT_BASE = 0xF4

PORTS = 4

TRIPLE = 3

DRIVER_BASE = 0x071C56

IMAGE_BYTES = 0x10000

FAST_LOOP = 0x0EDC

STOCK_LOOP = 0x0EC9

DESTINATION = 0x2000

SECOND = 0x3000

THIRD = 0x4000

POINTER = 0x0014

SECOND_POINTER = 0x00C8

THIRD_POINTER = 0x00CA

MEASURED_PAYLOAD = 0x30

ROOT = Path(__file__).resolve().parent.parent


def patcher() -> Any:
    where = ROOT / "spcfast.py"
    spec = importlib.util.spec_from_file_location("spcfast", where)
    assert spec is not None and spec.loader is not None, "no loader for that path"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Ports:
    def __init__(self, payload: bytes | bytearray, seed: int = spc700.UNSET_SEED) -> None:
        self.memory = spc700.Memory(fill=0, seed=seed)
        self.payload = bytes(payload)
        self.at = 0
        self.counter = 0
        self.handshakes = 0
        self.echoed = [0] * PORTS
        self.offer()

    @property
    def spent(self) -> bool:
        return self.at >= len(self.payload)

    def offer(self) -> None:
        for slot in range(1, TRIPLE + 1):
            at = self.at + slot - 1
            self.place(slot, self.payload[at] if at < len(self.payload) else 0)
        self.place(0, self.counter)

    def place(self, slot: int, value: int) -> None:
        self.memory.write8(PORT_BASE + slot, value & 0xFF)

    def read8(self, address: int) -> int:
        found = self.memory.read8(address)
        assert isinstance(found, int)
        return found

    def write8(self, address: int, value: int) -> None:
        if address == PORT_BASE:
            self.echoed[0] = value & 0xFF
            self.handshakes += 1
            self.at += TRIPLE
            self.counter = (self.counter + 1) & 0xFF
            self.offer()
            return
        if PORT_BASE < address < PORT_BASE + PORTS:
            self.echoed[address - PORT_BASE] = value & 0xFF
            return
        self.memory.write8(address, value)


class Transfer:
    def __init__(
        self,
        memory: Any,
        streams: tuple[bytes, ...],
        handshakes: int,
        steps: int,
        cycles: int | None = None,
    ) -> None:
        self.memory = memory
        self.streams = streams
        self.handshakes = handshakes
        self.steps = steps
        self.cycles = cycles


REGISTERS = range(0xF0, 0x100)

CONTROL = 0xF1

BOOT_HIDDEN = 0x00

FIRST_COUNTER = 0

UNECHOED = 0xFF

HARDWARE_CEILING = 4_000_000


class RunLimit(Exception): ...


class Console:
    def __init__(self, chip: Any, payload: bytes | bytearray, counter: int = FIRST_COUNTER) -> None:
        self.chip = chip
        self.payload = bytes(payload)
        self.at = 0
        self.counter = counter & 0xFF
        self.handshakes = 0
        self.seen = chip.read(0)

    @property
    def spent(self) -> bool:
        return self.at >= len(self.payload)

    def offer(self) -> None:
        for slot in range(1, TRIPLE + 1):
            at = self.at + slot - 1
            self.chip.write(slot, self.payload[at] if at < len(self.payload) else 0)
        self.chip.write(0, self.counter)

    def watch(self) -> bool:
        now = self.chip.read(0)
        if now == self.seen:
            return False
        self.seen = now
        self.handshakes += 1
        self.at += TRIPLE
        self.counter = (self.counter + 1) & 0xFF
        self.offer()
        return True


def image_of(rom: bytes | bytearray) -> bytes:
    return bytes(rom[DRIVER_BASE : DRIVER_BASE + IMAGE_BYTES])


def loaded(image: bytes | bytearray, payload: bytes | bytearray, at: int) -> Ports:
    ports = Ports(payload)
    for address, value in enumerate(image):
        ports.memory.write8(address, value)
    point(ports, POINTER, at)
    point(ports, SECOND_POINTER, SECOND)
    point(ports, THIRD_POINTER, THIRD)
    ports.offer()
    return ports


def point(ports: Ports, pointer: int, at: int) -> None:
    ports.memory.write8(pointer, at & 0xFF)
    ports.memory.write8(pointer + 1, (at >> 8) & 0xFF)


def run(ports: Ports, entry: int, payload: bytes | bytearray, at: int) -> Transfer:
    cpu = spc700.Cpu("spc700", ports)
    cpu.pc = entry
    cpu.y = 0
    cpu.p = False
    cpu.run_until(lambda machine: ports.spent and machine.pc == entry)
    carried = -(-len(payload) // TRIPLE)
    streams = tuple(
        bytes(ports.memory.read8(where + step) for step in range(carried))
        for where in (at, SECOND, THIRD)
    )
    return Transfer(ports, streams, ports.handshakes, cpu.steps)


def on_hardware(
    image: bytes | bytearray,
    payload: bytes | bytearray,
    at: int,
    entry: int = FAST_LOOP,
    counter: int | None = None,
    unechoed: int | None = None,
    control: int | None = None,
) -> Transfer:
    counter = FIRST_COUNTER if counter is None else counter
    unechoed = UNECHOED if unechoed is None else unechoed
    control = BOOT_HIDDEN if control is None else control

    chip = ssmp.Chip("s-smp")
    chip.reset()
    space = chip.space
    space.write8(CONTROL, control)
    for address, value in enumerate(image):
        if address not in REGISTERS:
            space.write8(address, value)
    point_space(space, POINTER, at)
    point_space(space, SECOND_POINTER, SECOND)
    point_space(space, THIRD_POINTER, THIRD)

    space.write8(PORT_BASE, unechoed)
    console = Console(chip, payload, counter)
    console.offer()

    cpu = chip.processor
    cpu.pc = entry
    cpu.y = 0
    cpu.p = False

    started = chip.cycles
    while True:
        chip.step()
        console.watch()
        if console.spent and cpu.pc == entry:
            break
        if chip.cycles - started > HARDWARE_CEILING:
            raise RunLimit(f"gave up after {chip.cycles - started} cycles at ${cpu.pc:04X}")

    carried = -(-len(payload) // TRIPLE)
    streams = tuple(
        bytes(space.read8(where + step) for step in range(carried)) for where in (at, SECOND, THIRD)
    )
    return Transfer(space, streams, console.handshakes, cpu.steps, chip.cycles - started)


def point_space(space: Any, pointer: int, at: int) -> None:
    space.write8(pointer, at & 0xFF)
    space.write8(pointer + 1, (at >> 8) & 0xFF)


def deliver(image: bytes | bytearray, payload: bytes | bytearray, at: int) -> Transfer:
    return run(loaded(image, payload, at), FAST_LOOP, payload, at)


def deliver_one_at_a_time(
    image: bytes | bytearray, payload: bytes | bytearray, at: int
) -> Transfer:
    return run(loaded(image, spread(payload), at), STOCK_LOOP, payload, at)


def spread(payload: bytes | bytearray) -> bytes:
    laid = bytearray()
    for value in payload:
        laid.append(value)
        laid.extend((0, 0))
    return bytes(laid)


def main(argv: list[str]) -> int:
    if not argv:
        print("usage: driver_run.py <rom>")
        return 2

    where = Path(argv[0])
    if not where.is_file():
        print(f"{where} is not a file this can read")
        return 2

    rom = bytearray(where.read_bytes())
    payload = bytes(range(MEASURED_PAYLOAD))

    stock_image = image_of(rom)
    fast_image = image_of(patcher().apply(rom))

    stock = deliver_one_at_a_time(stock_image, payload, DESTINATION)
    fast = deliver(fast_image, payload, DESTINATION)
    stock_unit = on_hardware(stock_image, spread(payload), DESTINATION, entry=STOCK_LOOP)
    fast_unit = on_hardware(fast_image, payload, DESTINATION)

    print(f"  {len(payload)} bytes through the driver as it ships and as it is patched")
    print(f"  stock    {stock.handshakes:3d} handshakes, {stock.steps:5d} instructions")
    print(f"  patched  {fast.handshakes:3d} handshakes, {fast.steps:5d} instructions")
    for at, stream in zip((DESTINATION, SECOND, THIRD), fast.streams, strict=True):
        print(f"  landed at {at:#06x}: {stream[:8].hex()}")

    slow_cycles, fast_cycles = stock_unit.cycles, fast_unit.cycles
    assert slow_cycles is not None and fast_cycles is not None, "a unit run always counts cycles"

    print("  the same two runs on the whole audio unit, which counts cycles")
    print(f"  stock    {stock_unit.handshakes:3d} handshakes, {slow_cycles:6d} cycles")
    print(f"  patched  {fast_unit.handshakes:3d} handshakes, {fast_cycles:6d} cycles")
    print(f"  faster by {slow_cycles / fast_cycles:.2f} times")
    agreed = fast_unit.streams == fast.streams and stock_unit.streams[0].startswith(
        stock.streams[0]
    )
    print(f"  stand-in and unit agree on every byte: {agreed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
