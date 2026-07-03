"""
Live demo: mvDockSpaceProxy KeepAlive comparison, native multi-viewport
detach/redock, nested/multilayer docking persistence, and cross-window data
pipeline continuity.

Left column  — dock space with NO proxy:  node gets GC'd when window is hidden.
Right column — dock space WITH proxy:     KeepAliveOnly fires every frame; node survives.

How to run:
    py -3.13 testing/demo_dock_proxy.py
    (run from the repo root, or set PYTHONPATH to the repo root — a script run
    directly does NOT put the repo root on sys.path, so a stale globally
    pip-installed dearpygui build can silently shadow this local one)

How to test (dock proxy, single layer):
    1. Dock "Panel L-2" into the LEFT host window's dock zone.
    2. Dock "Panel R-2" into the RIGHT host window's dock zone.
    3. Click "Hide Left"  → wait ~1 s → "Show Left":
         LEFT panels will have floated free (dock node was GC'd).
    4. Click "Hide Right" → wait ~1 s → "Show Right":
         RIGHT panels stay docked (proxy kept the node alive).

How to test (native multi-viewport):
    5. Dock "Viewport Live Panel" into either host's dock zone. Its frame
       counter keeps ticking — this is the same render loop, same DPG context.
    6. Drag the panel's tab fully outside the main app window. It detaches into
       its own native OS window (a real HWND + DX11 swapchain) — the counter
       keeps updating uninterrupted, proving no separate process/context is
       involved (contrast with DPG_modules/Addons/multiviewport, which spawns a
       child process for isolation instead).
    7. Drag the detached window's tab back over a host's dock zone to redock it.
       Watch for the same class of "content disappears" glitch fixed in
       be4e5a5 for the dock-space-proxy — this detach/reattach path is a new
       interaction the original proxy fix didn't have to consider.

How to test (nested/multilayer docking persistence — 3-way static comparison):
    NOTE: this is a static A/B/C comparison, not a live toggle. A proxy MUST
    be created in "host window → proxy → panel windows" order (DPG renders
    windowRoots in creation order) or KeepAliveOnly arms on a stale
    LastFrameActive and the node undocks anyway on the first hidden frame —
    see docs/HANDOFF_dock_proxy.md / project memory
    dock-proxy-keepalive-ordering. A button that adds a proxy at runtime,
    after the panels already exist, CANNOT work — we tried it, confirmed the
    ordering contract the hard way, and removed it.

    8. Dock "Sub-Host L1" into the LEFT host's dock zone, then dock
       "Panel L-1a"/"Panel L-1b" into Sub-Host L1's OWN internal dock zone.
       Hide/Show Left: everything floats free at both layers — no proxy
       anywhere on this side (baseline: fully broken).
    9. Dock "Sub-Host R-Unprotected" into the RIGHT host's dock zone, then
       dock "Panel RU-a"/"Panel RU-b" into its internal dock zone. Hide/Show
       Right: Sub-Host R-Unprotected itself STAYS docked (protected by
       right_dock's proxy, since it's just a window docked in right_dock's
       tree) — but RU-a/RU-b float free inside it. This proves a proxy on an
       OUTER dock space does NOT cascade protection into an INDEPENDENT
       nested dock space.
   10. Dock "Sub-Host R-Protected" into the RIGHT host's dock zone, then dock
       "Panel RP-a"/"Panel RP-b" into its internal dock zone. Hide/Show
       Right: everything stays docked at BOTH layers — this nested dock space
       has its own proxy, created immediately after it (correct order, before
       its panels exist), same contract as the outer proxy.

How to test (cross-window data pipeline):
   11. Drag the "Shared Value" slider in "Viewport Live Panel". The
       "Mirrored Value" progress bar in the Controls bar updates in real
       time — both widgets are bound via `source=` to the same value-registry
       item, no manual sync code required.
   12. Detach "Viewport Live Panel" into its own OS window (step 6) and move
       the slider again. The mirror in Controls still updates instantly,
       proving the shared item registry/value system spans the detached
       viewport boundary with zero IPC (contrast with the multiprocessing
       addon, where this would require pickling a message across a pipe).
   13. Click "Ping" in Viewport Live Panel repeatedly. "Ping count" in
       Controls increments each time — an explicit callback-driven
       cross-window update, same underlying guarantee as the slider mirror.
"""
import dearpygui._dearpygui as _dpg_c
print(f"[PY] _dearpygui loaded from: {getattr(_dpg_c, '__file__', 'unknown')}", flush=True)
import dearpygui.dearpygui as dpg


