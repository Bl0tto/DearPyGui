# Handoff: mvDockSpaceProxy — Visual Rendering Bugs (RESOLVED)

## Goal

Implement `mvDockSpaceProxy` as a mergeable PR against the upstream DearPyGui repository.
The feature keeps docked panels docked (rather than floating free) when their host window
is hidden and then shown again.

**Hard constraint:** Zero modifications to any file under `thirdparty/imgui/` or
`thirdparty/implot/`. All changes are DPG-side only — accessing ImGui internals via
`imgui_internal.h` (already included by 17 DPG source files) is acceptable and is the
established DPG pattern.

---

## Current Branch State (master)

Git user: Bl0tto  
Working branch: `master`  
Reference (confirmed-working with debug prints): `debug/dock-proxy-internal-api-backup` @ `1fbc52d`

The following changes are already committed and building cleanly.

### `src/mvContainers.h` (lines 299–328)

```cpp
struct mvDockSpaceProxyConfig
{
    ImGuiID dockSpaceId = 0;
};

namespace DearPyGui {
    void fill_configuration_dict(const mvDockSpaceProxyConfig& inConfig, PyObject* outDict);
    void set_required_configuration(PyObject* inDict, mvDockSpaceProxyConfig& outConfig);
    void set_configuration(PyObject* inDict, mvDockSpaceProxyConfig& outConfig);
    void draw_dock_space_proxy(ImDrawList* drawlist, mvAppItem& item, mvDockSpaceProxyConfig& config);
}

class mvDockSpaceProxy : public mvAppItem
{
public:
    mvDockSpaceProxyConfig configData{};
    explicit mvDockSpaceProxy(mvUUID uuid) : mvAppItem(uuid) {}
    void draw(ImDrawList* drawlist, float x, float y) override
        { DearPyGui::draw_dock_space_proxy(drawlist, *this, configData); }
    void handleSpecificRequiredArgs(PyObject* dict) override
        { DearPyGui::set_required_configuration(dict, configData); }
    void handleSpecificKeywordArgs(PyObject* dict) override
        { DearPyGui::set_configuration(dict, configData); }
    void getSpecificConfiguration(PyObject* dict) override
        { DearPyGui::fill_configuration_dict(configData, dict); }
};
```

### `src/mvContainers.cpp` — proxy draw function and helpers (lines ~1813–1884)

```cpp
static void SetDockNodeKeepAlive(ImGuiDockNode* node)
{
    if (!node) return;
    node->MergedFlags |= ImGuiDockNodeFlags_KeepAliveOnly;
    SetDockNodeKeepAlive(node->ChildNodes[0]);
    SetDockNodeKeepAlive(node->ChildNodes[1]);
}

static void SetDockNodeWindowsHidden(ImGuiDockNode* node, bool hidden)
{
    if (!node) return;
    for (ImGuiWindow* win : node->Windows)
    {
        win->Hidden = hidden;
        if (hidden)
            win->HiddenFramesCanSkipItems = 2;
        else
            win->HiddenFramesCanSkipItems = 0;
    }
    SetDockNodeWindowsHidden(node->ChildNodes[0], hidden);
    SetDockNodeWindowsHidden(node->ChildNodes[1], hidden);
}

void
DearPyGui::draw_dock_space_proxy(ImDrawList* drawlist, mvAppItem& item, mvDockSpaceProxyConfig& config)
{
    if (!item.config.show) return;
    if (config.dockSpaceId == 0) return;

    ImGuiContext& g = *GImGui;
    ImGuiDockNode* node = (ImGuiDockNode*)g.DockContext.Nodes.GetVoidPtr(config.dockSpaceId);
    if (!node) return;

    node->LastFrameAlive = g.FrameCount;

    bool hostActive = (node->LastFrameActive == g.FrameCount);

    SetDockNodeKeepAlive(node);
    SetDockNodeWindowsHidden(node, !hostActive);

    item.state.lastFrameUpdate = GContext->frame;
}

void
DearPyGui::set_required_configuration(PyObject* inDict, mvDockSpaceProxyConfig& outConfig)
{
    if (!VerifyRequiredArguments(GetParsers()[GetEntityCommand(mvAppItemType::mvDockSpaceProxy)], inDict))
        return;
    outConfig.dockSpaceId = (ImGuiID)(ToUUID(PyTuple_GetItem(inDict, 0)) & 0xFFFFFFFFULL);
}

void
DearPyGui::set_configuration(PyObject* inDict, mvDockSpaceProxyConfig& outConfig)
{
    if (inDict == nullptr) return;
    if (PyObject* item = PyDict_GetItemString(inDict, "dock_space_id"))
        outConfig.dockSpaceId = (ImGuiID)(ToUUID(item) & 0xFFFFFFFFULL);
}

void
DearPyGui::fill_configuration_dict(const mvDockSpaceProxyConfig& inConfig, PyObject* outDict)
{
    if (outDict == nullptr) return;
    PyDict_SetItemString(outDict, "dock_space_id", ToPyLong((long)inConfig.dockSpaceId));
}
```

