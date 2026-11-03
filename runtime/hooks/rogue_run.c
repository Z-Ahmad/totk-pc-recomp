// The roguelike's run director, version 0. A run is the list of chambers in rogue-run.txt next to totk.exe, one per line:
//
//   chamber <name> <clear flag> <cx> <cy> <cz> <radius> <exit y> <spawn x> <spawn y> <spawn z>
//
// Starting a run warps to the first chamber's spawn and sets its clear flag false (its StopCeilingClipperArea, placed
// with Presence {FlagName: <clear flag>, IsNegation: true}, seals the Ascend exit). About four times a second the
// director counts living enemies (running actors named Enemy_* with health above 0) within <radius> of the chamber's
// centre; at zero it sets the clear flag, which unseals the exit at once. Once cleared, a player within <radius>
// horizontally and above <exit y> (out through the ceiling) is warped to the next chamber. A chamber counts as clear
// only after an enemy was seen alive there or ten seconds passed, so enemies that have not loaded yet do not clear it.
//
// 1.2.1 main, from github.com/afiaka87/totk-mods (MIT, Copyright (c) Clay Mullis): runtime-support's Totk121Offsets.hpp,
// Scene.hpp and ActorRoster.hpp (scene, resident roster, process list and its lock), botw-abilities' Fury.cpp (the
// health chain) and bivouac's MapStampService.cpp (the warp manager and warpToWarpMarker). Only addresses and field
// offsets are taken; the code is ours.
#include "rogue_run.h"

#include <math.h>
#include <stdio.h>
#include <string.h>

#include "cpu.h"
#include "host.h"
#include "layout.h"
#include "platform/platform.h"
#include "rogue_flags.h"

// main offsets
#define SCENE_MODULE_SLOT 0x4728538ull      // the scene module (resident roster path)
#define SCENE_MODULE_HOLDER 0x462E180ull    // holds the address of the scene module's slot (warp path)
#define GET_SCENE_COMPONENT 0x1203C3Cull    // void *(sceneModule, index)
#define WARP_TO_MARKER 0x198CA5Cull         // void (warpMgr, const float pos[3], const float rot[3])
#define PROCESS_MGR_HOLDER 0x462DED8ull
#define PROCESS_LIST_LOCK 0x2B17270ull      // void (mutex)
#define PROCESS_LIST_UNLOCK 0x2B17280ull
// field offsets
#define SCENE_FROM_MODULE 0x1E8
#define SCENE_COMPONENTS 0x58
#define RESIDENT_COMPONENT 13
#define RESIDENT_COUNT 0x20
#define RESIDENT_LIST 0x28
#define RESIDENT_STRIDE 0x70
#define RESIDENT_DESCRIPTOR 0x08
#define ACTOR_FROM_DESCRIPTOR 0x40
#define ACTOR_NAME 0x218
#define ACTOR_COMPONENTS 0x228
#define ACTOR_POSITION 0x2B4
#define LIFE_FROM_COMPONENTS 0x2F8
#define LIFE_HOLDER 0x1830
#define LIFE_VALUE 8
#define PROCESS_MUTEX 72
#define PROCESS_ACTIVE_HEAD 112
#define PROCESS_LINK_OFFSET 124
#define PROCESS_NAME 24
#define PROCESS_STATE 36
#define WARP_COMPONENT 32
#define WARP_TARGET_INDEX 336

#define MAX_CHAMBERS 32
#define CHECK_EVERY 15        // frames between enemy counts
#define GRACE_FRAMES 600      // a chamber with no enemy seen counts as clear after this many frames

typedef struct {
    char name[32], flag[96];
    float centre[3], radius, exit_y, spawn[3];
} Chamber;

static Chamber chambers[MAX_CHAMBERS];
static int n_chambers;
static int current = -1;          // the chamber the player is in, -1 when no run
static int cleared, seen_enemy, enemies = -1;
static uint64_t since_arrival;
static int command;               // ROGUE_RUN_* from the panel
static char status[200] = "no run";

static int ok_ptr(uint64_t a) { return a >= 0x1000000ull && a < 0x8000000000ull && !(a & 3); }
static uint64_t rd64(uint64_t a) { return ok_ptr(a) ? *(volatile uint64_t *)a : 0; }
static uint32_t rd32(uint64_t a) { return ok_ptr(a) ? *(volatile uint32_t *)a : 0; }

