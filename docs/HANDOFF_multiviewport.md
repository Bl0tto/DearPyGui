# Handoff: Native ImGui Multi-Viewport Support

## Goal

Wire up `ImGuiConfigFlags_ViewportsEnable` so DPG windows can be dragged outside
the main application window and become independent native OS windows (their own
`HWND` + DX11 swapchain), while staying in the same process, same DPG item
registry, and same Python interpreter.

**Hard constraint:** Zero modifications to any file under `thirdparty/imgui/` —
the vendored ImGui (1.92.5) already ships full working platform/renderer
multi-viewport support in `imgui_impl_win32.h`/`imgui_impl_dx11.h`. All changes
are DPG-side wiring only.

**Scope:** Windows (win32 + DX11) only. Linux (`mvViewport_linux.cpp`,
glfw+OpenGL3) and macOS (`mvViewport_apple.mm`, metal — `present()` is
currently an empty stub) have the identical gap and are deferred to a
follow-up branch.

**Not in scope:** the existing `DPG_modules/Addons/multiviewport` addon
(DPG-Template repo). That addon spawns separate OS *processes* with
independent DPG contexts over IPC pipes, for crash isolation. This work is a
different, same-process mechanism and does not touch or replace it.

---

## Root Cause

Same shape as the docking gap fixed on `feat/add-dock-space`
(`ce57eff`/`8e9ac92`/`ca560b3`/`be4e5a5`): the vendored ImGui backend fully
supports the feature, but DPG's C++ core never enabled or drove it.

Specifically, before this branch:
- `mvIO` (`src/mvContext.h`) had no field to hold a viewports-enabled setting.
- `mvShowViewport()` (`src/mvViewport_win32.cpp`) set
  `ImGuiConfigFlags_DockingEnable` but never `ImGuiConfigFlags_ViewportsEnable`.
- `present()` (`src/mvGraphics_win32.cpp`) rendered the main draw data and
  presented the swapchain, but never called `ImGui::UpdatePlatformWindows()` /
  `ImGui::RenderPlatformWindowsDefault()` — the two calls that actually create
  and render the secondary platform windows every frame.

## The Fix

### `src/mvContext.h`

```cpp
bool docking = false;
bool dockingViewport = false;
bool dockingShiftOnly = false;
bool viewports = false;
```

### `src/mvViewport_win32.cpp` — `mvShowViewport()`

```cpp
if(GContext->IO.docking)
    io.ConfigFlags |= ImGuiConfigFlags_DockingEnable;

io.ConfigDockingWithShift = GContext->IO.dockingShiftOnly;

if(GContext->IO.viewports)
    io.ConfigFlags |= ImGuiConfigFlags_ViewportsEnable;
```

### `src/mvGraphics_win32.cpp` — `present()`

```cpp
ImGui_ImplDX11_RenderDrawData(ImGui::GetDrawData());

if (GContext->IO.viewports)
{
    ImGui::UpdatePlatformWindows();
    ImGui::RenderPlatformWindowsDefault();
}

static UINT presentFlags = 0;
```

The ordering — after `RenderDrawData`, before `Present` — matches the vendored
reference at `thirdparty/imgui/examples/example_win32_directx11/main.cpp`
(lines 187-198). Getting this wrong causes a 1-frame lag on secondary
viewports.

### Python API

Mirrors the existing `docking` flag exactly, in `configure_app()` /
`get_app_configuration()` (`src/dearpygui_commands.h`), the parser definition
(`src/dearpygui_parsers.h`), and the `.pyi` stub:

```python
dpg.configure_app(viewports=True)
```

`configure_app` is marked `internal=true` in its parser setup and has no
separate hand-written wrapper in `dearpygui/dearpygui.py` — only the `.pyi`
stub needed updating there.

---

## Testing

- `testing/simple_tests.py::TestViewports` — config roundtrip (`viewports`
  defaults to `False`, round-trips through `configure_app`/
  `get_app_configuration`, independent of `docking`). Kept config-only,
  matching this file's existing headless-testing convention (no test in this
  file calls `show_viewport()`/`start_dearpygui()`, since that opens a real
  window and blocks).
