import importlib.util
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hardware

ROOT = Path(__file__).resolve().parent

romimage = hardware.load("romimage")


def _load(name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, ROOT / f"{name}.py")
    assert spec is not None and spec.loader is not None, "no loader for that path"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


pack = _load("pack")
rombuild = _load("rombuild")
spcfast = _load("spcfast")
shinakuma = _load("shinakuma")
gamefixes = _load("gamefixes")
repeatload = _load("repeatload")
prefight = _load("prefight")


def build(region: str, workdir: Path) -> bytes:
    retail = romimage.dump.read(pack.REGIONS[region].retail)
    cart = repeatload.apply(gamefixes.apply(shinakuma.apply(spcfast.apply(retail))))
    bypass = prefight.apply(pack.assemble_bypass(region, cart, workdir))
    extra = ((prefight.TABLE_ADDRESS, prefight.table()),)
    image = rombuild.build(bypass, pack.entries_for(region), extra=extra).image
    assert isinstance(image, bytes)
    declared = romimage.rewrite.declare_rom_only(pack.unify_headers(image))
    assert isinstance(declared, bytes)
    return declared
