# Roguelike mode: design

A Hades-style run on TotK 1.2.1: pick a weapon class, start in the Depths, clear a chamber, Ascend through its sealed
ceiling to the next one, rising through Depths, Surface and Sky. Sages grant boons; Poes are the currency kept between
runs. This page holds the game design and, for each piece, how it can be built and how sure that is.

How things get built (see [docs/modding/](../modding/README.md)):

- **Data**: actor parameters, map placements, drop tables, text, edited with `tools/modkit` and loaded as a mod.
- **Hook**: C in `runtime/hooks/` calling the game's own functions (`hook` lines, `rt_call`); needs the 1.2.1 address
  of each function.
- **New content**: models (Blender), effects, AI graphs or event flows the kit cannot encode yet. The most work.

Prior art for hooks: [afiaka87/totk-mods](https://github.com/afiaka87/totk-mods) (MIT), exlaunch plugins for exactly
1.2.1 (build `9B4E43650501A4D4`): BotW Abilities (Stasis, Cryonis, Remote Bombs; Revali's Gale, Urbosa's Fury,
Mipha's Grace, Daruk's Protection), Self Recall, Infinite Ascend, Zonai Survey. The port cannot load the plugins
themselves (a `subsdk` plugin brings its own Switch code; [mods.md](../mods.md)), but their source names the 1.2.1
functions they call and their behaviour can be rebuilt as hooks. Code copied from them keeps its header and gets a row
in `THIRD_PARTY_NOTICES.md` ([AGENTS.md](../../AGENTS.md)).

Confidence: **known** = the game already does it or a 1.2.1 mod already does it; **likely** = the pieces exist, the
wiring is ours; **open** = not yet known to be possible.

## Run structure

| Piece | Approach | Confidence |
|---|---|---|
| Chamber exit sealed until cleared | `StopCeilingClipperAreaNoMerge` with `Presence {FlagName, IsNegation}`; Ascend allowed underground by an `Area` + `EnableUseUndergroundCeilingClipperArea` AI group (Depths tiles do this) | known: tested in game (Lookout Landing shelter, 2026-11-02): the blocker appears and disappears the moment the flag changes, even while Ascend is aimed at the ceiling |
| Setting run flags | `runtime/hooks/rogue_flags.c` (the game's setBool), dev panel `TOTK_ROGUE_DEV=1` | known (built) |
| Chamber cleared | defeat queries / counter flag in data, or a hook on enemy death | open |
| Moving to the next chamber | warp to a named `DestinationAnchor` after the Ascend | open |
| Death ends the run, Poes kept | hook on game over; meta-progression in a file beside the save | open |
| Run UI (boon choice, HUD) | ImGui first (as the dev panel), the game's layouts later | known (ImGui) |

## Weapons (the user's wishlist)

TotK's weapon classes set the moveset: one-handed (sword), two-handed (claymores and axes), spear. A weapon's model
and stats are data; its moveset comes from its class.

| Weapon | Feel | Upgrade ("hammer") | Approach | Confidence |
|---|---|---|---|---|
| Sword | standard reach and speed | chance to hit twice | one-handed class; the second hit from a hook on the damage the player deals | likely (the damage path is in BotW Abilities' Fury and Stasis code) |
| Axe | two-handed, for crowds, slower | longer spin reaches farther and spins faster | two-handed class; spin length and speed from the charge-attack parameters, or a hook | likely for length (parameters), open for reach |
| Katana | fast, longer reach than a sword | instant execute | no katana class: a one-handed weapon with a new model (Blender) and longer reach, or a spear moveset with a blade model; execute = a damage hook that kills below a health threshold | open for reach on the sword moveset; likely for execute |

## Boons (Sages)

| Sage | Theme | Boon idea | Approach | Confidence |
|---|---|---|---|---|
| Tulin (wind) | mobility | double jump | the mid-air gust Tulin's vow already gives; Revali's Gale in BotW Abilities is a working 1.2.1 jump boost | known |
| | | wind slice from attacks (Stormblade) | the Master Sword's beam at full health is a native ranged slash; give it to other weapons with a wind effect | likely |
| Sidon (water) | easy, dependable | bubble shield that blocks a hit | Sidon's vow water shield is native; Daruk's Protection in BotW Abilities is a working 1.2.1 shield | known |
| | | enemies drop heals and extra Poes | enemy drop tables are data | known |
| | | water stream or bubbles that knock back | Sidon's water attacks and splash items are native; triggering them on attack is a hook | likely |
| Yunobo (fire) | damage over time, needs synergies | attacks stack fire | burning is a native status; a stack count that raises its damage is ours (hook) | likely |
| | | fire resistance | Flame Guard is a native status effect (armor and food give it) | likely |
| Riju (lightning) | crowd control, low single-target damage | stun | shock is a native status | known |
| | | chain lightning | Riju's vow lightning is native; Urbosa's Fury in BotW Abilities is a working 1.2.1 area strike | known |
| Mineru (spirit) | Zonai | unlocks Fuse and Zonai devices | the abilities are unlocked by flags (run starts with them off) | likely |
| | | Zonai weapons get a bonus | Zonai weapon and part parameters are data | likely |
| | | Sheikah tech: Remote Bombs, Stasis | rebuild BotW Abilities' Remote Bomb and Stasis as hooks | known (it exists for 1.2.1), large |
| | | summon construct minions | Mineru's own construct is native; friendly soldier constructs are not | open |
| Zelda (time) | — | Rewind: Recall does not work on enemies | Self Recall (afiaka87/totk-mods) recalls Link himself: a "rewind on lethal hit, once per chamber" boon (Hades' Death Defiance) | known (Self Recall exists) |
| | | Stasis | BotW Abilities' Stasis+ (also freezes enemies for five seconds) | known, large |
| | | | Recall on projectiles and thrown rocks is native: a boon that sends them back | likely |

## Next steps

1. Read afiaka87/totk-mods for the 1.2.1 functions behind damage, status effects and abilities; record them in the
   recon notes and pick the first boon to build as a hook (candidates: Sidon's shield, Tulin's double jump).
2. Chamber-cleared detection and the warp to the next chamber.