- `testing/demo_dock_proxy.py` — extended with a "Viewport Live Panel"
  containing a per-frame counter. Interactive manual test: dock the panel,
  drag its tab outside the main window (detaches into a native OS window, the
  counter keeps ticking uninterrupted), drag it back to redock. This also
  exercises a new interaction the original dock-space-proxy fix didn't have
  to consider — watch for the same class of "content disappears on
  reattach" bug fixed in `be4e5a5`.
- `testing/simple_tests.py::TestNestedDockSpace` — structural coverage for
  nested dock spaces: a `dpg.add_dock_space()` placed inside a window that is
  itself parented under a different dock space is a fully independent
  `ImGuiDockNode` tree, and `add_dock_space_proxy` can target it directly
  (by id or by tag string).
- `testing/demo_dock_proxy.py` — extended further with a static three-way
  comparison: "Sub-Host L1" (no proxy anywhere), "Sub-Host R-Unprotected"
  (outer `right_dock` proxy only), and "Sub-Host R-Protected" (outer proxy +
  its own nested proxy, created in the correct order). Two findings came out
  of building this:
  1. **An outer dock space's `mvDockSpaceProxy` does not cascade KeepAlive
     protection into an independent nested dock space.** Sub-Host
     R-Unprotected itself stays docked when `right_host` is hidden/shown
     (protected by `keepalive_proxy` on `right_dock`, since it's just a
     window docked in `right_dock`'s tree) — but panels docked *inside* it
     still float free. Each dock-space layer needs its own proxy.
  2. **That second proxy cannot be added as a runtime "turn it on" toggle.**
     A first version of this demo tried exactly that — a button that called
     `add_dock_space_proxy` on click, after the nested dock space's panels
     already existed. It didn't work, which is the ordering contract from
     project memory `dock-proxy-keepalive-ordering` playing out directly:
     DPG renders `windowRoots` in creation order, so a proxy created after
     its panels is positioned after them in that order and arms
     `KeepAliveOnly` too late to protect the first hidden frame. The fix is
     structural, not a runtime toggle: "Sub-Host R-Protected"'s nested proxy
     is created immediately after its `add_dock_space()` call and before its
     panel windows exist, mirroring the mandatory "host → proxy → panels"
     order the outer `keepalive_proxy` already followed.
- `testing/demo_dock_proxy.py` — a `dpg.value_registry()` with a shared
  float (`shared_slider_value`) and int (`shared_ping_count`) demonstrates
  cross-window data pipeline continuity: a slider in "Viewport Live Panel"
  (`source=`-bound) mirrors live into a progress bar in the Controls bar even
  while the panel is detached into its own native OS window, and a "Ping"
  button drives an explicit cross-window counter update via
  `get_value`/`set_value`. Both prove the shared DPG item registry/value
  system spans the detached-viewport boundary with zero IPC — the core
  practical difference from the multiprocessing-based
  `DPG_modules/Addons/multiviewport` addon, where the same data flow would
  require pickling a message across a pipe.

## Known Upstream Limitations

Already researched and documented in
`docs/gemini-reports/dispatch/2026-07-04-imgui-native-multiviewport.md` —
not repeated here in full. Headline items to be aware of when using this
feature: focus-stealing / ALT-TAB ordering quirks on drag-out, minor
flickering during detach, per-monitor DPI and refresh-rate handling
differences across monitors, and the win32 backend's documented gap around
`ImGuiBackendFlags_HasParentViewport` (`viewport->ParentViewportID` is
ignored, so `io.ConfigViewportsNoDefaultParent` has no effect).

## References

- Dispatch report: `docs/gemini-reports/dispatch/2026-07-04-imgui-native-multiviewport.md`
- Docking precedent: commits `ce57eff`, `8e9ac92`, `ca560b3`, `be4e5a5` on `feat/add-dock-space`
- Vendored reference: `thirdparty/imgui/examples/example_win32_directx11/main.cpp`
- Existing process-isolation addon: `DPG_modules/Addons/multiviewport` (DPG-Template repo)
