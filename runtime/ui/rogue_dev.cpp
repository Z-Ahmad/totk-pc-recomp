// The roguelike's dev panel: a small window beside the in-game menu while it is open and TOTK_ROGUE_DEV=1. It lists the
// GameData bool flags named in rogue-dev-flags.txt next to totk.exe (one name per line, # starts a comment; read again
// every two seconds) with buttons that queue setBool for the per-frame hook (hooks/rogue_flags.c). The menu forwards
// clicks but no typed text, so the names come from the file rather than a text field.
#include <stdio.h>
#include <string.h>

#include "imgui.h"
#include "imgui_internal.h"   // BringWindowToDisplayFront: the menu window is full screen and drawn first

#include "hooks/rogue_flags.h"
extern "C" {
#include "platform/platform.h"
}

enum { MAX_FLAGS = 48 };
static char g_names[MAX_FLAGS][96];
static int g_count;
static char g_file[600];
static uint64_t g_read_ns;

static void read_flags(void) {
    if (!g_file[0]) {
        char exe[512];
        if (!plat_exe_path(exe, sizeof exe)) return;
        char *slash = strrchr(exe, '\\');
        char *fwd = strrchr(exe, '/');
        if (fwd > slash) slash = fwd;
        if (slash) slash[1] = 0;
        snprintf(g_file, sizeof g_file, "%srogue-dev-flags.txt", slash ? exe : "");
    }
    g_count = 0;
    FILE *f = fopen(g_file, "r");
    if (!f) return;
    char line[256];
    while (g_count < MAX_FLAGS && fgets(line, sizeof line, f)) {
        char *h = strchr(line, '#');
        if (h) *h = 0;
        char *s = line, *e = line + strlen(line);
        while (*s == ' ' || *s == '\t') s++;
        while (e > s && (e[-1] == '\n' || e[-1] == '\r' || e[-1] == ' ' || e[-1] == '\t')) e--;
        *e = 0;
        if (*s) snprintf(g_names[g_count++], sizeof g_names[0], "%s", s);
    }
    fclose(f);
}

extern "C" void rogue_dev_draw(float scale) {
    if (!rogue_dev_enabled()) return;
    const uint64_t now = plat_now_ns();
    if (!g_read_ns || now - g_read_ns > 2000000000ull) {
        read_flags();
        g_read_ns = now;
    }
    ImGui::SetNextWindowPos(ImVec2(24 * scale, 24 * scale), ImGuiCond_FirstUseEver);
    ImGui::Begin("Rogue dev", nullptr, ImGuiWindowFlags_AlwaysAutoResize | ImGuiWindowFlags_NoCollapse);
    ImGui::BringWindowToDisplayFront(ImGui::GetCurrentWindow());
    ImGui::TextUnformatted("GameData bool flags (rogue-dev-flags.txt)");
    if (!g_count) ImGui::TextWrapped("No flags: put one flag name per line into %s", g_file);
    for (int i = 0; i < g_count; i++) {
        ImGui::PushID(i);
        ImGui::TextUnformatted(g_names[i]);
        ImGui::SameLine();
        if (ImGui::SmallButton("true")) rogue_flag_request(g_names[i], 1);
        ImGui::SameLine();
        if (ImGui::SmallButton("false")) rogue_flag_request(g_names[i], 0);
        ImGui::PopID();
    }
    const char *st = rogue_flags_status();
    ImGui::Separator();
    ImGui::Text("Last write: %s", st[0] ? st : "none");
    ImGui::End();
}
