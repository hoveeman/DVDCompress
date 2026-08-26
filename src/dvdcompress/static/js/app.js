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
      menu_end_action: 'menu',
      output_mode: 'iso_only',
      burner_device: '',
      burn_speed: 4,
      use_gpu: true,
      passthrough: false,
    },
    settings: {
      max_concurrent_jobs: 5,
      preferred_audio_language: 'eng',
      prefer_surround_audio: true,
    },
    preview: {
      preview_mode: 'preview_video',
    },
    standaloneBurner: {
      iso_path: '',
      is_bluray: false,
      device_path: '',
      burn_speed: 4,
      disc_type: null,
      iso_size_bytes: null,
    },
    drives: [],
    telemetry: null,
    activeJobId: null,
    activeWebSocket: null,
    jobs: [],
    maxConcurrentJobs: 5,
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
        if (btn.id === 'tab-btn-settings') {
          openSettingsModal();
          return;
        }
        const targetViewId = btn.getAttribute('data-target');
        if (targetViewId) {
          switchTab(targetViewId);
        }
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

  function setDiscType(val) {
    state.config.disc_type = val;
    const container = document.getElementById('control-disc-type');
    if (container) {
      container.querySelectorAll('.segmented-option').forEach(opt => {
        if (opt.getAttribute('data-value') === val) {
          opt.classList.add('active');
        } else {
          opt.classList.remove('active');
        }
      });
    }
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
  }

  // Segmented Controls
  function initSegmentedControls() {
    // Disc Format
    setupSegmentGroup('control-disc-type', (val) => {
      setDiscType(val);
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
      const groupMenuEnd = document.getElementById('group-menu-end-action');
      if (groupMenuEnd) {
        groupMenuEnd.style.display = (val === 'menu') ? 'block' : 'none';
      }
    });

    // After Title Finishes
    setupSegmentGroup('control-menu-end-action', (val) => {
      state.config.menu_end_action = val;
    });

    // Standalone Burner Media Type
    setupSegmentGroup('control-burner-media-type', (val) => {
      state.standaloneBurner.is_bluray = (val === 'bluray');
      const isoInput = document.getElementById('input-burn-iso-path');
      if (isoInput && isoInput.value) {
        handleIsoPathChanged(isoInput.value.trim(), state.standaloneBurner.iso_size_bytes);
      }
    });

    const isoPathInput = document.getElementById('input-burn-iso-path');
    if (isoPathInput) {
      isoPathInput.addEventListener('input', (e) => {
        handleIsoPathChanged(e.target.value.trim(), null);
      });
    }

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

    // Direct Stream Passthrough Toggle
    const passthroughToggle = document.getElementById('toggle-passthrough');
    if (passthroughToggle) {
      passthroughToggle.addEventListener('change', (e) => {
        state.config.passthrough = e.target.checked;
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

    // Fast Complexity Sample Button
    const btnComplexity = document.getElementById('btn-analyze-complexity');
    if (btnComplexity) {
      btnComplexity.addEventListener('click', runComplexityAnalysis);
    }

    // Refresh & Clear Jobs Buttons
    const btnRefreshJobs = document.getElementById('btn-refresh-jobs');
    if (btnRefreshJobs) {
      btnRefreshJobs.addEventListener('click', loadJobHistory);
    }

    const btnClearHistory = document.getElementById('btn-clear-history');
    if (btnClearHistory) {
      btnClearHistory.addEventListener('click', async () => {
        const finishedJobs = (state.jobs || []).filter(j => ['completed', 'failed', 'cancelled'].includes(j.stage));
        if (finishedJobs.length === 0) {
          showToast('No past jobs to clear in history', 'info');
          return;
        }
        if (confirm(`Clear all ${finishedJobs.length} past job(s) from history?`)) {
          try {
            const res = await fetch('/api/jobs', { method: 'DELETE' });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            showToast(`Cleared ${data.count || finishedJobs.length} job(s) from history`, 'info');
            loadJobHistory();
          } catch (err) {
            showToast(`Failed to clear history: ${err.message}`, 'error');
          }
        }
      });
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

  function setSegmentGroupValue(containerId, value) {
    const container = document.getElementById(containerId);
    if (!container) return;
    container.querySelectorAll('.segmented-option').forEach(opt => {
      if (opt.getAttribute('data-value') === value) {
        opt.classList.add('active');
      } else {
        opt.classList.remove('active');
      }
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
              <button class="btn btn-secondary btn-sm btn-select-iso" title="Burn ISO">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.38-.5-2-1-3-1.072-2.143-.224-4.054 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.153.433-2.294 1-3a2.5 2.5 0 0 0 2.5 2.5z"></path></svg>
                Burn
              </button>
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
              if (isoInput) {
                isoInput.value = file.path;
                handleIsoPathChanged(file.path, file.size_bytes);
              }
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
  // Helper: Apply smart audio track selection based on user settings
  function applyDefaultAudioSelection(mediaInfo) {
    const streams = mediaInfo.audio_streams || [];
    if (streams.length === 0) return;

    const prefLang = (state.settings && state.settings.preferred_audio_language) ? state.settings.preferred_audio_language.toLowerCase().trim() : 'eng';
    const prefSurround = (state.settings && state.settings.prefer_surround_audio !== undefined) ? state.settings.prefer_surround_audio : true;

    function langMatches(streamLang, pref) {
      if (!streamLang || !pref) return false;
      const s = streamLang.toLowerCase().trim();
      const p = pref.toLowerCase().trim();
      if (p === 'und' || p === 'any' || p === 'all') return true;
      if (s === p) return true;
      if (p === 'eng' && (s === 'en' || s === 'eng' || s === 'english')) return true;
      if (p === 'spa' && (s === 'es' || s === 'spa' || s === 'spanish')) return true;
      if (p === 'fra' && (s === 'fr' || s === 'fra' || s === 'fre' || s === 'french')) return true;
      if (p === 'deu' && (s === 'de' || s === 'deu' || s === 'ger' || s === 'german')) return true;
      if (p === 'ita' && (s === 'it' || s === 'ita' || s === 'italian')) return true;
      if (p === 'jpn' && (s === 'ja' || s === 'jpn' || s === 'japanese')) return true;
      if (p === 'zho' && (s === 'zh' || s === 'zho' || s === 'chi' || s === 'chinese')) return true;
      if (p === 'por' && (s === 'pt' || s === 'por' || s === 'portuguese')) return true;
      if (p === 'rus' && (s === 'ru' || s === 'rus' || s === 'russian')) return true;
      if (p === 'kor' && (s === 'ko' || s === 'kor' || s === 'korean')) return true;
      if (p === 'nld' && (s === 'nl' || s === 'nld' || s === 'dut' || s === 'dutch')) return true;
      return s.startsWith(p) || p.startsWith(s);
    }

    let candidates = streams.filter(s => langMatches(s.language, prefLang));
    if (candidates.length === 0) {
      candidates = [...streams];
    }

    if (prefSurround) {
      candidates.sort((a, b) => (b.channels || 0) - (a.channels || 0) || (b.bitrate || 0) - (a.bitrate || 0));
    }

    const chosenStream = candidates[0] || streams[0];

    streams.forEach(s => {
      s._selected = (s.index === chosenStream.index);
    });
  }

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
      applyDefaultAudioSelection(mediaInfo);
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

      const audioCount = (item.audio_streams || []).length;
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
            <div class="stream-group-header" style="display: flex; align-items: center; justify-content: space-between;">
              <div class="stream-group-title" style="margin: 0;">Audio Streams (${audioCount})</div>
              ${audioCount > 0 ? `
                <div class="stream-group-actions" style="display: flex; align-items: center; gap: 6px;">
                  <button type="button" class="btn btn-secondary btn-xs btn-audio-default" title="Reset to preferred default audio track">Select Default</button>
                  <button type="button" class="btn btn-secondary btn-xs btn-audio-all" title="Select all audio tracks for this title">Select All</button>
                </div>
              ` : ''}
            </div>
            ${audioCount > 0 ? (item.audio_streams || []).map(a => `
              <div class="stream-item" style="display: flex; align-items: center; justify-content: space-between;">
                <label style="display: flex; align-items: center; gap: 8px; cursor: pointer; user-select: none; margin: 0;">
                  <input type="checkbox" class="audio-track-checkbox" data-track-index="${a.index}" ${a._selected !== false ? 'checked' : ''} style="cursor: pointer;" />
                  <span class="stream-name">#${a.index}: ${a.codec_name.toUpperCase()} (${a.channel_layout || a.channels + 'ch'}) [${(a.language || 'und').toUpperCase()}]</span>
                </label>
                <span class="stream-meta">${escapeHtml(a.title || 'Track ' + a.index)} ${a.bitrate ? '• ' + Math.round(a.bitrate / 1000) + ' kbps' : ''}</span>
              </div>
            `).join('') : '<div style="color: var(--text-tertiary);">No audio tracks found.</div>'}
            
            <div class="stream-group-header" style="display: flex; align-items: center; justify-content: space-between; margin-top: 10px;">
              <div class="stream-group-title" style="margin: 0;">Subtitle Streams (${subCount})</div>
              ${subCount > 0 ? `
                <div class="stream-group-actions" style="display: flex; align-items: center; gap: 6px;">
                  <button type="button" class="btn btn-secondary btn-xs btn-subs-none" title="Unselect all subtitle tracks for this title">Select None</button>
                  <button type="button" class="btn btn-secondary btn-xs btn-subs-all" title="Select all subtitle tracks for this title">Select All</button>
                </div>
              ` : ''}
            </div>
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

      // Per-title audio selection actions
      itemCard.querySelector('.btn-audio-default')?.addEventListener('click', () => {
        applyDefaultAudioSelection(item);
        renderPlaylist();
        recalculateBudget();
      });
      itemCard.querySelector('.btn-audio-all')?.addEventListener('click', () => {
        (item.audio_streams || []).forEach(a => { a._selected = true; });
        renderPlaylist();
        recalculateBudget();
      });

      // Audio track selection listeners
      itemCard.querySelectorAll('.audio-track-checkbox').forEach(cb => {
        cb.addEventListener('change', (e) => {
          const trackIdx = parseInt(e.target.dataset.trackIndex, 10);
          const audioStream = (item.audio_streams || []).find(a => a.index === trackIdx);
          if (audioStream) {
            audioStream._selected = e.target.checked;
          }
          // Ensure at least one audio track remains selected for playback
          const anySelected = (item.audio_streams || []).some(a => a._selected !== false);
          if (!anySelected && (item.audio_streams || []).length > 0) {
            item.audio_streams[0]._selected = true;
            renderPlaylist();
          }
          recalculateBudget();
        });
      });

      // Per-title subtitle selection actions
      itemCard.querySelector('.btn-subs-none')?.addEventListener('click', () => {
        (item.subtitle_streams || []).forEach(s => { s._excluded = true; });
        renderPlaylist();
      });
      itemCard.querySelector('.btn-subs-all')?.addEventListener('click', () => {
        (item.subtitle_streams || []).forEach(s => { s._excluded = false; });
        renderPlaylist();
      });

      // Subtitle track selection listeners
      itemCard.querySelectorAll('.sub-track-checkbox').forEach(cb => {
        cb.addEventListener('change', (e) => {
          const trackIdx = parseInt(e.target.dataset.trackIndex, 10);
          const subStream = (item.subtitle_streams || []).find(s => s.index === trackIdx);
          if (subStream) {
            subStream._excluded = !e.target.checked;
          }
          updateGlobalSubtitleButtonState();
        });
      });


      container.appendChild(itemCard);
    });

    if (countBadge) countBadge.textContent = `${state.playlist.length} Title${state.playlist.length === 1 ? '' : 's'}`;
    if (durText) durText.textContent = formatSeconds(totalDuration);
    if (sizeText) sizeText.textContent = formatBytes(totalSizeBytes);
    updateGlobalSubtitleButtonState();
  }

  function updateGlobalSubtitleButtonState() {
    const btnToggleSubs = document.getElementById('btn-toggle-all-subs');
    if (!btnToggleSubs) return;
    const totalSubs = state.playlist.reduce((sum, item) => sum + (item.subtitle_streams || []).length, 0);
    if (state.playlist.length === 0 || totalSubs === 0) {
      btnToggleSubs.style.display = 'none';
      return;
    }
    btnToggleSubs.style.display = 'inline-flex';
    const anySelected = state.playlist.some(item =>
      (item.subtitle_streams || []).some(s => !s._excluded)
    );
    btnToggleSubs.textContent = anySelected ? 'Deselect All Subtitles' : 'Select All Subtitles';
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

    const btnToggleSubs = document.getElementById('btn-toggle-all-subs');
    if (btnToggleSubs) {
      btnToggleSubs.addEventListener('click', () => {
        if (state.playlist.length === 0) return;
        const anySelected = state.playlist.some(item =>
          (item.subtitle_streams || []).some(s => !s._excluded)
        );
        const shouldExclude = anySelected;
        state.playlist.forEach(item => {
          (item.subtitle_streams || []).forEach(s => {
            s._excluded = shouldExclude;
          });
        });
        renderPlaylist();
        showToast(shouldExclude ? 'Unselected all subtitles' : 'Selected all subtitles', 'info');
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
    const recContainer = document.getElementById('gauge-recommendation-container');
    const formatRecChip = document.getElementById('disc-format-recommendation');
    const formatRecText = document.getElementById('disc-format-rec-text');
    const formatRecIcon = document.getElementById('disc-format-rec-icon');
    const btnApplyRec = document.getElementById('btn-apply-disc-rec');
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
      if (recContainer) recContainer.innerHTML = '';
      if (formatRecChip) formatRecChip.style.display = 'none';
      const complexityContainer = document.getElementById('gauge-complexity-container');
      if (complexityContainer) {
        complexityContainer.style.display = 'none';
        complexityContainer.innerHTML = '';
      }
      if (btnStart) btnStart.disabled = true;
      if (btnPreview) btnPreview.disabled = true;
      return;
    }

    const totalDuration = state.playlist.reduce((acc, item) => acc + (item.duration_sec || 0), 0);
    
    // Collect target audio bitrates for each selected audio track across all playlist items
    const isDvd = (state.config.disc_type === 'dvd5' || state.config.disc_type === 'dvd9');
    const audioTracksKbps = [];
    state.playlist.forEach(item => {
      const selected = (item.audio_streams || []).filter(a => a._selected !== false);
      const targetAudio = selected.length > 0 ? selected : ((item.audio_streams && item.audio_streams.length > 0) ? [item.audio_streams[0]] : []);
      if (targetAudio.length > 0) {
        targetAudio.forEach(a => {
          const channels = a.channels || 2;
          audioTracksKbps.push(channels >= 6 ? (isDvd ? 384 : 448) : 192);
        });
      } else {
        audioTracksKbps.push(192);
      }
    });

    if (audioTracksKbps.length === 0) audioTracksKbps.push(192);

    try {
      const res = await fetch('/api/calculate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          total_duration_sec: totalDuration,
          disc_type: state.config.disc_type,
          audio_tracks_kbps: audioTracksKbps,
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

      // Recommendations (Single vs Dual Layer)
      if (budget.recommendation_reason) {
        const isOptimal = budget.recommended_disc_type === state.config.disc_type;
        if (recContainer) {
          recContainer.innerHTML = `
            <div class="recommendation-box ${isOptimal ? 'optimal' : ''}">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="12" cy="12" r="10"></circle>
                <line x1="12" y1="16" x2="12" y2="12"></line>
                <line x1="12" y1="8" x2="12.01" y2="8"></line>
              </svg>
              <div>
                <strong>${isOptimal ? 'Optimal Media Match' : 'Media Recommendation'}:</strong>
                <div>${escapeHtml(budget.recommendation_reason)}</div>
              </div>
            </div>
          `;
        }

        if (formatRecChip && formatRecText) {
          formatRecChip.style.display = 'flex';
          formatRecChip.className = `disc-format-recommendation ${isOptimal ? 'optimal' : ''}`;
          if (formatRecIcon) formatRecIcon.textContent = isOptimal ? '✅' : '💡';
          formatRecText.textContent = budget.recommendation_reason;

          if (btnApplyRec) {
            if (!isOptimal && budget.recommended_disc_type) {
              const targetShortName = (budget.recommended_disc_type || '').toUpperCase();
              btnApplyRec.textContent = `Switch to ${targetShortName}`;
              btnApplyRec.style.display = 'inline-block';
              btnApplyRec.onclick = () => {
                setDiscType(budget.recommended_disc_type);
                showToast(`Target disc format switched to ${targetShortName}`, 'info');
              };
            } else {
              btnApplyRec.style.display = 'none';
            }
          }
        }
      } else {
        if (recContainer) recContainer.innerHTML = '';
        if (formatRecChip) formatRecChip.style.display = 'none';
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

  // Fast Video Complexity & Size Analyzer
  async function runComplexityAnalysis() {
    const btnComplexity = document.getElementById('btn-analyze-complexity');
    const container = document.getElementById('gauge-complexity-container');
    if (!state.playlist || state.playlist.length === 0) {
      showToast('Please add video files to the project first', 'info');
      return;
    }

    const origBtnText = btnComplexity ? btnComplexity.innerHTML : '⚡ Fast Sample';
    if (btnComplexity) {
      btnComplexity.disabled = true;
      btnComplexity.innerHTML = '⚡ Sampling...';
    }

    try {
      const res = await fetch('/api/analyze-complexity', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          input_files: state.playlist.map(item => item.path),
          disc_type: state.config.disc_type,
          tv_standard: state.config.tv_standard,
          aspect_ratio: state.config.aspect_ratio,
        }),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `HTTP ${res.status}`);
      }

      const result = await res.json();
      state.complexityResult = result;

      if (container) {
        container.style.display = 'block';
        const isOptimal = result.recommended_disc_type === state.config.disc_type;
        const badgeClass = result.complexity_level.toLowerCase().includes('low')
          ? 'low'
          : result.complexity_level.toLowerCase().includes('medium')
          ? 'medium'
          : 'high';

        container.innerHTML = `
          <div class="complexity-result-box">
            <div class="complexity-header">
              <div class="complexity-title">
                <span>⚡ Measured VBR Output</span>
              </div>
              <span class="complexity-badge ${badgeClass}">${escapeHtml(result.complexity_level.split(' ')[0])}</span>
            </div>

            <div class="complexity-metrics">
              <div class="complexity-metric-item">
                <span class="complexity-metric-label">Projected Final Size</span>
                <span class="complexity-metric-value">${result.projected_iso_size_gb.toFixed(1)} GB</span>
              </div>
              <div class="complexity-metric-item">
                <span class="complexity-metric-label">Empirical VBR Bitrate</span>
                <span class="complexity-metric-value">${result.empirical_video_bitrate_kbps.toLocaleString()} kbps</span>
              </div>
            </div>

            <div class="complexity-desc">
              ${escapeHtml(result.recommendation_text)}
            </div>

            ${
              !isOptimal && result.recommended_disc_type
                ? `<div style="margin-top: 0.25rem;">
                     <button type="button" class="btn btn-secondary btn-xs" id="btn-apply-complexity-disc">
                       Switch to ${(result.recommended_disc_type || '').toUpperCase()}
                     </button>
                   </div>`
                : ''
            }
          </div>
        `;

        const btnApply = document.getElementById('btn-apply-complexity-disc');
        if (btnApply) {
          btnApply.onclick = () => {
            setDiscType(result.recommended_disc_type);
            showToast(`Switched target format to ${(result.recommended_disc_type || '').toUpperCase()}`, 'info');
          };
        }
      }

      showToast(`Sample completed: Projected ISO ~${result.projected_iso_size_gb.toFixed(1)} GB`, 'success');
    } catch (err) {
      console.error('Failed to run complexity analysis:', err);
      showToast(`Sample analysis failed: ${err.message}`, 'error');
    } finally {
      if (btnComplexity) {
        btnComplexity.disabled = false;
        btnComplexity.innerHTML = origBtnText;
      }
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

  function handleIsoPathChanged(filePath, knownSizeBytes = null) {
    const badge = document.getElementById('standalone-iso-format-badge');
    if (!filePath) {
      if (badge) badge.style.display = 'none';
      state.standaloneBurner.disc_type = null;
      return;
    }

    let formatLabel = 'ISO Image';
    let isBluray = state.standaloneBurner.is_bluray;
    let discType = isBluray ? 'bd25' : 'dvd5';

    if (knownSizeBytes !== null && knownSizeBytes !== undefined && knownSizeBytes > 0) {
      if (isBluray) {
        if (knownSizeBytes > 100 * 1024 * 1024 * 1024) { discType = 'bd128'; formatLabel = `BDXL BD-128 (${formatBytes(knownSizeBytes)})`; }
        else if (knownSizeBytes > 66 * 1024 * 1024 * 1024) { discType = 'bd100'; formatLabel = `BDXL BD-100 (${formatBytes(knownSizeBytes)})`; }
        else if (knownSizeBytes > 50 * 1024 * 1024 * 1024) { discType = 'bd66'; formatLabel = `BD-66 UHD (${formatBytes(knownSizeBytes)})`; }
        else if (knownSizeBytes > 25 * 1024 * 1024 * 1024) { discType = 'bd50'; formatLabel = `BD-50 (${formatBytes(knownSizeBytes)})`; }
        else { discType = 'bd25'; formatLabel = `BD-25 (${formatBytes(knownSizeBytes)})`; }
      } else {
        if (knownSizeBytes > 4700000000) {
          discType = 'dvd9';
          formatLabel = `DVD-9 (${formatBytes(knownSizeBytes)})`;
        } else {
          discType = 'dvd5';
          formatLabel = `DVD-5 (${formatBytes(knownSizeBytes)})`;
        }
      }
    } else {
      formatLabel = isBluray ? 'Blu-ray ISO' : 'DVD ISO';
    }

    state.standaloneBurner.disc_type = discType;
    state.standaloneBurner.iso_size_bytes = knownSizeBytes;
    if (badge) {
      badge.textContent = formatLabel;
      badge.style.display = 'inline-block';
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
          if (input) {
            input.value = file.path;
            handleIsoPathChanged(file.path, file.size_bytes);
          }
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

    const selectedAudioIndices = [];
    state.playlist.forEach(item => {
      (item.audio_streams || []).forEach(a => {
        if (a._selected !== false) {
          selectedAudioIndices.push(a.index);
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
      menu_end_action: state.config.menu_end_action || 'menu',
      burner_device: state.config.burner_device || null,
      burn_speed: state.config.burn_speed || 4,
      use_gpu: state.config.use_gpu,
      passthrough: state.config.passthrough,
      selected_audio_indices: selectedAudioIndices,
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
      disc_type: state.standaloneBurner.disc_type || undefined,
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

    const selectedAudioIndices = [];
    (media.audio_streams || []).forEach(a => {
      if (a._selected !== false) {
        selectedAudioIndices.push(a.index);
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
      menu_end_action: state.config.menu_end_action || 'menu',
      use_gpu: state.config.use_gpu,
      passthrough: state.config.passthrough,
      selected_audio_indices: selectedAudioIndices,
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
    const speedLabel = document.getElementById('metric-speed-label');
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

    if (speedLabel) {
      if (job.stage === 'burning' || job.output_mode === 'burn_direct') {
        speedLabel.textContent = 'Burn Speed';
      } else {
        speedLabel.textContent = 'Encoding Speed';
      }
    }

    if (fpsSpeed) {
      if (job.stage === 'burning' || job.output_mode === 'burn_direct') {
        fpsSpeed.textContent = job.speed || '1.0x';
      } else {
        fpsSpeed.textContent = job.fps > 0 ? `${job.fps.toFixed(1)} FPS (${job.speed || '1.0x'})` : `${job.speed || '1.0x'}`;
      }
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

  // Helper: Format Duration for Job History
  function formatDuration(job) {
    if (!job) return '—';
    let duration = job.duration_sec;
    if (duration == null || duration === undefined) {
      if (job.started_at && !['completed', 'failed', 'cancelled', 'idle', 'queued'].includes(job.stage)) {
        duration = Math.max(0, (Date.now() / 1000) - job.started_at);
      }
    }
    if (duration == null || duration === undefined || isNaN(duration)) {
      return '—';
    }
    const totalSec = Math.round(duration);
    if (totalSec < 60) {
      return `${totalSec}s`;
    }
    const hrs = Math.floor(totalSec / 3600);
    const mins = Math.floor((totalSec % 3600) / 60);
    const secs = totalSec % 60;
    if (hrs > 0) {
      return `${hrs}h ${mins.toString().padStart(2, '0')}m ${secs.toString().padStart(2, '0')}s`;
    }
    return `${mins}m ${secs.toString().padStart(2, '0')}s`;
  }

  // Helper: Format Output Size for Job History
  function formatJobSize(job) {
    if (!job || !job.completed_size_bytes || job.completed_size_bytes <= 0) return '—';
    return formatBytes(job.completed_size_bytes);
  }

  const ITEMS_PER_PAGE = 10;

  // Job History
  async function loadJobHistory() {
    const tbody = document.getElementById('jobs-table-body');
    const empty = document.getElementById('jobs-empty');
    const paginationContainer = document.getElementById('jobs-pagination-controls');
    const paginationInfo = document.getElementById('jobs-pagination-info');
    const paginationButtons = document.getElementById('jobs-pagination-buttons');
    if (!tbody || !empty) return;

    try {
      const res = await fetch('/api/jobs');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const rawJobs = await res.json();

      // Ensure newest jobs appear at the top
      const jobs = [...rawJobs].sort((a, b) => {
        const tA = (a.created_at !== undefined && a.created_at !== null) ? a.created_at : 0;
        const tB = (b.created_at !== undefined && b.created_at !== null) ? b.created_at : 0;
        if (tA !== tB) return tB - tA;
        return 0;
      });
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
        if (paginationContainer) paginationContainer.style.display = 'none';
        return;
      }

      empty.style.display = 'none';

      const totalItems = jobs.length;
      const totalPages = Math.max(1, Math.ceil(totalItems / ITEMS_PER_PAGE));
      if (!state.jobHistoryPage || state.jobHistoryPage < 1) {
        state.jobHistoryPage = 1;
      } else if (state.jobHistoryPage > totalPages) {
        state.jobHistoryPage = totalPages;
      }

      const startIndex = (state.jobHistoryPage - 1) * ITEMS_PER_PAGE;
      const pageJobs = jobs.slice(startIndex, startIndex + ITEMS_PER_PAGE);

      pageJobs.forEach(j => {
        const tr = document.createElement('tr');
        const isPaused = j.stage === 'paused';
        const isActive = !['completed', 'failed', 'cancelled'].includes(j.stage);

        tr.innerHTML = `
          <td style="font-family: var(--font-mono); font-weight: 600;">${escapeHtml(j.job_id)}</td>
          <td>${escapeHtml(j.output_name)}</td>
          <td><span class="badge badge-stream">${(j.disc_type || '').toUpperCase()}</span></td>
          <td style="font-size: 0.75rem; color: var(--text-secondary);">${escapeHtml(j.output_mode || '')}</td>
          <td><span class="status-pill ${j.stage || 'idle'}">${(j.stage || 'idle').toUpperCase()}</span></td>
          <td style="font-family: var(--font-mono);">${(j.progress_percent || 0).toFixed(1)}%</td>
          <td style="font-family: var(--font-mono); font-size: 0.8rem; color: var(--text-secondary);">${formatDuration(j)}</td>
          <td style="font-family: var(--font-mono); font-size: 0.8rem; color: var(--text-secondary);">${formatJobSize(j)}</td>
          <td style="text-align: right; white-space: nowrap;">
            <button class="btn btn-secondary btn-sm btn-monitor-job">Monitor</button>
            ${isActive ? `<button class="btn btn-secondary btn-sm btn-pause-job-row" style="margin-left: 4px;">${isPaused ? 'Resume' : 'Pause'}</button>` : ''}
            ${isActive ? '<button class="btn btn-danger btn-sm btn-cancel-job-row" style="margin-left: 4px;">Cancel</button>' : ''}
            ${!isActive ? '<button class="btn btn-secondary btn-sm btn-edit-job-row" style="margin-left: 4px;" title="Edit and tweak in authoring">Edit</button>' : ''}
            ${!isActive ? '<button class="btn btn-primary btn-sm btn-retry-job-row" style="margin-left: 4px;" title="Re-run job with same settings">Retry</button>' : ''}
            ${!isActive ? '<button class="btn btn-danger btn-sm btn-delete-job-row" style="margin-left: 4px;" title="Remove this job from history">Remove</button>' : ''}
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

        tr.querySelector('.btn-edit-job-row')?.addEventListener('click', () => {
          editJobInAuthoring(j);
        });

        tr.querySelector('.btn-retry-job-row')?.addEventListener('click', () => {
          retryJob(j.job_id, j.output_name);
        });

        tr.querySelector('.btn-delete-job-row')?.addEventListener('click', async () => {
          try {
            const res = await fetch(`/api/jobs/${j.job_id}`, { method: 'DELETE' });
            if (!res.ok) {
              const err = await res.json().catch(() => ({}));
              throw new Error(err.detail || `HTTP ${res.status}`);
            }
            showToast(`Job ${j.job_id} removed from history`, 'info');
            loadJobHistory();
          } catch (err) {
            showToast(`Failed to remove job: ${err.message}`, 'error');
          }
        });

        tbody.appendChild(tr);
      });

      // Render pagination
      if (paginationContainer && paginationInfo && paginationButtons) {
        paginationContainer.style.display = 'flex';
        const startItem = startIndex + 1;
        const endItem = Math.min(startIndex + pageJobs.length, totalItems);
        paginationInfo.textContent = `Showing ${startItem}–${endItem} of ${totalItems} jobs`;

        paginationButtons.innerHTML = '';

        if (totalPages > 1) {
          // Prev button
          const prevBtn = document.createElement('button');
          prevBtn.type = 'button';
          prevBtn.className = 'pagination-btn';
          prevBtn.innerHTML = '&laquo; Prev';
          prevBtn.disabled = state.jobHistoryPage <= 1;
          prevBtn.addEventListener('click', () => {
            if (state.jobHistoryPage > 1) {
              state.jobHistoryPage--;
              loadJobHistory();
            }
          });
          paginationButtons.appendChild(prevBtn);

          // Page Number buttons
          for (let p = 1; p <= totalPages; p++) {
            const pageBtn = document.createElement('button');
            pageBtn.type = 'button';
            pageBtn.className = `pagination-btn ${p === state.jobHistoryPage ? 'active' : ''}`;
            pageBtn.textContent = p;
            pageBtn.addEventListener('click', () => {
              if (state.jobHistoryPage !== p) {
                state.jobHistoryPage = p;
                loadJobHistory();
              }
            });
            paginationButtons.appendChild(pageBtn);
          }

          // Next button
          const nextBtn = document.createElement('button');
          nextBtn.type = 'button';
          nextBtn.className = 'pagination-btn';
          nextBtn.innerHTML = 'Next &raquo;';
          nextBtn.disabled = state.jobHistoryPage >= totalPages;
          nextBtn.addEventListener('click', () => {
            if (state.jobHistoryPage < totalPages) {
              state.jobHistoryPage++;
              loadJobHistory();
            }
          });
          paginationButtons.appendChild(nextBtn);
        }
      }

    } catch (err) {
      console.error('Failed to load job history:', err);
    }
  }

  // Restore and Edit Job in Authoring View
  async function editJobInAuthoring(job) {
    if (!job) return;

    // 1. Output Name
    state.config.output_name = job.output_name || 'DVD_PROJECT';
    const inputOutputName = document.getElementById('input-output-name');
    if (inputOutputName) inputOutputName.value = state.config.output_name;

    // 2. Disc Type
    if (job.disc_type) {
      setDiscType(job.disc_type);
    }

    // 3. TV Standard
    if (job.tv_standard) {
      state.config.tv_standard = job.tv_standard;
      setSegmentGroupValue('control-tv-standard', job.tv_standard);
    }

    // 4. Aspect Ratio
    if (job.aspect_ratio) {
      state.config.aspect_ratio = job.aspect_ratio;
      setSegmentGroupValue('control-aspect-ratio', job.aspect_ratio);
    }

    // 5. Menu Mode & After Title Finishes
    if (job.menu_mode) {
      state.config.menu_mode = job.menu_mode;
      setSegmentGroupValue('control-menu-mode', job.menu_mode);
      const groupMenuEnd = document.getElementById('group-menu-end-action');
      if (groupMenuEnd) {
        groupMenuEnd.style.display = (job.menu_mode === 'menu') ? 'block' : 'none';
      }
    }
    if (job.menu_end_action) {
      state.config.menu_end_action = job.menu_end_action;
      setSegmentGroupValue('control-menu-end-action', job.menu_end_action);
    }

    // 6. Output Mode & Burner Options
    if (job.output_mode) {
      state.config.output_mode = job.output_mode;
      const selectOutputMode = document.getElementById('select-output-mode');
      if (selectOutputMode) selectOutputMode.value = job.output_mode;
      const burnerOptionsGroup = document.getElementById('burner-options-group');
      if (burnerOptionsGroup) {
        const needsBurner = (job.output_mode === 'author_and_burn' || job.output_mode === 'burn_direct');
        burnerOptionsGroup.style.display = needsBurner ? 'block' : 'none';
      }
    }

    // 7. Burn Speed
    if (job.burn_speed) {
      state.config.burn_speed = job.burn_speed;
      const selectBurnSpeed = document.getElementById('select-burn-speed');
      if (selectBurnSpeed) selectBurnSpeed.value = job.burn_speed.toString();
    }

    // 8. Burner Device
    if (job.burner_device) {
      state.config.burner_device = job.burner_device;
      const selectBurner = document.getElementById('select-burner-device');
      if (selectBurner) selectBurner.value = job.burner_device;
    }

    // 9. Hardware Acceleration (GPU)
    state.config.use_gpu = (job.use_gpu !== false);
    const toggleGpu = document.getElementById('toggle-gpu');
    if (toggleGpu) toggleGpu.checked = state.config.use_gpu;
    const descGpu = document.getElementById('gpu-toggle-desc');
    if (descGpu) descGpu.textContent = state.config.use_gpu ? 'NVIDIA NVENC / CUDA' : 'CPU (libx264 / libavcodec)';

    // 10. Direct Passthrough
    state.config.passthrough = !!job.passthrough;
    const togglePassthrough = document.getElementById('toggle-passthrough');
    if (togglePassthrough) togglePassthrough.checked = state.config.passthrough;

    // 11. Clear playlist and re-probe / load input files
    state.playlist = [];
    renderPlaylist();

    if (Array.isArray(job.input_files) && job.input_files.length > 0) {
      showToast(`Loading ${job.input_files.length} file(s) for '${job.output_name}'...`, 'info');
      for (const filePath of job.input_files) {
        await addFileToPlaylist(filePath);
      }

      // Restore selected audio indices if provided
      if (Array.isArray(job.selected_audio_indices) && job.selected_audio_indices.length > 0 && state.playlist.length > 0) {
        state.playlist.forEach(item => {
          (item.audio_streams || []).forEach(a => {
            a._selected = job.selected_audio_indices.includes(a.index);
          });
        });
        renderPlaylist();
      }

      // Restore selected subtitle indices if provided
      if (Array.isArray(job.selected_subtitle_indices) && state.playlist.length > 0) {
        state.playlist.forEach(item => {
          (item.subtitle_streams || []).forEach(sub => {
            sub._excluded = !job.selected_subtitle_indices.includes(sub.index);
          });
        });
        renderPlaylist();
      }
    }


    recalculateBudget();
    switchTab('view-authoring');
    window.scrollTo({ top: 0, behavior: 'smooth' });
    showToast(`Loaded project settings for '${job.output_name}'`, 'success');
  }

  // Re-enqueue and retry job
  async function retryJob(jobId, outputName) {
    try {
      showToast(`Retrying job '${outputName || jobId}'...`, 'info');
      const res = await fetch(`/api/jobs/${jobId}/retry`, { method: 'POST' });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `HTTP ${res.status}`);
      }
      const data = await res.json();
      showToast(`Job re-queued successfully (${data.job_id})`, 'success');
      connectJobWebSocket(data.job_id);
      loadJobHistory();
      window.scrollTo({ top: 0, behavior: 'smooth' });
    } catch (err) {
      showToast(`Failed to retry job: ${err.message}`, 'error');
    }
  }

  // App Settings & Concurrency Control
  async function loadSettings() {
    try {
      const res = await fetch('/api/settings');
      if (!res.ok) return;
      const data = await res.json();
      if (data) {
        state.settings = data;
        state.maxConcurrentJobs = data.max_concurrent_jobs || 5;
        updateSlotsDisplay();
        updateSettingsForm();
      }
    } catch (err) {
      console.error('Failed to load settings:', err);
    }
  }

  function updateSlotsDisplay() {
    const display = document.getElementById('slots-value');
    if (display) {
      display.textContent = state.maxConcurrentJobs || 5;
    }
  }

  async function updateMaxConcurrentJobs(delta) {
    const current = state.maxConcurrentJobs || 5;
    const newLimit = Math.max(1, Math.min(20, current + delta));
    if (newLimit === current) return;

    state.maxConcurrentJobs = newLimit;
    updateSlotsDisplay();

    try {
      const res = await fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ max_concurrent_jobs: newLimit }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const updated = await res.json();
      state.settings = updated;
      showToast(`Concurrent job slots set to ${newLimit}`, 'info');
      loadJobHistory();
    } catch (err) {
      showToast(`Failed to update concurrent slots: ${err.message}`, 'error');
    }
  }

  function initSlotsControl() {
    const btnDec = document.getElementById('btn-slots-decrement');
    const btnInc = document.getElementById('btn-slots-increment');
    if (btnDec) {
      btnDec.addEventListener('click', () => updateMaxConcurrentJobs(-1));
    }
    if (btnInc) {
      btnInc.addEventListener('click', () => updateMaxConcurrentJobs(1));
    }
  }

  // Settings Modal Functions
  function openSettingsModal() {
    const modal = document.getElementById('modal-settings');
    if (modal) {
      updateSettingsForm();
      modal.style.display = 'flex';
    }
  }

  function closeSettingsModal() {
    const modal = document.getElementById('modal-settings');
    if (modal) {
      modal.style.display = 'none';
    }
  }

  function updateSettingsForm() {
    const langSelect = document.getElementById('setting-audio-lang');
    const surroundToggle = document.getElementById('setting-prefer-surround');
    const maxConcurrentInput = document.getElementById('setting-max-concurrent');
    if (langSelect && state.settings) {
      langSelect.value = state.settings.preferred_audio_language || 'eng';
    }
    if (surroundToggle && state.settings) {
      surroundToggle.checked = (state.settings.prefer_surround_audio !== undefined) ? state.settings.prefer_surround_audio : true;
    }
    if (maxConcurrentInput) {
      maxConcurrentInput.value = state.maxConcurrentJobs || 5;
    }
  }

  async function saveSettingsModal() {
    const langSelect = document.getElementById('setting-audio-lang');
    const surroundToggle = document.getElementById('setting-prefer-surround');
    const maxConcurrentInput = document.getElementById('setting-max-concurrent');

    const newLang = langSelect ? langSelect.value : 'eng';
    const newSurround = surroundToggle ? surroundToggle.checked : true;
    const newConcurrent = maxConcurrentInput ? Math.max(1, Math.min(20, parseInt(maxConcurrentInput.value, 10) || 5)) : 5;

    try {
      const res = await fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          preferred_audio_language: newLang,
          prefer_surround_audio: newSurround,
          max_concurrent_jobs: newConcurrent,
        }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const updated = await res.json();
      state.settings = updated;
      state.maxConcurrentJobs = updated.max_concurrent_jobs || newConcurrent;
      updateSlotsDisplay();
      closeSettingsModal();
      showToast('Settings saved successfully', 'success');

      // Update audio selection on current playlist
      if (state.playlist.length > 0) {
        state.playlist.forEach(applyDefaultAudioSelection);
        renderPlaylist();
        recalculateBudget();
      }
    } catch (err) {
      showToast(`Failed to save settings: ${err.message}`, 'error');
    }
  }

  function initSettingsModal() {
    const btnClose = document.getElementById('btn-close-settings-modal');
    const btnCancel = document.getElementById('btn-cancel-settings-modal');
    const btnSave = document.getElementById('btn-save-settings');

    if (btnClose) btnClose.addEventListener('click', closeSettingsModal);
    if (btnCancel) btnCancel.addEventListener('click', closeSettingsModal);
    if (btnSave) btnSave.addEventListener('click', saveSettingsModal);
  }

  async function loadAppVersion() {
    try {
      const res = await fetch('/api/version');
      if (res.ok) {
        const data = await res.json();
        const verEl = document.getElementById('app-version');
        if (verEl && data.version) {
          verEl.textContent = 'v' + data.version;
        }
      }
    } catch (e) {
      console.warn('Failed to fetch app version:', e);
    }
  }

  // App Initialization
  function initApp() {
    initNavTabs();
    initSegmentedControls();
    initBrowserControls();
    initPlaylistControls();
    initSlotsControl();
    initSettingsModal();

    // Initial Data Fetching
    loadAppVersion();
    loadSettings();
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


