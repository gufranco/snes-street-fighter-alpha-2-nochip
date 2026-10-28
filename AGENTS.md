# Working in this repository

Read [`FAMILY.md`](FAMILY.md) first. It is the standard every member is built to
and it is identical in all twenty of them. This file is the part that is only
true here.

## What this project is, in one paragraph

Street Fighter Alpha 2 shipped with a decompression chip on the cartridge, and
without that chip the game does not run. This produces an image that does not
need it: every stream the S-DD1 would have expanded at runtime is expanded ahead
of time, and what is left is refitted into a windowed map that a plain 96 Mbit
cartridge can hold. Around that sit corrections to the game's own code and a
faster sample upload, both of which change instructions that run on real
hardware.

## The nine models, and why there are nine

Every claim about what a part does is made by a member on the import path, never
here. [`hardware.py`](hardware.py) is the only way any of them is reached, and it
is where a missing checkout is explained rather than left as an import error.

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

Nine is not thoroughness for its own sake. A patch to code that runs on hardware
is checked against a model held to its own suite, rather than against this
project's expectations. When two models can answer the same question, ask both:
the sample upload runs on a stand-in written from a reading of the driver and on
the whole audio unit, and the two agreeing is the check that neither provides
alone.

## The authority ladder applies, and rung four is the one to watch

The ladder is in [`FAMILY.md`](FAMILY.md). What is specific here is how much
material sits on the bottom rung. This game has been patched by many people, and
those patches come with changelogs, assembly and claims.

**A third party patch is never evidence.** Not about hardware, and not about
itself. One widely circulated package ships assembly describing a two byte
upload and a binary whose driver reads three ports per handshake; they are
eighteen months apart and describe different drivers. Anything taken from such a
package is re-derived here and measured, or it is not taken.

## What is settled and what is not

[`OPEN-QUESTIONS.md`](OPEN-QUESTIONS.md) is the list, and
[`conformance/divergences.json`](conformance/divergences.json) is the same list
in a form a program reads. The two must agree. The short version: the Japanese
stream table is converged rather than proved complete, two corrections are read
from the disassembly rather than seen on screen, and the FXPAK Pro run of the
chip-free `.sfc` is not explained by the firmware source. The guarded sample
upload and the sd2snes form are closed: both ran the whole game on an SD2SNES
Mk.II clone. The sd2snes form is written only with `--sd2snes` or `--fxpak`,
because the default image declares no chip, which is the truth.

## The order matters

Streams are found, decompressed, verified, and only then packed. A stream that
fails to decompress is a missing entry in a table, not a broken decompressor, and
the tools say which. Packing before verifying produces an image that boots and is
wrong somewhere nobody looked.

## The table is the design and the fallback is what keeps it honest

The family standard carries this rule; what follows is what it means here.

The table holds what the game asks for, never what the part accepts. Sizing
against the part's input domain concludes that nothing can be stored, because the
domain is the exponent of the argument count. Sizing against the game concludes
that almost all of it can. Any figure here says which of the two it measured.

What the game asks for is a property of the whole game. A recording is a floor,
and a recording of the attract demo with the controls untouched is the lowest
floor there is. A figure taken from one states the frames it covers and what the
run was doing.

Two questions come apart and are answered separately. Which calculations the game
can ask for is answered by reading the whole image, and that closes. Which values
it asks for them with is answered by running the game, and that does not: the
values are computed from state the image does not hold.

Every command has a fallback in 65816, and it is never optional. A lookup with no
row has no answer, so a replacement that meets one either hangs or reads whatever
was in memory. The intent is that the fallback never runs; the requirement is that
it always could. A slower answer beats a stopped machine.

A fallback nobody measured is a fallback nobody has. Its cost is stated in cycles
and a build reports how often it fired, rather than asserting it did not.

## The input is a retail cartridge, and it is not here

Neither image is in this repository and neither is any output. Everything
published is a digest, and [`artifacts.manifest.json`](artifacts.manifest.json)
carries four per artifact so a reader can confirm what they have without being
handed any of it. `sha256` is what decides; the other three are for
cross-referencing against public databases.

Nothing in `roms/`, `boot/`, or any `*.sfc`, `*.smc` or `*.bin` may be committed,
in any form, for any reason. [`.gitignore`](.gitignore) enforces the common
cases and is not the reason: the reason is that this project does not
redistribute what it did not write.

## Every gate, in the order to run them

```sh
uvx ruff@0.16.3 check .
uvx ruff@0.16.3 format --check .
uvx --python 3.12 mypy==1.14.1
pnpm run format:check
uvx yamllint==1.38.0 --strict .
uvx --python 3.12 --from coverage==7.6.10 coverage erase
for module in *.test.py tools/*.test.py conformance/*.test.py; do uvx --python 3.12 --from coverage==7.6.10 coverage run -a "$module" || break; done
uvx --python 3.12 --from coverage==7.6.10 coverage report
```

