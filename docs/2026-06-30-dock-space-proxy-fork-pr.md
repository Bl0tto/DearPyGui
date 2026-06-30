# DPG Fork PR — `mvDockSpaceProxy` (KeepAlive Proxy Window)

**Date:** 2026-06-30  
**Status:** Complete — merged to `master` of `github.com/Bl0tto/DearPyGui`  
**Branch:** `feat/add-dock-space` (merged; `master` is now canonical)  
**Commits:** `ce57eff` (phase 1 — `add_dock_space` + constants) · `8e9ac92` (phase 2 — `mvDockSpaceProxy`, stubs, tests)

---

## Problem

When a DPG window is on an **inactive tab** inside a viewport dock group, DPG stops
rendering that window's children (`ImGui::Begin()` returns false). Any `DockSpace()` call
inside a `child_window` inside that window therefore never fires, `LastFrameAlive` falls
behind `FrameCount`, and ImGui GCs the dock node after ~2 frames. All panels previously
docked in that node become undocked.

`mvDockNodeFlags_KeepAliveOnly` passed as a flag on the **same** `DockSpace()` call cannot
fix this because the call itself never executes on inactive frames — it's inside the
hierarchy that stopped rendering.

---

## Solution: Proxy Window Pattern

A tiny off-screen ImGui window that lives **outside** any tab hierarchy and always renders.
Each frame it calls `ImGui::DockSpace(id, {0,0}, ImGuiDockNodeFlags_KeepAliveOnly)` for a
registered dock-space ID. This keeps the dock node's `LastFrameAlive` current without
rendering a visible UI surface.

Python usage once landed:

```python
dock_tag = self.window_tag + 2

# Interactive dock space inside the child_window (unchanged)
dpg.add_dock_space(tag=dock_tag, width=0, height=0)

# Proxy at root level — keeps dock node alive when host tab is inactive
dpg.add_dock_space_proxy(dock_space_id=dock_tag, tag=dock_tag + 100)

# Cleanup in on_close()
if dpg.does_item_exist(dock_tag + 100):
    dpg.delete_item(dock_tag + 100)
```

---

## C++ Implementation Plan

### 1. New item type — `src/mvDockSpaceProxy.h`

```cpp
#pragma once
#include "mvAppItem.h"

struct mvDockSpaceProxyConfig {
    ImGuiID dock_space_id = 0;
};

class mvDockSpaceProxy : public mvAppItem {
public:
    mvDockSpaceProxyConfig config{};

    explicit mvDockSpaceProxy(mvUUID uuid);

    void draw(ImDrawList* drawlist, float x, float y) override;
    void handleSpecificKeywordArgs(PyObject* dict) override;
    void getSpecificConfiguration(PyObject* dict) override;
    void applySpecificTemplate(mvAppItem* item) override;
};

MV_REGISTER_WIDGET(mvDockSpaceProxy, MV_ITEM_DESC_DEFAULT,
                   StorageValueTypes::None, 0);
```

### 2. Implementation — `src/mvDockSpaceProxy.cpp`

```cpp
#include "mvDockSpaceProxy.h"
#include "mvPyUtils.h"
#include "mvLog.h"

mvDockSpaceProxy::mvDockSpaceProxy(mvUUID uuid)
    : mvAppItem(uuid) {}

void mvDockSpaceProxy::draw(ImDrawList*, float, float) {
    if (config.dock_space_id == 0) return;

    // Off-screen, zero-size, fully invisible window
    ImGui::SetNextWindowPos({-9999.f, -9999.f}, ImGuiCond_Always);
    ImGui::SetNextWindowSize({1.f, 1.f},         ImGuiCond_Always);

    constexpr ImGuiWindowFlags kFlags =
        ImGuiWindowFlags_NoDecoration        |
        ImGuiWindowFlags_NoInputs            |
        ImGuiWindowFlags_NoNav               |
        ImGuiWindowFlags_NoMove              |
        ImGuiWindowFlags_NoBackground        |
        ImGuiWindowFlags_NoBringToDisplayFront;

    std::string wnd_id = "##dpg_dsp_" + std::to_string(config.dock_space_id);
    ImGui::Begin(wnd_id.c_str(), nullptr, kFlags);
    ImGui::DockSpace(config.dock_space_id, {0.f, 0.f},
                     ImGuiDockNodeFlags_KeepAliveOnly);
    ImGui::End();
}

void mvDockSpaceProxy::handleSpecificKeywordArgs(PyObject* dict) {
    if (dict == nullptr) return;
    if (PyObject* item = PyDict_GetItemString(dict, "dock_space_id")) {
        config.dock_space_id = (ImGuiID)ToUUID(item);
    }
}

void mvDockSpaceProxy::getSpecificConfiguration(PyObject* dict) {
    if (dict == nullptr) return;
    PyDict_SetItemString(dict, "dock_space_id",
                         PyLong_FromLongLong((long long)config.dock_space_id));
}

void mvDockSpaceProxy::applySpecificTemplate(mvAppItem* item) {
    auto titem = static_cast<mvDockSpaceProxy*>(item);
    config.dock_space_id = titem->config.dock_space_id;
}
```

