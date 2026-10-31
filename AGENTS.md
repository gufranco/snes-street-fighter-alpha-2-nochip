# Working in this repository

Street Fighter Alpha 2 shipped with a decompression chip on the cartridge, and
without that chip the game does not run. This repository builds an image that
does not need it: every stream the S-DD1 would expand at runtime is expanded
ahead of time, and the result is laid out in a windowed map that a plain 96 Mbit
cartridge holds. Around that sit corrections to the game's own code and a faster
sample upload, both of which change instructions that run on real hardware.

[`README.md`](README.md) is the guide for a person who wants to build and play
it. [`REFERENCE.md`](REFERENCE.md) is the full interface, every command and how
the image is built and checked. This file is what an agent needs on top of both.

## Hard rules

**Fidelity wins every decision.** When it pulls against speed, a smaller diff, a
simpler implementation or a shorter test run, fidelity wins and the cost is
reported. A shortcut that no test notices is still wrong. Slower is acceptable;
less accurate never is.

**Docker carries every dependency, never the host.** Python, asar, the emulator
and reference builds and every lint and test tool live in the image the
[`Dockerfile`](Dockerfile) describes. The host needs Docker and git. Every
command runs through [`run.sh`](run.sh), or [`run.cmd`](run.cmd) on Windows, and
nothing here tells a reader to install a tool or uses one the host happens to
have.

**Three chip-free projects share one tooling layout.** This repository,
snes-dungeon-master-nochip and snes-pilotwings-nochip keep the same Dockerfile
stage names, launchers, gate script, [`toolchain.py`](toolchain.py), CI jobs and
doctor shape. A tooling change lands in all three in the same task, and a
difference between them comes from the game.

**No retail data is ever committed.** Nothing in `roms/` or `boot/`, and no
`*.sfc`, `*.smc` or `*.bin`, in any form. Everything published about an input
is a digest: [`artifacts.manifest.json`](artifacts.manifest.json) carries four
per file, and `sha256` decides.

## Where an answer comes from

Every factual question is answered by the highest source that has an answer, and
a lower one never overrules a higher one:

1. The bytes of a real dump, or a run on real hardware.
2. A model held to its own suite: one of the nine below.
3. A recording from an independent implementation, such as snes9x's
   `sdd1emu.cpp`.
4. Anything else, cited as what it is.

**A third party patch is never evidence**, not about hardware and not about
itself. One widely circulated package ships assembly describing a two byte upload
and a binary whose driver reads three ports per handshake; they are eighteen
months apart and describe different drivers. Anything taken from such a package
is re-derived here and measured, or it is not taken.

When two sources disagree and nothing above them answers, the answer is unknown.
It goes in [`conformance/divergences.json`](conformance/divergences.json) with
the measurement that would settle it, and it is never resolved by picking the
convenient source.

## The nine models

Every claim about what a part does is made by a model on the import path, never
here. [`hardware.py`](hardware.py) is the only way any of them is reached, and it
explains a missing checkout instead of failing on an import.

| Model | What it answers |
|:--|:--|
| `sdd1` | What the decompressor produces for a given stream |
| `mos65xx` | What the cartridge's own code does when run |
| `spc700` | What the audio processor does |
| `ssmp` | The same, with the mixer and boot program behind it, and cycles |
| `sdsp` | What reaches the mixer |
| `mapper` | Where an address lands in a cartridge |
| `romimage` | What a header says and what its checksum should be |
| `snesgfx` | Whether a decompressed stream reads as tiles |
| `snesdriver` | Where in the code the cartridge talks to its chip |

When two models can answer the same question, ask both. The sample upload runs on
a stand-in written from a reading of the driver and on the whole audio unit, and
the two agreeing is the check that neither provides alone.

Each model is a pinned submodule. Moving a pin changes this project's behaviour
until shown otherwise: run every gate against the newer copy before committing
the bump, and when an output changes, find the upstream commit that changed it
before touching anything that records the expected output. A digest edited to
make a check pass is the failure every check here exists to prevent.

## The stream table and its fallback

Streams are found, decompressed, verified, and only then packed. A stream that
fails to decompress is a missing entry in a table, not a broken decompressor,
and the tools say which. Packing before verifying produces an image that boots
and is wrong somewhere nobody looked.

The table holds what the game asks for. The USA table was read from a tagged
dump, so it is the game's own list. The Japanese table was found by running the
game, so a recording is a floor: a figure taken from one states the frames it
covers and what the run was doing, and it never describes what the whole game
uses.

A replacement for a part needs a fallback for the case its table does not cover,
because a lookup with no row either hangs or reads whatever was in memory. A
fallback nobody measured is a fallback nobody has: its cost is stated in cycles,
and a build reports how often it fired. The translate routine in
[`asm/sdd1-translate.asm`](asm/sdd1-translate.asm) scans without a bound and has
no fallback; the divergence record carries that.

## Every gate, in the order to run them

```sh
./run.sh --gates
```

[`scripts/gates.sh`](scripts/gates.sh) runs in the `gates` stage of the
[`Dockerfile`](Dockerfile) and stops at the first failure: ruff check, ruff
format, mypy, prettier, yamllint, shellcheck, actionlint, then every test module
under coverage and the coverage report. CI runs the same script in the same
image. A gate run on the host proves nothing about the image, and every gate
decides on its exit code, never on a phrase in its output. The suite is 1,323
tests and takes several minutes; a run that finishes faster did not run all of
it.

