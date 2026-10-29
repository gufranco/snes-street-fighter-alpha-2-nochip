import importlib.util
import sys
import unittest
from pathlib import Path
from typing import Any

import script

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hardware

sdd1 = hardware.load("sdd1")


ROOT = Path(__file__).resolve().parent


def load_module(name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, ROOT / f"{name}.py")
    assert spec is not None and spec.loader is not None, "no loader for that path"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ref = load_module("sdd1ref")


class WireFormatTest(unittest.TestCase):
    def test_a_request_carries_the_rom_then_every_case(self) -> None:
        rom = bytes(range(64))
        cases = [(0, 16), (32, 8)]

        blob = ref.encode_request(rom, cases)

        self.assertEqual(int.from_bytes(blob[:4], "little"), len(rom))
        self.assertEqual(blob[4 : 4 + len(rom)], rom)
        tail = blob[4 + len(rom) :]
        self.assertEqual(int.from_bytes(tail[:4], "little"), len(cases))
        self.assertEqual(int.from_bytes(tail[4:8], "little"), 0)
        self.assertEqual(int.from_bytes(tail[8:12], "little"), 16)

    def test_a_response_splits_on_the_requested_lengths(self) -> None:
        cases = [(0, 3), (10, 5)]

        parts = ref.decode_response(b"aaabbbbb", cases)

        self.assertEqual(parts, [b"aaa", b"bbbbb"])

    def test_a_zero_length_case_claims_a_full_64k_block(self) -> None:
        cases = [(0, 0)]

        parts = ref.decode_response(b"\x00" * sdd1.MAX_LENGTH, cases)

        self.assertEqual(len(parts[0]), sdd1.MAX_LENGTH)

    def test_a_short_response_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            ref.decode_response(b"aa", [(0, 3)])

    def test_a_length_above_a_64k_block_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            ref.encode_request(b"\x00" * 16, [(0, sdd1.MAX_LENGTH + 1)])

    def test_an_offset_outside_the_rom_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            ref.encode_request(b"\x00" * 16, [(16, 4)])


class ShellOutTest(unittest.TestCase):
    class Exited:
        def __init__(self, code: int, out: bytes = b"", err: bytes = b"") -> None:
            self.returncode, self.stdout, self.stderr = code, out, err

    def test_the_reference_runs_from_the_image_not_a_new_container(self) -> None:
        # Arrange
        expected = ["env", f"--chdir={ROOT}", "sdd1ref"]

        # Act
        found = ref.run_command()

        # Assert
        self.assertEqual(found, expected)

    def test_a_reference_on_the_path_is_available(self) -> None:
        # Arrange
        look = lambda _name: "/usr/local/bin/sdd1ref"  # noqa: E731

        # Act
        found = ref.reference_available(look)

        # Assert
        self.assertTrue(found)

    def test_a_reference_missing_from_the_path_is_not(self) -> None:
        # Arrange
        look = lambda _name: None  # noqa: E731

        # Act
        found = ref.reference_available(look)

        # Assert
        self.assertFalse(found)

    def test_the_named_snes9x_is_the_one_the_image_builds(self) -> None:
        # Arrange
        dockerfile = (ROOT / "Dockerfile").read_text()
        reference = dockerfile.split(" AS reference\n", 1)[1].split("\nFROM ", 1)[0]

        # Act
        found = f"ARG SNES9X_REF={ref.SNES9X}\n" in reference

        # Assert
        self.assertTrue(found)

    def test_a_reference_that_fails_is_reported_rather_than_parsed(self) -> None:
        with self.assertRaises(RuntimeError):
            ref.reference_outputs(
                bytes(1024), [(0, 16)], execute=lambda *_a, **_k: self.Exited(1, err=b"boom")
            )

    def test_a_reference_that_answers_is_split_into_one_output_per_case(self) -> None:
        found = ref.reference_outputs(
            bytes(1024),
            [(0, 4), (8, 4)],
            execute=lambda *_a, **_k: self.Exited(0, out=b"aaaabbbb"),
        )

        self.assertEqual(found, [b"aaaa", b"bbbb"])


