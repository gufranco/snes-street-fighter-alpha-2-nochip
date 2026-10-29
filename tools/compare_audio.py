import re
import subprocess
import sys
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import toolchain  # noqa: E402

IMAGES = ROOT / "build" / "all"
LOGS = ROOT / "build" / "logs"


ROSTER = 18
BUDGET = 4000

FREE_MAPPING = "-2"
CART_MAPPING = "-1"

BLOCK_END = re.compile(r"^BLKEND src=(\w\w):(\w{4}) len=(\d+) writes=(\d+) expect=(\d+)")
BLOCK_BAD = re.compile(r"^BLKBAD src=(\w\w):(\w{4}) dest=(\w{4}) len=(\d+) bad=(\d+) first=(\d+)")
BLOCKS = re.compile(r"^BLOCKS ok=(\d+) bad=(\d+)")
RESULT = re.compile(r"^RESULT load=(\w+) frames=(\d+)")


def mapping_for(stem: str) -> str:
    return FREE_MAPPING if stem.endswith("-free") else CART_MAPPING


class Usage(Exception):
    pass


def options(argv: list[str]) -> tuple[str, str, int, int, bool]:
    roster, budget, fights = ROSTER, BUDGET, False
    rest = []
    argv = list(argv[1:])
    while argv:
        entry = argv.pop(0)
        if entry == "--fights":
            fights = True
        elif entry == "--roster":
            roster = int(argv.pop(0))
        elif entry == "--budget":
            budget = int(argv.pop(0))
        else:
            rest.append(entry)
    if len(rest) != 2:
        raise Usage("two images are needed, a stock one and a patched one")
    return rest[0], rest[1], roster, budget, fights


def run(
    image: Path,
    roster: int = ROSTER,
    budget: int = BUDGET,
    fights: bool = False,
    execute: Callable[..., Any] = subprocess.run,
) -> Path:
    LOGS.mkdir(parents=True, exist_ok=True)
    image = Path(image).resolve()
    log = LOGS / f"audio-{image.stem}.txt"
    with log.open("wb") as handle:
        execute(
            toolchain.command(
                toolchain.EMULATOR,
                [
                    "SFTOUR=1",
                    f"SFTOURROSTER={roster}",
                    f"SFTOURBUDGET={budget}",
                    "SFVERIFY=1",
                    *(("SFTOURCONFIRM=1",) if fights else ()),
                ],
                [
                    str(image.relative_to(ROOT)),
                    str(roster * budget),
                    mapping_for(image.stem),
                ],
            ),
            stdout=handle,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    return log


def read(log: Path) -> dict[str, Any]:
    blocks = []
    corrupt = []
    ok = bad = frames = 0
    loaded = "?"
    for line in Path(log).read_text(errors="replace").splitlines():
        found = BLOCK_END.match(line)
        if found:
            bank, source, length, writes, expect = found.groups()
            blocks.append(
                {
                    "source": (int(bank, 16) << 16) | int(source, 16),
                    "length": int(length),
                    "writes": int(writes),
                    "expect": int(expect),
                }
            )
            continue
        found = BLOCK_BAD.match(line)
        if found:
            bank, source, dest, length, count, first = found.groups()
            corrupt.append(
                {
                    "source": (int(bank, 16) << 16) | int(source, 16),
                    "destination": int(dest, 16),
                    "length": int(length),
                    "bad": int(count),
                    "first": int(first),
                }
            )
            continue
        found = BLOCKS.match(line)
        if found:
            ok, bad = int(found.group(1)), int(found.group(2))
            continue
        found = RESULT.match(line)
        if found:
            loaded, frames = found.group(1), int(found.group(2))
    return {
        "load": loaded,
        "frames": frames,
        "ok": ok,
        "bad": bad,
        "blocks": blocks,
        "corrupt": corrupt,
    }


def uploads(found: dict[str, Any]) -> Counter[tuple[int, int]]:
    return Counter((block["source"], block["length"]) for block in found["blocks"])


def fewer(stock: dict[str, Any], patched: dict[str, Any]) -> dict[Any, Any]:
    before, after = uploads(stock), uploads(patched)
    return {
        source: (count, after.get(source, 0))
        for source, count in before.items()
        if after.get(source, 0) < count
    }


def missing(stock: dict[str, Any], patched: dict[str, Any]) -> list[Any]:
    after = uploads(patched)
    return [source for source in uploads(stock) if source not in after]


def cost(found: dict[str, Any]) -> float:
    written = sum(block["writes"] for block in found["blocks"])
    length = sum(block["length"] for block in found["blocks"])
    return written / length if length else 0.0


def verdict(stock: dict[str, Any], patched: dict[str, Any]) -> list[str]:
    reasons = []
    if stock["load"] != "ok" or patched["load"] != "ok":
        reasons.append("one of the builds did not load")
    if stock["bad"] or patched["bad"]:
        reasons.append("a block did not arrive intact")
    if missing(stock, patched):
        reasons.append("a source the stock build uploads was never uploaded")
    return reasons


def report(
    stock_name: str,
    patched_name: str,
    stock: dict[str, Any],
    patched: dict[str, Any],
    say: Callable[[str], None] = print,
) -> None:
    for name, found in ((stock_name, stock), (patched_name, patched)):
        say(
            f"  {name:24s} load={found['load']:3s} frames={found['frames']:6d} "
            f"blocks={len(found['blocks']):5d} ok={found['ok']:5d} bad={found['bad']:3d} "
            f"writes/byte={cost(found):.3f}"
        )

    for entry in (stock["corrupt"] + patched["corrupt"])[:10]:
        say(
            f"    CORRUPT {entry['source']:#08x} to {entry['destination']:#06x}, "
            f"{entry['bad']} of {entry['length']} bytes wrong from byte {entry['first']}"
        )

    gone = missing(stock, patched)
    for source, length in gone[:10]:
        say(f"    NEVER UPLOADED {source:#08x} for {length} bytes")

    say(f"    {len(fewer(stock, patched))} sources uploaded fewer times, {len(gone)} never")
    if cost(stock) and cost(patched):
        say(f"    writes per byte went from {cost(stock):.3f} to {cost(patched):.3f}")


def main(
    argv: list[str],
    drive: Callable[..., Path] = run,
    say: Callable[..., None] = print,
) -> int:
    try:
        stock, patched, roster, budget, fights = options(argv)
    except (Usage, IndexError, ValueError) as refusal:
        say(f"  {refusal}", file=sys.stderr)
        say(
            "usage: compare_audio.py [--fights] [--roster N] [--budget N] <stock> <patched>",
            file=sys.stderr,
        )
        return 2

    stock_path, patched_path = Path(stock), Path(patched)
    stock_run = read(drive(stock_path, roster, budget, fights))
    patched_run = read(drive(patched_path, roster, budget, fights))

    report(stock_path.name, patched_path.name, stock_run, patched_run, say)
    reasons = verdict(stock_run, patched_run)
    for reason in reasons:
        say(f"    FAIL {reason}")
    return 1 if reasons else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
