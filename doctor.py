import importlib
import platform
import shutil
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, override

import script

ROOT = Path(__file__).resolve().parent

import environment  # noqa: E402

sys.path.insert(0, str(ROOT))

import hardware  # noqa: E402
import toolchain  # noqa: E402
from version import VERSION  # noqa: E402

sys.path.insert(0, str(ROOT / "tools"))

identify = importlib.import_module("identify")

OLDEST_PYTHON = (3, 12)

PROJECT = "snes-street-fighter-alpha-2-nochip"

PART = "sdd1"

TOOLS = toolchain.PROGRAMS

NEXT_WHEN_CLEAN = toolchain.launched("pack.py")

NEXT_WHEN_NOT = f"fix the first line marked ! above, then run {toolchain.launched('doctor.py')}"


class Finding:
    def __init__(self, name: str, ok: bool, detail: str, advice: str | None = None) -> None:
        self.name = name
        self.ok = ok
        self.detail = detail
        self.advice = advice

    @property
    def line(self) -> str:
        return f"  {'ok  ' if self.ok else '   !'}  {self.name}: {self.detail}"

    @property
    def report(self) -> str:
        if self.ok or not self.advice:
            return self.line
        return f"{self.line}\n         {self.advice}"

    @override
    def __repr__(self) -> str:
        return f"<Finding {self.name} {'ok' if self.ok else 'not ok'}>"


def _python() -> Finding:
    return Finding(
        "python",
        sys.version_info[:2] >= OLDEST_PYTHON,
        f"{platform.python_version()} on {platform.system()} {platform.machine()}",
        f"this project needs {OLDEST_PYTHON[0]}.{OLDEST_PYTHON[1]} or newer",
    )


def _project() -> Finding:
    return Finding(PROJECT, True, f"version {VERSION}")


def _checkout(cloned: Callable[[], bool] = hardware.is_git_checkout) -> Finding:
    if cloned():
        return Finding("checkout", True, "a git clone, so the submodules can be fetched")
    return Finding(
        "checkout",
        False,
        "no git metadata, so this came from a downloaded archive",
        "a downloaded ZIP never carries the submodules and nothing can add them"
        " afterwards; delete this folder and clone instead:"
        f" git clone --recurse-submodules {hardware.ORIGIN}",
    )


def _default_import(package: str) -> Any:
    hardware.install()
    return importlib.import_module(package)


def _model(package: str, where: Path, load: Callable[[str], Any]) -> Finding:
    if not Path(where).is_dir() or not any(Path(where).iterdir()):
        return Finding(
            package,
            False,
            f"{Path(where).name} is not checked out",
            "the models live in their own repositories and are pinned here as"
            " submodules; run git submodule update --init --recursive",
        )
    try:
        found = load(package)
    except Exception as trouble:
        return Finding(
            package,
            False,
            f"{type(trouble).__name__}: {trouble}",
            "the model is here and will not import, which is the line above"
            " rather than a missing checkout",
        )
    return Finding(package, True, f"version {getattr(found, 'VERSION', 'not stated')}")


def _default_cartridges() -> list[Any]:
    manifest = identify.read_manifest()
    return [identify.diagnose(one, manifest) for one in manifest["artifacts"]]


def _cartridges(diagnose: Callable[[], list[Any]] = _default_cartridges) -> list[Finding]:
    try:
        found = list(diagnose())
    except Exception as trouble:
        return [
            Finding(
                "cartridge",
                False,
                f"{type(trouble).__name__}: {trouble}",
                "the manifest could not be read, so nothing here says which dump"
                " this project wants",
            )
        ]
    lines = []
    for one in found:
        digest = f", sha256 {one.identity.sha256}" if one.identity else ""
        lines.append(
            Finding(
                f"cartridge {one.filename}",
                one.state in (identify.STATE_OK, identify.STATE_UNDECLARED),
                f"{one.state}{': ' + one.detail if one.detail else ''}{digest}",
                "the digests this project accepts are published in"
                " artifacts.manifest.json; nothing here says where to obtain a dump",
            )
        )
    return lines


