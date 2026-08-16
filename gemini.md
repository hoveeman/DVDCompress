# DVDCompress — Comprehensive Project Knowledge Base (Gemini Context)

**Version:** 1.0.0  
**Repository:** [https://github.com/hoveeman/DVDCompress](https://github.com/hoveeman/DVDCompress)  
**Docker Hub Image:** [hovee/dvdcompress:latest](https://hub.docker.com/r/hovee/dvdcompress)  
**License:** MIT  

---

## 1. Project Overview & Mission

**DVDCompress** is a modern, self-hosted, containerized web application designed to author, compress, and burn digital video files (`.mkv`, `.mp4`, `.avi`, `.mov`, `.ts`, `.webm`, etc.) into 100% standard-compliant, physical **DVD-Video** (`VIDEO_TS`) and **Blu-ray** (`BDMV`) optical discs or master ISO images.

### Key Capabilities:
- **Dynamic Bitrate Budgeting:** Mathematically calculates the maximum allowable video and audio bitrates based on source duration and disc sector capacity to guarantee optimal visual fidelity without overflowing.
- **Hardware Acceleration:** Native NVIDIA GPU hardware decoding (NVDEC/CUDA) and encoding (`h264_nvenc`, `hevc_nvenc`) with CPU fallback (`mpeg2video`, `libx264`, `libx265`).
- **Disc Format Support:** DVD-5 (4.7 GB), DVD-9 (8.5 GB), BD-25, BD-50, BD-66 (UHD), and BDXL TL BD-100 (100 GB) / QL BD-128 (128 GB).
- **Aspect Ratio & Subtitle Fidelity:** Direct 16:9 widescreen anamorphic scaling and automated PGS/SRT subtitle conversion into standard DVD subpictures (`dvdsub`) with remote-selectable tracks.
- **Full-Duration Chapter Generation:** Automatically extracts embedded chapter markers from source files or creates 5-minute interval chapters across the full duration of the title.
- **Direct Optical Disc Burning & ISO Mastering:** Native hardware drive discovery (`/dev/sr*`, `/dev/sg*`), burning via `growisofs` and `cdrskin`/`xorriso`, and standalone ISO burner tab.
- **Job & Queue Management:** Asynchronous pipeline orchestration with pause, resume (via `SIGSTOP`/`SIGCONT`), cancellation, and automatic sequential queue pickup when an active job finishes.
- **Real-Time Telemetry:** Live WebSocket updates streaming CPU %, RAM, GPU %, VRAM, temperature, encoding FPS, speed multiplier (e.g. `4.09x`), and ETA.

---

## 2. Technical Stack & Dependencies

### Backend
- **Language:** Python 3.10+ (Ubuntu 22.04 runtime base)
- **Framework:** FastAPI + Starlette + Pydantic v2 + Uvicorn
- **Concurrency:** `asyncio` subprocess execution, non-blocking stream readers, listener broadcast queues
- **System Telemetry:** `psutil` + `/proc` fallback + `nvidia-smi` CLI query parsing

### Frontend
- **Architecture:** Single-Page Application (SPA) in Vanilla HTML5 / ES6 JavaScript / CSS3 (No external frameworks, React, or CDNs required).
- **Design System:** Dark-mode theme with curated design tokens, dynamic disc capacity gauge, live log terminal with auto-scroll, responsive cards, and real-time hardware telemetry chips.

### Media Authoring & Optical Utilities (Container Binaries)
- **`ffmpeg` / `ffprobe`:** Video scaling, stream mapping, audio transcoding to AC3, subtitle conversion (`dvdsub`), progress telemetry parsing.
- **`dvdauthor`:** DVD-Video titleset generation (`VIDEO_TS`), PGC navigation, audio/subtitle language assignment.
- **`tsMuxeR` (v2.7.0):** Blu-ray BDMV structure authoring and chapter formatting.
- **`genisoimage`:** DVD-Video UDF bridge ISO mastering (`-dvd-video -udf`).
- **`xorriso`:** Blu-ray UDF 2.50 ISO mastering.
- **`growisofs` (`dvd+rw-tools`):** Direct DVD optical burning with buffer underrun protection.
- **`cdrskin` / `wodim`:** Direct Blu-ray optical burning (`-dao`).
- **`lsscsi` / `sg3-utils` / `pciutils`:** SCSI device discovery and optical drive probing.

---

## 3. Disc Target Capacities & Sector Budgeting

| Disc Format | Physical Type | Target Capacity | Usable Sector Budget | Max Video Bitrate | Audio Format | Video Format |
| :--- | :--- | :---: | :---: | :---: | :--- | :--- |
| **DVD-5** | Single Layer | 4.7 GB | **4,300 MB** | 8,000 kbps | AC3 Stereo/5.1 (48kHz) | MPEG-2 (NTSC 720×480 / PAL 720×576) |
| **DVD-9** | Dual Layer | 8.5 GB | **7,850 MB** | 8,000 kbps | AC3 Stereo/5.1 (48kHz) | MPEG-2 (NTSC 720×480 / PAL 720×576) |
| **BD-25** | Single Layer | 25.0 GB | **23,000 MB** | 35,000 kbps | AC3 Stereo/5.1 | H.264 High@L4.1 (1080p) |
| **BD-50** | Dual Layer | 50.0 GB | **46,000 MB** | 35,000 kbps | AC3 Stereo/5.1 | H.264 High@L4.1 (1080p) |
| **BD-66** | Dual Layer UHD | 66.0 GB | **61,500 MB** | 35,000 kbps | AC3 Stereo/5.1 | H.264 / HEVC UHD-BD |
| **BD-100** | Triple Layer BDXL | 100.0 GB | **92,000 MB** | 35,000 kbps | AC3 Stereo/5.1 | H.264 / HEVC BDXL |
| **BD-128** | Quad Layer BDXL | 128.0 GB | **118,000 MB** | 35,000 kbps | AC3 Stereo/5.1 | H.264 / HEVC BDXL |

*Note on Safe Outer-Edge Margins:* DVDCompress intentionally targets ~4,300 MB on DVD-5 and ~7,850 MB on DVD-9 to stay safely away from the outer 10% edge of recordable media where dye thinning causes laser tracking errors on older players.

---

## 4. Codebase Architecture & Key Files

```
DVDCompress/
├── .github/
│   └── workflows/
│       └── docker-publish.yml     # Automated Docker Hub multi-arch build on push to main
├── docs/
│   └── icon.png                   # Official 512x512 PNG brand icon
├── src/
│   └── dvdcompress/
│       ├── __init__.py            # Package entrypoint and version definition (v1.0.0)
│       ├── api.py                 # FastAPI routes, WebSocket handler, standalone ISO burn pipeline
│       ├── authoring.py           # dvdauthor.xml and tsMuxeR meta specification generators
│       ├── burner.py              # lsscsi drive discovery, growisofs/cdrskin command builder & progress parser
│       ├── calculator.py          # Mathematical bitrate and sector capacity allocation engine
│       ├── config.py              # Environment variable configuration and path settings
│       ├── iso.py                 # genisoimage and xorriso command generators
│       ├── job_manager.py         # Async multi-stage pipeline manager, SIGSTOP pause/resume, auto-pickup queue
│       ├── models.py              # Domain Pydantic models (DiscType, TVStandard, JobStage, MediaInfo, etc.)
│       ├── probe.py               # ffprobe JSON runner and stream/chapter/subtitle metadata extractor
│       ├── system_info.py         # psutil CPU/RAM and nvidia-smi GPU telemetry reader
│       └── static/                # Single-Page Web UI
│           ├── index.html         # Semantic HTML5 layout with live telemetry chips and capacity gauge
│           ├── css/
│           │   └── style.css      # Dark-mode design system with responsive tokens
│           └── js/
│               └── app.js         # ES6 application controller, WebSocket client, dynamic gauge updater
├── tests/
│   ├── test_api.py                # REST API and WebSocket test suite
│   ├── test_authoring.py          # dvdauthor XML and tsMuxeR meta generation tests
│   ├── test_burner.py             # Drive parsing and burning command generation tests
│   ├── test_calculator.py         # Bitrate budgeting and disc capacity clamping tests
│   ├── test_e2e.py                # 15 comprehensive end-to-end integration tests
│   ├── test_job_manager.py        # Job lifecycle, pause/resume, and auto-resume tests
│   ├── test_probe.py              # ffprobe parsing and fallback tests
│   ├── test_transcoder.py         # FFmpeg transcode command structure and progress line parsing tests
│   └── test_ui.py                 # Static file serving and HTML layout tests
├── Dockerfile                     # Multi-stage CUDA 12.4.1 Ubuntu container definition with tsMuxeR
├── entrypoint.sh                  # Startup script verifying GPU, directory permissions, and launching Uvicorn
├── docker-compose.yml             # Standard Docker Compose configuration with GPU and optical passthrough
├── unraid-template.xml            # Official Unraid Community Applications template XML
├── pyproject.toml                 # Packaging, dependencies, build settings, and pytest configuration
└── README.md                      # Public GitHub documentation
```

---

## 5. Deployment & Configuration

### Environment Variables

| Variable | Default | Purpose |
| :--- | :--- | :--- |
| `DVDCOMPRESS_HOST` / `HOST` | `0.0.0.0` | Bind IP for web server |
| `DVDCOMPRESS_PORT` / `PORT` | `8080` | Web server listening port |
| `DVDCOMPRESS_MEDIA_DIR` / `MEDIA_DIR` | `/media` | Source video file storage |
| `DVDCOMPRESS_OUTPUT_DIR` / `OUTPUT_DIR` | `/output` | Destination for created ISOs |
| `DVDCOMPRESS_CONFIG_DIR` / `CONFIG_DIR` | `/config` | Application persistent config storage |
| `DVDCOMPRESS_TEMP_DIR` / `TEMP_DIR` | `/tmp/dvdcompress` | Working scratch directory |
| `DVDCOMPRESS_LOG_LEVEL` / `LOG_LEVEL` | `INFO` | Verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `NVIDIA_VISIBLE_DEVICES` | `all` | GPU passthrough selector |
| `NVIDIA_DRIVER_CAPABILITIES` | `all,video,compute,utility` | Enables NVENC/NVDEC in container |

### Unraid OS Template Settings
- **Repository:** `hovee/dvdcompress:latest`
- **Privileged:** `true` (Required for optical burner SCSI ioctl access)
- **Path 1 (Media):** `/mnt/user/Media` $\rightarrow$ `/media` *(Read-only)*
- **Path 2 (Output):** `/mnt/user/Media/dvd_output` $\rightarrow$ `/output` *(Read/Write)*
- **Path 3 (Config):** `/mnt/user/appdata/dvdcompress` $\rightarrow$ `/config`
- **Devices:** `/dev/sr0`, `/dev/sg0`
- **Extra Parameters:** `--gpus all --runtime=nvidia`

---

## 6. Testing & CI/CD Workflow

### Running Automated Test Suite
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest tests/ -v
```
*Current test suite:* **87 tests passing 100%**.

### Automated Release Pipeline
Pushes to the `main` branch trigger `.github/workflows/docker-publish.yml`, which runs unit tests and automatically builds and pushes the multi-platform container to **`hovee/dvdcompress:latest`** on Docker Hub.
