import hashlib
import importlib.util
import subprocess
import sys
from collections import namedtuple
from collections.abc import Callable
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hardware


def load_images(load: Callable[[str], Any] = hardware.load) -> Any:
    try:
        return load("romimage")
    except hardware.ModelMissing as unchecked:
        raise SystemExit(str(unchecked)) from None


image_package = load_images()

dump = image_package.dump
rewrite = image_package.rewrite
copier = image_package.copier


ROOT = Path(__file__).resolve().parent


def _load(name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, ROOT / f"{name}.py")
    assert spec is not None and spec.loader is not None, "no loader for that path"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


rombuild = _load("rombuild")
spcfast = _load("spcfast")
shinakuma = _load("shinakuma")
gamefixes = _load("gamefixes")
repeatload = _load("repeatload")
prefight = _load("prefight")
jpstreams = _load("jpstreams")
usastreams = _load("usastreams")
version = _load("version")
gate = _load("gate")

Region = namedtuple("Region", "title retail bypass tagged")

REGIONS = {
    "usa": Region(
        title="sfa2-usa",
        retail=ROOT / "roms" / "sfa2-usa-final.sfc",
        bypass="asm/sdd1-bypass.asm",
        tagged=ROOT / "roms" / "sfa2-usa-vc-sound-restored.sfc",
    ),
    "jp": Region(
        title="sfz2-jp",
        retail=ROOT / "roms" / "sfz2-jp-final.sfc",
        bypass="asm/sdd1-bypass-jp.asm",
        tagged=None,
    ),
}

DIST = ROOT / "dist"
MANIFEST = "SHA256SUMS"

SD2SNES_CHIPSET = 0x43
HEADED_EXTENSION = ".smc"
EMULATOR = "emulator"
SUPER_EVERDRIVE = "supereverdrive"
SD2SNES = "sd2snes"
FXPAK = "fxpak"
GAME_DOCTOR = "gamedoctor"
DEVICES = (EMULATOR, SUPER_EVERDRIVE, SD2SNES, FXPAK, GAME_DOCTOR)


def output_name(region: str, release: str | None = None) -> str:
    found = version.stamped(f"{REGIONS[region].title}-nochip", release)
    assert isinstance(found, str)
    return found


def headed_name(region: str, release: str | None = None) -> str:
    found = version.stamped(f"{REGIONS[region].title}-nochip", release, HEADED_EXTENSION)
    assert isinstance(found, str)
    return found


def release_folder(release: str | None = None) -> str:
    found = version.stamped("", release, "")
    assert isinstance(found, str)
    return found.lstrip("-")


HEADER_ALIGNMENT = 0x8000
HEADER_OFFSET = 0x7FC0
HEADER_IDENTITY = rewrite.MAP_MODE + 1


def header_copies(image: bytes | bytearray) -> list[int]:
    anchor = rewrite.anchor_of(image)
    if anchor is None:
        return []
    identity = bytes(image[anchor : anchor + HEADER_IDENTITY])
    return [
        at
        for at in range(HEADER_OFFSET, len(image), HEADER_ALIGNMENT)
        if image[at : at + HEADER_IDENTITY] == identity
    ]


def unify_headers(image: bytes | bytearray) -> bytes:
    copies = header_copies(image)
    if not copies:
        return bytes(image)
    anchor = rewrite.anchor_of(image)
    block = bytes(image[anchor : anchor + rewrite.HEADER_BYTES])
    unified = bytearray(image)
    for at in copies:
        unified[at : at + len(block)] = block
    return bytes(unified)


def forms_of(region: str, image: bytes) -> list[tuple[str, bytes]]:
    plain = output_name(region)
    headed = headed_name(region)
    sd2snes = copier.for_sd2snes(image, SD2SNES_CHIPSET)
    return [
        (f"{EMULATOR}/{plain}", image),
        (f"{SUPER_EVERDRIVE}/{plain}", image),
        (f"{SD2SNES}/{headed}", sd2snes),
        (f"{FXPAK}/{headed}", sd2snes),
        (f"{GAME_DOCTOR}/{headed}", copier.for_game_doctor(image)),
    ]


def manifest_line(name: str, image: bytes | bytearray) -> str:
    return f"{hashlib.sha256(image).hexdigest()}  {name}"


