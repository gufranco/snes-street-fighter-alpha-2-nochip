import importlib.util
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, NamedTuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import hardware
import script

sdd1 = hardware.load("sdd1")

snesgfx = hardware.load("snesgfx")

FOUR_BIT = snesgfx.FORMATS["4bpp"]

TILE_BYTES = 32

SMALLEST = 512


class Survey(NamedTuple):
    aligned: int
    unaligned: int
    meanReuse: float
    meanReuseOfNoise: float
    withAnyRepeat: int
    noiseWithAnyRepeat: int


def tiles(data: bytes | bytearray | None) -> list[tuple[int, ...]] | None:
    if not data:
        return None
    try:
        found = FOUR_BIT.decode(bytes(data))
    except snesgfx.Truncated:
        return None
    return [tuple(one) for one in found]


def reuse(data: bytes | bytearray | None) -> float | None:
    cut = tiles(data)
    if cut is None:
        return None
    return 1 - len(set(cut)) / len(cut)


def noise(length: int) -> bytes:
    return os.urandom(length)


def survey(runs: list[bytes]) -> Survey:
    aligned = unaligned = 0
    real, control = [], []
    for data in runs:
        found = reuse(data)
        if found is None:
            unaligned += 1
            continue
        aligned += 1
        real.append(found)
        control.append(reuse(noise(len(data))) or 0.0)
    return Survey(
        aligned=aligned,
        unaligned=unaligned,
        meanReuse=sum(real) / len(real) if real else 0.0,
        meanReuseOfNoise=sum(control) / len(control) if control else 0.0,
        withAnyRepeat=sum(1 for one in real if one > 0),
        noiseWithAnyRepeat=sum(1 for one in control if one > 0),
    )


def table_for(where: Path | str) -> Any:
    name = "usastreams" if "usa" in Path(where).name.lower() else "jpstreams"
    root = Path(__file__).resolve().parent.parent
    spec = importlib.util.spec_from_file_location(name, root / f"{name}.py")
    assert spec is not None and spec.loader is not None, "no loader for that path"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.STREAMS


def against(where: Path | str, limit: int | None = None, table: Any = None) -> Survey:
    rom = bytearray(Path(where).read_bytes())
    runs = []
    for off, length in table_for(where) if table is None else table:
        if length < SMALLEST:
            continue
        found = sdd1.decompress(rom, off, length)
        runs.append(bytes(found.data) if hasattr(found, "data") else bytes(found))
        if limit is not None and len(runs) >= limit:
            break
    return survey(runs)


def main(argv: list[str], say: Callable[[str], None] = print) -> int:
    if not argv:
        say("usage: tile_shape.py <rom> [streams]")
        return 2

    where = Path(argv[0])
    if not where.is_file():
        say(f"{where} is not a file this can read")
        return 2

    limit = int(argv[1]) if len(argv) > 1 else None
    found = against(where, limit=limit)

    say(f"  {found.aligned} streams are a whole number of {TILE_BYTES} byte tiles")
    say(f"  {found.unaligned} are not, and are not measured")
    say(f"  duplicate tile fraction, decompressed: {found.meanReuse:.4f}")
    say(f"  the same, random bytes of equal length: {found.meanReuseOfNoise:.4f}")
    say(f"  sheets repeating any tile: {found.withAnyRepeat}, controls: {found.noiseWithAnyRepeat}")
    return 0


script.entry(__name__, main, sys.argv[1:])
