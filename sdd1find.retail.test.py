import importlib.util
import random
import sys
import unittest
from pathlib import Path
from typing import Any, ClassVar, override

import script

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hardware

sdd1 = hardware.load("sdd1")

dump = hardware.load("romimage").dump

ROOT = Path(__file__).resolve().parent


def load_module(name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, ROOT / f"{name}.py")
    assert spec is not None and spec.loader is not None, "no loader for that path"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


find = load_module("sdd1find")

ALPHA2 = ROOT / "roms" / "sfa2-usa-final.sfc"

KNOWN_STREAM = 0x13C03B

KNOWN_LENGTH = 1536

FLAT_HEADED_STREAM = 0x7890

FLAT_HEADED_LENGTH = 832


@unittest.skipUnless(ALPHA2.exists(), "the alpha 2 rom is not present")
class FindStreamsTest(unittest.TestCase):
    output: ClassVar[Any]
    rom: ClassVar[Any]

    @classmethod
    @override
    def setUpClass(cls) -> None:
        cls.rom = dump.read(ALPHA2)
        cls.output = sdd1.decompress(cls.rom, KNOWN_STREAM, KNOWN_LENGTH).data

    def build_reference(self, seed: int = 1) -> Any:
        rng = random.Random(seed)
        noise = bytes(rng.randrange(256) for _ in range(4096))
        return noise + self.output + noise

    def test_a_known_stream_is_located_in_a_synthetic_reference(self) -> None:
        reference = self.build_reference()

        hits = find.find_streams(
            self.rom, reference, start=KNOWN_STREAM - 64, stop=KNOWN_STREAM + 64
        )

        self.assertIn(KNOWN_STREAM, [hit.source for hit in hits])

    def test_the_hit_reports_where_the_output_landed(self) -> None:
        reference = self.build_reference()

        hits = [
            hit
            for hit in find.find_streams(
                self.rom, reference, start=KNOWN_STREAM, stop=KNOWN_STREAM + 1
            )
            if hit.source == KNOWN_STREAM
        ]

        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].target, 4096)
        self.assertGreaterEqual(hits[0].length, find.CONFIRM_LENGTH)

    def test_a_reference_without_the_stream_yields_nothing(self) -> None:
        rng = random.Random(2)
        reference = bytes(rng.randrange(256) for _ in range(8192))

        hits = find.find_streams(
            self.rom, reference, start=KNOWN_STREAM - 64, stop=KNOWN_STREAM + 64
        )

        self.assertEqual(hits, [])

    def test_a_stream_that_opens_on_a_blank_tile_is_not_locatable(self) -> None:
        blank = sdd1.decompress(self.rom, FLAT_HEADED_STREAM, FLAT_HEADED_LENGTH).data
        rng = random.Random(3)
        noise = bytes(rng.randrange(256) for _ in range(4096))
        reference = noise + blank + noise

        hits = find.find_streams(
            self.rom,
            reference,
            start=FLAT_HEADED_STREAM,
            stop=FLAT_HEADED_STREAM + 1,
        )

        self.assertEqual(hits, [])

    def test_neighbouring_offsets_do_not_masquerade_as_the_stream(self) -> None:
        reference = self.build_reference()

        hits = find.find_streams(self.rom, reference, start=KNOWN_STREAM - 8, stop=KNOWN_STREAM)

        self.assertEqual(hits, [])


script.entry(__name__, unittest.main)
