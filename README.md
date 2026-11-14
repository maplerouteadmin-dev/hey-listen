# Hey, Listen!

An AI-voiced dialogue mod for the Ocarina of Time Switch remake. Every unvoiced line of dialogue gets a
consistent, character-fitting voice, generated locally with [Qwen3-TTS](https://github.com/QwenLM/Qwen3-TTS) —
no cloning or imitation of the official English voice cast.

Lines the game already voices (cutscenes, some boss dialogue) keep their official audio untouched; this mod
only fills in what was silent before.

## Install

Run `Install Voices (Download).bat`. It finds whichever of Hookshot, Longshot, or an emulator
(Fritchii/eden) you have installed, and installs into all of them. The main story cast downloads by
default; it'll ask before downloading anything bigger.

| Tier | Covers | Download size |
|---|---|---|
| Main | Story-critical NPCs (Navi, Zelda, Ganondorf, Sheik, Saria, Darunia, Ruto, Rauru, Impa, Nabooru, Kaepora, the Deku Tree, and the rest of the cast who already have some official voice acting) | ~90 MB |
| Named | Everything in Main, plus every other named NPC with a personality (shopkeepers, townsfolk, Dampé, Skull Kid, etc.) | ~320 MB |
| Full | Everything, including generic repeated background/crowd NPC lines | ~460 MB |

To remove it, run `Remove Voice Mod.bat` (or the per-target one for Hookshot/Longshot).

## Tested with

Most of the actual day-to-day testing has been on **Longshot** — that's the one this has seen the most
play-time on. The others are confirmed working, just with less mileage so far.

| | Status |
|---|---|
| **Longshot** (native PC recompilation) | ✅ Confirmed working, most tested |
| **Hookshot** (native PC recompilation) | ✅ Confirmed working |
| **Fritchii** (emulator) | ✅ Confirmed working |
| **eden** (emulator, Fritchii's predecessor) | ⚠️ Same install format as Fritchii, not independently re-tested recently |
| Any other emulator (Ryujinx, suyu, sudachi, citron, etc.) | ❌ Not tested |
| Any other OoT recompilation project | ❌ Not tested |

If you get it working somewhere not listed here, open an issue — a PR adding to this table is welcome.

## Building it yourself

You need your own legally-obtained copy of the game (a `.nup` dump). Nothing in this repo contains any
of Nintendo's game files or official voice audio.

1. `Generate Whole Game.bat` — generates every clip with Qwen3-TTS (needs a CUDA GPU; several hours).
2. `Build Voice Mod.bat` — packages the generated clips into a mod folder.
3. `tools/install_voice_mod.ps1 -Stage <mod folder>` — installs it.

## How it avoids redistributing Nintendo's audio

The mod never copies the game's own voice performance audio. For dialogue that mixes official and
synthesized lines in the same internal bank file, only small timing/duration metadata gets re-embedded
(no audio samples) — the official voice clips themselves are always read from your own game files, never
from this repo or its releases.
