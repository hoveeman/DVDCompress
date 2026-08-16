/**
 * DVDCompress Web UI - Modern Client Application
 */

(function () {
  'use strict';

  // Application State
  const state = {
    currentPath: '/media',
    parentPath: null,
    browserFiles: [],
    playlist: [], // Array of probed media objects
    config: {
      output_name: 'DVD_PROJECT',
      disc_type: 'dvd5',
      tv_standard: 'auto',
      aspect_ratio: '16:9',
      menu_mode: 'autoplay',
      output_mode: 'iso_only',
      burner_device: '',
      burn_speed: 4,
      use_gpu: true,
    },
    preview: {
      preview_mode: 'preview_video',
    },
    standaloneBurner: {
      iso_path: '',
      is_bluray: false,
      device_path: '',
      burn_speed: 4,
    },
    drives: [],
    telemetry: null,
    activeJobId: null,
    activeWebSocket: null,
    jobs: [],
    calculatedBudget: null,
    terminalLogs: [],
    autoScroll: true,
  };

  // Helper: Format Seconds to HH:MM:SS
  function formatSeconds(seconds) {
    if (!seconds || isNaN(seconds) || seconds < 0) return '00:00:00';
    const sec = Math.floor(seconds);
    const hrs = Math.floor(sec / 3600);
    const mins = Math.floor((sec % 3600) / 60);
    const s = sec % 60;
    return `${hrs.toString().padStart(2, '0')}:${mins.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
  }

  // Helper: Format Bytes
  function formatBytes(bytes) {
    if (!bytes || bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
  }

  // Helper: Escape HTML
  function escapeHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }

  // Helper: Show Toast Notification
  function showToast(message, type = 'info', duration = 3500) {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    
    let iconSvg = '';
    if (type === 'error') {
      iconSvg = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#ef4444" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><line x1="15" y1="9" x2="9" y2="15"></line><line x1="9" y1="9" x2="15" y2="15"></line></svg>';
    } else if (type === 'success') {
      iconSvg = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#10b981" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><polyline points="9 11 12 14 22 4"></polyline></svg>';
    } else {
      iconSvg = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#3b82f6" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg>';
    }

    toast.innerHTML = `
      ${iconSvg}
      <span style="font-size: 0.85rem; font-weight: 500;">${escapeHtml(message)}</span>
    `;

    container.appendChild(toast);

    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transform = 'translateX(100%)';
      toast.style.transition = 'all 0.3s ease-out';
      setTimeout(() => toast.remove(), 300);
    }, duration);
  }

  // Navigation Tabs Switching
  function initNavTabs() {
    const navButtons = document.querySelectorAll('.nav-tab');
    navButtons.forEach(btn => {
      btn.addEventListener('click', () => {
        const targetViewId = btn.getAttribute('data-target');
        switchTab(targetViewId);
      });
    });
  }

  function switchTab(viewId) {
    document.querySelectorAll('.nav-tab').forEach(b => {
      const isTarget = b.getAttribute('data-target') === viewId;
      b.classList.toggle('active', isTarget);
      b.setAttribute('aria-selected', isTarget ? 'true' : 'false');
    });

    document.querySelectorAll('.tab-view').forEach(view => {
      view.classList.toggle('active', view.id === viewId);
    });

    if (viewId === 'view-jobs') {
      loadJobHistory();
    } else if (viewId === 'view-burner') {
      loadQuickIsoFiles();
    }
  }

  // Segmented Controls
  function initSegmentedControls() {
    // Disc Format
    setupSegmentGroup('control-disc-type', (val) => {
      state.config.disc_type = val;
      const subtitleMap = {
        dvd5: 'Target: DVD-5 (4,300 MB)',
        dvd9: 'Target: DVD-9 (7,850 MB)',
        bd25: 'Target: BD-25 (23,000 MB)',
        bd50: 'Target: BD-50 (46,000 MB)',
        bd66: 'Target: BD-66 UHD (61,500 MB)',
        bd100: 'Target: BDXL BD-100 (92,000 MB)',
        bd128: 'Target: BDXL BD-128 (118,000 MB)',
      };
      const sub = document.getElementById('gauge-subtitle');
      if (sub) sub.textContent = subtitleMap[val] || 'Target Capacity';
      recalculateBudget();
    });

    // TV Standard
    setupSegmentGroup('control-tv-standard', (val) => {
      state.config.tv_standard = val;
    });

    // Aspect Ratio
    setupSegmentGroup('control-aspect-ratio', (val) => {
      state.config.aspect_ratio = val;
    });

    // Playback Mode
    setupSegmentGroup('control-menu-mode', (val) => {
      state.config.menu_mode = val;
    });

    // Standalone Burner Media Type
    setupSegmentGroup('control-burner-media-type', (val) => {
      state.standaloneBurner.is_bluray = (val === 'bluray');
    });

    // Output Mode Select
    const outputModeSelect = document.getElementById('select-output-mode');
    const burnerOptionsGroup = document.getElementById('burner-options-group');
    if (outputModeSelect) {
      outputModeSelect.addEventListener('change', (e) => {
        state.config.output_mode = e.target.value;
        const needsBurner = (e.target.value === 'author_and_burn' || e.target.value === 'burn_direct');
        if (burnerOptionsGroup) {
          burnerOptionsGroup.style.display = needsBurner ? 'block' : 'none';
        }
      });
    }

    // Output Project Name
    const outputNameInput = document.getElementById('input-output-name');
    if (outputNameInput) {
      outputNameInput.addEventListener('input', (e) => {
        state.config.output_name = e.target.value.trim() || 'DVD_PROJECT';
      });
    }

    // Burn Speed
    const burnSpeedSelect = document.getElementById('select-burn-speed');
    if (burnSpeedSelect) {
      burnSpeedSelect.addEventListener('change', (e) => {
        state.config.burn_speed = parseInt(e.target.value, 10) || 4;
      });
    }

    // Burner Device Select
    const burnerDeviceSelect = document.getElementById('select-burner-device');
    if (burnerDeviceSelect) {
      burnerDeviceSelect.addEventListener('change', (e) => {
        state.config.burner_device = e.target.value;
      });
    }

    // Hardware Acceleration Toggle
    const gpuToggle = document.getElementById('toggle-gpu');
    if (gpuToggle) {
      gpuToggle.addEventListener('change', (e) => {
        state.config.use_gpu = e.target.checked;
        const desc = document.getElementById('gpu-toggle-desc');
        if (desc) {
          desc.textContent = e.target.checked ? 'NVIDIA NVENC / CUDA' : 'CPU (libx264 / libavcodec)';
        }
      });
    }

    // Drive Rescan Button
    const btnRescan = document.getElementById('btn-rescan-drives');
    if (btnRescan) {
      btnRescan.addEventListener('click', () => loadDrives(true));
    }

    // Start Project Button
    const btnStart = document.getElementById('btn-start-project');
    if (btnStart) {
      btnStart.addEventListener('click', startProject);
    }

    // Preview Project Button & Modal
    const btnPreview = document.getElementById('btn-preview-project');
    if (btnPreview) {
      btnPreview.addEventListener('click', openPreviewModal);
    }

    const btnClosePreview = document.getElementById('btn-close-preview-modal');
    if (btnClosePreview) {
      btnClosePreview.addEventListener('click', closePreviewModal);
    }

    const btnCancelPreview = document.getElementById('btn-cancel-preview-modal');
    if (btnCancelPreview) {
      btnCancelPreview.addEventListener('click', closePreviewModal);
    }

    const btnConfirmPreview = document.getElementById('btn-confirm-preview');
    if (btnConfirmPreview) {
      btnConfirmPreview.addEventListener('click', startPreviewProject);
    }

    const selectPreviewTitle = document.getElementById('select-preview-title');
    if (selectPreviewTitle) {
      selectPreviewTitle.addEventListener('change', updatePreviewInfoSummary);
    }

    setupSegmentGroup('control-preview-type', (val) => {
      state.preview.preview_mode = val;
      updatePreviewInfoSummary();
    });

    // Standalone Burn ISO Button
    const btnBurnIso = document.getElementById('btn-start-burn-iso');
    if (btnBurnIso) {
      btnBurnIso.addEventListener('click', startBurnIso);
    }

    // Cancel Job Button
    const btnCancel = document.getElementById('btn-cancel-job');
    if (btnCancel) {
      btnCancel.addEventListener('click', cancelActiveJob);
    }

    // Pause / Resume Job Button
    const btnPause = document.getElementById('btn-pause-job');
    if (btnPause) {
      btnPause.addEventListener('click', togglePauseActiveJob);
    }

    // Clear Logs Button
    const btnClearLogs = document.getElementById('btn-clear-logs');
    if (btnClearLogs) {
      btnClearLogs.addEventListener('click', () => {
        const term = document.getElementById('terminal-logs');
        if (term) term.innerHTML = '';
      });
    }

    // Copy Logs Button
    const btnCopyLogs = document.getElementById('btn-copy-logs');
    if (btnCopyLogs) {
      btnCopyLogs.addEventListener('click', () => {
        const term = document.getElementById('terminal-logs');
        if (term) {
          navigator.clipboard.writeText(term.innerText).then(() => {
            showToast('Logs copied to clipboard', 'success');
          }).catch(() => {
            showToast('Failed to copy logs', 'error');
          });
        }
      });
    }

    // Autoscroll Checkbox
    const chkAuto = document.getElementById('chk-autoscroll');
    if (chkAuto) {
      chkAuto.addEventListener('change', (e) => {
        state.autoScroll = e.target.checked;
      });
    }

    // Refresh Jobs Button
    const btnRefreshJobs = document.getElementById('btn-refresh-jobs');
    if (btnRefreshJobs) {
      btnRefreshJobs.addEventListener('click', loadJobHistory);
    }
  }

  function setupSegmentGroup(containerId, onChange) {
    const container = document.getElementById(containerId);
    if (!container) return;

    container.addEventListener('click', (e) => {
      const target = e.target.closest('.segmented-option');
      if (!target) return;

      container.querySelectorAll('.segmented-option').forEach(opt => opt.classList.remove('active'));
      target.classList.add('active');
      const val = target.getAttribute('data-value');
      if (onChange) onChange(val);
    });
  }

  // File Browser Implementation
  async function loadBrowserPath(targetPath) {
    const pathBar = document.getElementById('browser-path-bar');
    const tbody = document.getElementById('browser-table-body');
    if (!tbody) return;

    tbody.innerHTML = '<tr><td colspan="3" style="text-align: center; color: var(--text-tertiary); padding: 1rem;"><div class="spinner"></div> Loading files...</td></tr>';

    try {
      const res = await fetch(`/api/files?path=${encodeURIComponent(targetPath || '')}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();

      state.currentPath = data.current_path;
      state.parentPath = data.parent_path;

      // Update Path Bar Breadcrumbs
      if (pathBar) {
        pathBar.innerHTML = '';
        const parts = data.current_path.split('/').filter(Boolean);
        
        const rootSpan = document.createElement('span');
        rootSpan.className = 'path-segment';
        rootSpan.textContent = '/';
        rootSpan.addEventListener('click', () => loadBrowserPath('/'));
        pathBar.appendChild(rootSpan);

        let accumulated = '';
        parts.forEach((p, idx) => {
          accumulated += '/' + p;
          const currentAcc = accumulated;
          
          const sep = document.createElement('span');
          sep.className = 'path-separator';
          sep.textContent = '/';
          pathBar.appendChild(sep);

          const seg = document.createElement('span');
          seg.className = 'path-segment';
          seg.textContent = p;
          seg.addEventListener('click', () => loadBrowserPath(currentAcc));
          pathBar.appendChild(seg);
        });
      }

      // Render Rows
      tbody.innerHTML = '';

      if (data.directories.length === 0 && data.files.length === 0) {
        tbody.innerHTML = '<tr><td colspan="3" style="text-align: center; color: var(--text-tertiary); padding: 1.5rem;">No media or ISO files found in this folder.</td></tr>';
        return;
      }

      // Render Subdirectories
      data.directories.forEach(dir => {
        const tr = document.createElement('tr');
        tr.className = 'file-row';
        tr.innerHTML = `
          <td>
            <div class="file-item-name">
              <svg class="file-icon folder" viewBox="0 0 24 24" fill="currentColor">
                <path d="M10 4H4c-1.1 0-1.99.9-1.99 2L2 18c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V8c0-1.1-.9-2-2-2h-8l-2-2z"/>
              </svg>
              <span>${escapeHtml(dir.name)}</span>
            </div>
          </td>
          <td style="color: var(--text-tertiary); font-size: 0.75rem;">DIR</td>
          <td style="text-align: right;">
            <button class="btn btn-secondary btn-sm" style="padding: 2px 8px;">Open</button>
          </td>
        `;
        tr.addEventListener('click', () => loadBrowserPath(dir.path));
        tbody.appendChild(tr);
      });

      // Render Files
      data.files.forEach(file => {
        const tr = document.createElement('tr');
        tr.className = 'file-row';
        
        let iconClass = 'video';
        let badge = '<span class="badge badge-video">VIDEO</span>';
        if (file.is_iso) {
          iconClass = 'iso';
          badge = '<span class="badge badge-iso">ISO</span>';
        }

        tr.innerHTML = `
          <td>
            <div class="file-item-name">
              <svg class="file-icon ${iconClass}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                ${file.is_iso 
                  ? '<circle cx="12" cy="12" r="10"></circle><circle cx="12" cy="12" r="3"></circle>' 
                  : '<polygon points="23 7 16 12 23 17 23 7"></polygon><rect x="1" y="5" width="15" height="14" rx="2" ry="2"></rect>'}
              </svg>
              <span title="${escapeHtml(file.path)}">${escapeHtml(file.name)}</span>
              ${badge}
            </div>
          </td>
          <td style="font-family: var(--font-mono); font-size: 0.75rem; color: var(--text-secondary);">${formatBytes(file.size_bytes)}</td>
          <td style="text-align: right;">
            ${file.is_video ? `
              <button class="btn btn-primary btn-sm btn-add-video" title="Add to Project">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"></line><line x1="5" y1="12" x2="19" y2="12"></line></svg>
                Add
              </button>
            ` : `
              <button class="btn btn-secondary btn-sm btn-select-iso" title="Burn ISO">Burn</button>
            `}
          </td>
        `;

        if (file.is_video) {
          const addBtn = tr.querySelector('.btn-add-video');
          if (addBtn) {
            addBtn.addEventListener('click', (e) => {
              e.stopPropagation();
              addFileToPlaylist(file.path);
            });
          }
        } else if (file.is_iso) {
          const isoBtn = tr.querySelector('.btn-select-iso');
          if (isoBtn) {
            isoBtn.addEventListener('click', (e) => {
              e.stopPropagation();
              const isoInput = document.getElementById('input-burn-iso-path');
              if (isoInput) isoInput.value = file.path;
              switchTab('view-burner');
            });
          }
        }

        tbody.appendChild(tr);
      });

    } catch (err) {
      tbody.innerHTML = `<tr><td colspan="3" style="text-align: center; color: var(--color-danger); padding: 1rem;">Failed to load files: ${escapeHtml(err.message)}</td></tr>`;
      showToast(`Error browsing path: ${err.message}`, 'error');
    }
  }

  function initBrowserControls() {
    const btnMedia = document.getElementById('btn-path-media');
    if (btnMedia) btnMedia.addEventListener('click', () => loadBrowserPath('/media'));

    const btnOutput = document.getElementById('btn-path-output');
    if (btnOutput) btnOutput.addEventListener('click', () => loadBrowserPath('/output'));

    const btnParent = document.getElementById('btn-browser-parent');
    if (btnParent) {
      btnParent.addEventListener('click', () => {
        if (state.parentPath) {
          loadBrowserPath(state.parentPath);
        } else {
          loadBrowserPath('/media');
        }
      });
    }

    const btnRefresh = document.getElementById('btn-browser-refresh');
    if (btnRefresh) btnRefresh.addEventListener('click', () => loadBrowserPath(state.currentPath));
  }

  // Probing & Playlist Management
  async function addFileToPlaylist(filePath) {
    // Check if already in playlist
    if (state.playlist.some(item => item.path === filePath)) {
      showToast('File is already in the project playlist', 'info');
      return;
    }

    showToast(`Probing ${filePath.split('/').pop()}...`, 'info', 2000);

    try {
      const res = await fetch('/api/probe', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ file_path: filePath }),
      });

      if (!res.ok) {
        const errorData = await res.json().catch(() => ({}));
        throw new Error(errorData.detail || `HTTP ${res.status}`);
      }

      const mediaInfo = await res.json();
      mediaInfo._expanded = false;
      state.playlist.push(mediaInfo);
      
      renderPlaylist();
      recalculateBudget();
      showToast(`Added: ${mediaInfo.filename}`, 'success');
    } catch (err) {
      showToast(`Failed to probe video: ${err.message}`, 'error');
    }
  }

  function removePlaylistItem(index) {
    state.playlist.splice(index, 1);
    renderPlaylist();
    recalculateBudget();
  }

  function movePlaylistItem(fromIndex, toIndex) {
    if (toIndex < 0 || toIndex >= state.playlist.length) return;
    const item = state.playlist.splice(fromIndex, 1)[0];
    state.playlist.splice(toIndex, 0, item);
    renderPlaylist();
    recalculateBudget();
  }

  function renderPlaylist() {
    const container = document.getElementById('playlist-container');
    const emptyState = document.getElementById('playlist-empty');
    const countBadge = document.getElementById('queue-count-badge');
    const durText = document.getElementById('queue-duration-text');
    const sizeText = document.getElementById('queue-size-text');

    if (!container || !emptyState) return;

    if (state.playlist.length === 0) {
      container.innerHTML = '';
      emptyState.style.display = 'flex';
      if (countBadge) countBadge.textContent = '0 Titles';
      if (durText) durText.textContent = '00:00:00';
      if (sizeText) sizeText.textContent = '0 MB';
      return;
    }

    emptyState.style.display = 'none';
    container.innerHTML = '';

    let totalDuration = 0;
    let totalSizeBytes = 0;

    state.playlist.forEach((item, idx) => {
      totalDuration += item.duration_sec || 0;
      totalSizeBytes += item.size_bytes || 0;

      const itemCard = document.createElement('div');
      itemCard.className = 'playlist-item';

      const audioSummary = (item.audio_streams || []).map(a => `${a.codec_name} (${a.channel_layout || a.channels + 'ch'})`).join(', ') || 'None';
      const subCount = (item.subtitle_streams || []).length;

      itemCard.innerHTML = `
        <div class="item-main-row">
          <div class="item-info">
            <span class="item-index">#${idx + 1}</span>
            <div class="item-title-meta">
              <span class="item-filename" title="${escapeHtml(item.path)}">${escapeHtml(item.filename)}</span>
              <div class="item-meta-tags">
                <span class="badge badge-stream">${formatSeconds(item.duration_sec)}</span>
                <span class="badge badge-stream">${item.width}x${item.height}</span>
                <span class="badge badge-stream">${item.frame_rate ? item.frame_rate.toFixed(2) + ' fps' : 'Auto fps'}</span>
                <span class="badge badge-stream">${(item.video_codec || 'video').toUpperCase()}</span>
                <span class="badge badge-stream">${formatBytes(item.size_bytes)}</span>
              </div>
            </div>
          </div>
          <div class="item-controls">
            <button class="btn btn-secondary btn-icon-only btn-item-up" title="Move Up" ${idx === 0 ? 'disabled' : ''}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="18 15 12 9 6 15"></polyline></svg>
            </button>
            <button class="btn btn-secondary btn-icon-only btn-item-down" title="Move Down" ${idx === state.playlist.length - 1 ? 'disabled' : ''}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"></polyline></svg>
            </button>
            <button class="btn btn-secondary btn-icon-only btn-item-inspect" title="Inspect Audio &amp; Subtitle Tracks">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg>
            </button>
            <button class="btn btn-danger btn-icon-only btn-item-remove" title="Remove">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
            </button>
          </div>
        </div>

        ${item._expanded ? `
          <div class="stream-inspector-content">
            <div class="stream-group-title">Audio Streams (${(item.audio_streams || []).length})</div>
            ${(item.audio_streams || []).map(a => `
              <div class="stream-item">
                <span class="stream-name">#${a.index}: ${a.codec_name.toUpperCase()} (${a.channel_layout || a.channels + 'ch'}) [${a.language || 'und'}]</span>
                <span class="stream-meta">${a.title || 'Track ' + a.index} ${a.bitrate ? '• ' + Math.round(a.bitrate / 1000) + ' kbps' : ''}</span>
              </div>
            `).join('')}
            
            <div class="stream-group-title" style="margin-top: 4px;">Subtitle Streams (${subCount})</div>
            ${subCount > 0 ? (item.subtitle_streams || []).map(s => `
              <div class="stream-item" style="display: flex; align-items: center; justify-content: space-between;">
                <label style="display: flex; align-items: center; gap: 8px; cursor: pointer; user-select: none; margin: 0;">
                  <input type="checkbox" class="sub-track-checkbox" data-track-index="${s.index}" ${s._excluded ? '' : 'checked'} style="cursor: pointer;" />
                  <span class="stream-name">#${s.index}: ${s.codec_name.toUpperCase()} [${(s.language || 'und').toUpperCase()}]</span>
                </label>
                <span class="stream-meta">${escapeHtml(s.title || 'Subtitle ' + s.index)}${s.is_forced ? ' • Forced' : ''}${s.is_default ? ' • Default' : ''}</span>
              </div>
            `).join('') : '<div style="color: var(--text-tertiary);">No subtitle tracks found.</div>'}
          </div>
        ` : ''}
      `;

      // Event listeners
      itemCard.querySelector('.btn-item-up')?.addEventListener('click', () => movePlaylistItem(idx, idx - 1));
      itemCard.querySelector('.btn-item-down')?.addEventListener('click', () => movePlaylistItem(idx, idx + 1));
      itemCard.querySelector('.btn-item-inspect')?.addEventListener('click', () => {
        item._expanded = !item._expanded;
        renderPlaylist();
      });
      itemCard.querySelector('.btn-item-remove')?.addEventListener('click', () => removePlaylistItem(idx));

      // Subtitle track selection listeners
      itemCard.querySelectorAll('.sub-track-checkbox').forEach(cb => {
        cb.addEventListener('change', (e) => {
          const trackIdx = parseInt(e.target.dataset.trackIndex, 10);
          const subStream = (item.subtitle_streams || []).find(s => s.index === trackIdx);
          if (subStream) {
            subStream._excluded = !e.target.checked;
          }
        });
      });

      container.appendChild(itemCard);
    });

    if (countBadge) countBadge.textContent = `${state.playlist.length} Title${state.playlist.length === 1 ? '' : 's'}`;
    if (durText) durText.textContent = formatSeconds(totalDuration);
    if (sizeText) sizeText.textContent = formatBytes(totalSizeBytes);
  }

  function initPlaylistControls() {
    const btnClear = document.getElementById('btn-clear-queue');
    if (btnClear) {
      btnClear.addEventListener('click', () => {
        if (state.playlist.length === 0) return;
        state.playlist = [];
        renderPlaylist();
        recalculateBudget();
        showToast('Playlist cleared', 'info');
      });
    }
  }

  // Bitrate Budget & Capacity Gauge Calculation
  async function recalculateBudget() {
    const percentText = document.getElementById('gauge-percent-text');
    const barVideo = document.getElementById('capacity-bar-video');
    const barAudio = document.getElementById('capacity-bar-audio');
    const barOverhead = document.getElementById('capacity-bar-overhead');
    const barOverflow = document.getElementById('capacity-bar-overflow');
    const statVideo = document.getElementById('stat-video-bitrate');
    const statAudio = document.getElementById('stat-audio-bitrate');
    const statOverhead = document.getElementById('stat-mux-overhead');
    const statUsage = document.getElementById('stat-capacity-usage');
    const warningsContainer = document.getElementById('gauge-warnings-container');
    const btnStart = document.getElementById('btn-start-project');
    const btnPreview = document.getElementById('btn-preview-project');

    if (state.playlist.length === 0) {
      if (percentText) percentText.textContent = '0.0%';
      if (barVideo) barVideo.style.width = '0%';
      if (barAudio) barAudio.style.width = '0%';
      if (barOverhead) barOverhead.style.width = '0%';
      if (barOverflow) barOverflow.style.width = '0%';
      if (statVideo) statVideo.textContent = '0 kbps';
      if (statAudio) statAudio.textContent = '192 kbps';
      if (statOverhead) statOverhead.textContent = '0 kbps';
      if (statUsage) statUsage.textContent = '0 / 4,480 MB';
      if (warningsContainer) warningsContainer.innerHTML = '';
      if (btnStart) btnStart.disabled = true;
      if (btnPreview) btnPreview.disabled = true;
      return;
    }

    const totalDuration = state.playlist.reduce((acc, item) => acc + (item.duration_sec || 0), 0);
    
    // Collect all audio tracks bitrates or fallback to 192 kbps
    const audioTracks = [];
    state.playlist.forEach(item => {
      if (item.audio_streams && item.audio_streams.length > 0) {
        item.audio_streams.forEach(a => audioTracks.push(a.bitrate ? Math.round(a.bitrate / 1000) : 192));
      } else {
        audioTracks.push(192);
      }
    });

    try {
      const res = await fetch('/api/calculate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          total_duration_sec: totalDuration,
          disc_type: state.config.disc_type,
          audio_tracks_kbps: audioTracks.length > 0 ? audioTracks : [192],
          video_count: state.playlist.length,
        }),
      });

      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const budget = await res.json();
      state.calculatedBudget = budget;

      // Update Gauge Text & Color
      const capPct = budget.capacity_percent;
      if (percentText) {
        percentText.textContent = `${capPct.toFixed(1)}%`;
        percentText.className = 'gauge-percent' + (capPct > 100 ? ' danger' : capPct > 90 ? ' warning' : '');
      }

      // Calculate bar segments
      const targetMB = budget.target_capacity_mb || 4480;
      const videoMB = (budget.video_bitrate_kbps * totalDuration) / (8 * 1024);
      const audioMB = (budget.audio_bitrate_kbps * totalDuration) / (8 * 1024);
      const muxMB = (budget.mux_overhead_kbps * totalDuration) / (8 * 1024);

      const videoPct = Math.min(100, (videoMB / targetMB) * 100);
      const audioPct = Math.min(100, (audioMB / targetMB) * 100);
      const muxPct = Math.min(100, (muxMB / targetMB) * 100);
      const overflowPct = capPct > 100 ? Math.min(100, capPct - 100) : 0;

      if (barVideo) barVideo.style.width = `${videoPct}%`;
      if (barAudio) barAudio.style.width = `${audioPct}%`;
      if (barOverhead) barOverhead.style.width = `${muxPct}%`;
      if (barOverflow) barOverflow.style.width = `${overflowPct}%`;

      // Stats
      if (statVideo) statVideo.textContent = `${budget.video_bitrate_kbps.toLocaleString()} kbps`;
      if (statAudio) statAudio.textContent = `${budget.audio_bitrate_kbps.toLocaleString()} kbps`;
      if (statOverhead) statOverhead.textContent = `${budget.mux_overhead_kbps.toLocaleString()} kbps`;
      if (statUsage) statUsage.textContent = `${Math.round(budget.used_capacity_mb).toLocaleString()} / ${Math.round(targetMB).toLocaleString()} MB`;

      // Warnings
      if (warningsContainer) {
        warningsContainer.innerHTML = '';
        if (budget.warnings && budget.warnings.length > 0) {
          budget.warnings.forEach(warn => {
            const warnBox = document.createElement('div');
            warnBox.className = `warning-box ${!budget.fits_disc ? 'danger' : ''}`;
            warnBox.innerHTML = `
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path>
                <line x1="12" y1="9" x2="12" y2="13"></line>
                <line x1="12" y1="17" x2="12.01" y2="17"></line>
              </svg>
              <span>${escapeHtml(warn)}</span>
            `;
            warningsContainer.appendChild(warnBox);
          });
        }
      }

      // Enable start project & preview buttons
      if (btnStart) {
        btnStart.disabled = !budget.fits_disc && capPct > 105;
      }
      if (btnPreview) {
        btnPreview.disabled = state.playlist.length === 0;
      }

    } catch (err) {
      console.error('Calculation error:', err);
    }
  }

  // Optical Drives & System Telemetry
  async function loadDrives(forceToast = false) {
    try {
      const res = await fetch('/api/drives');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const drives = await res.json();
      state.drives = drives;

      const driveSelects = [
        document.getElementById('select-burner-device'),
        document.getElementById('select-standalone-drive'),
      ];

      driveSelects.forEach(select => {
        if (!select) return;
        select.innerHTML = '';
        if (drives.length === 0) {
          select.innerHTML = '<option value="">No optical drives found (/dev/sr*)</option>';
        } else {
          drives.forEach(d => {
            const opt = document.createElement('option');
            opt.value = d.device_path;
            opt.textContent = `${d.device_path} - ${d.model || 'Optical Burner'} (${d.vendor || 'Generic'})`;
            select.appendChild(opt);
          });
          if (!state.config.burner_device && drives[0]) {
            state.config.burner_device = drives[0].device_path;
          }
          if (!state.standaloneBurner.device_path && drives[0]) {
            state.standaloneBurner.device_path = drives[0].device_path;
          }
        }
      });

      if (forceToast) {
        showToast(`Detected ${drives.length} optical drive(s)`, 'success');
      }
    } catch (err) {
      console.error('Drive scan failed:', err);
    }
  }

  async function pollHardwareTelemetry() {
    try {
      const res = await fetch('/api/system');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      state.telemetry = data;

      const cpuStatus = document.getElementById('telemetry-cpu-status');
      const ramStatus = document.getElementById('telemetry-ram-status');
      const gpuStatus = document.getElementById('telemetry-gpu-status');
      const sysDot = document.getElementById('system-status-dot');

      if (cpuStatus && data.cpu_percent !== undefined) {
        cpuStatus.textContent = `${data.cpu_percent}%`;
      }

      if (ramStatus && data.ram_used_gb !== undefined && data.ram_total_gb !== undefined) {
        ramStatus.textContent = `${data.ram_used_gb}/${data.ram_total_gb}GB (${data.ram_percent}%)`;
      }

      if (gpuStatus) {
        if (data.gpu_available) {
          const usedGB = (data.gpu_memory_used_mb / 1024).toFixed(1);
          const totalGB = (data.gpu_memory_total_mb / 1024).toFixed(1);
          gpuStatus.textContent = `${data.gpu_utilization_percent}% • ${usedGB}/${totalGB}GB • ${data.gpu_temp_c}°C`;
        } else {
          gpuStatus.textContent = 'CPU Mode (No GPU)';
        }
      }

      if (sysDot) sysDot.className = 'status-dot';
    } catch (err) {
      const sysDot = document.getElementById('system-status-dot');
      if (sysDot) sysDot.className = 'status-dot danger';
    }
  }

  // Quick select ISOs in /output
  async function loadQuickIsoFiles() {
    const list = document.getElementById('iso-quick-list');
    if (!list) return;

    try {
      const res = await fetch('/api/files?path=/output');
      if (!res.ok) return;
      const data = await res.json();
      const isoFiles = (data.files || []).filter(f => f.is_iso);

      list.innerHTML = '';
      if (isoFiles.length === 0) {
        list.innerHTML = '<div style="font-size: 0.75rem; color: var(--text-tertiary);">No ISO files found in /output</div>';
        return;
      }

      isoFiles.forEach(file => {
        const item = document.createElement('div');
        item.style.cssText = 'display: flex; align-items: center; justify-content: space-between; background: var(--bg-input); border: 1px solid var(--border-subtle); padding: 4px 8px; border-radius: 4px; font-size: 0.8rem; cursor: pointer;';
        item.innerHTML = `
          <span style="font-family: var(--font-mono);">${escapeHtml(file.name)}</span>
          <span style="color: var(--text-tertiary); font-size: 0.75rem;">${formatBytes(file.size_bytes)}</span>
        `;
        item.addEventListener('click', () => {
          const input = document.getElementById('input-burn-iso-path');
          if (input) input.value = file.path;
        });
        list.appendChild(item);
      });
    } catch (err) {
      console.error(err);
    }
  }

  // Project Creation & Pipeline Monitoring
  async function startProject() {
    if (state.playlist.length === 0) {
      showToast('Please add at least one video to the project playlist', 'error');
      return;
    }

    const selectedSubtitleIndices = [];
    state.playlist.forEach(item => {
      (item.subtitle_streams || []).forEach(s => {
        if (!s._excluded) {
          selectedSubtitleIndices.push(s.index);
        }
      });
    });

    const payload = {
      input_files: state.playlist.map(item => item.path),
      disc_type: state.config.disc_type,
      output_mode: state.config.output_mode,
      output_name: state.config.output_name || 'DVD_PROJECT',
      tv_standard: state.config.tv_standard,
      aspect_ratio: state.config.aspect_ratio,
      menu_mode: state.config.menu_mode,
      burner_device: state.config.burner_device || null,
      burn_speed: state.config.burn_speed || 4,
      use_gpu: state.config.use_gpu,
      selected_subtitle_indices: selectedSubtitleIndices,
    };

    const btnStart = document.getElementById('btn-start-project');
    if (btnStart) btnStart.disabled = true;

    try {
      const res = await fetch('/api/jobs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const errorData = await res.json().catch(() => ({}));
        throw new Error(errorData.detail || `HTTP ${res.status}`);
      }

      const data = await res.json();
      showToast(`Job ${data.job_id} launched successfully!`, 'success');

      // Switch to Pipeline View and connect WebSocket
      switchTab('view-jobs');
      connectJobWebSocket(data.job_id);

    } catch (err) {
      showToast(`Failed to start job: ${err.message}`, 'error');
      if (btnStart) btnStart.disabled = false;
    }
  }

  async function startBurnIso() {
    const isoPathInput = document.getElementById('input-burn-iso-path');
    const driveSelect = document.getElementById('select-standalone-drive');
    const speedSelect = document.getElementById('select-standalone-speed');

    const isoPath = isoPathInput ? isoPathInput.value.trim() : '';
    const drivePath = driveSelect ? driveSelect.value : '';
    const speed = speedSelect ? parseInt(speedSelect.value, 10) : 4;

    if (!isoPath) {
      showToast('Please specify an ISO image path', 'error');
      return;
    }

    if (!drivePath) {
      showToast('Please select an optical burner drive', 'error');
      return;
    }

    const payload = {
      iso_path: isoPath,
      device_path: drivePath,
      burn_speed: speed,
      is_bluray: state.standaloneBurner.is_bluray,
    };

    try {
      const res = await fetch('/api/burn-iso', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const errorData = await res.json().catch(() => ({}));
        throw new Error(errorData.detail || `HTTP ${res.status}`);
      }

      const data = await res.json();
      showToast(`Burn job ${data.job_id} started!`, 'success');

      switchTab('view-jobs');
      connectJobWebSocket(data.job_id);
    } catch (err) {
      showToast(`Failed to start burn: ${err.message}`, 'error');
    }
  }

  // 1-Minute Preview Management
  function openPreviewModal() {
    if (state.playlist.length === 0) {
      showToast('Please add at least one video to generate a preview', 'error');
      return;
    }

    const select = document.getElementById('select-preview-title');
    if (select) {
      select.innerHTML = '';
      state.playlist.forEach((item, idx) => {
        const opt = document.createElement('option');
        opt.value = idx;
        opt.textContent = `#${idx + 1}: ${item.filename} (${formatSeconds(item.duration_sec)})`;
        select.appendChild(opt);
      });
      select.value = 0;
    }

    updatePreviewInfoSummary();

    const modal = document.getElementById('modal-preview');
    if (modal) {
      modal.style.display = 'flex';
    }
  }

  function closePreviewModal() {
    const modal = document.getElementById('modal-preview');
    if (modal) {
      modal.style.display = 'none';
    }
  }

  function updatePreviewInfoSummary() {
    const select = document.getElementById('select-preview-title');
    const windowText = document.getElementById('preview-window-text');
    const encodingText = document.getElementById('preview-encoding-text');
    if (!select || state.playlist.length === 0) return;

    const idx = parseInt(select.value, 10) || 0;
    const media = state.playlist[idx] || state.playlist[0];
    if (!media) return;

    const dur = media.duration_sec || 0;
    if (dur > 60) {
      const seekStart = Math.max(0, (dur / 2) - 30);
      const seekEnd = seekStart + 60;
      if (windowText) {
        windowText.textContent = `Midpoint 60s (${formatSeconds(seekStart)} - ${formatSeconds(seekEnd)})`;
      }
    } else {
      if (windowText) {
        windowText.textContent = `Full 0:00 - ${formatSeconds(dur)} (${Math.round(dur)}s clip)`;
      }
    }

    if (encodingText) {
      const isBluray = ['bd25', 'bd50', 'bd66', 'bd100', 'bd128'].includes(state.config.disc_type);
      const codec = isBluray ? 'H.264 High@L4.1 1080p' : `MPEG-2 ${state.config.tv_standard.toUpperCase()} ${state.config.aspect_ratio}`;
      const bitrate = state.calculatedBudget ? `${state.calculatedBudget.video_bitrate_kbps.toLocaleString()} kbps` : 'Auto';
      const gpu = state.config.use_gpu ? 'GPU' : 'CPU';
      const modeLabel = state.preview.preview_mode === 'preview_iso' ? 'Mini-ISO' : (isBluray ? '.m2ts' : '.mpg');
      encodingText.textContent = `${codec} • ${bitrate} (${gpu}) • ${modeLabel}`;
    }
  }

  async function startPreviewProject() {
    if (state.playlist.length === 0) {
      showToast('Please add at least one video to generate a preview', 'error');
      return;
    }

    const select = document.getElementById('select-preview-title');
    const idx = select ? (parseInt(select.value, 10) || 0) : 0;
    const media = state.playlist[idx] || state.playlist[0];
    if (!media) return;

    const baseName = state.config.output_name || 'DVD_PROJECT';
    const selectedSubtitleIndices = [];
    (media.subtitle_streams || []).forEach(s => {
      if (!s._excluded) {
        selectedSubtitleIndices.push(s.index);
      }
    });

    const payload = {
      input_file: media.path,
      preview_mode: state.preview.preview_mode,
      disc_type: state.config.disc_type,
      output_name: `preview_${baseName}`,
      tv_standard: state.config.tv_standard,
      aspect_ratio: state.config.aspect_ratio,
      menu_mode: state.config.menu_mode,
      use_gpu: state.config.use_gpu,
      selected_subtitle_indices: selectedSubtitleIndices,
    };

    closePreviewModal();

    try {
      const res = await fetch('/api/preview', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const errorData = await res.json().catch(() => ({}));
        throw new Error(errorData.detail || `HTTP ${res.status}`);
      }

      const data = await res.json();
      showToast(`Preview job ${data.job_id} started! Writing to dvd_output`, 'success');

      // Switch to Pipeline View and connect WebSocket
      switchTab('view-jobs');
      connectJobWebSocket(data.job_id);
    } catch (err) {
      showToast(`Failed to start preview: ${err.message}`, 'error');
    }
  }

  // WebSocket Live Pipeline Subscriber
  function connectJobWebSocket(jobId) {
    if (state.activeWebSocket) {
      try { state.activeWebSocket.close(); } catch (e) {}
      state.activeWebSocket = null;
    }

    state.activeJobId = jobId;

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/jobs/${jobId}`;
    const ws = new WebSocket(wsUrl);
    state.activeWebSocket = ws;

    const titleElem = document.getElementById('pipeline-job-title');
    const subtitleElem = document.getElementById('pipeline-job-subtitle');
    const btnCancel = document.getElementById('btn-cancel-job');

    if (titleElem) titleElem.textContent = `Job: ${jobId}`;
    if (btnCancel) btnCancel.style.display = 'inline-flex';

    ws.onopen = () => {
      appendTerminalLog(`[SYSTEM] Connected to real-time monitor for job ${jobId}`);
    };

    ws.onmessage = (event) => {
      try {
        const job = JSON.parse(event.data);
        updateJobPipelineUI(job);
      } catch (err) {
        console.error('Error parsing WS message:', err);
      }
    };

    ws.onerror = (err) => {
      appendTerminalLog(`[ERROR] WebSocket error on job ${jobId}`, 'error');
    };

    ws.onclose = () => {
      appendTerminalLog(`[SYSTEM] Disconnected from monitor for job ${jobId}`);
    };
  }

  function updateJobPipelineUI(job) {
    const subtitleElem = document.getElementById('pipeline-job-subtitle');
    const badge = document.getElementById('pipeline-stage-badge');
    const overallProg = document.getElementById('metric-overall-progress');
    const stageProg = document.getElementById('metric-stage-progress');
    const fpsSpeed = document.getElementById('metric-fps-speed');
    const etaElem = document.getElementById('metric-eta');
    const btnCancel = document.getElementById('btn-cancel-job');
    const btnPause = document.getElementById('btn-pause-job');

    if (subtitleElem) {
      subtitleElem.textContent = `${job.output_name} • Format: ${job.disc_type.toUpperCase()} • Mode: ${job.output_mode}`;
    }

    if (badge) {
      badge.textContent = (job.stage || 'IDLE').toUpperCase();
      badge.className = `status-pill ${job.stage || 'idle'}`;
    }

    if (overallProg) overallProg.textContent = `${(job.progress_percent || 0).toFixed(1)}%`;
    if (stageProg) stageProg.textContent = `${(job.stage_percent || 0).toFixed(1)}%`;
    if (fpsSpeed) {
      fpsSpeed.textContent = job.fps > 0 ? `${job.fps.toFixed(1)} FPS (${job.speed || '1.0x'})` : `${job.speed || '1.0x'}`;
    }
    if (etaElem) etaElem.textContent = job.eta || '--:--';

    // Update 5-Stage Stepper
    const stageOrder = ['probing', 'transcoding', 'authoring', 'mastering_iso', 'burning'];
    const activeStage = job.stage === 'paused' ? (job.previous_stage || 'transcoding') : job.stage;
    const currentIdx = stageOrder.indexOf(activeStage);

    stageOrder.forEach((st, idx) => {
      const stepElem = document.getElementById(`step-${st}`);
      if (!stepElem) return;

      stepElem.classList.remove('active', 'completed', 'failed');

      if (job.stage === 'failed' && idx === currentIdx) {
        stepElem.classList.add('failed');
      } else if (job.stage === 'completed' || idx < currentIdx) {
        stepElem.classList.add('completed');
      } else if (idx === currentIdx) {
        stepElem.classList.add('active');
      }
    });

    // Append logs
    if (job.logs && job.logs.length > 0) {
      const term = document.getElementById('terminal-logs');
      if (term) {
        term.innerHTML = '';
        job.logs.forEach(logLine => appendTerminalLog(logLine, false));
        if (state.autoScroll) {
          term.scrollTop = term.scrollHeight;
        }
      }
    }

    const isTerminal = ['completed', 'failed', 'cancelled'].includes(job.stage);

    if (btnPause) {
      if (isTerminal) {
        btnPause.style.display = 'none';
      } else {
        btnPause.style.display = 'inline-flex';
        btnPause.textContent = job.stage === 'paused' ? 'Resume' : 'Pause';
      }
    }

    if (btnCancel) {
      btnCancel.style.display = isTerminal ? 'none' : 'inline-flex';
    }

    if (job.stage === 'completed') {
      showToast(`Job ${job.job_id} completed successfully!`, 'success');
    } else if (job.stage === 'failed') {
      showToast(`Job ${job.job_id} failed: ${job.error_message || 'Unknown error'}`, 'error');
    }
  }

  function appendTerminalLog(text, autoScroll = true) {
    const term = document.getElementById('terminal-logs');
    if (!term) return;

    const div = document.createElement('div');
    div.className = 'log-line';
    if (text.includes('[ERROR]') || text.includes('ERROR:')) div.className += ' error';
    else if (text.includes('[WARN]') || text.includes('WARNING:')) div.className += ' warn';
    else if (text.includes('[OK]') || text.includes('completed') || text.includes('success')) div.className += ' success';
    else if (text.includes('[INFO]') || text.includes('[SYSTEM]')) div.className += ' info';

    div.textContent = text;
    term.appendChild(div);

    if (autoScroll && state.autoScroll) {
      term.scrollTop = term.scrollHeight;
    }
  }

  async function togglePauseActiveJob() {
    if (!state.activeJobId) return;

    // Check current state from state.jobs or fetch
    let isPaused = false;
    const currentJob = (state.jobs || []).find(j => j.job_id === state.activeJobId);
    if (currentJob) {
      isPaused = currentJob.stage === 'paused';
    }

    const action = isPaused ? 'resume' : 'pause';

    try {
      const res = await fetch(`/api/jobs/${state.activeJobId}/${action}`, { method: 'POST' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      showToast(`Job ${state.activeJobId} ${action}d`, 'info');
      loadJobHistory();
    } catch (err) {
      showToast(`Failed to ${action} job: ${err.message}`, 'error');
    }
  }

  async function cancelActiveJob() {
    if (!state.activeJobId) return;

    if (!confirm(`Are you sure you want to cancel Job ${state.activeJobId}?`)) {
      return;
    }

    try {
      const res = await fetch(`/api/jobs/${state.activeJobId}/cancel`, { method: 'POST' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      showToast(`Cancellation requested for job ${state.activeJobId}`, 'info');
      loadJobHistory();
    } catch (err) {
      showToast(`Failed to cancel job: ${err.message}`, 'error');
    }
  }

  // Job History
  async function loadJobHistory() {
    const tbody = document.getElementById('jobs-table-body');
    const empty = document.getElementById('jobs-empty');
    if (!tbody || !empty) return;

    try {
      const res = await fetch('/api/jobs');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const jobs = await res.json();
      state.jobs = jobs;

      const activeBadge = document.getElementById('active-jobs-badge');
      const activeCount = jobs.filter(j => !['completed', 'failed', 'cancelled'].includes(j.stage)).length;
      if (activeBadge) {
        activeBadge.textContent = activeCount;
        activeBadge.style.display = activeCount > 0 ? 'inline-block' : 'none';
      }

      tbody.innerHTML = '';
      if (jobs.length === 0) {
        empty.style.display = 'flex';
        return;
      }

      empty.style.display = 'none';

      jobs.forEach(j => {
        const tr = document.createElement('tr');
        const isPaused = j.stage === 'paused';
        const isActive = !['completed', 'failed', 'cancelled'].includes(j.stage);

        tr.innerHTML = `
          <td style="font-family: var(--font-mono); font-weight: 600;">${escapeHtml(j.job_id)}</td>
          <td>${escapeHtml(j.output_name)}</td>
          <td><span class="badge badge-stream">${(j.disc_type || '').toUpperCase()}</span></td>
          <td style="font-size: 0.75rem; color: var(--text-secondary);">${j.output_mode}</td>
          <td><span class="status-pill ${j.stage || 'idle'}">${(j.stage || 'idle').toUpperCase()}</span></td>
          <td style="font-family: var(--font-mono);">${(j.progress_percent || 0).toFixed(1)}%</td>
          <td style="text-align: right; white-space: nowrap;">
            <button class="btn btn-secondary btn-sm btn-monitor-job">Monitor</button>
            ${isActive ? `<button class="btn btn-secondary btn-sm btn-pause-job-row" style="margin-left: 4px;">${isPaused ? 'Resume' : 'Pause'}</button>` : ''}
            ${isActive ? '<button class="btn btn-danger btn-sm btn-cancel-job-row" style="margin-left: 4px;">Cancel</button>' : ''}
          </td>
        `;

        tr.querySelector('.btn-monitor-job')?.addEventListener('click', () => {
          connectJobWebSocket(j.job_id);
          window.scrollTo({ top: 0, behavior: 'smooth' });
        });

        tr.querySelector('.btn-pause-job-row')?.addEventListener('click', async () => {
          const act = j.stage === 'paused' ? 'resume' : 'pause';
          await fetch(`/api/jobs/${j.job_id}/${act}`, { method: 'POST' });
          loadJobHistory();
        });

        tr.querySelector('.btn-cancel-job-row')?.addEventListener('click', async () => {
          if (confirm(`Cancel job ${j.job_id}?`)) {
            await fetch(`/api/jobs/${j.job_id}/cancel`, { method: 'POST' });
            loadJobHistory();
          }
        });

        tbody.appendChild(tr);
      });

    } catch (err) {
      console.error('Failed to load job history:', err);
    }
  }

  // App Initialization
  function initApp() {
    initNavTabs();
    initSegmentedControls();
    initBrowserControls();
    initPlaylistControls();

    // Initial Data Fetching
    loadBrowserPath('/media');
    loadDrives();
    pollHardwareTelemetry();
    loadJobHistory();

    // Periodic Telemetry Polling (every 3s)
    setInterval(pollHardwareTelemetry, 3000);
    // Periodic Jobs Polling (every 5s)
    setInterval(loadJobHistory, 5000);
  }

  // Run when DOM is ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initApp);
  } else {
    initApp();
  }

})();
