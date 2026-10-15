import importlib
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent

ORIGIN = "https://github.com/gufranco/snes-street-fighter-alpha-2-nochip.git"

PACKAGES: dict[str, str] = {
    "mos65xx": "mos65xx-python",
    "spc700": "sony-spc700-python",
    "sdd1": "snes-sdd1-python",
    "sdsp": "sony-s-dsp-python",
    "mapper": "snes-mapper-python",
    "romimage": "snes-rom-image-python",
    "ssmp": "sony-s-smp-python",
    "snesgfx": "snes-graphics-python",
    "snesdriver": "snes-driver-python",
}


class UnknownPackage(Exception):
    pass


class ModelMissing(Exception): ...


def root_of(package: str) -> Path:
    directory = PACKAGES.get(package)
    if directory is None:
        raise UnknownPackage(
            f"{package} is not vendored here; this project carries {', '.join(sorted(PACKAGES))}"
        )
    return ROOT / directory


def install() -> None:
    for package in PACKAGES:
        entry = str(root_of(package))
        if entry not in sys.path:
            sys.path.insert(0, entry)


def is_checked_out(package: str) -> bool:
    directory = root_of(package)
    return directory.is_dir() and any(directory.iterdir())


def missing_models() -> list[str]:
    return [package for package in PACKAGES if not is_checked_out(package)]


def is_git_checkout() -> bool:
    return any((folder / ".git").exists() for folder in (ROOT, *ROOT.parents))


def checkout_message(missing: list[str], from_git: bool) -> str:
    named = ", ".join(sorted(missing))
    subject = "model is" if len(missing) == 1 else "models are"
    said = (
        f"the {named} {subject} pinned here but not checked out. "
        "A submodule is a pinned commit rather than content, so the directory is "
        "empty and nothing here can import."
    )
    if from_git:
        return f"{said}\n    git submodule update --init --recursive\nfills them in."
    return (
        f"{said}\n"
        "This tree has no git metadata, so it came from a downloaded archive. A source "
        "zip never carries submodule content and nothing can fill it in afterwards, so "
        "there is no repair for this copy. Clone instead:\n"
        f"    git clone --recurse-submodules {ORIGIN}"
    )


def load(package: str) -> Any:
    if not is_checked_out(package):
        raise ModelMissing(checkout_message(missing_models(), is_git_checkout()))
    install()
    return importlib.import_module(package)