### 3. Register item type — `src/mvItemTypes.h`

Add to the enum (after `mvDockSpace` if it exists, otherwise near other dock items):

```cpp
mvDockSpaceProxy,
```

### 4. Register Python parser — `src/mvContext.cpp` (or equivalent parser registry)

```cpp
add_parser(
    CreatePythonParser("add_dock_space_proxy", MV_PARSER_STAGE_SETUP,
        "Keeps a dock space node alive when its host window is on an inactive tab. "
        "Place this at the application root (no parent). "
        "Delete it in the host panel's on_close() handler.",
        {
            SectionDoc,
            { "dock_space_id", mvPyDataType::UUID,
              mvArgType::REQUIRED_ARG, "0",
              "Tag of the dpg.add_dock_space() item to keep alive." },
        }),
    mvDockSpaceProxy
);
```

### 5. Expose constant in `__init__.pyi` stub

```python
def add_dock_space_proxy(
    *,
    dock_space_id: int,
    tag: int | str = 0,
    parent: int | str = 0,
    before: int | str = 0,
    show: bool = True,
    user_data: Any = None,
    use_internal_label: bool = True,
) -> int: ...
```

---

## File Change Summary

| File | Change |
|------|--------|
| `src/mvDockSpaceProxy.h` | New — item class + config struct |
| `src/mvDockSpaceProxy.cpp` | New — draw(), parser handlers |
| `src/mvItemTypes.h` | Add `mvDockSpaceProxy` to enum |
| `src/mvContext.cpp` | Register Python parser |
| `dearpygui/dearpygui.pyi` | Add `add_dock_space_proxy` stub |
| `tests/test_dock_proxy.py` | Smoke test (see §Testing below) |

Estimated LOC: ~130 C++ + ~30 Python stub + ~40 test

---

## Testing

```python
# tests/test_dock_proxy.py
import dearpygui.dearpygui as dpg
import pytest

@pytest.mark.skipif(
    not hasattr(dpg, "add_dock_space_proxy"),
    reason="requires custom DPG fork"
)
def test_dock_space_proxy_lifecycle():
    dpg.create_context()
    dpg.create_viewport()
    dpg.setup_dearpygui()

    dock_tag  = dpg.generate_uuid()
    proxy_tag = dpg.generate_uuid()

    with dpg.window():
        with dpg.child_window():
            dpg.add_dock_space(tag=dock_tag)

    dpg.add_dock_space_proxy(dock_space_id=dock_tag, tag=proxy_tag)

    # Proxy must exist at root level
    assert dpg.does_item_exist(proxy_tag)

    # Cleanup
    dpg.delete_item(proxy_tag)
    assert not dpg.does_item_exist(proxy_tag)

    dpg.destroy_context()
```

---

## Integration in DPG-Template-dev

Once the wheel is rebuilt and installed:

1. `DPG_modules/Showcase/panels/docking/__init__.py` — add proxy creation in
   `LocalDockSpacePanel.create()` and `NestedSplitPanel.create()`, delete in `on_close()`.
2. `DPG_modules/Showcase/_window.py` — add proxy for `_SHOWCASE_DOCK_TAG` at the
   showcase window level, delete in `_on_window_close()`.
3. Update `_HAS_DOCK_SPACE` checks to also gate on `hasattr(dpg, "add_dock_space_proxy")`.

---

## Upstream PR Checklist

To submit this work back to `hoffstadt/DearPyGui`:

1. **Add upstream remote** (once only):
   ```bash
   git remote add upstream https://github.com/hoffstadt/DearPyGui.git
   git fetch upstream
   ```

2. **Rebase feature branch on upstream master** to eliminate any divergence:
   ```bash
   git checkout feat/add-dock-space
   git rebase upstream/master
   # resolve any conflicts, then:
   git push origin feat/add-dock-space --force-with-lease
   ```

3. **Open the PR** on GitHub:
   - **From:** `Bl0tto/DearPyGui:feat/add-dock-space`
   - **Into:** `hoffstadt/DearPyGui:master`
   - Title: `feat: add add_dock_space(), mvDockSpaceProxy, and mvDockNodeFlags_* constants`
   - Body: paste the Problem / Solution / File Change Summary sections from this doc

4. **Consider splitting** — upstream maintainers may prefer two PRs:
   - PR 1: `add_dock_space()` + `mvDockNodeFlags_*` constants (phase 1, self-contained)
   - PR 2: `mvDockSpaceProxy` (phase 2, depends on PR 1)

5. **Check** `CONTRIBUTING.md` in the upstream repo for formatting and CLA requirements before opening.

---

## Open Questions

- Does DPG's item-draw order guarantee the proxy window's `draw()` is called every frame
  even when it has no parent? Verify with `mvAppItem::_parentPtr == nullptr` path in
  `mvItemRegistry`. Fallback: parent the proxy to a `dpg.add_texture_registry()` or
  `dpg.add_item_handler_registry()` which always renders.
- ImGui window name must be unique per proxy instance — `"##dpg_dsp_" + dock_space_id`
  is stable and unique as long as dock_space_id is unique (guaranteed by DPG UUID).