A test that needs a retail dump goes in `<module>.retail.test.py` beside the
module, and code that only runs on a dump, such as `build` in
[`pack.retail.py`](pack.retail.py), goes in `<module>.retail.py`. Both skip where
the dump is absent. The gate holds every file to 100% unless the run declares
`RETAIL_INPUTS=absent`, which CI does because it never holds a dump; only then
does the report leave `*.retail.*` out, and its heading says so.

`pnpm`, never `npm`. The JSON and YAML formatter is a separate gate from ruff.

## Conventions

| Thing | Rule |
|:--|:--|
| Language | Python, standard library only at runtime |
| Comments | None in Python source, docstrings included. Tool directives and the three test markers are the only exceptions |
| Tests | `<module>.test.py` beside the module. `# Arrange`, `# Act`, `# Assert`, each opening its block, one blank line between, nothing else inside the body. Each name is a sentence about behaviour |
| Coverage | 100% of statements and branches, enforced, with no exclusion directive |
| Types | `mypy` strict, plus the optional error classes in [`pyproject.toml`](pyproject.toml) |
| Lint and format | `ruff`, clean |
| Commits | Conventional Commits, subject under 50 characters |
| Docs | [`README.md`](README.md) in four languages, English first and each translation made from it; the interface only in [`REFERENCE.md`](REFERENCE.md). Every count a document states is one somebody ran |

**A check nobody has seen fail is not known to work.** Drive every new check
against input that should fail it before keeping it. A check that examined
nothing exits zero exactly like one that examined everything, so a runner prints
what it checked.

**The doctor reports, it never hides.** [`doctor.py`](doctor.py) prints what it
looked at on this machine, reports a missing file as missing, turns a check that
throws into a line naming what it threw, and exits non-zero when something is
wrong. Its output is meant to be pasted into an issue unchanged.

The configuration files carry no comments, so the reasons for their ignores and
exclusions live here:

- `BLE001` in [`doctor.py`](doctor.py): the doctor reports whatever a check
  throws, and a narrower catch would let an unforeseen failure end the report as
  a traceback.
- `BLE001` and `T201` in [`environment.py`](environment.py): a check that throws
  becomes a line in the report, and the printed report is the product.
- The submodule paths in the coverage `omit`, the ruff `extend-exclude`, the
  mypy `exclude`, [`.prettierignore`](.prettierignore) and
  [`.yamllint.yaml`](.yamllint.yaml): each model is measured in its own
  repository against its own gate. `build/` holds generated and third party
  sources this project does not own.
- [`spcfast.py`](spcfast.py) in the coverage `omit`: it is generated by
  [`tools/freeze_spcfast.py`](tools/freeze_spcfast.py), which is measured, and
  its frame hook is parked with an empty pattern, so neither the finder nor the
  run that would place it can execute. The tests pin that dormancy through
  `FRAME_HOOK` and `runs_for`.
- The PLR complexity and magic-value rules in the ruff `ignore`: enabling them
  reports 35 sites, mostly argument-count checks in command entry points, not
  yet rewritten.

## Things that will bite you

**A comment claiming a measurement is not a measurement.** One here said the
audio unit's boot window had to be hidden or the driver ran away. Running it both
ways showed the window changes nothing. Read what the test exercises before
believing what the prose asserts.

**The models start unclean.** Registers and memory hold arbitrary but
reproducible values, because hardware does. Anything relying on a register being
zero without setting it relies on the model being tidier than the machine.

**The audio ports are two sets of latches, not one.** The driver cannot read its
own acknowledgement and the console cannot read what it wrote. A harness that
models them as one location appears to work and measures the wrong thing.

**The counter the console offers first is compared, not echoed.** Hand the driver
a value it did not expect and it takes the other side of a branch two
instructions in and never returns.

## Before calling anything finished

Every gate above, green, in this session. Then: does each new claim in a document
or the record correspond to something a test drives, and has that test been seen
to fail? A change leaves a measurement rather than an assertion: cycles from the
audio unit for speed, a digest for what a stream contains. A corrected answer
stays visible in the record beside what replaced it.

## Assembly is source, is commented line by line, and is fast

**Everything ships as source.** The `.asm` files are the deliverable. Nothing
assembled is checked in: no patched image, no object file, no symbol file, no
table pasted in as a block of numbers. A build produces those into an ignored
directory. A table that can be computed is computed by the assembler at build
time from the expression that describes it.

**Every file is commented line by line, for a reader who does not know
assembly.** This differs from the Python rule on purpose: in assembly there are
no names, only registers, raw addresses and opcodes, and nothing in `lda $2140`
says what `$2140` is. Each file opens with what it does and what a reader needs
to follow it, each block says what it is for, and each line that is not
self-evident says what it does and why. A number that came from a measurement
says which one.

**Performance is an absolute priority.** This code runs in place of a coprocessor
on a 3.58 MHz processor, inside a frame budget the game already spends:

- Count cycles, not instructions, and state the count where it matters.
- Prefer the shortest addressing mode that reaches: direct page over absolute,
  absolute over long.
- Keep the direct page pointed at the working set so the cheap mode is reachable.
- Stay in sixteen bit mode for anything that moves words; `rep`/`sep` pairs
  around a byte operation usually cost more than they save.
- Unroll the inner loop of anything that runs per scanline or per pixel.
- Prefer a table lookup to arithmetic when the table fits, and arithmetic to a
  lookup when the arithmetic is a shift.
- Inline instead of calling from an inner loop; `jsr` plus `rts` is twelve
  cycles that compute nothing.
- Reach ROM through the fast mirror at banks `$80` to `$BF` when the cartridge
  is configured for it, which answers a fetch in six master clocks against
  eight.

A routine that is correct and slow is not finished. Where a faster form was
rejected, the reason is written beside the slower one.