static int load_chambers(void) {
    char path[600];
    if (!plat_exe_path(path, sizeof path)) return 0;
    char *slash = strrchr(path, '\\'), *fwd = strrchr(path, '/');
    if (fwd > slash) slash = fwd;
    snprintf(slash ? slash + 1 : path, sizeof path - (slash ? (size_t)(slash + 1 - path) : 0), "rogue-run.txt");
    FILE *f = fopen(path, "r");
    n_chambers = 0;
    if (!f) {
        rt_log("rogue: run: no %s", path);
        return 0;
    }
    char line[400];
    while (n_chambers < MAX_CHAMBERS && fgets(line, sizeof line, f)) {
        Chamber *ch = &chambers[n_chambers];
        if (sscanf(line, " chamber %31s %95s %f %f %f %f %f %f %f %f", ch->name, ch->flag, &ch->centre[0], &ch->centre[1],
                   &ch->centre[2], &ch->radius, &ch->exit_y, &ch->spawn[0], &ch->spawn[1], &ch->spawn[2]) == 10)
            n_chambers++;
    }
    fclose(f);
    rt_log("rogue: run: %d chambers from %s", n_chambers, path);
    return n_chambers;
}

// The player actor through the scene's resident roster, or 0.
static uint64_t player_actor(void) {
    const uint64_t module = rd64(MOD_MAIN_BASE + SCENE_MODULE_SLOT);
    const uint64_t scene = rd64(module + SCENE_FROM_MODULE);
    const uint64_t comps = rd64(scene + SCENE_COMPONENTS);
    const uint64_t mgr = rd64(comps + 8 * RESIDENT_COMPONENT);
    const int count = (int)rd32(mgr + RESIDENT_COUNT);
    const uint64_t list = rd64(mgr + RESIDENT_LIST);
    if (!ok_ptr(mgr) || !ok_ptr(list) || count <= 0 || count > 256) return 0;
    for (int i = 0; i < count; i++) {
        const uint64_t actor = rd64(rd64(list + (uint64_t)i * RESIDENT_STRIDE + RESIDENT_DESCRIPTOR) + ACTOR_FROM_DESCRIPTOR);
        const uint64_t name = rd64(actor + ACTOR_NAME);
        if (ok_ptr(name) && !strcmp((const char *)name, "Player")) return actor;
    }
    return 0;
}

static int alive(uint64_t actor) {
    const uint64_t holder = rd64(rd64(rd64(actor + ACTOR_COMPONENTS) + LIFE_FROM_COMPONENTS) + LIFE_HOLDER);
    return ok_ptr(holder) && (int)rd32(holder + LIFE_VALUE) > 0;
}

static float dist2(const float *a, const float *b) {
    const float x = a[0] - b[0], y = a[1] - b[1], z = a[2] - b[2];
    return x * x + y * y + z * z;
}

// Living enemies within the chamber's radius, walking the running processes under the game's list lock; -1 when the
// process list is not readable.
static int count_enemies(Cpu *c, const Chamber *ch) {
    const uint64_t pm = rd64(rd64(MOD_MAIN_BASE + PROCESS_MGR_HOLDER));
    if (!ok_ptr(pm)) return -1;
    const int link = (int)rd32(pm + PROCESS_LINK_OFFSET);
    if (link <= 0 || link >= 4096) return -1;
    rt_call(c, MOD_MAIN_BASE + PROCESS_LIST_LOCK, 1, pm + PROCESS_MUTEX);
    const uint64_t anchor = pm + PROCESS_ACTIVE_HEAD - 8, start = rd64(pm + PROCESS_ACTIVE_HEAD);
    const float r2 = ch->radius * ch->radius;
    int n = 0, walked = 0;
    for (uint64_t node = start; ok_ptr(node) && node != anchor && walked < 4096; walked++) {
        const uint64_t proc = node - (uint64_t)link;
        const uint64_t name = rd64(proc + PROCESS_NAME);
        if (ok_ptr(proc) && rd32(proc + PROCESS_STATE) == 4 && ok_ptr(name) && !strncmp((const char *)name, "Enemy_", 6) &&
            dist2((const float *)(proc + ACTOR_POSITION), ch->centre) <= r2 && alive(proc))
            n++;
        node = rd64(node + 8);
        if (node == start) break;
    }
    rt_call(c, MOD_MAIN_BASE + PROCESS_LIST_UNLOCK, 1, pm + PROCESS_MUTEX);
    return n;
}