class CompareTest(unittest.TestCase):
    ROM = bytes(0x400000)

    def test_a_case_the_two_agree_on_is_not_a_mismatch(self) -> None:
        want = ref.sdd1.decompress(self.ROM, 0x100000, 16).data

        self.assertEqual(ref.compare(self.ROM, [(0x100000, 16)], lambda *_a: [want]), [])

    def test_a_case_they_differ_on_names_the_first_differing_byte(self) -> None:
        want = bytearray(ref.sdd1.decompress(self.ROM, 0x100000, 16).data)
        want[3] ^= 0xFF

        found = ref.compare(self.ROM, [(0x100000, 16)], lambda *_a: [bytes(want)])

        self.assertEqual(found[0][2], "first differing byte at 3")

    def test_a_case_this_package_cannot_decode_is_named_as_truncated(self) -> None:
        found = ref.compare(self.ROM, [(0x3FFFFF, 8192)], lambda *_a: [bytes(8192)])

        self.assertEqual(found[0][2], "truncated")


class CommandTest(unittest.TestCase):
    ROM = bytes(0x400000)

    def run_with(self, argv: list[str], **rest: Any) -> tuple[int, list[str]]:
        said: list[str] = []
        code = ref.main(
            argv,
            read=lambda _p: self.ROM,
            say=lambda *args, **_k: said.append(str(args[0])),
            **{"available": lambda: True, "check": lambda *_a: [], **rest},
        )
        return code, said

    def test_no_rom_named_prints_the_usage(self) -> None:
        code, said = self.run_with(["sdd1ref.py"])

        self.assertEqual((code, "usage" in said[0]), (2, True))

    def test_a_missing_reference_stops_the_run_and_names_the_launcher(self) -> None:
        # Arrange
        argv = ["sdd1ref.py", "rom"]

        # Act
        code, said = self.run_with(argv, available=lambda: False)

        # Assert
        self.assertEqual(code, 1)
        self.assertIn("./run.sh <script>", "\n".join(said))

    def test_a_run_where_every_case_agrees_passes(self) -> None:
        # Arrange
        argv = ["sdd1ref.py", "rom", "3"]

        # Act
        code, said = self.run_with(argv)

        # Assert
        self.assertEqual(code, 0)
        self.assertIn("[ok] 3 cases identical to snes9x 1.63", said)

    def test_a_seed_can_be_named_so_the_sample_repeats(self) -> None:
        seen: list[list[tuple[int, int]]] = []

        def _record(_rom: Any, cases: list[tuple[int, int]]) -> list[Any]:
            seen.append(cases)
            return []

        for _ in range(2):
            self.run_with(["sdd1ref.py", "rom", "3", "7"], check=_record)

        self.assertEqual(seen[0], seen[1])

    def test_a_run_with_a_mismatch_names_it_and_fails(self) -> None:
        code, said = self.run_with(
            ["sdd1ref.py", "rom", "1"], check=lambda *_a: [(0x100000, 16, "wrong")]
        )

        self.assertEqual((code, "MISMATCH" in "\n".join(said)), (1, True))

    def test_only_the_first_twenty_mismatches_are_listed(self) -> None:
        many = [(n, 16, "wrong") for n in range(30)]

        _, said = self.run_with(["sdd1ref.py", "rom", "30"], check=lambda *_a: many)

        self.assertEqual(len([one for one in said if "MISMATCH" in one]), 20)


class SampleTest(unittest.TestCase):
    def test_a_rom_too_small_to_hold_a_block_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            ref.sample_cases(bytes(16), 1, 1)

    def test_the_same_seed_chooses_the_same_cases(self) -> None:
        rom = bytes(0x100000)

        self.assertEqual(ref.sample_cases(rom, 5, 1), ref.sample_cases(rom, 5, 1))

    def test_every_length_it_chooses_is_one_it_was_offered(self) -> None:
        cases = ref.sample_cases(bytes(0x100000), 20, 1)

        self.assertTrue(all(length in ref.SAMPLE_LENGTHS for _, length in cases))


script.entry(__name__, unittest.main, verbosity=2)
