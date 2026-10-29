import importlib.util
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def load(name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, ROOT / f"{name}.py")
    assert spec is not None and spec.loader is not None, "no loader for that path"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


spcfast = load("spcfast")
shinakuma = load("shinakuma")


def variants(retail: bytes | bytearray) -> dict[str, bytes | bytearray]:
    fast = spcfast.apply(retail)
    return {"base": retail, "spc": fast, "both": shinakuma.apply(fast)}
