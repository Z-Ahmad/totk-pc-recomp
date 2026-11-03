# Where things live in the 1.2.1 RomFS

The merged 1.2.1 RomFS holds about 304,000 files. Paths below are RomFS paths, as `search` prints them and as a mod's
`romfs/` folder mirrors them. Most files end in `.zs` (zstd, see [formats.md](formats.md)). `python -m tools.modkit
search` finds files; `ls` lists an archive. Counts come from `python -m tools.modkit survey` on 1.2.1.

## Version numbers in names

Some files carry a data version in their name: `Mals/USen.Product.121.sarc.zs`,
`GameData/GameDataList.Product.110.byml.zs`, `RSDB/ActorInfo.Product.121.rstbl.byml.zs`,
`UI/LayoutArchive/Common.Product.110.Nin_NX_NVN.blarc.zs`, and event flows such as `Event/EventFlow/<name>.110.bfevfl.zs`
next to an unversioned `<name>.bfevfl.zs`. The merged RomFS has one version of each `.Product.<n>.` file. Edit the file
under the name it has; mods made for 1.2.1 that the user has installed replace the versioned event flow copies. Which
copy the game reads when both a versioned and an unversioned event flow exist was not checked.

## Actors: `Pack/Actor/<Actor>.pack.zs`

One SARC per actor (about 15,000), compressed with `pack.zsdic`. Inside:

- `Actor/<Actor>.engine__actor__ActorParam.bgyml`: the root. `$parent` names the template it inherits from as
  `Work/<path>.gyml`, which is the member `<path>.bgyml` of the same archive (`Work/Actor/Weapon_Sword_Metal_Base...gyml`
  is `Actor/Weapon_Sword_Metal_Base....bgyml`). `Components` maps component names (`WeaponRef`, `LifeRef`, ...) to
  members, written `?<member path>`.
- Component parameters: `Component/<Kind>/<Name>.<namespace>__component__<Kind>Param.bgyml` (for example
  `Component/WeaponParam/...game__component__WeaponParam.bgyml`), each with its own `$parent` chain. Values a file does
  not set come from its parent.
- Life, damage and physics: `Life/LifeParameters/*.game__life__LifeParameters.bgyml` (`MaxLife`: durability for
  weapons), `Life/DamageParameters/`, `Phive/...` (shapes, rigid bodies, controller sets).
- AI and behaviour of enemies: AINB and `Component/AIScheduleParam`, `Game/BSA/...` (action sequences).

Actor families by name prefix: `Weapon_`, `Armor_`, `Enemy_<Family>` (34 families, 306 actors on 1.2.1), `TBox_`
(28 chest kinds), `Item_`, `Obj_`, `DgnObj_` (shrine pieces), `SkyObj_`, `MinusObj_` (Depths), `Npc_`, `SpObj_` (Zonai
devices). Cross-actor tables: `RSDB/*.Product.121.rstbl.byml.zs` (`ActorInfo`, `GameActorInfo`, `PouchActorInfo`,
`Tag`, `EnhancementMaterialInfo`, ...); `GameParameter/` (game-wide parameters such as `EnemyCommonParam`,
`DropGlobalParam`).

## Maps: `Banc/`

A scene's placements are a pair of BYML files, `<scene>_Static.bcett.byml.zs` and `<scene>_Dynamic.bcett.byml.zs`
(dictionary `bcett.byml.zsdic`). The root has `Actors`: an array of placements, each with `Gyaml` (the actor name),
`Hash` (u64, the placement's id), `SRTHash`, `Translate`, `Rotate`, `Scale`, `Phive` (`Placement.ID`, usually the same
u64), and optionally `Dynamic` (per-placement parameters), `Links` (`Src`/`Dst` hashes, `Gyaml`, `Name`), `Bakeable`,
`Name`, `Scale`, `Presence`, `Rails` and a few more. Besides `Actors` a root may have `FilePath` (the source name),
`PhiveHeader`, `AiGroups`, `SimultaneousGroups`, `FarDeleteGroups`, `Rails`, `PlgGdTable`.

| Area | Files |
|---|---|
| Surface | `Banc/MainField/<A-J>-<1-8>_{Static,Dynamic}` (80 tiles) |
| Depths | `Banc/MinusField/<A-J>-<1-8>_{Static,Dynamic}` (80 tiles) |
| Sky | `Banc/MainField/Sky/<region>_SkyIsland<nn>_...` (64 scenes) |
| Shrines | `Banc/SmallDungeon/Dungeon<nnn>_{Static,Dynamic}` (152 shrines) |
| Chasms | `Banc/MainField/DeepHole/` |
| Caves and wells | `Banc/MainField/Cave/<Cave_or_Well>_<nnnn>_GroupSet_<nnn>_...` |
| Temples and castle | `Banc/LargeDungeon/LargeDungeon<Name>_...`, `Banc/MainField/LargeDungeon/`, `Banc/MainField/Castle/` |
| Other | `Banc/NormalStage/` (opening, title), `Banc/BossVehicle/` |
| Bulk static objects | `Banc/<field>/Merged/Mrg_*.bcett.byml.zs` (about 136,000 files) |

The Merged files hold static scenery only: decoding all of them gives 1.43 million placements and no chest or enemy.
Edit chests and enemies in the tile, shrine or cave files.

