// GameData bool writes from host code, for the roguelike's dev panel and later the run director.
//
// 1.2.1 main (found with Ghidra; the recon notes live under the ignored build/):
// - main+0x462e3d8 holds the address of the global that points at the GameData manager (gmd::GameDataMgr).
// - main+0xb20a48 is its setBool(mgr, value, hash): it finds the hash in the bool table (mgr+0x20, capacity +0x2c)
//   and queues {value & 1, hash} on the lock-free write ring (mgr+0x38, size +0x30, cursor +0x40) that the game
//   applies later, or hands an unknown hash to the store at mgr+0x68. The game's own HoldGameDataSetBoolSimple AINB
//   node (main+0x126d9dc) writes the same ring inline, and setInt (main+0xb51b08) is the int twin.
// - Flag hashes are murmur3_32 of the flag name, seed 0 (tools/modkit/survey.py checks them against the game's tables).
//
// Requests come from the render thread (ui/rogue_dev.cpp) through a single-producer ring and are applied by the
// per-frame hook (hooks/frame.c) with rt_call, which needs a game thread's Cpu.
#include "rogue_flags.h"

#include <stdio.h>
#include <string.h>

#include "cfg.h"
#include "cpu.h"
#include "host.h"
#include "layout.h"

#define GMD_MGR_GLOBAL_PTR 0x462e3d8ull
#define GMD_SET_BOOL 0xb20a48ull
#define QUEUE 32

typedef struct { uint32_t hash; uint8_t value; char name[96]; } Request;

static Request queue[QUEUE];
static uint32_t q_head, q_tail;   // head: the panel's next slot; tail: the hook's next request
static char status[160];

uint32_t rogue_flag_hash(const char *name) {
    const uint8_t *d = (const uint8_t *)name;
    const size_t len = strlen(name);
    const uint32_t c1 = 0xcc9e2d51u, c2 = 0x1b873593u;
    uint32_t h = 0, k;
    size_t i = 0;
    for (; i + 4 <= len; i += 4) {
        memcpy(&k, d + i, 4);
        k *= c1; k = (k << 15) | (k >> 17); k *= c2;
        h ^= k; h = (h << 13) | (h >> 19); h = h * 5 + 0xe6546b64u;
    }
    k = 0;
    switch (len & 3) {
    case 3: k ^= (uint32_t)d[i + 2] << 16; /* fall through */
    case 2: k ^= (uint32_t)d[i + 1] << 8;  /* fall through */
    case 1: k ^= d[i]; k *= c1; k = (k << 15) | (k >> 17); k *= c2; h ^= k;
    }
    h ^= (uint32_t)len;
    h ^= h >> 16; h *= 0x85ebca6bu; h ^= h >> 13; h *= 0xc2b2ae35u; h ^= h >> 16;
    return h;
}

int rogue_flag_request(const char *name, int value) {
    const uint32_t head = __atomic_load_n(&q_head, __ATOMIC_RELAXED);
    if (head - __atomic_load_n(&q_tail, __ATOMIC_ACQUIRE) >= QUEUE) return 0;
    Request *r = &queue[head % QUEUE];
    r->hash = rogue_flag_hash(name);
    r->value = (uint8_t)(value != 0);
    snprintf(r->name, sizeof r->name, "%s", name);
    __atomic_store_n(&q_head, head + 1, __ATOMIC_RELEASE);
    return 1;
}

void rogue_flags_frame(Cpu *c) {
    uint32_t tail = __atomic_load_n(&q_tail, __ATOMIC_RELAXED);
    if (tail == __atomic_load_n(&q_head, __ATOMIC_ACQUIRE)) return;
    const uint64_t global = *(volatile uint64_t *)(MOD_MAIN_BASE + GMD_MGR_GLOBAL_PTR);
    const uint64_t mgr = global ? *(volatile uint64_t *)global : 0;
    if (!mgr) return;   // the manager does not exist yet (boot); try again next frame
    uint64_t saved[8];
    memcpy(saved, c->x, sizeof saved);   // the hooked function's result and the caller's argument registers
    for (; tail != __atomic_load_n(&q_head, __ATOMIC_ACQUIRE); tail++) {
        const Request *r = &queue[tail % QUEUE];
        rt_call(c, MOD_MAIN_BASE + GMD_SET_BOOL, 3, mgr, (uint64_t)r->value, (uint64_t)r->hash);
        snprintf(status, sizeof status, "%s = %s (hash %u)", r->name, r->value ? "true" : "false", r->hash);
        rt_log("rogue: setBool %s", status);
    }
    __atomic_store_n(&q_tail, tail, __ATOMIC_RELEASE);
    memcpy(c->x, saved, sizeof saved);
}

const char *rogue_flags_status(void) { return status; }

int rogue_dev_enabled(void) {
    const char *v = cfg_get("TOTK_ROGUE_DEV");
    return v && strcmp(v, "0") != 0;
}
