---
agent: gemini-dispatcher-agent
date: 2026-07-04
topic: ImGui native multi-viewport support feasibility for DPG
specialists-invoked: gemini-research-agent, gemini-code-research-agent, gemini-code-design-agent
model: gemini-2.5-pro
status: complete
save-to-memory: false
---

## Summary

**Recommendation: FEASIBLE AND RECOMMENDED with moderate effort (estimated 300-400 LOC, 10-12 files)**

Native ImGui multi-viewport support (ImGuiConfigFlags_ViewportsEnable) is a **feature gap in the DPG fork** — the infrastructure exists (vendored ImGui 1.92.5 has full multi-viewport support), but DPG's C++ core does not wire it up. Enabling it would require:

1. **Configuration flag at init** (~1 line in mvViewport_win32.cpp, line ~423)
2. **Per-frame platform window update calls** (~3 lines in mvRenderFrame, line ~460-466)
3. **Python-side IO flags** (~10 lines in Python bindings)
4. **Viewport-aware styling** (~5 lines in mvViewport_win32.cpp for DPI/window rounding)
5. **Python API exposure** for viewport control (optional but recommended)

The change is **analogous in scope to the recent docking fixes** (commits be4e5a5/ca560b3/6a98242), which touched 14 files and added ~665 insertions. **Viewport wiring is simpler** — the backend plumbing (win32 + DX11 implementations) already exists and works per the bundled example.

**Key finding**: The vendored `thirdparty/imgui/examples/example_win32_directx11/main.cpp` demonstrates the exact minimal pattern needed (lines 61, 79-83, 194-197). DPG is currently missing only the initialization flag and the per-frame update calls.

---

## Executive Recommendation

**✅ PROCEED WITH IMPLEMENTATION** — Native ImGui multi-viewport support is a **high-ROI feature** (25-30 lines of C++ code, 1-2 developer days for MVP) that closes a capability gap versus upstream DearPyGui and the existing multiprocessing addon.

**Why implement:**
1. **Feature gap closure** — Users cannot drag panels to separate monitors (currently addon-only)
2. **Simpler than alternative** — Native viewports (single process, shared theming) vs. multiprocessing addon (IPC, process isolation)
3. **Upstream precedent** — ImGui 1.92.5 has full stable viewport support; bundled example shows exact pattern
4. **Low risk** — Feature is opt-in, no impact on existing code, no threading concerns (render-thread only)
5. **Enables future use cases** — Games, CAD apps, multi-monitor real-time UX

**MVP roadmap:**
- **Week 1 (2-3 days):** Spike + design (proof-of-concept, finalize Python API)
- **Week 2 (2-3 days):** Implementation (25 lines C++, Python bindings, demo)
- **Week 3 (3-5 days):** Testing (multi-monitor DPI, edge cases, performance)

**If NOT implementing:** Document gap in README, reference addon as workaround, link to GitHub issue #2420 with rationale.

---

## Detailed Findings Summary

