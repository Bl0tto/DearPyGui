"""
Live demo: mvDockSpaceProxy KeepAlive comparison.

Left window  — dock space with NO proxy:  node gets GC'd when window is hidden.
Right window — dock space WITH proxy:     KeepAliveOnly fires every frame; node survives.

How to run:
    py -3.13 testing/demo_dock_proxy.py

How to test:
    1. Dock "Panel L-*" panels into the LEFT host window's dock zone.
    2. Dock "Panel R-*" panels into the RIGHT host window's dock zone.
    3. Click "Hide Left"  → wait ~1 s → "Show Left":
         LEFT panels will have floated free (dock node was GC'd).
    4. Click "Hide Right" → wait ~1 s → "Show Right":
         RIGHT panels stay docked (proxy kept the node alive).
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

def main() -> None:
    dpg.create_context()
    dpg.configure_app(docking=True, docking_space=False)
    dpg.create_viewport(title="DockSpaceProxy — KeepAlive Demo", width=960, height=640)
    dpg.setup_dearpygui()

    # ── Control bar ──────────────────────────────────────────────────────────
    with dpg.window(label="Controls", tag="ctrl", no_close=True, no_resize=True,
                    no_move=True, no_title_bar=True, width=960, height=80, pos=[0, 0]):
        dpg.add_text(
            "1. Dock Panel L-* into LEFT host, Panel R-* into RIGHT host.\n"
            "2. Hide a host window, wait ~1 s, show it again.\n"
            "   LEFT → panels float free (node GC'd).   RIGHT → panels stay docked (proxy active).",
            wrap=940,
        )
        with dpg.group(horizontal=True):
            dpg.add_button(
                label="Hide Left",
                callback=lambda: dpg.configure_item("left_host", show=False),
            )
            dpg.add_button(
                label="Show Left",
                callback=lambda: dpg.configure_item("left_host", show=True),
            )
            dpg.add_spacer(width=40)
            dpg.add_button(label="Hide Right", callback=_hide_right)
            dpg.add_button(label="Show Right", callback=_show_right)

    # ── Left host — NO proxy ─────────────────────────────────────────────────
    with dpg.window(label="LEFT HOST — No Proxy", tag="left_host",
                    width=450, height=480, pos=[10, 90]):
        left_dock = dpg.add_dock_space()

    # ── Right host — WITH proxy ──────────────────────────────────────────────
    with dpg.window(label="RIGHT HOST — With Proxy", tag="right_host",
                    width=450, height=480, pos=[500, 90]):
        right_dock = dpg.add_dock_space()

    # Proxy at root: always rendered by DPG's root render loop regardless of
    # right_host's visibility.
    dpg.add_dock_space_proxy(right_dock, tag="keepalive_proxy")
    print(f"[PY] setup: right_dock id={right_dock!r}  proxy exists={dpg.does_item_exist('keepalive_proxy')}", flush=True)

    # ── Floating panels the user drags into each host ────────────────────────
    with dpg.window(label="Panel L-1", width=200, height=90, pos=[30, 590]):
        dpg.add_text("Dock me into LEFT host")
        dpg.add_text("No proxy — node will be GC'd")

    with dpg.window(label="Panel L-2", width=200, height=80, pos=[240, 590]):
        dpg.add_text("Dock me into LEFT host too")

    with dpg.window(label="Panel R-1", width=200, height=90, pos=[520, 590]):
        dpg.add_text("Dock me into RIGHT host")
        dpg.add_text("Proxy active — node survives")

    with dpg.window(label="Panel R-2", width=200, height=80, pos=[730, 590]):
        dpg.add_text("Dock me into RIGHT host too")

    dpg.show_viewport()
    dpg.start_dearpygui()
    dpg.destroy_context()


if __name__ == "__main__":
    main()