def _hide_right() -> None:
    print("[PY] Hide Right clicked", flush=True)
    dpg.configure_item("right_host", show=False)

def _show_right() -> None:
    print("[PY] Show Right clicked", flush=True)
    dpg.configure_item("right_host", show=True)

def _ping() -> None:
    dpg.set_value("shared_ping_count", dpg.get_value("shared_ping_count") + 1)

def main() -> None:
    dpg.create_context()
    dpg.configure_app(docking=True, docking_space=False, viewports=True)
    dpg.create_viewport(title="DockSpaceProxy — KeepAlive + Multiviewport Demo", width=1300, height=900)
    dpg.setup_dearpygui()

    # ── Shared cross-window state ────────────────────────────────────────────
    with dpg.value_registry():
        dpg.add_float_value(default_value=0.0, tag="shared_slider_value")
        dpg.add_int_value(default_value=0, tag="shared_ping_count")

    # ── Control bar ──────────────────────────────────────────────────────────
    with dpg.window(label="Controls", tag="ctrl", no_close=True, no_resize=True,
                    no_move=True, no_title_bar=True, width=1280, height=140, pos=[0, 0]):
        dpg.add_text(
            "Dock proxy:   Panel L-2 → LEFT host   |   Panel R-2 → RIGHT host   |   Hide/Show to compare GC vs KeepAlive.\n"
            "Nested test (static A/B/C): Sub-Host L1 (no proxy) vs Sub-Host R-Unprotected (outer proxy only)\n"
            "  vs Sub-Host R-Protected (outer + nested proxy) — see docstring, this can't be toggled live.\n"
            "Data pipeline: drag the slider or click Ping in 'Viewport Live Panel' and watch this bar update.",
            wrap=1260,
        )
        with dpg.group(horizontal=True):
            dpg.add_button(label="Hide Left", callback=lambda: dpg.configure_item("left_host", show=False))
            dpg.add_button(label="Show Left", callback=lambda: dpg.configure_item("left_host", show=True))
            dpg.add_spacer(width=40)
            dpg.add_button(label="Hide Right", callback=_hide_right)
            dpg.add_button(label="Show Right", callback=_show_right)
        with dpg.group(horizontal=True):
            dpg.add_text("Mirrored Value:")
            dpg.add_progress_bar(source="shared_slider_value", label="", width=200)
            dpg.add_spacer(width=40)
            dpg.add_text("Ping count: 0", tag="ping_count_display")

    # ── Left host — NO proxy ─────────────────────────────────────────────────
    with dpg.window(label="LEFT HOST — No Proxy", tag="left_host",
                    width=450, height=440, pos=[10, 150]):
        left_dock = dpg.add_dock_space()

    # ── Right host — WITH proxy ──────────────────────────────────────────────
    with dpg.window(label="RIGHT HOST — With Proxy", tag="right_host",
                    width=450, height=440, pos=[500, 150]):
        right_dock = dpg.add_dock_space()

    # Proxy at root: always rendered by DPG's root render loop regardless of
    # right_host's visibility.
    dpg.add_dock_space_proxy(right_dock, tag="keepalive_proxy")
    print(f"[PY] setup: right_dock id={right_dock!r}  proxy exists={dpg.does_item_exist('keepalive_proxy')}", flush=True)

    # ── Single-layer panels ───────────────────────────────────────────────────
    with dpg.window(label="Panel L-2", width=200, height=80, pos=[10, 610]):
        dpg.add_text("Dock me into LEFT host (single layer)")

    with dpg.window(label="Panel R-2", width=200, height=80, pos=[500, 610]):
        dpg.add_text("Dock me into RIGHT host (single layer)")

    # ── Sub-Host L1 — nested dock space, no proxy anywhere on this side ─────
    with dpg.window(label="Sub-Host L1", tag="sub_host_l1", width=220, height=100, pos=[220, 610]):
        dpg.add_text("Dock me into LEFT host, then dock L-1a/L-1b into me.")
        l1_nested_dock = dpg.add_dock_space(tag="l1_nested_dock")

    with dpg.window(label="Panel L-1a", width=180, height=70, pos=[10, 720]):
        dpg.add_text("Dock me into Sub-Host L1")

    with dpg.window(label="Panel L-1b", width=180, height=70, pos=[220, 720]):
        dpg.add_text("Dock me into Sub-Host L1 too")

    # ── Sub-Host R-Unprotected — outer proxy only, nested layer unprotected ──
    with dpg.window(label="Sub-Host R-Unprotected", tag="sub_host_r_unprotected",
                    width=220, height=100, pos=[500, 720]):
        dpg.add_text("Dock me into RIGHT host, then dock RU-a/RU-b into me.\nI persist, they won't.")
        ru_nested_dock = dpg.add_dock_space(tag="ru_nested_dock")

    with dpg.window(label="Panel RU-a", width=180, height=70, pos=[500, 830]):
        dpg.add_text("Dock me into Sub-Host R-Unprotected")

    with dpg.window(label="Panel RU-b", width=180, height=70, pos=[690, 830]):
        dpg.add_text("Dock me into Sub-Host R-Unprotected too")

    # ── Sub-Host R-Protected — outer AND nested proxy, correct order ─────────
    # Nested proxy is created HERE, immediately after rp_nested_dock and
    # before Panel RP-a/RP-b exist — mandatory "host → proxy → panels"
    # ordering (see module docstring / dock-proxy-keepalive-ordering memory).
    with dpg.window(label="Sub-Host R-Protected", tag="sub_host_r_protected",
                    width=220, height=100, pos=[900, 720]):
        dpg.add_text("Dock me into RIGHT host, then dock RP-a/RP-b into me.\nBoth layers persist.")
        rp_nested_dock = dpg.add_dock_space(tag="rp_nested_dock")

    dpg.add_dock_space_proxy(rp_nested_dock, tag="nested_keepalive_proxy")

    with dpg.window(label="Panel RP-a", width=180, height=70, pos=[900, 830]):
        dpg.add_text("Dock me into Sub-Host R-Protected")

    with dpg.window(label="Panel RP-b", width=180, height=70, pos=[1090, 830]):
        dpg.add_text("Dock me into Sub-Host R-Protected too")

    # ── Viewport live panel — proves data pipeline continuity across detach ──
    with dpg.window(label="Viewport Live Panel", width=300, height=180, pos=[990, 150]):
        dpg.add_text(
            "Dock me, then drag my tab OUTSIDE the app window.\n"
            "I'll become a native OS window and keep ticking.",
            wrap=280,
        )
        dpg.add_text("Frame: 0", tag="viewport_frame_counter")
        dpg.add_slider_float(label="Shared Value", source="shared_slider_value",
                             min_value=0.0, max_value=1.0, width=200)
        dpg.add_button(label="Ping", callback=_ping)

    dpg.show_viewport()
    while dpg.is_dearpygui_running():
        dpg.set_value("viewport_frame_counter", f"Frame: {dpg.get_frame_count()}")
        dpg.set_value("ping_count_display", f"Ping count: {dpg.get_value('shared_ping_count')}")
        dpg.render_dearpygui_frame()
    dpg.destroy_context()


if __name__ == "__main__":
    main()
