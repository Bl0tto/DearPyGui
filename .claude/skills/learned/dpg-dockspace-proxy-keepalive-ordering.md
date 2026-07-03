---
name: dpg-dockspace-proxy-keepalive-ordering
description: "Gate ImGui KeepAliveOnly arming on host frame-skip; render dock proxy after host, before panels, or docked content vanishes"
user-invocable: false
origin: auto-extracted
---

# DPG DockSpaceProxy: KeepAliveOnly Must Be Frame-Conditional and Render-Order Aware

**Extracted:** 2026-07-03
**Context:** DearPyGui-fork engine work on mvDockSpaceProxy (src/mvContainers.cpp) or any future ImGui dock-node keep-alive mechanism

## Problem
ImGui's `ImGuiDockNode::MergedFlags` is only recomputed once per frame, inside the host
window's `DockNodeUpdate()` (called from `DockSpace()`). Any code that ORs
`ImGuiDockNodeFlags_KeepAliveOnly` into `MergedFlags` *after* that point in the same frame
leaves the flag armed for the rest of the frame. Since DPG renders root items
(`windowRoots`) in creation order, a proxy item created after the host but before the
docked panels will unconditionally re-arm `KeepAliveOnly` even on frames where the host
is fully visible — every downstream panel's `BeginDocked()` then hits the
`KeepAliveOnly` early-return (`imgui.cpp` ~line 21037) with `DockTabIsVisible = false`,
and `Begin()` (~line 8565) hides the window: docked panels show their tab but the
client area is empty (single node) or solid white (split node), even though nothing is
"hidden" from the app's perspective.

## Solution
Only arm `KeepAliveOnly` on frames where the host did NOT submit the dockspace this
frame (`node->LastFrameActive != g.FrameCount`). Leave `MergedFlags` untouched on
frames where the host is active, so `BeginDocked()` reaches its normal
`DockTabIsVisible = true` path.

```cpp
bool hostActive = (node->LastFrameActive == g.FrameCount);

if (!hostActive)
    SetDockNodeKeepAlive(node);       // only arm when host skipped this frame
SetDockNodeWindowsHidden(node, !hostActive);
```

Creation-order contract (required, not just a nicety): create the host window, then
the proxy item, then the docked panel windows. Proxy-before-host means `hostActive`
reads stale data; proxy-after-panels means `LastFrameAlive` isn't bumped before the
panels' `BeginDocked()` runs on the first hidden frame, so they undock instead of
staying docked-but-hidden (`imgui.cpp` ~line 20991).

## When to Use
- Modifying or extending `mvDockSpaceProxy` / `draw_dock_space_proxy` in
  `src/mvContainers.cpp`
- Debugging docked DPG panels that show an empty or white client area only while
  their host window is visible (not while hidden — that's the opposite symptom)
- Writing any new ImGui dock-node keep-alive mechanism: check whether the flag being
  set is `SharedFlags`/`LocalFlags` (safe to set anytime — merged fresh via
  `UpdateMergedFlags()`) vs. `MergedFlags` directly (frame-order-sensitive, only safe
  to set after the point in the frame where recomputation already happened)
