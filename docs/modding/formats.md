# File formats and what the kit does with them

Numbers on this page come from running the kit over the 1.2.1 RomFS: `python -m tools.modkit roundtrip` (every BYML
file and every archive, all members included) and the tests in `tests/modkit_test.py`.

| Format | Extensions | Kit | Round trip on 1.2.1 |
|---|---|---|---|
| zstd | `*.zs` | decompress (with the right dictionary), compress with the original's dictionary | decodes every file |
| SARC | `.pack`, `.bkres`, `.ta`, `.sarc`, `.bfarc`, `.blarc`, `.genvb` (all `.zs`) | list, unpack, pack, replace members | 36,714 of 36,714 archives byte-identical, and the archives nested in them |
| BYML | `.byml`, `.bgyml`, `.bcett.byml`, `.rstbl.byml` | decode to YAML/JSON, encode back | 470,733 byte-identical, 196 semantically equal, 0 different |
| MSBT | `.msbt` (inside `Mals/*.sarc.zs`) | decode to YAML/JSON, encode back | 21,140 of 21,140 (14 languages) byte-identical |
| BFEVFL, AINB, BFRES/MCPK, BNTX/TXTG, BFLYT/BFLAN, BWAV/BARS, Phive, ASB, BAEV, RESTBL | | extract and replace whole files only | not decoded |

## zstd and the dictionaries

A `.zs` file is one zstd frame. `Pack/ZsDic.pack.zs` (a SARC compressed without a dictionary) holds three
dictionaries; the frame header names the one it needs by id:

| id | member | files on 1.2.1 (every `.zs` frame header read) |
|---|---|---|
| 1 | `zs.zsdic` | 33,712: `.bkres.zs`, Phive (`.bphsh`, `.bphsc`, `.bphnm`), `.bfevfl.zs`, `.bfres.zs`, `.byml.zs` outside maps (`.esetb`, `.rstbl` and side tables), `.asb.zs`, `.baev.zs`, `.sarc.zs`, ... |
| 2 | `bcett.byml.zsdic` | 137,444: every `*.bcett.byml.zs` (map placements) |
| 3 | `pack.zsdic` | 15,074: every `*.pack.zs` except `Pack/ZsDic.pack.zs` |
| none | | 32,166: `*.bntx.zs`, `*.ta.zs`, `*.vsts.zs`, `*.bars.zs`, the size table, `Pack/ZsDic.pack.zs`, two files under `System/` |

The kit decompresses with the dictionary the frame names (`tools/modkit/romfs.py`, after `tools/make_romfs_patches.py`)
and compresses an edit of a game file with the dictionary that file used, at level 19 (`RomFS.compress_like`). A file
the game does not have gets the dictionary by the rule of the table (`RomFS.dictionary_for_name`), which every `.zs`
file of 1.2.1 but those three follows. Whether the game picks the dictionary from the frame header or from the file
name is not known, so the kit keeps both the same. The compressed
bytes differ from Nintendo's, but the frame names the same dictionary and decompresses to the bytes the kit wrote,
which `compress_like` checks.

## SARC

Little-endian SARC (`tools/modkit/sarc.py` has the layout). Names and data are stored in name-hash order (hash
`h = h * 0x65 + c` over the name's bytes as signed chars). Each member is aligned by its format, inferred from the
padding in every archive of the RomFS and checked by the byte-identical rebuild:

| Alignment | Members |
|---|---|
| 0x2000 | `FRES` (`.bfres`, `.genvres`, `.bofx`) |
| 0x1000 | `BNTX`, `BNSH`, `BAHS` (`.sharcb`) |
| 0x100 | `Gfx2` (`.gsh`) |
| 0x10 | `FLAN` (`.bflan`), `FLYT` (`.bflyt`), `FCPX`, `.bfotf`, `.bfttf`, `.glsl` |
| 8 | everything else (BYML, MSBT, AINB, AAMP, Phive, ...) |
| 4 | `.hght`, `.mate`, `.extm` (members of `TerrainArc/*.ta.zs`), `.skybin`: packed without padding |

The data starts at the largest alignment of the archive's members. An edited or added member is placed by the same
rule, so the archive is laid out the way the game's own are. Big-endian SARC and nameless members are refused (none in
1.2.1).

## BYML

`tools/modkit/byml.py` has the node layout. On 1.2.1: version 7 (a few 5 and 6), little-endian (`YB`) except
`GameData/GameDataList.Product.110.byml.zs`, which is big-endian (`BY`). Node types used: strings, bool, s32, f32, u32,
s64, u64, f64, binary (`RSDB/Tag`), aligned binary, null, arrays, dictionaries, and the v7 hash dictionaries
(`Voice/BwavInfo/*.byml.zs`, two members of `Pack/Bootup.Nin_NX_NVN.pack.zs`).