Per-scene settings: `Banc/GameBancParam/<scene>.game__banc__GameBancParam.bgyml` (the scene's main Banc, its
location, `SmallDungeonParamRef`), `Scene/Component/SmallDungeonParam/Dungeon<nnn>...bgyml` (a shrine's `Type`).
Side tables per field (`Banc/<field>/<Table>/<field>.<table>.byml.zs`): `StartPos`, `DungeonTreasureBox` (shrine ->
the `Hash` strings of its chest placements), `HiddenKorok`, `LocationArea`, `RecycleBox`, `StaticGameDataArea`,
`TreasureMap`, `AlternativeAnchor`, `LargeDungeonCheckPoint`, `DefeatHonor`, `NoEscapeRangeArea`,
`ChallengeFollowerPlayingArea`, `CraftSignboardNpc`. Other per-area data sits beside the maps: `Phive/` (collision,
nav meshes), `TerrainArc/`, `Cave/`, `Bake/`, `VolumeStats/`.

## Chests and their contents

A chest is a placement of a `TBox_*` actor. **What it holds is a parameter of the placement**, in its `Dynamic` dict:
`Drop__DropActor` names the actor that comes out (an item, weapon, armor or bundle), `Drop__DropActor_Attachment` a
fused attachment where there is one. Other keys seen on chests: `PlacementMotion_MotionType`, `PlacementMotion_DigOutDown`,
`MimicTexture`. The chest actor's pack holds no contents. Recipe: [recipes.md](recipes.md).

## Game state: `GameData/GameDataList.Product.110.byml.zs`

The flag table: **big-endian** BYML. `Data` has one array per type (`Bool`, `Int`, `Float`, `Enum`, `String64`,
`Struct`, `Bool64bitKey`, the `*Array` types, ...), `MetaData` the save layout (offsets, sizes, `SaveDirectory`). Each
entry: `Hash`, `DefaultValue` (or `Values`/`RawValues` for enums), `ResetTypeValue`, `SaveFileIndex`, plus
`ArraySize`/`OriginalSize` for arrays. Names are not stored:

- `Hash` of a named flag is **murmur3_32 of the flag name, seed 0** (checked: the Enum and EnumArray entries store
  their value names next to the hashes, and all 26,197 match; 6,093 flag hashes match names found in the game's event
  flows, AINB files and tables).
  Names may be dotted (`<Struct>.<member>`). `tools/modkit/survey.py` murmur3_32 computes it.
- Each shrine has an Enum `DungeonState.Dungeon<nnn>`.
- `Bool64bitKey` (about 130,000 entries) is keyed by u64: 93,211 of them equal the `Hash` of a placement in the maps,
  so they hold per-placement state. Which state (opened, taken, defeated) and what `ExtraByte` means are open.

## Event flows, AI, logic

- `Event/EventFlow/<name>.bfevfl.zs`: event flows (cutscenes, dialogue, item get, shrine entry and clear). Names start
  with `Dm_`/`DmF_` (demos), `Npc_` and others.
- `Event/EventSetting/`, `RSDB/EventSetting.Product.121.rstbl.byml.zs`: event settings (BYML).
- AINB: `AI/*.ainb` (actor AI), `Logic/*.logic.root.ainb` (scene logic), `Sequence/*.module.ainb` (game sequence:
  loading, banc change, save). Not compressed.

## Text: `Mals/<lang>.Product.121.sarc.zs`

One SARC of MSBT files per language (14: `USen`, `EUen`, `JPja`, ...). Folders: `ActorMsg/` (item, weapon, enemy names:
labels `<Actor>_Name`, `<Actor>_Caption`, `<Actor>_BaseName` in `ActorMsg/PouchContent.msbt`), `EventFlowMsg/` (dialogue
by event flow), `LayoutMsg/` (UI text by layout), `LocationMsg/Location.msbt` (place names; the shrines are labelled
`Dungeon<nnn>`), `StaticMsg/`, `ChallengeMsg/` (quests), `NpcTerrorMsg/`, `ShoutMsg/`, `StaffRollMsg/`. The game shows
the language of the port's `lang` setting in `totk.ini` (`TOTK_LANG`; by default the Windows locale).

## Models, textures, UI, sound

- Models: `Model/<name>.bfres.mc` (12,393; Nintendo's mesh codec container `MCPK`), animations and some models as
  `.bfres.zs` (`FRES`).
- Textures: `TexToGo/<name>.txtg` and numbered mip files (`<name>.<n>.txtg`), `*.bntx.zs` (`BNTX`).
- UI: `UI/LayoutArchive/<name>.Nin_NX_NVN.blarc.zs` (SARC of `blyt/*.bflyt`, `anim/*.bflan`, `timg/*.bntx`), fonts
  `Font/*.Nin_NX_NVN.bfarc.zs`, map height maps `UI/Map/`.
- Sound: `Sound/Resource/**/*.bwav`, `*.bars.zs`; voice `Voice/`.
- Effects `Effect/`, animation `AS/` (`ASB`), `AnimationEvent/` (`*.baev.zs`).

## Open questions

- Which game state each `Bool64bitKey` entry stores for its placement, and what `ExtraByte` is.
- The values of `ResetTypeValue` (seen: 0, 16, 17, 336, ...): which reset (blood moon, area change) each bit means.
- Whether the game reads `<name>.bfevfl.zs` or `<name>.<ver>.bfevfl.zs` when both exist.