### Other wired-up files (already complete, do not need changes)

| File | What was added |
|------|----------------|
| `src/mvAppItem.cpp` | Parser: `dock_space_id` as `REQUIRED_ARG` (positional UUID) |
| `src/mvItemRegistry.cpp` | `mvDockSpaceProxy` registered as a root-level item |
| `src/mvAppItemCommons.h` | `mvDockSpaceProxy` case in item dispatch switch |
| `testing/simple_tests.py` | `TestDockSpaceProxy` — 5 tests, all passing |
| `testing/demo_dock_proxy.py` | Interactive hide/show demo |

Python API (already wired):
```python
dpg.add_dock_space_proxy(dock_space_id, *, tag=..., show=True)
```

---

## What Currently Works

- `dockSpaceId` is correctly populated from the positional Python arg.
- The dock node's `LastFrameAlive` is bumped every frame — prevents GC.
- `KeepAliveOnly` flag is pre-armed — `BeginDocked()` doesn't eject panels.
- Panels **do remain logically docked** — they are never ejected to floating.
- All 20 regression tests pass.

---

## Visual Bugs — RESOLVED (2026-07-03)

Both bugs below shared a single root cause and are fixed by gating
`SetDockNodeKeepAlive()` on `!hostActive` in `draw_dock_space_proxy`.

### Actual root cause (none of the original hypotheses)

The proxy unconditionally OR'd `ImGuiDockNodeFlags_KeepAliveOnly` into
`node->MergedFlags` **every frame, including frames where the host was visible**.
Per-frame order (DPG renders `windowRoots` in creation order — host → proxy → panels):

1. Host's `DockSpace()` → `DockNodeUpdate()` → `UpdateMergedFlags()` recomputes
   `MergedFlags` (clearing stale flags) and draws the tab bar.
2. Proxy re-ORs `KeepAliveOnly` into `MergedFlags`.
3. Panels call `Begin()` → `BeginDocked()` → `imgui.cpp:21037`
   `if (node->MergedFlags & KeepAliveOnly) return;` with `DockTabIsVisible = false`.
4. `Begin()` (`imgui.cpp:8565`): `DockIsActive && !DockTabIsVisible` → window hidden →
   all widget content skipped. Tabs (drawn in step 1) remain → empty panel (Bug A);
   split child nodes → white client area (Bug B).

The old code comment assumed the proxy rendered *after* the panels, so the flag would
be cleared before live panels saw it — false: the proxy must be created (and thus
rendered) *before* the panels, otherwise on the first hidden frame `LastFrameAlive`
is stale when the panels' `BeginDocked()` runs and they undock (`imgui.cpp:20991`).

**Fix:** arm `KeepAliveOnly` only on frames where the host did not submit the
dockspace (`node->LastFrameActive != g.FrameCount`). On visible frames the proxy
leaves `MergedFlags` untouched, so `BeginDocked()` reaches the
`DockTabIsVisible = true` path and content renders normally.

**Ordering contract (documented in code):** create the host window first, then the
proxy, then the panel windows — host → proxy → panels in DPG creation order.

## Original Bug Reports (historical, see attached screenshots)

The panels stay docked correctly but render incorrectly in two distinct scenarios.

### Bug A — Full dock (all panels fill a single undivided node)

**Symptom:** When docked, panels lose all text content and render as an empty
dockable drop-zone — the hatched/empty dock-target appearance ImGui shows for an
unfilled node. No widget content is visible.

*See: `demo_right_panel_docked_tab.png`*

### Bug B — Split view (two panels split side-by-side into sibling nodes)

**Symptom:** When docked, panels turn solid white. The entire client area of each
panel is a white rectangle with no content.

*See: `demo_right_panel_docked_split.png`*

---

## Root Cause Hypotheses

Both bugs point to panel content not being submitted on the first visible frame after unhide.
Investigate in this order:

### 1. `SkipItems` not cleared on unhide (most likely)

`win->SkipItems` is set to `true` by ImGui when `hidden_regular = true`. On unhide,
`SetDockNodeWindowsHidden` clears `HiddenFramesCanSkipItems = 0` and `Hidden = false`,
but **does not explicitly clear `win->SkipItems`**. If ImGui doesn't clear it before DPG
submits widget content that frame, every `dpg.add_*` call is a no-op.

