"""Automated tests for DVDCompress Web UI static assets and endpoints."""

import os
import shutil
import subprocess
import pytest
from fastapi.testclient import TestClient

from dvdcompress.api import app

client = TestClient(app)


def test_index_html_served():
    """Verify that root URL '/' correctly serves the index.html page."""
    res = client.get("/")
    assert res.status_code == 200
    assert "text/html" in res.headers.get("content-type", "")
    html = res.text

    # Title & Metadata
    assert "DVDCompress" in html
    assert "Modern DVD &amp; Blu-ray Authoring" in html or "Modern DVD & Blu-ray Authoring" in html

    # Header & Telemetry
    assert 'id="gpu-telemetry-chip"' in html
    assert 'id="sys-status-chip"' in html

    # Navigation Tabs
    assert 'id="tab-btn-authoring"' in html
    assert 'id="tab-btn-burner"' in html
    assert 'id="tab-btn-jobs"' in html

    # Media Explorer & Playlist
    assert 'id="browser-card"' in html
    assert 'id="browser-table-body"' in html
    assert 'id="playlist-container"' in html
    assert 'id="btn-clear-queue"' in html

    # Capacity Gauge & Bitrate Controls
    assert 'id="gauge-card"' in html
    assert 'id="capacity-bar-video"' in html
    assert 'id="stat-video-bitrate"' in html
    assert 'id="stat-capacity-usage"' in html

    # Disc Configuration
    assert 'id="input-output-name"' in html
    assert 'id="control-disc-type"' in html
    assert 'id="control-tv-standard"' in html
    assert 'id="control-aspect-ratio"' in html
    assert 'id="control-menu-mode"' in html
    assert 'id="select-output-mode"' in html
    assert 'id="toggle-gpu"' in html
    assert 'id="btn-start-project"' in html

    # Standalone ISO Burner Tab
    assert 'id="input-burn-iso-path"' in html
    assert 'id="select-standalone-drive"' in html
    assert 'id="btn-start-burn-iso"' in html

    # Active Pipeline & Terminal
    assert 'id="pipeline-stepper"' in html
    assert 'id="metric-overall-progress"' in html
    assert 'id="terminal-logs"' in html
    assert 'id="btn-cancel-job"' in html
    assert 'id="jobs-history-table"' in html


def test_css_stylesheet_served():
    """Verify that CSS stylesheet is served with proper content-type and tokens."""
    res = client.get("/css/style.css")
    assert res.status_code == 200
    assert "text/css" in res.headers.get("content-type", "")
    css = res.text

    # Design tokens & color system
    assert "--bg-base:" in css
    assert "--bg-surface:" in css
    assert "--accent-primary:" in css
    assert "--color-success:" in css
    assert "--color-danger:" in css

    # Component classes
    assert ".app-header" in css
    assert ".telemetry-chip" in css
    assert ".nav-tab" in css
    assert ".progress-segment" in css
    assert ".pipeline-tracker" in css
    assert ".terminal-window" in css
    assert ".status-pill" in css


def test_javascript_app_served():
    """Verify that JavaScript app bundle is served with proper content-type and logic."""
    res = client.get("/js/app.js")
    assert res.status_code == 200
    assert any(ct in res.headers.get("content-type", "") for ct in ["javascript", "text/plain"])
    js = res.text

    # Key functions & state management
    assert "loadBrowserPath" in js
    assert "addFileToPlaylist" in js
    assert "recalculateBudget" in js
    assert "connectJobWebSocket" in js
    assert "startProject" in js
    assert "startBurnIso" in js
    assert "pollHardwareTelemetry" in js
    assert "/api/files" in js
    assert "/api/calculate" in js
    assert "/api/drives" in js
    assert "/ws/jobs/" in js


def test_preview_modal_and_button_in_html():
    res = client.get("/")
    assert res.status_code == 200
    html = res.text

    assert 'id="btn-preview-project"' in html
    assert 'id="modal-preview"' in html
    assert 'id="btn-confirm-preview"' in html
    assert 'id="preview-type-video"' in html
    assert 'id="preview-type-iso"' in html


def test_javascript_syntax_validity():
    """Verify that app.js is syntactically valid JavaScript."""
    res = client.get("/js/app.js")
    assert res.status_code == 200
    js_code = res.text

    node_bin = shutil.which("node")
    if node_bin:
        proc = subprocess.run(
            [node_bin, "--check", "-"],
            input=js_code,
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 0, f"JavaScript syntax error: {proc.stderr}"


def test_subtitle_ui_elements_in_app_js():
    res = client.get("/js/app.js")
    assert res.status_code == 200
    js = res.text
    assert "sub-track-checkbox" in js
    assert "selected_subtitle_indices" in js
    assert "btn-subs-none" in js
    assert "btn-subs-all" in js
    assert "btn-toggle-all-subs" in js

    res_html = client.get("/")
    assert res_html.status_code == 200
    assert 'id="btn-toggle-all-subs"' in res_html.text


def test_passthrough_ui_elements():
    # 1. HTML Toggle Switch
    res_html = client.get("/")
    assert res_html.status_code == 200
    assert "toggle-passthrough" in res_html.text
    assert "Direct Passthrough" in res_html.text

    # 2. JavaScript Wiring
    res_js = client.get("/js/app.js")
    assert res_js.status_code == 200
    assert "toggle-passthrough" in res_js.text
    assert "passthrough" in res_js.text


def test_slots_stepper_ui_elements():
    # 1. HTML Stepper in Job History
    res_html = client.get("/")
    assert res_html.status_code == 200
    html = res_html.text
    assert "slots-control-container" in html
    assert "btn-slots-decrement" in html
    assert "btn-slots-increment" in html
    assert "slots-value" in html
    assert "Concurrent Slots:" in html

    # 2. CSS Stepper & Badge styles
    res_css = client.get("/css/style.css")
    assert res_css.status_code == 200
    css = res_css.text
    assert ".slots-control-group" in css
    assert ".stepper-widget" in css
    assert ".btn-stepper" in css
    assert ".slots-display" in css
    assert ".status-pill.queued" in css

    # 3. JavaScript Wiring
    res_js = client.get("/js/app.js")
    assert res_js.status_code == 200
    js = res_js.text
    assert "loadSettings" in js
    assert "updateMaxConcurrentJobs" in js
    assert "initSlotsControl" in js
    assert "maxConcurrentJobs" in js
    assert "/api/settings" in js






