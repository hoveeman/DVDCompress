# Hable Filmic Tone-Mapping Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement automated Hable filmic tone-mapping (`tonemap=hable`) when transcoding HDR10/Dolby Vision/BT.2020 sources to SDR DVD MPEG-2 and Blu-ray AVC.

**Architecture:** Detect HDR metadata in `probe.py` / `models.py`, inject the 32-bit float Hable tone-mapping filter in `transcoder.py`, and orchestrate in `job_manager.py`.

**Tech Stack:** Python 3.10+, FFmpeg, FastAPI, Pytest.

---

### Task 1: HDR Detection in `models.py` & `probe.py`
**Files:**
- Modify: `src/dvdcompress/models.py`
- Modify: `src/dvdcompress/probe.py`
- Test: `tests/test_probe.py`

- [ ] **Step 1: Write failing test in `tests/test_probe.py`**
- [ ] **Step 2: Run pytest to verify failure**
- [ ] **Step 3: Update `models.py` and `probe.py` with `is_hdr` detection**
- [ ] **Step 4: Run pytest to verify pass**
- [ ] **Step 5: Commit Task 1**

---

### Task 2: Hable Filmic Filtergraph in `transcoder.py`
**Files:**
- Modify: `src/dvdcompress/transcoder.py`
- Test: `tests/test_transcoder.py`

- [ ] **Step 1: Write failing test in `tests/test_transcoder.py`**
- [ ] **Step 2: Run pytest to verify failure**
- [ ] **Step 3: Update `build_dvd_transcode_command` and `build_bluray_transcode_command` with `is_hdr` parameter and Hable filter**
- [ ] **Step 4: Run pytest to verify pass**
- [ ] **Step 5: Commit Task 2**

---

### Task 3: Pipeline Integration & End-to-End Tests
**Files:**
- Modify: `src/dvdcompress/job_manager.py`
- Modify: `tests/test_e2e.py`

- [ ] **Step 1: Update `job_manager.py` to forward `is_hdr=info.is_hdr` and log Hable tone-mapping**
- [ ] **Step 2: Add E2E tests for HDR Hable transcoding in `tests/test_e2e.py`**
- [ ] **Step 3: Run full test suite (`pytest tests/ -v`) and verify 100% pass**
- [ ] **Step 4: Commit Task 3 and push to main**
