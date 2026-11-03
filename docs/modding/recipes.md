# Recipes

Each recipe was run as written on the 1.2.1 RomFS and checked with `show` and `diff` on the file it wrote. **None was
checked in the game.** Community mods for 1.2.1 change the same members the same way (a weapon's `WeaponParam`, an
object's `LifeParameters`), which is good evidence, not proof, that the game reads these values as described.

Commands run from the repository root; `M` stands for `.venv-modkit\Scripts\python -m tools.modkit`. The decoded YAML
is game data: keep it under `build/` (git-ignored). `--mods` is the mods folder: for the game to load the mod, the
`mods` folder next to `totk.exe`; for a trial run, a folder under `build/`. Restart the game after installing.

## Change a weapon's attack and durability

A weapon is an actor pack; attack is in its `WeaponParam`, durability in its `LifeParameters`.

1. Find the weapon's pack and its members:

   ```
   M search "Pack/Actor/Weapon_Sword_*"
   M ls Pack/Actor/Weapon_Sword_001.pack.zs
   ```

   `Actor/<name>.engine__actor__ActorParam.bgyml` names the members it uses (`WeaponRef`, `LifeRef`). The text name
   shown in game is in `ActorMsg/PouchContent.msbt` under `<name>_Name` (recipe 3).
2. Decode the two members:

   ```
   M decode "Pack/Actor/Weapon_Sword_001.pack.zs::Component/WeaponParam/Weapon_Sword_001.game__component__WeaponParam.bgyml" -o build/work/weapon.yml
   M decode "Pack/Actor/Weapon_Sword_001.pack.zs::Life/LifeParameters/Weapon_Sword_001.game__life__LifeParameters.bgyml" -o build/work/life.yml
   ```

3. Edit `BaseAttack` in `weapon.yml` and `MaxLife` in `life.yml` (both s32: no decimal point). A key the file does not
   have is inherited from the file its `$parent` names (`Work/<path>.gyml` = member `<path>.bgyml` of the same pack);
   adding the key to the leaf file is the usual way to override it (not checked in game).
4. Install both into one mod. The second `install` edits the pack the first one wrote:

   ```
   M install build/work/weapon.yml --to "Pack/Actor/Weapon_Sword_001.pack.zs::Component/WeaponParam/Weapon_Sword_001.game__component__WeaponParam.bgyml" --mod MyWeapons --mods <mods folder>
   M install build/work/life.yml --to "Pack/Actor/Weapon_Sword_001.pack.zs::Life/LifeParameters/Weapon_Sword_001.game__life__LifeParameters.bgyml" --mod MyWeapons --mods <mods folder>
   ```

5. Check: `M diff "<mods folder>/MyWeapons/romfs/Pack/Actor/Weapon_Sword_001.pack.zs"` lists exactly the two values
   you changed.

Shared members: a member such as `Component/WeaponParam/Weapon_Sword_Base...` is copied into every pack that uses it.
Changing a template changes it only in the packs you edit.

## Change what a chest holds

A chest's contents are a parameter of its placement in a map file (see [romfs.md](romfs.md), Chests), not of the
chest actor.

1. Find the map that holds the chest. Shrines: `Banc/SmallDungeon/Dungeon<nnn>_{Static,Dynamic}.bcett.byml.zs`;
   surface and Depths: the tile files `Banc/MainField/<A-J>-<n>_...` and `Banc/MinusField/<A-J>-<n>_...`; sky, caves
   and chasms in the folders [romfs.md](romfs.md) lists. Chests are in both `_Static` and `_Dynamic` files; decode both
   and search for `TBox_`. For a shrine, `Banc/SmallDungeon/DungeonTreasureBox/SmallDungeon.dungeontreasurebox.byml.zs`
   lists the `Hash` of each chest placement per shrine.

   ```
   M decode Banc/SmallDungeon/Dungeon001_Dynamic.bcett.byml.zs -o build/work/shrine.yml
   ```

2. In the chest's entry (`Gyaml: TBox_...`), set `Dynamic: Drop__DropActor:` to the actor that should come out: an
   item, weapon, armor or bundle actor name as `M search "Pack/Actor/*"` lists them. Leave `Hash`, `SRTHash` and
   `Phive` alone: they identify the placement (and its saved state, below).
3. Install and check:

   ```
   M install build/work/shrine.yml --to Banc/SmallDungeon/Dungeon001_Dynamic.bcett.byml.zs --mod MyChests --mods <mods folder>
   M diff "<mods folder>/MyChests/romfs/Banc/SmallDungeon/Dungeon001_Dynamic.bcett.byml.zs"
   ```

Saved state: the GameData table has a `Bool64bitKey` entry per placement `Hash` for most placements, very likely the
opened state. A chest already opened in a save will most likely stay opened after its contents change; check with a
chest you have not opened.

## Edit text

Text is per language in `Mals/<lang>.Product.121.sarc.zs`. Edit the language the game runs in (the `lang` setting of
`totk.ini`, by default the Windows locale; `USen` for US English).

1. Find the message. Item names are `<actor>_Name` in `ActorMsg/PouchContent.msbt`, place names in
   `LocationMsg/Location.msbt`, dialogue in `EventFlowMsg/<event flow>.msbt`:

   ```
   M ls Mals/USen.Product.121.sarc.zs
   M decode "Mals/USen.Product.121.sarc.zs::ActorMsg/PouchContent.msbt" -o build/work/pouch.yml
   ```

2. Change the text after the label. Keep the `{{...}}` tags unless you know what they do; a literal `{` or `\` is
   written `\{` or `\\`.
3. Install and check:

   ```
   M install build/work/pouch.yml --to "Mals/USen.Product.121.sarc.zs::ActorMsg/PouchContent.msbt" --mod MyText --mods <mods folder>
   M diff "<mods folder>/MyText/romfs/Mals/USen.Product.121.sarc.zs"
   ```

The whole language archive (about 11 MB) goes into the mod, so this mod and any other that changes the same
language's text (or the port's Xbox prompts, [loading.md](loading.md)) replace each other.

## Other things that work the same way

- Any BYML file or member: `decode`, edit, `install --to <path>[::member]`. Several edits into one archive accumulate.
- A whole file you made elsewhere (a texture, an event flow): `install <file> --to <path>` stores it compressed like
  the original; inside an archive with `::member`.
- A new file the game does not have: `install` adds it under the given path and picks its dictionary by name. Whether
  the game then loads it depends on something referring to it (an actor pack, a map, a table).
