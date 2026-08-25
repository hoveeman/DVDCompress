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


def test_job_history_remove_and_clear_ui_elements():
    # 1. HTML Clear History button
    res_html = client.get("/")
    assert res_html.status_code == 200
    assert 'id="btn-clear-history"' in res_html.text

    # 2. JavaScript wiring for row remove and history clear
    res_js = client.get("/js/app.js")
    assert res_js.status_code == 200
    js = res_js.text
    assert "btn-clear-history" in js
    assert "btn-delete-job-row" in js


def test_disc_recommendation_ui_elements():
    # 1. HTML containers
    res_html = client.get("/")
    assert res_html.status_code == 200
    html = res_html.text
    assert 'id="gauge-recommendation-container"' in html
    assert 'id="disc-format-recommendation"' in html
    assert 'id="btn-apply-disc-rec"' in html

    # 2. CSS styles
    res_css = client.get("/css/style.css")
    assert res_css.status_code == 200
    css = res_css.text
    assert ".recommendation-box" in css
    assert ".disc-format-recommendation" in css
    assert ".btn-apply-rec" in css

    # 3. JavaScript logic
    res_js = client.get("/js/app.js")
    assert res_js.status_code == 200
    js = res_js.text
    assert "recommendation_reason" in js
    assert "disc-format-recommendation" in js
    assert "setDiscType" in js


def test_complexity_sampling_ui_elements():
    # 1. HTML button & container
    res_html = client.get("/")
    assert res_html.status_code == 200
    html = res_html.text
    assert 'id="btn-analyze-complexity"' in html
    assert 'id="gauge-complexity-container"' in html

    # 2. CSS styles
    res_css = client.get("/css/style.css")
    assert res_css.status_code == 200
    css = res_css.text
    assert ".complexity-result-box" in css
    assert ".complexity-badge" in css

    # 3. JavaScript wiring
    res_js = client.get("/js/app.js")
    assert res_js.status_code == 200
    js = res_js.text
    assert "btn-analyze-complexity" in js
    assert "runComplexityAnalysis" in js
    assert "/api/analyze-complexity" in js


def test_standalone_iso_format_and_speed_label_ui():
    res_html = client.get("/")
    assert res_html.status_code == 200
    html = res_html.text
    assert 'id="standalone-iso-format-badge"' in html
    assert 'id="metric-speed-label"' in html

    res_js = client.get("/js/app.js")
    assert res_js.status_code == 200
    js = res_js.text
    assert "handleIsoPathChanged" in js
    assert "standalone-iso-format-badge" in js
    assert "metric-speed-label" in js
    assert "Burn Speed" in js


def test_job_history_retry_and_edit_ui():
    res_js = client.get("/js/app.js")
    assert res_js.status_code == 200
    js = res_js.text
    assert "btn-retry-job-row" in js
    assert "btn-edit-job-row" in js
    assert "retryJob" in js
    assert "editJobInAuthoring" in js


def test_job_history_table_responsive_container():
    # Verify index.html wraps jobs-history-table in a responsive scroll container
    res_html = client.get("/")
    assert res_html.status_code == 200
    html = res_html.text
    assert 'class="jobs-table-container"' in html
    assert 'id="jobs-history-table"' in html

    # Verify CSS contains overflow-x scrolling and min-width for table
    res_css = client.get("/css/style.css")
    assert res_css.status_code == 200
    css = res_css.text
    assert ".jobs-table-container" in css
    assert "overflow-x: auto" in css
    assert "-webkit-overflow-scrolling: touch" in css
    assert ".jobs-table" in css


def test_menu_end_action_ui_elements():
    res_html = client.get("/")
    assert res_html.status_code == 200
    html = res_html.text
    assert 'id="group-menu-end-action"' in html
    assert 'id="control-menu-end-action"' in html
    assert 'data-value="menu"' in html
    assert 'data-value="next"' in html
    assert "Return to Menu" in html
    assert "Play Next Title" in html

    res_js = client.get("/js/app.js")
    assert res_js.status_code == 200
    js = res_js.text
    assert "control-menu-end-action" in js
    assert "menu_end_action" in js
    assert "group-menu-end-action" in js


def test_job_history_table_headers_and_pagination_ui():
    res_html = client.get("/")
    assert res_html.status_code == 200
    html = res_html.text
    assert "<th>Duration</th>" in html
    assert "<th>Size</th>" in html
    assert 'id="jobs-pagination-controls"' in html
    assert 'id="jobs-pagination-info"' in html
    assert 'id="jobs-pagination-buttons"' in html

    res_css = client.get("/css/style.css")
    assert res_css.status_code == 200
    css = res_css.text
    assert ".jobs-pagination" in css
    assert ".pagination-btn" in css

    res_js = client.get("/js/app.js")
    assert res_js.status_code == 200
    js = res_js.text
    assert "formatDuration" in js
    assert "formatJobSize" in js
    assert "ITEMS_PER_PAGE = 10" in js
    assert "jobs-pagination-controls" in js
    assert "jobs-pagination-info" in js
    assert "jobs-pagination-buttons" in js