def entries_for(region: str) -> Any:
    table = jpstreams.STREAMS if region == "jp" else usastreams.STREAMS
    return rombuild.entries_from_map({str(source): length for source, length in table})


class AssemblyFailed(Exception): ...


def assembly_failure(region: str, result: Any) -> str:
    said = [
        f"the {region} bypass patch did not assemble: build.py exited {result.returncode}",
        "",
        "This step assembles the patch in a container, so Docker has to be installed",
        "and running. Check it answers with: docker --version",
    ]
    for stream, raw in (("stdout", result.stdout), ("stderr", result.stderr)):
        text = (raw or "").strip()
        if text:
            said += ["", f"--- build.py {stream} ---", text]
    return "\n".join(said)


def assemble_command(region: str, staged: Path, produced_name: str) -> list[str]:
    return [
        sys.executable,
        "build.py",
        REGIONS[region].bypass,
        str(Path(staged).relative_to(ROOT)),
        produced_name,
    ]


def _shell_out(args: list[str]) -> Any:
    return subprocess.run(args, cwd=ROOT, check=False, capture_output=True, text=True)


def assemble_bypass(
    region: str,
    cart: bytes | bytearray,
    workdir: Path,
    execute: Callable[[list[str]], Any] = _shell_out,
) -> bytes:
    staged = workdir / f"{region}-patched.sfc"
    staged.write_bytes(cart)
    produced_name = f"{region}-bypass.sfc"
    result = execute(assemble_command(region, staged, produced_name))
    if result.returncode != 0:
        raise AssemblyFailed(assembly_failure(region, result))
    produced = ROOT / "asm" / produced_name
    image = produced.read_bytes()
    produced.unlink()
    return image


def build(region: str, workdir: Path) -> bytes:
    retail = dump.read(REGIONS[region].retail)
    cart = repeatload.apply(gamefixes.apply(shinakuma.apply(spcfast.apply(retail))))
    bypass = prefight.apply(assemble_bypass(region, cart, workdir))
    extra = ((prefight.TABLE_ADDRESS, prefight.table()),)
    image = rombuild.build(bypass, entries_for(region), extra=extra).image
    assert isinstance(image, bytes)
    declared = rewrite.declare_rom_only(unify_headers(image))
    assert isinstance(declared, bytes)
    return declared


def main(
    argv: list[str],
    make: Any = None,
    gate_check: Any = None,
    say: Callable[[str], None] = print,
    complain: Callable[[str], None] | None = None,
    dist: Path | None = None,
    forms: Callable[[str, bytes], list[tuple[str, bytes]]] = forms_of,
) -> int:
    complain = say if complain is None else complain
    make = build if make is None else make
    gate_check = gate.check if gate_check is None else gate_check
    dist = DIST if dist is None else Path(dist)

    wanted = argv[1:] or sorted(REGIONS)
    unknown = [region for region in wanted if region not in REGIONS]
    if unknown:
        complain(f"unknown region: {', '.join(unknown)}")
        return 2

    missing = [str(REGIONS[r].retail) for r in wanted if not REGIONS[r].retail.exists()]
    if missing:
        complain("these retail dumps are not present:")
        for path in missing:
            complain(f"  {path}")
        return 1

    for region in wanted:
        findings = gate_check(region)
        if findings:
            complain(f"the {region} stream table does not pass the gate:")
            for finding in findings:
                complain(f"  {finding}")
            return 1

    dist.mkdir(exist_ok=True)
    workdir = dist / "work"
    workdir.mkdir(exist_ok=True)
    release = dist / release_folder()
    release.mkdir(exist_ok=True)

    lines = []
    for region in wanted:
        try:
            image = make(region, workdir)
        except AssemblyFailed as failure:
            complain(str(failure))
            return 1
        for name, written in forms(region, image):
            (release / name).parent.mkdir(parents=True, exist_ok=True)
            (release / name).write_bytes(written)
            lines.append(manifest_line(name, written))
            say(f"  {release.name}/{name}  {len(written):,} bytes")

    (release / MANIFEST).write_text("\n".join(lines) + "\n")
    say(f"  {release.name}/{MANIFEST}  {len(lines)} images")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
