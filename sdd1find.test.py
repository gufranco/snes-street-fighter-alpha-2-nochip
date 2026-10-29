import importlib.util
import random
import sys
import unittest
from pathlib import Path
from typing import Any

import script

sys.path.insert(0, str(Path(__file__).resolve().parent))


ROOT = Path(__file__).resolve().parent


def load_module(name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, ROOT / f"{name}.py")
    assert spec is not None and spec.loader is not None, "no loader for that path"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


find = load_module("sdd1find")


class BitmapTest(unittest.TestCase):
    def test_every_window_of_the_source_is_marked(self) -> None:
        data = bytes(range(64))

        bitmap = find.build_bitmap(data, window=4, bits=16)

        for i in range(len(data) - 3):
            self.assertTrue(find.probe(bitmap, data[i : i + 4], bits=16))

    def test_an_absent_window_is_usually_rejected(self) -> None:
        data = bytes(range(64))
        bitmap = find.build_bitmap(data, window=4, bits=20)
        rng = random.Random(4)

        rejected = sum(
            0 if find.probe(bitmap, bytes(rng.randrange(256) for _ in range(4)), bits=20) else 1
            for _ in range(200)
        )

        self.assertGreater(rejected, 190)

    def test_a_bitmap_sized_in_bits_allocates_that_many_slots(self) -> None:
        bitmap = find.build_bitmap(b"abcd", window=4, bits=16)

        self.assertEqual(len(bitmap), (1 << 16) // 8)


class EntropyTest(unittest.TestCase):
    def test_flat_output_is_rejected(self) -> None:
        self.assertFalse(find.is_distinctive(b"\x00" * 64, minimum=10))

    def test_a_two_value_pattern_is_rejected(self) -> None:
        self.assertFalse(find.is_distinctive(b"\x01\x02" * 32, minimum=10))

    def test_real_tile_data_is_accepted(self) -> None:
        rng = random.Random(9)
        blob = bytes(rng.randrange(256) for _ in range(64))

        self.assertTrue(find.is_distinctive(blob, minimum=10))


class SyntheticFindTest(unittest.TestCase):
    STREAM = 0x1000

    @classmethod
    def source(cls, seed: int = 5) -> bytes:
        rng = random.Random(seed)
        rom = bytearray(0x20000)
        rom[cls.STREAM : cls.STREAM + 0x2000] = bytes(rng.randrange(256) for _ in range(8192))
        return bytes(rom)

    @classmethod
    def reference(cls, rom: bytes, length: int = 512, seed: int = 6) -> bytes:
        rng = random.Random(seed)
        noise = bytes(rng.randrange(256) for _ in range(2048))
        output: bytes = find.sdd1.decompress(rom, cls.STREAM, length).data
        return noise + output

    def test_a_stream_whose_output_is_in_the_reference_is_found(self) -> None:
        rom = self.source()

        hits = find.find_streams(rom, self.reference(rom), self.STREAM, self.STREAM + 1)

        self.assertEqual([hit.source for hit in hits], [self.STREAM])

    def test_the_hit_says_where_in_the_reference_the_output_landed(self) -> None:
        rom = self.source()

        hits = find.find_streams(rom, self.reference(rom), self.STREAM, self.STREAM + 1)

        self.assertEqual(hits[0].target, 2048)

    def test_the_hit_says_how_far_the_two_agree(self) -> None:
        rom = self.source()

        hits = find.find_streams(rom, self.reference(rom), self.STREAM, self.STREAM + 1)

        self.assertEqual(hits[0].length, 512)

    def test_a_reference_that_does_not_carry_the_output_yields_nothing(self) -> None:
        rom = self.source()

        hits = find.find_streams(rom, bytes(4096), self.STREAM, self.STREAM + 1)

        self.assertEqual(hits, [])

    def test_progress_is_reported_at_the_interval_it_was_given(self) -> None:
        seen: list[int] = []

        find.find_streams(
            bytes(0x20000), bytes(4096), 0, 250001, progress=lambda at, _n: seen.append(at)
        )

        self.assertEqual(seen, [0, 250000])


class CommandTest(unittest.TestCase):
    def run_with(self, argv: list[str], source: bytes, reference: bytes) -> tuple[int, list[str]]:
        said: list[str] = []
        code = find.main(
            argv,
            read=lambda where: source if str(where) == argv[1] else reference,
            say=lambda *args, **_k: said.append(str(args[0])),
        )
        return code, said

    def test_too_few_arguments_prints_the_usage(self) -> None:
        code, said = self.run_with(["sdd1find.py", "one"], b"", b"")

        self.assertEqual((code, "usage" in said[0]), (2, True))

    def test_a_scan_that_finds_a_stream_reports_it(self) -> None:
        rom = SyntheticFindTest.source()
        reference = SyntheticFindTest.reference(rom)

        code, said = self.run_with(
            ["sdd1find.py", "source", "reference", "0x1000", "0x1001"], rom, reference
        )

        self.assertEqual((code, "confirmed streams: 1" in "\n".join(said)), (0, True))

    def test_the_report_names_the_deepest_confirmations(self) -> None:
        rom = SyntheticFindTest.source()

        _, said = self.run_with(
            ["sdd1find.py", "source", "reference", "0x1000", "0x1001"],
            rom,
            SyntheticFindTest.reference(rom),
        )

        self.assertIn("bytes verbatim", "\n".join(said))

    def test_a_scan_that_finds_nothing_says_so(self) -> None:
        _, said = self.run_with(
            ["sdd1find.py", "source", "reference", "0x1000", "0x1001"], bytes(0x20000), bytes(4096)
        )

        self.assertIn("confirmed streams: 0", "\n".join(said))

    def test_no_range_named_means_the_whole_cartridge(self) -> None:
        _, said = self.run_with(["sdd1find.py", "source", "reference"], bytes(4096), bytes(4096))

        self.assertIn("0x0..0x1000", "\n".join(said))

    @staticmethod
    def two_adjacent() -> tuple[bytes, bytes]:
        rng = random.Random(31)
        rom = bytearray(0x8000)
        rom[0x1000:0x4000] = bytes(rng.randrange(256) for _ in range(0x3000))
        first = find.sdd1.decompress(bytes(rom), 0x1000, 512).data
        second = find.sdd1.decompress(bytes(rom), 0x1400, 512).data
        return bytes(rom), bytes(2048) + first + second

    def test_neighbouring_streams_are_reported_as_one_chain(self) -> None:
        rom, reference = self.two_adjacent()

        _, said = self.run_with(
            ["sdd1find.py", "source", "reference", "0x1000", "0x1401"], rom, reference
        )

        self.assertIn("2 streams  source 0x0001000", "\n".join(said))

    def test_a_scan_with_no_chain_reports_none(self) -> None:
        rom = SyntheticFindTest.source()

        _, said = self.run_with(
            ["sdd1find.py", "source", "reference", "0x1000", "0x1001"],
            rom,
            SyntheticFindTest.reference(rom),
        )

        self.assertIn("contiguous chains of streams: 0", "\n".join(said))


class ExtendTest(unittest.TestCase):
    def test_agreement_stops_where_the_reference_stops(self) -> None:
        rom = SyntheticFindTest.source()
        short = find.sdd1.decompress(rom, SyntheticFindTest.STREAM, find.CONFIRM_LENGTH).data

        found = find.extend(rom, short, SyntheticFindTest.STREAM, 0)

        self.assertEqual(found, find.CONFIRM_LENGTH)

    def test_a_longer_agreement_is_reported_as_longer(self) -> None:
        rom = SyntheticFindTest.source()
        long = find.sdd1.decompress(rom, SyntheticFindTest.STREAM, 512).data

        found = find.extend(rom, long, SyntheticFindTest.STREAM, 0)

        self.assertEqual(found, 512)


class ChainTest(unittest.TestCase):
    @staticmethod
    def hit(source: int, target: int, length: int) -> Any:
        return find.Hit(source, target, length)

    def test_two_hits_that_meet_form_one_chain(self) -> None:
        found = find.chains([self.hit(0, 0, 16), self.hit(1, 16, 16)])

        self.assertEqual(len(found), 1)

    def test_two_hits_with_a_gap_between_them_form_two(self) -> None:
        found = find.chains([self.hit(0, 0, 16), self.hit(1, 1000, 16)])

        self.assertEqual(len(found), 2)

    def test_a_gap_within_the_tolerance_still_joins_them(self) -> None:
        found = find.chains([self.hit(0, 0, 16), self.hit(1, 18, 16)])

        self.assertEqual(len(found), 1)

    def test_no_hits_at_all_form_no_chains(self) -> None:
        self.assertEqual(find.chains([]), [])


class ProbeRefusalTest(unittest.TestCase):
    def test_an_offset_that_does_not_decode_is_passed_over(self) -> None:
        rng = random.Random(31)
        rom = bytearray(0x8000)
        rom[0x7000:0x8000] = bytes(rng.randrange(256) for _ in range(0x1000))

        self.assertEqual(find.find_streams(bytes(rom), bytes(4096), 0x7FFE, 0x8000), [])

    @staticmethod
    def near_the_end() -> bytes:
        rng = random.Random(31)
        rom = bytearray(0x8000)
        rom[0x7000:0x8000] = bytes(rng.randrange(256) for _ in range(0x1000))
        return bytes(rom)

    def test_an_offset_whose_confirmation_runs_off_the_cartridge_is_passed_over(self) -> None:
        rom = self.near_the_end()
        head = find.sdd1.decompress(rom, 0x7FF0, find.PROBE_LENGTH).data
        reference = bytes(1024) + head + bytes(1024)

        self.assertEqual(find.find_streams(rom, reference, 0x7FF0, 0x7FF1), [])

    def test_a_false_positive_from_a_narrow_filter_is_rejected_by_the_lookup(self) -> None:
        rom = SyntheticFindTest.source()

        found = find.find_streams(
            rom, bytes(range(256)) * 16, 0x1000, 0x1001, probe_bits=4, confirm_bits=4
        )

        self.assertEqual(found, [])

    def test_an_offset_whose_probe_is_not_distinctive_is_passed_over(self) -> None:
        self.assertEqual(find.find_streams(bytes(0x2000), bytes(4096), 0x1000, 0x1001), [])

    def test_an_offset_whose_probe_is_not_in_the_reference_is_passed_over(self) -> None:
        rom = SyntheticFindTest.source()

        self.assertEqual(find.find_streams(rom, bytes(0x2000), 0x1000, 0x1001), [])

    NARROW = bytes.fromhex("03030201020102020200000001ff0001020202000100ff0302030101ff030002")

    def test_an_offset_whose_confirmation_is_not_distinctive_is_passed_over(self) -> None:
        rom = bytearray(0x2000)
        rom[0x1000 : 0x1000 + len(self.NARROW)] = self.NARROW
        head = find.sdd1.decompress(bytes(rom), 0x1000, find.PROBE_LENGTH).data
        reference = bytes(1024) + head + bytes(1024)

        found = find.find_streams(bytes(rom), reference, 0x1000, 0x1001)

        self.assertEqual(found, [])

    def test_an_offset_confirmed_by_the_probe_but_not_by_the_output_is_passed_over(self) -> None:
        rom = SyntheticFindTest.source()
        head = find.sdd1.decompress(rom, 0x1000, find.PROBE_LENGTH).data

        found = find.find_streams(rom, bytes(2048) + head + bytes(2048), 0x1000, 0x1001)

        self.assertEqual(found, [])


class ExtendStopTest(unittest.TestCase):
    def test_a_stream_that_runs_off_the_cartridge_stops_where_it_stopped(self) -> None:
        rom = bytearray(0x2000)
        rng = random.Random(9)
        rom[0x1F00:0x2000] = bytes(rng.randrange(256) for _ in range(256))
        whole = find.sdd1.decompress(bytes(rom), 0x1F00, find.CONFIRM_LENGTH).data

        found = find.extend(bytes(rom), whole, 0x1F00, 0, limit=0x100000)

        self.assertEqual(found, find.CONFIRM_LENGTH)

    def test_a_stream_that_runs_out_of_cartridge_keeps_what_it_confirmed(self) -> None:
        rng = random.Random(41)
        rom = bytearray(0x8000)
        rom[0x7000:0x8000] = bytes(rng.randrange(256) for _ in range(0x1000))
        blob = find.sdd1.decompress(bytes(rom), 0x7FC8, find.CONFIRM_LENGTH).data

        found = find.extend(bytes(rom), blob, 0x7FC8, 0)

        self.assertEqual(found, find.CONFIRM_LENGTH)

    def test_a_stream_already_at_the_limit_is_never_extended(self) -> None:
        rom = SyntheticFindTest.source()
        blob = find.sdd1.decompress(rom, SyntheticFindTest.STREAM, find.CONFIRM_LENGTH).data

        found = find.extend(rom, blob, SyntheticFindTest.STREAM, 0, limit=find.CONFIRM_LENGTH)

        self.assertEqual(found, find.CONFIRM_LENGTH)


script.entry(__name__, unittest.main, verbosity=2)