Every tool is pinned because a local install of a different version disagrees,
and a report from a version nobody ships is worse than no report. The suite
takes several minutes and 1,280 tests; a run that finishes faster than that did
not run all of it.

A test that needs a retail dump goes in `<module>.retail.test.py` beside the
module, reports as skipped where the dump is absent, and is left out of the
coverage measurement. Every other line is covered by a test that needs nothing
the repository does not carry, so the 100% gate holds on a machine with no dump,
which is what CI is.

`pnpm`, never `npm`. The JSON and YAML formatter is a separate gate from ruff and
CI runs both, so a run that passes ruff alone has not passed lint.

## Conventions that are not negotiable

- Python only. No comments in source, and a docstring counts as one.
- Tests are `<module>.test.py`. Arrange, act and assert,
  each block opened by its bare marker, and nothing else inside a test body.
- A check nobody has seen fail is not known to work. Drive every new check
  against input that should fail it before keeping it.
- A digest edited to make a check pass is the failure this whole standard exists
  to prevent.
- Conventional Commits, subject under 50 characters.

The configuration files carry no comments, so the reasons for their ignores and
exclusions live here:

- `BLE001` in [`doctor.py`](doctor.py): the doctor exists so nothing fails
  silently. It reports whatever a check throws, and a narrower catch would let an
  unforeseen failure end the report as a traceback.
- `BLE001` and `T201` in [`environment.py`](environment.py): a check that throws
  has to become a line in the report rather than end the run, and the printed
  report is the product.
- The submodule paths in the coverage `omit`, the mypy `exclude` and
  [`.prettierignore`](.prettierignore): each model is measured and checked in
  its own repository against its own gate, so a figure taken from here would
  mean nothing, and a file a member ignores fails here if it is not ignored. `build/` holds generated and third
  party sources this project does not own.
- The `if __name__ == "__main__":` coverage exclusion: the guard hands argv to a
  function that is tested directly, and importing the module to cover it would
  run the tool rather than test it.
- The `def build(region` coverage exclusion: it composes the whole build over a
  retail dump, and a synthetic stand-in would satisfy each step by construction.
  It is measured by running it in
  [`pack.retail.test.py`](pack.retail.test.py), which skips where the dump is
  absent.
- The `def variants(` coverage exclusion: deriving the three cartridge variants
  needs the retail dump, and each patch it composes carries its own proof in
  [`spcfast.test.py`](spcfast.test.py) and
  [`shinakuma.test.py`](shinakuma.test.py). The loop that consumes the variants
  is measured.
- The `frame_hook_site` coverage exclusions: [`spcfast.py`](spcfast.py) is
  generated by [`tools/freeze_spcfast.py`](tools/freeze_spcfast.py), and its
  frame hook is parked with an empty pattern, so neither the finder nor the run
  that would place it can execute. The tests pin that dormancy through
  `FRAME_HOOK` and `runs_for`.
- The optional mypy error classes: this project rewrites cartridge code, so the
  errors worth catching are a length, an offset or a None crossing a boundary.

## Things that will bite you

**A docstring claiming a measurement is not a measurement.** One here said the
audio unit's boot window had to be hidden or the driver ran away. Running it both
ways showed the window changes nothing. Read what the test actually exercises
before believing what the prose asserts.

**The models start unclean.** Registers and memory hold arbitrary but
reproducible values, because hardware does. Anything relying on a register being
zero without setting it was relying on the model being tidier than the machine.

**The audio ports are two sets of latches, not one.** The driver cannot read its
own acknowledgement and the console cannot read what it wrote. A harness that
models them as one location will appear to work and will measure the wrong thing.

**The counter the console offers first is compared, not echoed.** Hand the driver
a value it did not expect and it takes the other side of a branch two
instructions in and never returns.

## Before calling anything finished

Every gate above, green, in this session. Then: does any new claim in the record or the readme
correspond to something a test actually drives, and has that test been seen to
fail? If a question was closed, is it closed in both
[`OPEN-QUESTIONS.md`](OPEN-QUESTIONS.md) and
[`conformance/divergences.json`](conformance/divergences.json)?

## What a change is expected to leave behind

A measurement rather than an assertion. If the change is about speed, cycles from
the audio unit rather than instruction counts. If it is about what a stream
contains, a digest. If it closed a question, the question moved rather than
disappeared, and if it corrected an earlier wrong answer, the earlier answer is
still visible with what replaced it.

## Bound the domain before building a table, never after