def _default_decompress() -> Any:
    stream = bytes(range(256))
    return _default_import("sdd1").decompress(stream, 0, 8)


def _decompressor(decompress: Callable[[], Any] = _default_decompress) -> Finding:
    try:
        found = decompress()
    except Exception as trouble:
        return Finding(
            "decompressor",
            False,
            f"{type(trouble).__name__}: {trouble}",
            "the S-DD1 model is here and will not decode, which is the line above",
        )
    return Finding("decompressor", True, f"decoded {len(found)} bytes of a stream nobody owns")


def _tools(named: Any = TOOLS, look: Any = shutil.which) -> list[Finding]:
    lines = []
    for one in named:
        where = look(one)
        lines.append(
            Finding(
                one,
                bool(where),
                where or "not on the path",
                f"{one} ships in this project's image; start every command through"
                f" {toolchain.launched('<script>')}, which runs it there",
            )
        )
    return lines


def _default_beneath() -> list[tuple[str, bool]]:
    return _ask_each(sorted(hardware.PACKAGES), hardware.root_of, importlib.import_module)


def _ask_each(
    packages: list[str], locate: Callable[[str], Path], load: Callable[[str], Any]
) -> list[tuple[str, bool]]:
    found: list[tuple[str, bool]] = []
    for package in packages:
        where = Path(locate(package))
        if not where.is_dir():
            continue
        if str(where) not in sys.path:
            sys.path.insert(0, str(where))
        try:
            underneath = load(f"{package}.doctor")
        except ModuleNotFoundError:
            continue
        found.extend((where.name, one) for one in underneath.examine())
    return found


def _default_unused() -> tuple[str, ...]:
    return ()


def _beneath(beneath: Any, unused: Any = _default_unused) -> list[Finding]:
    try:
        found = list(beneath())
    except Exception as trouble:
        return [
            Finding(
                "the models underneath",
                False,
                f"{type(trouble).__name__}: {trouble}",
                "one of the models could not be examined; it is either not checked"
                " out or older than this project expects, and both are fixed by"
                " running git submodule update --init --recursive",
            )
        ]
    elsewhere = set(unused())
    lines = []
    for where, one in found:
        spare = one.name in elsewhere and not one.ok
        lines.append(
            Finding(
                f"{where} / {one.name}",
                one.ok or spare,
                f"{one.detail}, and this cartridge does not carry it" if spare else one.detail,
                None if spare else one.advice,
            )
        )
    return lines


def examine(load: Any = _default_import, beneath: Any = _default_beneath) -> list[Finding]:
    found = [_python(), _project(), _checkout()]
    found.extend(
        _model(package, hardware.root_of(package), load) for package in sorted(hardware.PACKAGES)
    )
    found.extend(_cartridges())
    found.append(_decompressor())
    found.extend(_tools())
    found.extend(_beneath(beneath))
    return found


def report(found: list[Finding]) -> list[str]:
    unwell = [one for one in found if not one.ok]
    lines = [f"{PROJECT} {VERSION} on {platform.python_version()}, {platform.system()}", ""]
    lines.append("  the machine")
    lines.extend(environment.lines(ROOT))
    lines.append("")
    lines.append("  this package")
    lines.extend(one.report for one in found)
    lines.append("")
    if unwell:
        lines.append(f"  {len(unwell)} of {len(found)} checks did not pass")
        lines.append(f"  next: {NEXT_WHEN_NOT}")
    else:
        lines.append(f"  {len(found)} checks, nothing to report")
        lines.append(f"  next: {NEXT_WHEN_CLEAN}")
    return lines


def main(argv: Any = (), examine: Any = examine, say: Callable[[str], None] = print) -> int:
    found = examine()
    for line in report(found):
        say(line)
    return 1 if any(not one.ok for one in found) else 0


script.entry(__name__, main, sys.argv[1:])