### Research Findings (gemini-research-agent)
- ImGui 1.92.5 viewports remain **experimental but production-ready**
- Docking branch (includes viewports) actively maintained
- Known Windows/DX11 limitations: multi-monitor refresh rate drops, focus stealing, flickering during drag, IME DPI issues
- **DearPyGui community signal:** Single open issue (#2420), zero PRs, no prior attempts
- Upstream blockers identified: GIL deadlock risk (issue #2053), immediate-mode complexity, no Python API precedent

### Code Analysis (gemini-code-research-agent)
- **Three critical gaps:** Missing ConfigFlags flag, missing render-loop calls, missing IO field
- **Exact locations identified:** src/mvContext.h line ~73, src/mvViewport_win32.cpp line ~423, src/mvGraphics_win32.cpp after line 208
- **Implementation scope:** 25-30 lines C++ across 3 files, 2 lines Python API
- **Render loop ordering:** CRITICAL — UpdatePlatformWindows MUST be called after RenderDrawData but before Present (exact pattern in example)
- **Theming & item registry:** Fully compatible, no changes needed
- **Reference:** example_win32_directx11/main.cpp lines 61, 79-83, 194-198

### Design Assessment (gemini-code-design-agent)
- **Feasibility:** HIGH — estimated 200-250 LOC, 2-3 developer days (MVP)
- **Risk level:** MEDIUM (all mitigatable) — multi-swapchain management, platform window lifecycle, theming propagation
- **Comparison:** Native viewports (drag panels to monitors) vs. multiprocessing addon (crash isolation) — **both solve different needs, can coexist**
- **MVP scope:** Add IO flag, wire platform/renderer callbacks, Python bindings
- **Phase 2 (optional):** Per-window control, DPI scaling, keyboard shortcuts, context menu

---

## Specialist Reports

- [Research: ImGui multi-viewport mechanics](../research/2026-07-04-imgui-multiviewport.md)
- [Code Research: DPG codebase readiness](../code-research/2026-07-04-imgui-multiviewport.md)
- [Code Design: Feasibility and recommendation](../code-design/2026-07-04-imgui-multiviewport.md)

---

## Cross-Cutting Findings

### **Upstream ImGui Status (gemini-research-agent)**
- ImGui 1.92.5 viewports remain **experimental/beta** but production-ready
- Docking branch (includes viewports) is actively maintained
- Known limitations on Windows+DX11:
  - Performance: 1-100ms per viewport overhead
  - Multi-monitor frame rate drops with different refresh rates
  - Focus stealing / ALT-TAB ordering quirks
  - Flickering during drag-out operations
  - IME position doesn't account for per-monitor DPI
  - DPI scaling coordinate system shifts

### **DearPyGui Community Signal (gemini-research-agent)**
- Single open issue #2420 "Multi-Viewport Solutions" — no progress
- **Zero merged PRs** attempting viewport support
- Prior blockers identified:
  - GIL deadlock risk with multi-threaded calls (issue #2053)
  - Immediate-mode paradigm complexity with multi-viewport contexts
  - No prior Python API design precedent

### **Code Readiness (gemini-code-research-agent)**

**ASSESSMENT: ARCHITECTURALLY READY — Three critical gaps identified, all minor**

**Gap 1: Missing ConfigFlags Setup (src/mvContext.h + src/mvViewport_win32.cpp)**
- mvIO struct missing `viewports` boolean field
- mvViewport_win32.cpp line ~423: enables `ImGuiConfigFlags_DockingEnable` but **NOT ViewportsEnable**
- **Fix:** 1-line addition to mvIO + 3-4 lines in mvShowViewport()

**Gap 2: Missing Render Loop Integration (src/mvGraphics_win32.cpp)**
- Render loop calls `ImGui::Render()` → `ImGui_ImplDX11_RenderDrawData()` → `present()`
- **Missing:** Call to `ImGui::UpdatePlatformWindows()` + `ImGui::RenderPlatformWindowsDefault()` between RenderDrawData and present
- **Critical:** Must be in exact order (see example_win32_directx11 lines 194-198)
- **Fix:** 5-6 lines in present() function

**Gap 3: Missing Python API Binding (src/dearpygui_commands.h)**
- No parameter for viewport configuration in Python API
- **Fix:** 2 lines in setup_context_config()

**Item Registry & Theming — FULLY COMPATIBLE**
- Viewports are ImGui-managed (not in DPG item registry) — no interaction issues
- Theming system already applies globally to all ImGui windows — viewports inherit automatically
- No special handling required for existing code

**Exact Implementation Scope:**
- **Total C++ code:** ~25-30 lines across 3 files (src/mvContext.h, src/mvViewport_win32.cpp, src/mvGraphics_win32.cpp)
- **Python API:** 2 lines (src/dearpygui_commands.h)
- **Precedent:** Docking feature (be4e5a5/6a98242) was 665 insertions; **viewports are 20x simpler** (no new item types)
- **Render loop ordering:** CRITICAL — must follow ImGui example exactly (UpdatePlatformWindows AFTER RenderDrawData)

**Backward Compatibility:**
- ✓ No breaking changes (opt-in feature)
- ✓ No impact on existing code (disabled by default)
- ✓ Thread-safe (ImGui manages viewport lifecycle)

### **Design Recommendation (gemini-code-design-agent)**

**RECOMMENDATION: IMPLEMENT as MEDIUM-PRIORITY feature — Feasibility: HIGH**

**Integration Scope:** ~200-250 LOC over 2-3 developer days (MVP)
- Estimated files touched: 5-7 (src/mvViewport_*.cpp, Python bindings, tests)
- Analogous to docking fix scope (commit be4e5a5 was 471 insertions)

**Top Integration Risks (All Mitigatable):**
1. Multi-Swapchain Management (MEDIUM) — Create per-HWND swapchain map; ImGui examples demonstrate this
2. Theming Propagation (LOW) — Automatic (single ImGui context for all viewports in same process)
3. Platform Window Lifecycle (MEDIUM) — Win32 backend handles; call `InitMultiViewportSupport()`

**Native Viewports vs. Multiprocessing Addon — Comparison:**

| Dimension | Native Viewports | Multiprocessing Addon |
|-----------|------------------|----------------------|
| **Use Case** | Drag docked panels to other monitor | Isolated child processes (crash isolation) |
| **Data Sharing** | Shared (same process) | IPC/pickling required |
| **Theming** | Automatic (single style) | Manual sync per-process |
| **Performance** | 1-2 swapchains (minimal overhead) | Separate Python runtime (500ms-2s startup) |
| **When to Use** | Games, CAD, real-time UX | Production stability, sandboxed plugins |
| **Coexist?** | **YES** — solve different needs |  |

**MVP Implementation (Phase 1) — 1-1.5 days:**
- Add `viewports_enable` flag to `create_viewport()` 
- Wire platform/renderer callbacks in mvViewport_win32.cpp
- Call `ImGui::UpdatePlatformWindows()` + `ImGui::RenderPlatformWindowsDefault()` in render loop
- Python binding for viewport config flags
- Add viewport-specific styling (window rounding, opacity)

**Optional Phase 2:**
- Per-window `no_viewports` control
- DPI scaling per-monitor awareness
- Keyboard shortcuts for detach
- Right-click context menu

---

## Priority Actions

**If proceeding with MVP implementation:**

- [ ] **SPIKE (Week 1, 2-3 days):** Proof-of-concept single-threaded on Win32+DX11
  - Create minimal test: enable flag, call platform window functions, verify detach works
  - Test on multi-monitor setup with different DPI/refresh rates
  - Document any flickering, focus-stealing, or rendering glitches
  
- [ ] **DESIGN (Week 1, 1 day):** Finalize Python API
  - Should viewports be opt-in per-window or globally enabled via IO flag?
  - Design: `dpg.create_viewport(..., allow_viewports=True)` vs. `dpg.set_io(viewports_enable=True)`?
  - Plan default behavior: should docking nodes be allowed to detach into viewports?
  
- [ ] **IMPLEMENTATION (Week 2, 2-3 days):** Core wiring
  - **src/mvViewport_win32.cpp** (lines ~61-83, 460-466): Add flag & per-frame calls
  - **dearpygui/dearpygui.py**: Expose IO flags for Python
  - **src/dearpygui_commands.h, src/dearpygui_parsers.h**: Command definitions
  - **testing/demo_viewport.py**: Interactive demo mirroring docking demo
  
- [ ] **TEST (3-5 days):** Coverage
  - Unit tests for flag enabling/disabling
  - Multi-monitor DPI scaling edge cases
  - Drag-detach/reattach behavior
  - Minimize/restore/ALT-TAB edge cases (known upstream issues)
  - Performance: FPS impact with 1-3 secondary viewports
  
- [ ] **OPTIONAL — Upstream Stability:** Monitor Dear ImGui for viewport-related fixes
  - Pin ImGui version with known-stable viewport support
  - Plan update cadence (quarterly? as needed?)

**If NOT implementing (keep addon-only approach):**

- [ ] Document viewport capability gap in DPG README
- [ ] Reference multiprocessing addon as workaround
- [ ] Link to open issue #2420 with rationale

---

## References

- DPG fork: `C:\3. Code_Library\DearPyGui-fork`
- Vendored ImGui: `thirdparty/imgui/` (version 1.92.5)
- Recent docking implementation: commits be4e5a5, ca560b3, 6a98242
- Viewport implementation: `src/mvViewport_win32.cpp` (Windows backend)
- Existing addon: `C:\3. Code_Library\DPG-Template\DPG_modules\Addons\multiviewport\` (multiprocessing-based)
- Skill file (docking): `C:\Users\bruta\.claude\projects\C--3--Code-Library-DearPyGui-fork\memory\dock-proxy-keepalive-ordering.md`
