# Code-level modding on this port

The game's code is compiled ahead of time from the 1.2.1 `main` into C (`recomp/`) and linked into `totk.exe`. Nothing
can write new instructions into it while it runs, so every change to the game's behaviour in code is made **when the C
is generated**, or by host C code in `runtime/` that the game calls. Three ways, from the least to the most work:

| Way | Write | Built by | Good for |
|---|---|---|---|
| ExeFS patch (`.pchtxt`, `.ips`) | patch file in a mod | the setup's rebuild, at the next start | changing a few instructions, as Switch mods do |
| Cheat (`cheats/<id>.txt`) | Atmosphère cheat file in a mod | code cheats: the rebuild; data cheats: none | memory writes, button-held toggles |
| Runtime C hook | C in `runtime/`, `site` lines in `recomp/patches-v121.txt` | a source build ([docs/building.md](../building.md)) | new logic: a run director, custom rules, reading and writing game state |

## ExeFS patches

The player side is in [docs/mods.md](../mods.md) (Code patches); `tools/exefs_patches.py` has the rules.

- Put `.pchtxt` or `.ips` files in `<mod>/exefs/` (or `atmosphere/exefs_patches/<name>/`).
- A file is for 1.2.1 when it names 1.2.1 `main`'s build id: an `.ips` file in its name, a `.pchtxt` file on its
  `@nsobid-<hex>` line (trailing zeros may be left out). The build id starts `9B4E43650501A4D4` (the cheat file name of
  [docs/cheats.md](../cheats.md)); the whole id is the 32 bytes at 0x40 of the ExeFS `main`:

  ```
  python -c "print(open(r'<game>\exefs\main','rb').read(0x60)[0x40:].hex().upper())"
  ```

- Offsets are the ones emulators use: an `.ips` offset counts the 0x100-byte NSO header; a `.pchtxt` offset adds its
  `@flag offset_shift` first. Patch lines apply between `@enabled` and `@disabled`; `@stop` ends the file.
- What can be built: an instruction replaced in place, and a branch into a code cave the file writes into `main`'s
  zero padding (the cave is inlined at the branch). What cannot: writes into `main`'s data, and writes the site rules
  of `recomp/patches.py` cannot express (a branch or `ret` that is not the last word, a site at `br`/`blr`/`ret`, ...).
  Such a file is left out whole and the Mods tab says why.
- Each usable file becomes one patch set, switched on and off with its mod without another rebuild. A file that patches
  a site of one of the port's own sets (60 fps, resolution, ...) switches that set off while the mod is on.

## Cheats

[docs/cheats.md](../cheats.md) covers them: the file for 1.2.1 is `cheats/9B4E43650501A4D4.txt`; code cheats (opcode 0
into `main`) are built in like ExeFS patches; data cheats (heap, pointer chains, button conditions) run in the port's
cheat VM every frame (`runtime/cheats.c`). A data cheat is the quickest way to try a memory write found with a
debugger, before turning it into code.

## Runtime C hooks

This is where the roguelike's run director belongs: C in `runtime/` that runs when the game reaches chosen points.

### The pieces

- **Patch sets and sites** (`recomp/patches.py`, `recomp/patches-v121.txt`). `set <name> <env> <default>` declares a
  switch (an environment variable or `totk.ini` key through `cfg.c`); `site <set> main <offset> <original word>
  <replacement words>` replaces one instruction of `main` (offset from the module base, the original word checked when
  the C is generated). The generated C reads `if (rt_patch_on[<set>]) { replacement } else { original }`. Replacement
  words may use `@page:x<n>` (`adrp` to the patch page, a 4 KiB page after `main` that the runtime owns) and may end
  in a `bl`, `b`, conditional branch or `ret`.
- **Function hooks** (`hook <set> main <offset> <c_function>` in `recomp/patches-v121.txt`; `recomp/patches.py`,
  header). The way to hook one of the game's own functions: the generator emits its body as `f_<addr>_orig` and makes
  `f_<addr>`, which every direct call, tail branch and the dispatch table use, call
  `void <c_function>(Cpu *c, void (*orig)(Cpu *c))` while the set is on. The hook sees the arguments in `c->x[0..7]`,
  runs the original with `orig(c)` before, after or not at all, and leaves the result in `c->x[0]`. Hook code goes in
  `runtime/hooks/<feature>.c` (compiled automatically). Example: `runtime/hooks/probe.c`, set `hook_probe`
  (`TOTK_HOOK_PROBE=1`), which logs a function that runs once per frame. The offset must be a function start (the
  generator checks).
- **Host functions at a guest address** (`runtime/dispatch.h` rt_register_host), the older per-call-site way. A host C function registered at an
  address on the patch page is what a guest `bl` to that address runs. The working example is the `zstd` set of
  `recomp/patches-v143.txt` with `runtime/ov_zstd.c`: each call site of the game's zstd decoder becomes
  `bl page+0xff0` / `bl page+0xfe0`, and `zstd_register` (a constructor) registers the two host functions there. A
  hook of a game function is that pattern: a `site` per call site (or at the function's first instruction, branching
  to the page), and a host function with the guest's arguments in `Cpu` (`c->x[0]` ...) that does its work and may
  call the original (`rt_call`); the result goes back in `c->x[0]` (`host_multiframe` in `ov_zstd.c`).
- **Symbol overrides and observers** (`runtime/host.h` HOST_OVERRIDE, HOST_OBSERVER, rt_original). For functions
  `main` imports by symbol from the SDK (`nn::os::...`, `nn::fs::...`): an override replaces the function, an observer
  runs around it and calls `rt_original(c)`. Examples: `runtime/ov_system.c` (system overrides and the memory observers),
  `runtime/fs_host.c` (the `nn::fs` overrides). The game's own functions in `main` are not imported, so they need sites.
- **Calling the game** (`rt_call(c, fn, n, ...)`, `runtime/host.h`): host code calls a guest function with up to 8
  arguments.
- **The patch page** (`recomp/patches.py`, header): the words in use and who owns them: +0..15 frame rate, +16..55
  output sizes, +56..59 aspect, +60..63 field of view, +92..95 shadow map; host functions at +0xfe0 and +0xff0 on
  1.4.3. A new hook takes words and slots outside these.

### Steps for a new hook (1.2.1)

1. Find the game function and its call sites in 1.2.1 `main` with a disassembler (Ghidra with the Switch loader,
   Capstone, `llvm-objdump`: [docs/architecture.md](../architecture.md), Toolchain). Record offsets from `main`'s base
   and the original instruction words; addresses differ from 1.4.3.
2. Add a `set` and a `hook` line to `recomp/patches-v121.txt` (or `site` lines for single instructions), with a
   comment on what it does, as the existing ones have.
3. Write the hook in a new `runtime/hooks/<feature>.c` with the signature above, and log through `rt_log`.
4. Rebuild the game from source ([docs/building.md](../building.md)); the generator stops on a site whose original
   word does not match. Run the lifter's checks the docs name before committing generator changes.
5. Keep game data out of the repository: offsets and instruction words in `patches-v121.txt` are allowed (the file
   is full of them), dumps and disassembly listings are not.

## Open questions

- Which game functions a roguelike needs to hook (scene change between Banc scenes, warp, damage and death, item
  pickup, GameData flag reads and writes): their 1.2.1 addresses are not found yet.
- Whether a new patch set on 1.2.1 can share the page slots that `ov_zstd.c` uses on 1.4.3 (the `zstd` set has no
  1.2.1 sites).
