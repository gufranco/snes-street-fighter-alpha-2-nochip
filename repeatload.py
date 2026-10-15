import importlib.util
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent


def _load(name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, ROOT / f"{name}.py")
    assert spec is not None and spec.loader is not None, "no loader for that path"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


spcfast = _load("spcfast")

HOOK_FILE = 0x070069
REPLACED = bytes([0xA9, 0x00, 0x15])

FILLER_FILE = 0x07F600
FILLER_END = 0x07F700
FILLER_SIZE = FILLER_END - FILLER_FILE
ROUTINE_ADDRESS = FILLER_FILE & 0xFFFF

MARKER = 0x7E9000

JSR = 0x20

ROUTINE = bytes.fromhex(
    "e220a303f03148af00907ec95ad017af01907ec9a5d00faf02907ec301d00768"
    "a90083038011688f02907ea95a8f00907ea9a58f01907ec220a9001560"
)


def hook() -> bytes:
    return bytes([JSR, ROUTINE_ADDRESS & 0xFF, ROUTINE_ADDRESS >> 8])


def is_patched(rom: bytes | bytearray) -> bool:
    if rom[HOOK_FILE : HOOK_FILE + len(REPLACED)] != hook():
        return False
    return rom[FILLER_FILE : FILLER_FILE + len(ROUTINE)] == ROUTINE


def apply(rom: bytes | bytearray) -> bytes:
    if is_patched(rom):
        return bytes(rom)
    if rom[HOOK_FILE : HOOK_FILE + len(REPLACED)] != REPLACED:
        raise ValueError("the sound engine's allocator setup is not where this patch expects it")
    if set(rom[FILLER_FILE:FILLER_END]) != {0xFF}:
        raise ValueError("the filler the routine needs is not free")

    patched = bytearray(rom)
    patched[FILLER_FILE : FILLER_FILE + len(ROUTINE)] = ROUTINE
    patched[HOOK_FILE : HOOK_FILE + len(REPLACED)] = hook()
    return bytes(spcfast.write_checksum(patched))


def report(rom: bytes | bytearray, say: Callable[[str], None] = print) -> None:
    state = "already applied" if is_patched(rom) else "ready"
    say(f"  hook      $C7:{HOOK_FILE & 0xFFFF:04X}  {REPLACED.hex(' ')} -> {hook().hex(' ')}")
    say(f"  routine   $C7:{ROUTINE_ADDRESS:04X}  {len(ROUTINE)} bytes")
    say(f"  marker    ${MARKER:06X}  two byte magic and the last list id")
    say(f"  state     {state}")


def main(
    argv: list[str],
    say: Callable[[str], None] = print,
    complain: Callable[[str], None] | None = None,
) -> int:
    complain = say if complain is None else complain
    if len(argv) != 3:
        complain("usage: repeatload.py <source-rom> <output-rom>")
        return 2

    source, output = Path(argv[1]), Path(argv[2])
    if source.resolve() == output.resolve():
        complain("refusing to patch the source ROM in place")
        return 1

    rom = source.read_bytes()
    report(rom, say)
    output.write_bytes(apply(rom))
    say(f"[done] {output} ({output.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