// The game's own fast travel to a position (the map's travel to a warp marker), with its loading.
static int warp_to(Cpu *c, const float *pos) {
    const uint64_t module = rd64(rd64(MOD_MAIN_BASE + SCENE_MODULE_HOLDER));
    if (!ok_ptr(module)) return 0;
    const uint64_t mgr = rt_call(c, MOD_MAIN_BASE + GET_SCENE_COMPONENT, 2, module, (uint64_t)WARP_COMPONENT);
    if (!ok_ptr(mgr)) return 0;
    *(volatile int32_t *)(mgr + WARP_TARGET_INDEX) = -1;
    // The two vectors go on the guest stack below sp, and sp moves under them for the call.
    const uint64_t sp = c->sp, data = (sp - 0x40) & ~15ull;
    float *v = (float *)data;
    v[0] = pos[0]; v[1] = pos[1] + 2.0f; v[2] = pos[2];   // arrive hovering 2 m up, as the map's travel does
    v[4] = v[5] = v[6] = 0.0f;
    c->sp = (data - 0x40) & ~15ull;
    rt_call(c, MOD_MAIN_BASE + WARP_TO_MARKER, 3, mgr, data, data + 16);
    c->sp = sp;
    return 1;
}

static void enter(Cpu *c, int k) {
    current = k;
    cleared = seen_enemy = 0;
    enemies = -1;
    since_arrival = 0;
    rogue_flag_set_now(c, chambers[k].flag, 0);   // seal its exit
    const int ok = warp_to(c, chambers[k].spawn);
    rt_log("rogue: run: chamber %d/%d %s (%s)", k + 1, n_chambers, chambers[k].name, ok ? "warping" : "warp unavailable");
}

void rogue_run_command(int cmd) { __atomic_store_n(&command, cmd, __ATOMIC_RELEASE); }

const char *rogue_run_status(void) { return status; }

static void step(Cpu *c) {
    const int cmd = __atomic_exchange_n(&command, 0, __ATOMIC_ACQ_REL);
    if (cmd == ROGUE_RUN_STOP && current >= 0) {
        rt_log("rogue: run: stopped in chamber %d", current + 1);
        current = -1;
        snprintf(status, sizeof status, "no run");
    }
    if (cmd == ROGUE_RUN_START && load_chambers()) enter(c, 0);
    if (current < 0) return;

    const Chamber *ch = &chambers[current];
    since_arrival++;
    if (!cleared && since_arrival % CHECK_EVERY == 0) {
        enemies = count_enemies(c, ch);
        if (enemies > 0) seen_enemy = 1;
        if (enemies == 0 && (seen_enemy || since_arrival > GRACE_FRAMES)) {
            cleared = 1;
            rogue_flag_set_now(c, ch->flag, 1);   // unseal the exit
            rt_log("rogue: run: chamber %d %s cleared", current + 1, ch->name);
        }
    }
    if (cleared) {
        const uint64_t player = player_actor();
        if (player) {
            const float *p = (const float *)(player + ACTOR_POSITION);
            const float dx = p[0] - ch->centre[0], dz = p[2] - ch->centre[2];
            if (dx * dx + dz * dz <= ch->radius * ch->radius && p[1] > ch->exit_y) {
                if (current + 1 < n_chambers) {
                    enter(c, current + 1);
                } else {
                    rt_log("rogue: run: complete (%d chambers)", n_chambers);
                    current = -1;
                }
            }
        }
    }
    if (current >= 0)
        snprintf(status, sizeof status, "chamber %d/%d %s: %s", current + 1, n_chambers, chambers[current].name,
                 cleared ? "cleared, Ascend out" : enemies < 0 ? "counting enemies" : "");
    if (current >= 0 && !cleared && enemies >= 0)
        snprintf(status + strlen(status), sizeof status - strlen(status), "%d enemies left", enemies);
    if (current < 0 && cmd != ROGUE_RUN_STOP) snprintf(status, sizeof status, "run complete");
}

void rogue_run_frame(Cpu *c) {
    uint64_t saved[8];
    memcpy(saved, c->x, sizeof saved);   // the hooked function's result and the caller's argument registers
    step(c);
    memcpy(c->x, saved, sizeof saved);
}