**Fix to try:** Add `win->SkipItems = false;` in the `else` (unhide) branch of
`SetDockNodeWindowsHidden`.

### 2. `ContentSize` / `SizeFull` zeroed during hide

When `HiddenFramesCanSkipItems > 0`, ImGui preserves `ContentSize` (imgui.cpp line ~6931).
If the counter was wrong for even one frame, ImGui may have frozen the size to zero,
causing a zero-area window that appears white or empty.

**Fix to try:** After unhide, check `win->ContentSize` — if it's `{0,0}`, restore it
from `win->ContentSizeExplicit` or `win->SizeFull`.

### 3. Recursive walk missing leaf windows in split view

Split nodes have `node->Windows.Size == 0` — all panels live in `ChildNodes[0]->Windows`
and `ChildNodes[1]->Windows`. The recursive calls in `SetDockNodeWindowsHidden` should
reach them, but verify by adding a counter of windows visited vs windows expected.

**Fix to try:** Add a debug `fprintf` or DPG log line counting how many `ImGuiWindow*`
are visited during an unhide pass. Compare to the actual number of docked panels.

### 4. Tab-bar / focus state in split view (Bug B specific)

In split view, each child node has a tab bar. After unhide, the tab bar's `SelectedTabId`
or `NextSelectedTabId` may be stale, causing ImGui to think no tab is active → white area.

**Fix to try:** After clearing Hidden flags, also reset `node->TabBar` state if non-null:
`node->TabBar->NextSelectedTabId = node->TabBar->SelectedTabId;`

---

## Key ImGui Internals (all in `thirdparty/imgui/imgui_internal.h`, no changes needed)

```cpp
struct ImGuiDockNode {
    ImGuiDockNodeFlags MergedFlags;     // KeepAliveOnly keeps node alive
    int  LastFrameAlive;                // bump each frame to prevent GC
    int  LastFrameActive;               // 0 when host window is hidden
    ImGuiDockNode* ChildNodes[2];       // split children (null if leaf)
    ImVector<ImGuiWindow*> Windows;     // panels at this leaf node
    ImGuiTabBar* TabBar;                // tab bar (split nodes have this)
};

struct ImGuiWindow {
    bool  Hidden;
    short HiddenFramesCanSkipItems;     // 2 → after Begin() decrement → 1 → hidden_regular=true
    bool  SkipItems;                    // must also clear this on unhide
    ImVec2 ContentSize;
    ImVec2 SizeFull;
};
```

ImGui hide/show lifecycle (imgui.cpp, relevant lines):
- `~7940`: All `HiddenFrames*` counters decremented **inside `Begin()`**, before any check.
  Setting to `2` means: decrement → `1` → `hidden_regular = true` for that frame. ✓  
  Setting to `1` would mean: decrement → `0` → `hidden_regular = false`. ✗ (old bug, already fixed)
- `~7943`: `hidden_regular = (HiddenFramesCanSkipItems > 0)`
- `~7951`: `SkipItems = hidden_regular || ...`
- `~6931`: `ContentSize` preserved only when `HiddenFramesCanSkipItems > 0`

---

## Build & Test

```powershell
# 1. Build
cmake --build cmake-build-local --config Release

# 2. Deploy
cp cmake-build-local/DearPyGui/Release/_dearpygui.pyd output/dearpygui/_dearpygui.pyd

# 3. Regression — all 20 must pass before and after any change
$env:PYTHONPATH = "output"
py -3.13 -m unittest testing/simple_tests.py -v

# 4. Demo
py -3.13 testing/demo_dock_proxy.py
```

**Demo test sequence:**
1. Dock `Panel R-1` and `Panel R-2` into the RIGHT HOST window.
2. Click **Hide Right** — panels must disappear (not float, not show white, not show drop-zone).
3. Click **Show Right** — panels must re-appear with full content, still docked.
4. Repeat with R-1 and R-2 split side-by-side (drag one to the right edge to split).

---

## PR Scope — Files to Include

Only these files should differ from upstream master in the final PR.
**No `thirdparty/` files.**

| File | Change |
|------|--------|
| `src/mvContainers.h` | `mvDockSpaceProxyConfig` + `mvDockSpaceProxy` class |
| `src/mvContainers.cpp` | draw function, helpers, set/fill functions |
| `src/mvAppItem.cpp` | Parser registration |
| `src/mvItemRegistry.cpp` | Root-item registration |
| `src/mvAppItemCommons.h` | Dispatch case |
| `testing/simple_tests.py` | `TestDockSpaceProxy` class |
| `testing/demo_dock_proxy.py` | Interactive demo |
