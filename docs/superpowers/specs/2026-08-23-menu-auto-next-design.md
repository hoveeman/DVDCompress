# DVD Menu: Auto-Play Next Title Configuration Design

**Date:** 2026-08-23  
**Status:** Approved  
**Author:** Antigravity  

## 1. Overview & Goals
When authoring a DVD-Video disc with an interactive Title Menu, users can select whether individual title playback returns immediately to the Title Menu upon completion, or automatically proceeds to the next title in sequence before finally returning to the menu.

This feature adds an **"After Title Finishes"** configuration option in the DVDCompress Web UI when **Title Menu** is active, supporting:
1. **Return to Menu (Default):** Each title returns to the DVD Title Menu when finished.
2. **Play Next Title:** Selecting any title plays that title and continues sequentially through subsequent titles (e.g. Title 1 $\rightarrow$ Title 2 $\rightarrow$ ... $\rightarrow$ Title $N$), returning to the menu after the last title completes.

---

## 2. Technical Architecture & Changes

### 2.1 Domain Models (`src/dvdcompress/models.py`)
```python
class MenuEndAction(str, Enum):
    RETURN_TO_MENU = "menu"
    PLAY_NEXT = "next"
```
- Added `menu_end_action: MenuEndAction = MenuEndAction.RETURN_TO_MENU` to `ProjectConfig` and `Job`.

### 2.2 API Layer (`src/dvdcompress/api.py`)
- Updated `CreateJobRequest`, `StartAuthorBurnRequest`, and `StartSamplePreviewRequest` to accept `menu_end_action: MenuEndAction = MenuEndAction.RETURN_TO_MENU`.
- Job creation propagates `menu_end_action` to `JobManager`.

### 2.3 Web UI (`src/dvdcompress/static/index.html` & `src/dvdcompress/static/js/app.js`)
- **HTML Layout:** Added `#group-menu-end-action` container containing `#control-menu-end-action` segmented control with options `Return to Menu` (`data-value="menu"`) and `Play Next Title` (`data-value="next"`).
- **JavaScript Controller:**
  - Dynamic visibility toggled when switching playback mode between `autoplay` and `menu`.
  - State tracking in `state.config.menu_end_action`.
  - Integration with job history replay/edit flows.

### 2.4 Authoring Generator (`src/dvdcompress/authoring.py`)
- Updated `generate_dvdauthor_xml()`:
  - Accepts `menu_end_action: MenuEndAction = MenuEndAction.RETURN_TO_MENU`.
  - If `menu_mode == MenuMode.MENU` and `menu_end_action == MenuEndAction.PLAY_NEXT`:
    - For title indices $0 \le i < N - 1$: generates `<post>jump pgc {i + 2};</post>`.
    - For final title index $i = N - 1$: generates `<post>call vmgm menu entry title;</post>`.
  - If `menu_mode == MenuMode.MENU` and `menu_end_action == MenuEndAction.RETURN_TO_MENU`:
    - For all title indices $0 \le i < N$: generates `<post>call vmgm menu entry title;</post>`.

### 2.5 Job Pipeline (`src/dvdcompress/job_manager.py`)
- Forwards `job.menu_end_action` to `generate_dvdauthor_xml()`.

---

## 3. Testing & Verification Plan

1. **Unit Tests (`tests/test_authoring.py`):**
   - Test XML post-actions for `menu_end_action=MenuEndAction.RETURN_TO_MENU`.
   - Test XML post-actions for `menu_end_action=MenuEndAction.PLAY_NEXT` verifying title 1 jumps to PGC 2 and title $N$ calls VMGM menu.
2. **API Tests (`tests/test_api.py`):**
   - Verify job creation endpoint accepts `menu_end_action`.
3. **UI Tests (`tests/test_ui.py`):**
   - Verify `#control-menu-end-action` exists in `index.html` and `app.js` handles segment events.
4. **End-to-End Tests (`tests/test_e2e.py`):**
   - Verify full authoring pipeline with `menu_end_action=MenuEndAction.PLAY_NEXT`.