Text form (`show`, `decode`; `encode` reads it back). The header keeps how the file is stored; leave it as it is:

```yaml
version: 7
big_endian: false
share_containers: false
root:
  Name: a string
  Count: 5                 # s32
  Scale: 1.5               # f32: always with a '.' (1.0, never 1)
  Id: !u 3000000000        # u32
  Hash: !ul 1234567890123  # u64 (!l s64, !f64 f64)
  Pos: [0.0, 1.5, -2.0]    # short arrays of scalars on one line
  Blob: !!binary AAEC      # binary; !abin {align: 8, data: <hex>} for aligned binary
  Table: !h32 {5: 1}       # hash dictionary (!h64: u64 keys)
```

JSON (`--json`) carries the same types as one-key objects: `{"!u": 5}`, `{"!ul": ...}`, `{"!h32": {...}}`, and so on.
A number without a fraction is s32, with one f32; f32 values are written in their shortest exact form.

Writing matches the game's layout (tables sorted by bytes, 64-bit values, then containers in depth-first pre-order;
containers keep the order the file stored them in), which is why nearly every file comes back byte for byte. Two
things are not the game's:

- `share_containers`: some files store each equal container once, others every copy; the decoder records which
  (any shared container seen) and the encoder follows it. In 196 files (195 map `*_Static.bcett.byml.zs`, among them 9
  shrines, and `Game/TravelerInfo/TravelerInfo.byml.zs`) the game shares only some equal containers; the kit shares
  all, so these come back smaller and decode to the same values. The game's reader follows node offsets, so this
  should not matter to it; that was not checked in game.
- NaN payloads are not kept (a NaN reads back as the default NaN). No 1.2.1 file has one where it would show.

## MSBT

`tools/modkit/msbt.py` has the layout. Every 1.2.1 MSBT is UTF-16 with exactly two sections, `LBL1` (labels in
buckets by hash; the bucket count varies per file and is kept) and `TXT2` (the messages). Text form:

```yaml
encoding: utf-16
version: 3
label_buckets: 101
messages:
  Some_Label: Text with a tag {{0.3:ffff}} and a plain one {{1.4}}
```

`{{group.type:hex}}` is an inline tag (U+000E, group, type, parameter bytes), `{{/group.type}}` a closing tag
(U+000F, none in 1.2.1), `\{` and `\\` a literal brace and backslash. Messages keep their order; a new label can go
anywhere, the encoder puts it in its hash bucket. Tags seen in the USen text, most common first: groups 0, 3, 4 (type 0
with 8 to 40 bytes of parameters), 5, 2, 201, 1. What each means in TotK is open: the kit keeps them as numbers.

## Formats the kit does not decode

These can be extracted (`extract`, `unpack`) and a replacement installed whole (`install` takes any file), but the kit
cannot read or edit inside them.

| Format | Where | Notes |
|---|---|---|
| BFEVFL (`BFEV`) | `Event/EventFlow/*.bfevfl.zs` | event flows: dialogue, cutscenes, item get, shrine entry and clear |
| AINB (`AIB `, version 0x407) | `AI/`, `Logic/`, `Sequence/`, inside packs | AI and logic node graphs |
| MCPK | `Model/*.bfres.mc` | mesh-codec container around BFRES models |
| BFRES (`FRES`) | `*.bfres.zs` | animations, some models |
| BNTX, TXTG | `*.bntx.zs`, `TexToGo/*.txtg` | textures; `tools/make_romfs_patches.py` bntx_swap shows the BNTX header |
| BFLYT, BFLAN | inside `UI/LayoutArchive/*.blarc.zs` | layouts and their animations; `make_romfs_patches.py` edits a few fields |
| BWAV, BARS | `Sound/` | audio |
| Phive (`Phiv`) | `Phive/` | collision, navigation meshes |
| ASB, BAEV | `AS/`, `AnimationEvent/` | animation sequences and events |
| RESTBL | `System/Resource/ResourceSizeTable.Product.121.rsizetable.zs` | the port rebuilds it for mods ([loading.md](loading.md)); layout in `tests/mods_romfs_check.py` |

## Open questions

- The rule by which the game's BYML writer shares some equal containers and not others (the 196 files).
- The meaning of the MSBT tag groups in TotK.
- Editing event flows, AINB, models and textures needs codecs the kit does not have; tools for them that a public
  MIT/BSD-licensed project could depend on were not surveyed.
