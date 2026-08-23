# DVD Menu Auto-Play Next Title Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow users to choose between returning to the DVD Title Menu or auto-playing the next title in sequence when a title finishes playing.

**Architecture:** Add `MenuEndAction` enum (`menu`, `next`) to domain models, wire it through FastAPI and `JobManager`, update `generate_dvdauthor_xml` to generate sequential PGC jumps with terminal menu calls for `next`, and add an interactive "After Title Finishes" segmented control in the Single-Page Web UI.

**Tech Stack:** Python 3.10+, FastAPI, Vanilla HTML5/CSS3/ES6 JavaScript, dvdauthor, pytest.

---

### Task 1: Domain Models & Authoring Generator

**Files:**
- Modify: `src/dvdcompress/models.py`
- Modify: `src/dvdcompress/__init__.py`
- Modify: `src/dvdcompress/authoring.py`
- Modify: `tests/test_authoring.py`

- [ ] **Step 1: Write failing tests in `tests/test_authoring.py` for `MenuEndAction.PLAY_NEXT` and `MenuEndAction.RETURN_TO_MENU`**
- [ ] **Step 2: Run tests to verify they fail**
- [ ] **Step 3: Implement `MenuEndAction` in `models.py`, export in `__init__.py`, and update `generate_dvdauthor_xml` in `authoring.py`**
- [ ] **Step 4: Run `pytest tests/test_authoring.py` to verify all pass**

---

### Task 2: API & Job Manager Pipeline Integration

**Files:**
- Modify: `src/dvdcompress/api.py`
- Modify: `src/dvdcompress/job_manager.py`
- Modify: `tests/test_api.py`
- Modify: `tests/test_job_manager.py`
- Modify: `tests/test_e2e.py`

- [ ] **Step 1: Write failing tests in `tests/test_api.py` and `tests/test_job_manager.py`**
- [ ] **Step 2: Run tests to verify failure**
- [ ] **Step 3: Update `api.py` request schemas and `job_manager.py` to propagate `menu_end_action`**
- [ ] **Step 4: Run `pytest tests/test_api.py tests/test_job_manager.py tests/test_e2e.py` to verify pass**

---

### Task 3: Web UI Frontend Implementation

**Files:**
- Modify: `src/dvdcompress/static/index.html`
- Modify: `src/dvdcompress/static/js/app.js`
- Modify: `tests/test_ui.py`

- [ ] **Step 1: Write failing UI tests in `tests/test_ui.py` for `#group-menu-end-action` and segment control binding**
- [ ] **Step 2: Run tests to verify failure**
- [ ] **Step 3: Implement HTML layout in `index.html` and controller event handling in `app.js`**
- [ ] **Step 4: Run full test suite (`pytest tests/ -v`) to verify 100% pass**

---
