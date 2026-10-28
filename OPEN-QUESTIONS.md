# Open questions

What this project does not know for certain, and what it would take to find out.

This member makes fewer claims about hardware than its size suggests. It
decompresses streams ahead of time, refits what is left into a map with no
coprocessor in it, and patches code. Every statement about what a part actually
does is made by one of the nine members on its import path, each held to its own
suite. So most of what could go wrong here is not a question about silicon. It is
a question about coverage: whether the streams found are all the streams, and
whether a correction that reads right has ever been seen to matter.

Every entry below is also in
[`conformance/divergences.json`](conformance/divergences.json) with its status
and severity, so a program can read what a person reads here.

## The FXPAK Pro run of the `.sfc` is not explained

The FXPAK Pro runs the same sd2snes firmware as the SD2SNES. That firmware picks
its 96 Mbit map only for map byte `$22` or `$32` with chip `$43` or `$45`, and
release v1.11.2 also needs the file to be exactly `0xC00200` bytes. The `.sfc`
declares chip `$00`, so by the firmware source it falls back to plain LoROM and
reads the graphics banks from the wrong offsets.

The hardware table records the `.sfc` running on an FXPAK Pro, and that run was
recorded before any of this was known. On an SD2SNES Mk.II clone running
firmware 1.11.2, the `.sfc` built with all six header copies rewritten goes
black at power on, which is what the source predicts. Either the FXPAK Pro run
used a firmware that maps the file differently, or the recorded run was not the
image it is listed as.

**What would settle it:** the `.sfc` and the `.smc` from the same build run on
the FXPAK Pro, with the firmware version noted.

## The Japanese stream table cannot be proved complete

A stream nobody asks for cannot be found by asking. The table was built by
driving the Japanese cartridge and recording all 1,661 requests it made, and the
search converged, meaning further driving stopped finding anything new. That is
the strongest statement available and it is not a proof.

The USA table does not have this problem. It came out of an image that tags where
each stream begins, so it was read rather than discovered, and the two methods
agreeing on the streams they share is what makes the Japanese one credible.

If a screen ever comes up wrong, the fix is mechanical rather than exploratory:
drive the retail cartridge to that screen, read what it asks the chip for, add
it. Nothing about the approach has to change.

**What would settle it:** a tagged Japanese image, or a run that reaches every
screen in the game.

## Two corrections are not demonstrated on screen

The object table overflow needs eight simultaneous shadow frames and a projectile
collision in the same instant. The thrown father sprite sits in a scene no run
here reaches. Both corrections rest on reading the disassembly.

What the runs do show is that neither changes anything that is reached, which
bounds the risk without demonstrating the benefit. That is a weaker claim than
the rest of this project makes, and it is written down rather than rounded up.

**What would settle it:** a recorded input sequence that reaches either scene,
run before and after.

## What the prototype settled, and what it did not

Capcom shipped a prototype of the Japanese cartridge dated 1996-09-15. It
declares no coprocessor and stores uncompressed a large amount of what the retail
cartridge compresses.

Decompressing every stream in the Japanese table and searching that prototype
finds **242 matching in full, 311,264 bytes**, with no partial match counted.
Those bytes are Capcom's own data from before the compression step, so for those
entries the table is not merely converged, it is confirmed against the source.

That is a correctness result and not a completeness one, and the two are kept
apart deliberately. A stream missing from the table is still missing from it, and
the prototype cannot reveal one, because it is a different build: 2,138 of the
table's streams are absent from it and 472 share only a first sixty four bytes.
The section above stands unchanged.

## What is closed, and why it is worth saying

**The guarded sample upload runs on a cartridge.** Release 1.5.4 decided whether
a new block had begun on a single read of the counter port. The two sides of an
audio port are not clocked together, so a read that lands during the other
side's write can return a mixture of old and new bits, and no emulator models
that. Issue #31 reported a black screen right after the Capcom logo on an
SD2SNES Mk.II clone, an original SD2SNES and an SD2SNES Pro, and a Game Doctor
SF7 that ran only without the fast upload. On the SPC700 model, one read that
looks ahead left the 1.5.4 loops spinning forever.

The receive loops now read the counter a second time before believing a new
block has begun, as the audio unit's boot program does at `$FFE9` to `$FFED`.
The deciding run used the 4 MB retail ROM with nothing but the upload patch on
the SD2SNES Mk.II clone, firmware 1.11.2. Built from 1.5.4 it went black after
the logo. Built with the second read, at SHA-256
`38b519adcebc6702ead736b6fd35aa82a93736489b1ee41ec4db24f76c07e141`, it was played
through the whole game with Ken, Ryu and Akuma, with normal sound and no
unusual pause. That image touches neither the map nor the header, so the second
read is what fixed the black screen.

**The sd2snes form runs on a cartridge.** The `.smc` sets chip `$43` in all six
header copies and adds a 512 byte copier header, which is what firmware v1.11.2
needs before it picks the map that places every address where this project's map
does. On the same SD2SNES Mk.II clone, the USA `.smc` built with the guarded
upload was played through the whole game. That form is now written only when
[`pack.py`](pack.py) is given `--sd2snes` or `--fxpak`, because the game has no
chip and the default image says so.

Both runs are by Hamilton Pimentel, reported in issue #31 on 2026-10-27, with
photographs in [`photos/sd2snes-mk2/`](photos/sd2snes-mk2). The other two
cartridges in that issue, the original SD2SNES and the SD2SNES Pro, have not run
the new build.

**The boot window does not reach the upload driver.** An earlier reading here
said the audio driver ran away when the unit's boot program was left covering the
top of memory. Running it both ways reaches the same bytes in the same cycles,
because this driver never reads what the window covers. The window is still
switched off, because that is the state a console leaves it in, and a test keeps
the measurement so that a patch which does reach up there shows a difference
instead of hiding one.

It is listed because the wrong version of it was written down first, and a
correction that leaves no trace teaches nobody.

## Boundaries, so nobody mistakes them for gaps

**Nothing here models hardware.** The nine members do. The one thing this
measures directly is how many cycles a patched driver spends, and it measures
that by running the driver on the audio unit rather than by counting from a
table. That distinction is the reason the unit is on the import path at all.

**A published patch is not evidence, including about itself.** A widely
circulated third party package ships assembly dated 2021-03-08 that describes a
two byte upload, and a binary dated 2022-10-21 whose audio driver reads three
ports per handshake and self modifies its destinations. The two describe
different drivers, and the changelog entry naming two bytes predates both.
Nothing here is derived from either. The mismatch is recorded so that no later
reader treats the published assembly as a description of the shipped binary.

The same gap closes off its later work entirely. That package advertises fixes
for a double KO hang, a freeze when facing Zangief and a black screen crash,
dated 2021-06-14, 2021-06-21 and 2022-10-13, all after its published assembly and
none present in it. Subtracting every address that assembly touches from the
binary diff leaves 641 unexplained runs and 39,643 bytes, unlabelled, and the
same diff adds 64 long calls into bank `$C7` and 39 into bank `$D2`, whose
mapping depends on the very S-DD1 window this project removes. The three fixes
are therefore neither identifiable nor addressable here, and no run here reaches
a double KO to demonstrate one if they were. They are wanted and they are out of
reach, which is a different thing from being ignored.

**Neither cartridge is here, and neither is any output.** Everything published is
a digest. That is a rule rather than a limitation, and it is the reason the
manifest identifies inputs by four digests each: a reader can confirm they have
the right file without being handed any part of it.
