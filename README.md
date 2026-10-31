# Street Fighter Alpha 2 without the S-DD1

English | [日本語](README.ja.md) | [简体中文](README.zh-Hans.md) | [繁體中文 (香港)](README.zh-HK.md)

[![ci](https://img.shields.io/github/actions/workflow/status/gufranco/snes-street-fighter-alpha-2-nochip/ci.yml?branch=main&style=flat-square&label=ci)](https://github.com/gufranco/snes-street-fighter-alpha-2-nochip/actions/workflows/ci.yml)
[![release](https://img.shields.io/github/v/release/gufranco/snes-street-fighter-alpha-2-nochip?style=flat-square&label=release)](https://github.com/gufranco/snes-street-fighter-alpha-2-nochip/releases/latest)
[![license](https://img.shields.io/github/license/gufranco/snes-street-fighter-alpha-2-nochip?style=flat-square&label=license)](LICENSE)

Street Fighter Alpha 2 and Street Fighter Zero 2 for the Super Nintendo keep their graphics compressed, and an S-DD1 chip on the cartridge decompresses them while the game runs. Without that chip the game shows nothing.

This project builds an image that does not need the chip. It decompresses every graphics stream ahead of time, lays the result out in a 96 Mbit image and patches the game to read it. You supply the retail cartridge dump; nothing here contains game data.

The built image also loads faster before each fight, unlocks Shin Akuma and carries eleven bug fixes.

## What you need

- git and Docker. Every other tool runs inside this project's Docker image.
- A dump of your own cartridge, 4,194,304 bytes, with no copier header:

| Cartridge | File name in `roms/` | SHA-256 |
|:--|:--|:--|
| Street Fighter Alpha 2, USA | `sfa2-usa-final.sfc` | `910a29f834199c63c22beddc749baba746da9922196a553255deade59f4fc127` |
| Street Fighter Zero 2, Japan | `sfz2-jp-final.sfc` | `f15731675e22dbf3882b777b2d8cd541a637dfdf5d8880c83903cf1e0b64590e` |

## Build

1. Install git and Docker. On macOS, Docker Desktop or `brew install colima docker` followed by `colima start` both work. On Windows, type `.\run.cmd` wherever this page says `./run.sh`.

2. Clone the repository with its submodules. A ZIP download from GitHub does not work, because it leaves out the nine pinned submodules.

   ```bash
   git clone --recurse-submodules https://github.com/gufranco/snes-street-fighter-alpha-2-nochip.git
   cd snes-street-fighter-alpha-2-nochip
   ```

3. Copy your dump into `roms/` under the name in the table above, then check it. The first run builds the Docker image and takes several minutes.

   ```bash
   ./run.sh tools/identify.py
   ```

4. Run the doctor. It checks the checkout, the dumps and the tools, and names the next command to run.

   ```bash
   ./run.sh doctor.py
   ```

5. Build.

   ```bash
   ./run.sh pack.py
   ```

[`pack.py`](pack.py) builds both regions, or only the ones you name, such as `./run.sh pack.py usa`. The files land in `dist/v<version>/`, one folder per device, with a `SHA256SUMS` file.

## Which file to use

Every folder holds the same image. Only the 512 bytes in front of it and the chipset the header declares change, because each device decides how to map the image from those.

| Folder | Use it on | File size |
|:--|:--|:--|
| `emulator` | snes9x and other emulators | 12,582,912 bytes |
| `supereverdrive` | Super EverDrive | 12,582,912 bytes |
| `sd2snes` | SD2SNES and SD2SNES Pro | 12,583,424 bytes |
| `fxpak` | FXPAK Pro | 12,583,424 bytes |
| `gamedoctor` | Game Doctor SF7 | 12,583,424 bytes |

The sd2snes firmware picks its 96 Mbit map only for a header declaring chip `$43` or `$45` and a file of exactly 12,583,424 bytes, so the `sd2snes` and `fxpak` files declare chip `$43` even though the image has none. The `gamedoctor` file carries the 512 byte header that maps all 24 chunks of 4 Mbit.

## What changes in the game

**Shorter pause before each fight.** The pause comes from the sound driver, which sends samples to the audio chip one byte at a time. The patched driver sends three bytes per handshake and skips sample lists that are already loaded.

| | Retail | This build |
|:--|:--|:--|
| Longest pre-fight pause, USA | 2.90 s | 0.80 s |
| Longest pre-fight pause, Japan | 2.60 s | 0.72 s |

**Shin Akuma unlocked.** He has been in the cartridge since 1996, behind a cheat nobody documented until 2021.

**Eleven corrections** to the game's own code:

| Fix | Regions |
|:--|:--|
| Sodom's name restored on the life bar, select, versus and results screens | USA |
| Akuma's win poses in arcade order | Both |
| The live-object count no longer exceeds the object table when a ninth shadow frame is requested | Both |
| Three sprite records corrected where Sagat holds Dan's father | Both |
| 45 calls to an empty routine rewritten to return directly | Both |

The chip-free image also stores the 24,704 byte table the game used to spend 27 frames building before every fight.

## Tested hardware

| Device | Image | Result |
|:--|:--|:--|
| Game Doctor SF7, 128 Mbit DRAM | USA and Japan, `gamedoctor` file | Reaches a fight |
| SD2SNES and SD2SNES Pro, firmware 1.11.2 | USA and Japan, `sd2snes` file | Reaches a fight |
| SD2SNES Mk.II clone, firmware 1.11.2 | USA, `sd2snes` file | Whole game |
| FXPAK Pro | USA, chip-free image | Runs |
| Super EverDrive | USA, chip-free image | Title screen, from a [photograph](https://x.com/yoshinokentarou/status/2111959864163664247/photo/1) by @yoshinokentarou |

The SD2SNES, SD2SNES Pro and Game Doctor runs are herrkuhn's, from [issue 31](https://github.com/gufranco/snes-street-fighter-alpha-2-nochip/issues/31) and [issue 37](https://github.com/gufranco/snes-street-fighter-alpha-2-nochip/issues/37). The Mk.II clone run and the photographs below are Hamilton Pimentel's, from issue 31.

<p align="center">
  <img src="photos/sd2snes-mk2/01-sd2snes-in-a-super-famicom.jpg" width="250" alt="An SD2SNES cartridge in a Super Famicom, powered on">
  <img src="photos/sd2snes-mk2/02-title-animation.jpg" width="250" alt="The Street Fighter Alpha 2 title animation on a CRT television">
  <img src="photos/sd2snes-mk2/03-title-screen.jpg" width="250" alt="The title screen with Capcom U.S.A.'s copyright line">
  <img src="photos/sd2snes-mk2/04-player-select.jpg" width="250" alt="The player select screen with Ryu chosen">
  <img src="photos/sd2snes-mk2/05-ryu-against-ken.jpg" width="250" alt="Ryu and Ken facing each other at the start of a fight">
  <img src="photos/sd2snes-mk2/06-akuma-next-opponent.jpg" width="250" alt="The arcade map with Akuma and Guy named as the next opponent">
  <img src="photos/sd2snes-mk2/07-akuma-wins.jpg" width="250" alt="Akuma's win screen with the quote Now stay down">
  <img src="photos/sd2snes-mk2/08-ending-credits.jpg" width="250" alt="The ending credits, object design and sound supervisor">
  <img src="photos/sd2snes-mk2/09-thank-you-for-playing.jpg" width="250" alt="The closing screen, thank you for playing, presented by Capcom">
</p>

On emulators, snes9x loads the image since [pull request 1082](https://github.com/snes9xgit/snes9x/pull/1082) added the map it uses. ares, Mesen2, bsnes and Mednafen have not been tried.

## Reporting a problem

Open an [issue](https://github.com/gufranco/snes-street-fighter-alpha-2-nochip/issues) with the output of `./run.sh doctor.py`. For a wrong screen, say which file and region you used and attach a photo or capture of it. Never attach a ROM or anything decoded from one.

## How it is built and checked

Every stream is decompressed with a Python model of the chip and compared byte for byte with snes9x's `sdd1emu.cpp`: 2,817 USA and 2,855 Japanese streams, none different. Each finished image runs for 12,000 frames on an emulator harness, and every sample upload is compared with its source. The build steps, the image layout, every command and the Python interface are in [REFERENCE.md](REFERENCE.md). [CONTRIBUTING.md](CONTRIBUTING.md) covers the test gates.

## Credits and references

- Andreas Naive reverse engineered the S-DD1 compression algorithm.
- DarkAkuma's SNES Classic patch tags every stream in the USA ROM, which gave the USA stream table.
- neviksti's chip-free Star Ocean conversion was the reference for the decompressor and the memory map.
- The bsnes disassembler tables are the source of both disassemblers used here.
- Modern Vintage Gamer, [A closer look at Street Fighter Alpha 2 on the Super Nintendo](https://www.youtube.com/watch?v=fB9GlZUYNUQ), on where the pause comes from.
- [Street Fighter Alpha 2 thread on Zeldix](https://www.zeldix.net/t1831-street-fighter-alpha-2), with gizaha's patches and changelog.
- Nintendo Life, [After 25 Years, A New Cheat Code Has Been Discovered For Street Fighter Alpha 2 On The SNES](https://www.nintendolife.com/news/2021/01/after_25_years_a_new_cheat_code_has_been_discovered_for_street_fighter_alpha_2_on_the_snes).
- Retroware, [The Curious Case of Street Fighter Alpha 2 on the SNES](https://articles.retroware.com/2021/03/08/the-curious-case-of-street-fighter-alpha-2-on-the-snes/).
- [snes9x](https://github.com/snes9xgit/snes9x) 1.63, [issue 1081](https://github.com/snes9xgit/snes9x/issues/1081) and [pull request 1082](https://github.com/snes9xgit/snes9x/pull/1082).

To cite this project, use [CITATION.cff](CITATION.cff).

## License

MIT, see [LICENSE](LICENSE). It covers the tooling, the assembly and the documentation, and grants no rights in the game.
