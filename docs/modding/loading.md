# How the port loads a mod

The player-facing rules are in [docs/mods.md](../mods.md); this page sums up what matters when you make a mod. The code
is `runtime/mods.c` (the scan, order and switches) and `runtime/romfs.c` (serving the files, the resource size table).

## Where the files go

- The mods folder is `mods` next to `totk.exe` (setting `mods_dir` under `[mods]` in `totk.ini`, `TOTK_MODS_DIR`).
  One folder per mod.
- A mod's RomFS root is the first of these that exists inside its folder: `romfs`, `romfslite`,
  `atmosphere/contents/0100F2C0115B6000/romfs`, `contents/0100F2C0115B6000/romfs`, `0100F2C0115B6000/romfs`
  (`runtime/mods.c`, header comment). The same places hold `exefs` and `cheats`.
- A file at `<root>/<RomFS path>` replaces the game's file at that path; a path the game does not have is added. A path
  that matches a game path only when case is ignored is served under the game's spelling.
- The kit writes exactly this layout: `install ... --mods <mods folder> --mod <name>` writes
  `<mods folder>/<name>/romfs/<RomFS path>`.

## Which file wins

- One file comes from one place: there is no merge of two mods' edits to the same file. The higher mod in the Mods tab
  order wins the whole file. Merge with TKMM when two mods must change one file ([docs/mods.md](../mods.md)).
- Any player mod beats the port's own RomFS overlay (`romfs-patches*` next to `totk.exe`, `runtime/romfs.c`
  overlay_contest). That overlay replaces `UI/LayoutArchive/Common.Product.110.Nin_NX_NVN.blarc.zs` (the 60 fps menu
  background fix, and the HUD layout for other aspect ratios), and with Xbox prompts also the `Font/*.bfarc.zs`
  archives, the `Mals/*.sarc.zs` text archives and the resource size table (see `romfs-patches*/manifest.tsv` in the
  install folder). A mod that ships one of these files drops the port's change to it.
- A file whose name carries another update's version (`.Product.<n>.` other than what 1.2.1 has) is left out. Keep the
  original's name: 1.2.1's text archives are `Mals/<lang>.Product.121.sarc.zs`, its UI archive `Common.Product.110`.
- Changes apply at the next start. `logs\totk.log` lists each mod (`mods:` lines) and the size table
  (`RomFS: resource size table:`).

## The resource size table (RESTBL)

`System/Resource/ResourceSizeTable.Product.121.rsizetable.zs` tells the game how much memory to reserve for each file;
a file larger than its entry fails to load. With any mod enabled, the port rebuilds the table at start: it merges the
tables the mods ship and raises the entries of the files the mods made larger or added (`runtime/romfs.c`
restbl_overlay; checked by `tests/mods_romfs_check.py`). So on this port a mod needs no RESTBL file of its own. A mod
for emulators and the Switch does: there, ship an updated table or merge through TKMM. `install` prints a note when the
new file is larger than the original.

## Checking that a mod is served, without playing

`totk.exe --probe-fs` reads files through the game's file functions and compares each overlay file with what it
serves; `tests/mods_romfs_check.py` drives it with a mods folder of its own (`TOTK_MODS_DIR`, `TOTK_MODS_ORDER`,
`TOTK_MODS_DISABLED`). It checks the file plumbing, not what the game does with the file. The kit's own checks are
`show` (decode the installed file) and `diff` (what it changes against the game's).

## Open questions

- Whether the game reads every file through the RomFS on each load or keeps some resident from boot
  (`Pack/Bootup.Nin_NX_NVN.pack.zs`): an edit to a resident file needs a restart in any case; whether it needs more is
  not known.
