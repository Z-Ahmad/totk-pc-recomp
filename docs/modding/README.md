# Modding TotK 1.2.1 on this port

Start here, agent or person. This folder is the wiki for making mods of *Tears of the Kingdom* **1.2.1** that run on
this port; `tools/modkit/` is the kit that reads, decodes, edits and writes the game's files. The game version is fixed
at 1.2.1: paths, offsets and the code patch sites below are for that update only.

## Read first

1. The rules below.
2. [loading.md](loading.md): how the port finds a mod and what the resource size table means for you.
3. [romfs.md](romfs.md): where things live in the game's files.
4. [formats.md](formats.md): each file format, and what the kit can and cannot do with it.
5. [recipes.md](recipes.md): step-by-step edits (weapon stats, chest contents, text).
6. [code.md](code.md): code-level modding: `.pchtxt`/IPS patches, cheats, and C hooks in the port's runtime.

## Rules

- **The repository is public. Nothing extracted from or derived from the game is committed**: no game files, no
  decoded YAML of them, no dumps, no survey output, no lists of the game's names or values. Generated files go under
  `build/` (git-ignored). Run `python tools/check_content.py --staged` before every commit; CI runs the same check.
  Docs describe formats and paths; they do not paste game data.
- Copy only MIT, BSD, ISC, zlib or Apache-2.0 code, keep its header and add a row to `THIRD_PARTY_NOTICES.md`. GPL code
  (for example oead, Switch Toolbox, yuzu and its forks) may be read for behaviour only;
  a GPL library may at most be an optional, documented dependency that is never vendored. The kit has none: its
  codecs are written here, and PyYAML (MIT) is its one dependency.
- The game's files are read only. The kit reads `<game>/romfs/romfs.bin` and `<game>/romfs/index.json` (the merged
  1.2.1 RomFS the setup leaves in the install folder) and writes only where `-o` / `--mods` point.
- Never run the game from an agent task unless the user asks; check edits with `show`, `diff` and the tests instead.
- Code, comments, docs and commit messages are in English; commit messages are plain sentences
  ([AGENTS.md](../../AGENTS.md)).

## Set up

The kit needs Python 3.14 (stdlib `compression.zstd`) and, for YAML, PyYAML. From the repository root (when uv is not on PATH,
WinGet puts it at `%LOCALAPPDATA%\Microsoft\WinGet\Links\uv.exe`):

```bash
uv venv --python 3.14 .venv-modkit
```

```bash
uv pip install --python .venv-modkit/Scripts/python.exe -r tools/modkit/requirements.txt
```

`.venv-py314` runs everything except YAML (`--json` output works there). The kit finds the game folder from `--game`,
then `TOTK_GAME`, then a folder named `Game` next to the repository (or next to the main checkout of a worktree).

## Commands

Run from the repository root as `.venv-modkit\Scripts\python -m tools.modkit <command>`; `--help` lists them all.
A SPEC is a RomFS path or a local file, with `::member` for a file inside an archive (repeat for nested archives).

| Command | What it does |
|---|---|
| `info` | game folder, file count, the three zstd dictionaries |
| `search 'Pack/Actor/TBox_*'` | RomFS paths by glob (`*` crosses `/`, case-insensitive), `--regex`, `--sizes` |
| `extract SPEC -o FILE` | the file's bytes, decompressed (`--raw`: as stored) |
| `ls SPEC` / `unpack SPEC -o DIR` / `pack DIR -o FILE` | list, unpack and build SARC archives |
| `show SPEC` / `decode SPEC -o FILE.yml` | BYML or MSBT as YAML (`--json` or a `.json` name: JSON) |
| `encode FILE.yml -o OUT` | YAML or JSON back to BYML or MSBT bytes |
| `install FILE --to SPEC --mod NAME --mods DIR` | write an edit into `DIR/NAME/romfs/<path>`, inside its archive, compressed like the original |
| `diff FILE` | what a mod file changes against the game's: members, BYML values, messages |
| `roundtrip [PATTERN]` | decode and re-encode files and count byte-identical results |
| `survey` | index maps, chests, enemies and GameData flags into `build/modkit/survey/` |

A whole edit, start to end, is in [recipes.md](recipes.md). Tests: `.venv-modkit\Scripts\python tests\modkit_test.py`
(the game tests skip without a game folder).

## What is verified and what is not

Every codec claim in these pages was checked by running the kit on the 1.2.1 RomFS (numbers in
[formats.md](formats.md)). That a given edit has the effect in game named in [recipes.md](recipes.md) was **not**
checked by running the game: the recipes say so where it matters. Open questions are listed at the end of each page.
