import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any, override

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import hardware  # noqa: E402
import script  # noqa: E402

sdsp = hardware.load("sdsp")

APU_RAM = 0x10000

BLOCK_BYTES = 9

DIRECTORY_BYTES = 4

MAX_BLOCKS = APU_RAM // BLOCK_BYTES

END_FLAG = 0x01

RUNS_OFF = "runs off the end without ending"

LOOP_UNALIGNED = "loop point is not on a block boundary"

LOOP_OUTSIDE = "loop point is outside the sample"

DIRECTORY_WRITTEN = "the directory entry itself is being written"

OVERWRITTEN = "a playing sample is being written"

RENDER_SAMPLES = 512

REG_MVOLL = 0x0C
REG_MVOLR = 0x1C
REG_DIR = 0x5D
REG_KON = 0x4C
REG_FLG = 0x6C
REG_ENDX = 0x7C
V_SRCN = 0x04
V_PITCHL = 0x02
V_PITCHH = 0x03
V_VOLL = 0x00
V_VOLR = 0x01
V_ADSR0 = 0x05
V_GAIN = 0x07

FULL_VOLUME = 0x7F

UNIT_PITCH = 0x1000

DIRECT_GAIN = 0x7F


class Unreadable(Exception):
    pass


class Chain:
    def __init__(self, start: int, blocks: int, reach: range, fault: str | None) -> None:
        self.start = start
        self.blocks = blocks
        self.reach = reach
        self.fault = fault

    @override
    def __repr__(self) -> str:
        return f"<Chain at {self.start:#06x}, {self.blocks} blocks, {self.fault or 'ends'}>"


class Fault:
    def __init__(self, sample: int, fault: str, at: int) -> None:
        self.sample = sample
        self.fault = fault
        self.at = at

    @override
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Fault):
            return NotImplemented
        return (self.sample, self.fault, self.at) == (other.sample, other.fault, other.at)

    @override
    def __hash__(self) -> int:
        return hash((self.sample, self.fault, self.at))

    @override
    def __repr__(self) -> str:
        return f"<Fault sample {self.sample} at {self.at:#06x}: {self.fault}>"


def load(image: bytes | bytearray) -> bytearray:
    if len(image) != APU_RAM:
        raise Unreadable(f"an audio memory image is {APU_RAM} bytes, not {len(image)}")
    return bytearray(image)


def entry(ram: bytearray, directory: int, sample: int) -> tuple[int, int]:
    at = (directory + sample * DIRECTORY_BYTES) & 0xFFFF
    start = ram[at] | (ram[(at + 1) & 0xFFFF] << 8)
    loop = ram[(at + 2) & 0xFFFF] | (ram[(at + 3) & 0xFFFF] << 8)
    return start, loop


def chain(ram: bytearray, start: int) -> Chain:
    at = start
    for blocks in range(1, MAX_BLOCKS + 1):
        if at + BLOCK_BYTES > APU_RAM:
            return Chain(start, blocks - 1, range(start, min(at, APU_RAM)), RUNS_OFF)
        header = ram[at]
        at += BLOCK_BYTES
        if header & END_FLAG:
            return Chain(start, blocks, range(start, at), None)
    return Chain(start, MAX_BLOCKS, range(start, APU_RAM), RUNS_OFF)


def _prepare(ram: bytearray, directory: int, sample: int) -> Any:
    memory = sdsp.Memory()
    for address, value in enumerate(ram):
        memory.write8(address, value)
    chip = sdsp.Chip("s-dsp", memory).reset()
    chip.write(REG_FLG, 0x00)
    chip.write(REG_MVOLL, FULL_VOLUME)
    chip.write(REG_MVOLR, FULL_VOLUME)
    chip.write(REG_DIR, (directory >> 8) & 0xFF)
    chip.write(V_SRCN, sample & 0xFF)
    chip.write(V_PITCHL, UNIT_PITCH & 0xFF)
    chip.write(V_PITCHH, UNIT_PITCH >> 8)
    chip.write(V_VOLL, FULL_VOLUME)
    chip.write(V_VOLR, FULL_VOLUME)
    chip.write(V_ADSR0, 0x00)
    chip.write(V_GAIN, DIRECT_GAIN)
    chip.write(REG_KON, 0x01)
    return chip


def play(ram: bytearray, directory: int, sample: int, samples: int = RENDER_SAMPLES) -> Any:
    return _prepare(ram, directory, sample).render(samples)


def reaches_end(ram: bytearray, directory: int, sample: int, samples: int = RENDER_SAMPLES) -> bool:
    chip = _prepare(ram, directory, sample)
    chip.render(samples)
    return bool(chip.read(REG_ENDX) & 0x01)


def faults(ram: bytearray, directory: int, used: Sequence[int]) -> list[Fault]:
    found = []
    for sample in used:
        start, loop = entry(ram, directory, sample)
        walked = chain(ram, start)
        if walked.fault:
            found.append(Fault(sample, walked.fault, start))
            continue
        if loop not in walked.reach:
            found.append(Fault(sample, LOOP_OUTSIDE, loop))
        elif (loop - start) % BLOCK_BYTES:
            found.append(Fault(sample, LOOP_UNALIGNED, loop))
    return found


def overlaps(ram: bytearray, directory: int, used: Sequence[int]) -> list[tuple[int, int, int]]:
    reached: dict[int, tuple[int, set[int]]] = {}
    for sample in used:
        start, _ = entry(ram, directory, sample)
        walked = chain(ram, start)
        if walked.fault is None:
            reached[sample] = (start, set(walked.reach))

    found = []
    names = sorted(reached)
    for first_index, first in enumerate(names):
        for second in names[first_index + 1 :]:
            if reached[first][0] == reached[second][0]:
                continue
            shared = reached[first][1] & reached[second][1]
            if shared:
                found.append((first, second, min(shared)))
    return found


def collisions(
    ram: bytearray, directory: int, playing: Sequence[int], written: Sequence[int]
) -> list[Fault]:
    touched = set(written)
    found = []
    for sample in playing:
        at = (directory + sample * DIRECTORY_BYTES) & 0xFFFF
        if touched & set(range(at, at + DIRECTORY_BYTES)):
            found.append(Fault(sample, DIRECTORY_WRITTEN, at))
            continue
        start, _ = entry(ram, directory, sample)
        walked = chain(ram, start)
        shared = touched & set(walked.reach)
        if shared:
            found.append(Fault(sample, OVERWRITTEN, min(shared)))
    return found


def report(ram: bytearray, directory: int, used: Sequence[int]) -> list[str]:
    lines = []
    for fault in faults(ram, directory, used):
        lines.append(f"  sample {fault.sample:3d} at {fault.at:#06x}: {fault.fault}")
    for first, second, at in overlaps(ram, directory, used):
        lines.append(f"  samples {first:3d} and {second:3d} share {at:#06x}")
    if not lines:
        lines.append(f"  {len(list(used))} samples, all well formed and none sharing bytes")
    return lines


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: sample_audit.py <apu-ram-image> <directory-page> [sample ...]")
        return 2
    ram = load(Path(argv[0]).read_bytes())
    directory = int(argv[1], 0)
    used = [int(name, 0) for name in argv[2:]] or list(range(0x100))
    for line in report(ram, directory, used):
        print(line)
    return 0


script.entry(__name__, main, sys.argv[1:])