A table keyed on values taken from a recording covers the recording and nothing
else. That is not a small caveat, it is the whole behaviour of the thing: a
recorded-set table answers the run it was built from perfectly and answers a run
it has not seen almost never. Measure it and the gap is not subtle. Splitting one
recording in half and asking the second half what the first half learned, this
project's table answered 7.2% of calls. Asking it a different recording of the
same demo it answered 91.4%, and that number is worse than useless without the
first one beside it: the recordings are the same attract sequence, so the 91.4%
measures repetition and not coverage.

So the domain comes first, and it comes from the code.

**Do this in order, per calculation, before a single row is written.**

1. **Read the part's own program for what bounds each input.** A table lookup
   with a fixed size bounds its index. A mask bounds a word. A shift bounds a
   magnitude. A clamp bounds both ends. These are true bounds, independent of
   any recording, and they are the only kind that is.

2. **Read the calling code for what it can compose.** An argument built from a
   fixed table, a constant, or a quantised angle has a domain the caller decides
   and the image holds. This closes for the same reason the command census
   closes: it is a property of the image, not of a run.

3. **Size an exhaustive table over that domain.** Both the span of each word and
   the set of distinct values it can take, because they give very different
   answers when an input is quantised. This project has an argument whose span is
   32,769 and whose value set is seven, and the two sizings differ by four orders
   of magnitude.

4. **Choose per calculation, and record which case it is.**

   | case | what to build |
   |---|---|
   | the exhaustive table fits | build it. No miss is possible, and the fallback behind it becomes unreachable rather than merely unlikely |
   | it does not fit, but the arithmetic is readable | read the arithmetic. A routine covers the whole domain and costs no space |
   | neither | a recorded-set table, and say plainly that it covers the recording and what the holdout rate is |

5. **Publish the holdout for every calculation in the third case.** Build the
   table from part of the recordings and ask it the rest. A coverage figure with
   no holdout beside it is a claim about the data it was built from.

**A recorded-set table is the last resort, never the first move.** Reaching for
one before steps 1 to 3 have been done produces a table that looks finished,
measures well against its own inputs, and fails on a player. The failure is
silent, because a fallback answers and nothing reports that it did.

**Weight the effort by traffic, not by command count.** Three commands here are
77% of all calls. Making a rare command exhaustive while a heavy one is guessing
from its nearest neighbour is work in the wrong place.

**A miss is not the same as a wrong answer, and both get measured.** When a
fallback takes the nearest row, how near it is varies by orders of magnitude
between calculations: measured on real misses here, one command's nearest row is
never more than 26 out and another's is 23,154 out. The first is a near miss and
the second is noise. Which is which decides whether a recorded-set table is
tolerable for that calculation at all.

## Assembly is source, is commented line by line, and is fast

Three rules bind every `.asm` file in this repository, and a file that breaks any
of them is incomplete rather than merely untidy.

**Everything ships as source.** The `.asm` files are the deliverable. Nothing
assembled is checked in: no patched image, no object file, no symbol file, no
table pasted in as a block of numbers. A build produces those into an ignored
directory and a clone reproduces them from source. Where a table can be computed,
it is computed by the assembler at build time from the same expression that
describes it, because a table worked out where it is used cannot drift away from
the code that uses it and a table pasted in as numbers can.

**Every file is commented line by line, for a reader who does not know
assembly.** This is not the comment policy that governs the rest of the
repository, and the difference is deliberate. In a high level language a name
carries the meaning, so a comment restating it is noise that goes stale. In
assembly there are no names: there are registers, raw addresses and opcodes, and
nothing in `lda $2140` says what `$2140` is or why it is being read. So each file
opens with what it does and what a reader needs to know to follow it, each block
says what it is for, and each line that is not self-evident carries a short note
of what it does and why. A number that came from a measurement says which one.

**Performance is an absolute priority.** This code runs in place of a coprocessor
on a 3.58 MHz processor, inside a frame budget the game already spends. Every
routine is written for speed first:

- Count cycles, not instructions, and state the count where it matters.
- Prefer the shortest addressing mode that reaches: direct page over absolute,
  absolute over long. Direct page is one byte and one cycle cheaper per access.
- Keep the direct page pointed at the working set so the cheap mode is reachable.
- Stay in sixteen bit mode for anything that moves words; `rep`/`sep` pairs
  around a byte operation usually cost more than they save.
- Unroll the inner loop of anything that runs per scanline or per pixel. The
  branch and the counter are pure overhead there.
- Prefer a table lookup to arithmetic when the table fits, and arithmetic to a
  lookup when the arithmetic is a shift.
- Do not call a subroutine from an inner loop when it can be inlined; `jsr` plus
  `rts` is twelve cycles that compute nothing.
- Reach ROM through the fast mirror at banks `$80`-`$BF` when the cartridge is
  configured for it, which answers a fetch in six master clocks against eight.

A routine that is correct and slow is not finished. Where a faster form was
rejected, the reason is written down beside the slower one, because the next
reader will otherwise assume nobody thought of it.
