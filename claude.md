# DVDCompress — Project Knowledge Base & Architecture Manual (Claude Context)

**Project Name:** DVDCompress  
**Version:** 1.0.0  
**GitHub Repository:** [https://github.com/hoveeman/DVDCompress](https://github.com/hoveeman/DVDCompress)  
**Docker Hub Registry:** [hovee/dvdcompress:latest](https://hub.docker.com/r/hovee/dvdcompress)  
**License:** MIT  

---

## 1. System Summary & Core Objective

DVDCompress is an automated, web-based media authoring and optical compression platform designed for Linux container environments (Unraid, TrueNAS, Synology, Docker Compose). It transforms modern video media into fully standard-compliant, standalone-playable **DVD-Video** (`VIDEO_TS`) and **Blu-ray** (`BDMV`) physical optical discs or ISO filesystem images.

The platform solves the challenge of authoring arbitrary digital files (`.mkv`, `.mp4`, etc.) to fixed-capacity optical discs without manual bitrate calculations, video aspect distortion, or failed burns.

---

## 2. Core Functional Subsystems

### A. Mathematical Bitrate Budgeting Engine (`calculator.py`)
- Calculates the optimal video bitrate ($R_v$) to fill target disc media without exceeding physical sector capacities:
  $$R_v = \frac{(C_{\text{target}} \times 8 \times 1024) - (D \times R_a) - M}{D}$$
  where:
  - $C_{\text{target}}$: Usable disc budget in Megabytes (factoring in UDF/ISO filesystem and outer-edge dye safety margins).
  - $D$: Total duration across all queued playlist video tracks in seconds.
  - $R_a$: Total allocated audio stream bitrates (e.g. 192 kbps AC3 stereo, 384–448 kbps 5.1).
  - $M$: MPEG Program Stream / Transport Stream packet muxing overhead (allocated at ~2.5%).
- Clamps bitrates to standard physical hardware player limits:
  - **DVD-Video:** Capped at 8,000 kbps (total bitrate $\le$ 9,800 kbps).
  - **Blu-ray:** Capped at 35,000 kbps.

### B. Transcoding & Hardware Acceleration Engine (`transcoder.py`)
- **NVIDIA GPU Acceleration:**
  - Decodes input video via NVDEC (`-hwaccel cuda`).
  - Blu-ray AVC/H.264 streams encoded via NVENC (`-c:v h264_nvenc -profile:v high -level 4.1`).
  - Transcoding progress parsed in real time (`fps`, `speed`, `eta`, `frame`) splitting on `\r` and `\n` to prevent buffer overflows.
- **CPU Fallback:**
  - Multi-threaded software encoding with `mpeg2video` (DVD) and `libx264 -bluray-compat 1` (Blu-ray).
- **Aspect Ratio Handling:**
  - Applies 16:9 Anamorphic scaling (`scale=720:480,setsar=32/27,setdar=16/9` for NTSC / `scale=720:576,setsar=64/45,setdar=16/9` for PAL) or 4:3 Fullscreen (`setsar=8/9,setdar=4/3`) without unwanted letterbox bars on 16:9 displays.
- **Subtitles:**
  - Automatically maps and converts PGS/SRT subtitles into DVD subpictures (`-map 0:s? -c:s dvdsub`).

### C. Disc Authoring & Mastering (`authoring.py`, `iso.py`)
- **DVD-Video:** Generates standard `dvdauthor.xml` with VTS titlesets, automatic 5-minute interval chapters (or extracted source chapters), `<video aspect="16:9" widescreen="nopanscan" />`, and `<subpicture>` language tracks.
- **Blu-ray:** Generates `tsMuxeR.meta` specifications and builds complete `BDMV` and `CERTIFICATE` hierarchies.
- **ISO Mastering:**
  - DVD: `genisoimage -dvd-video -udf -V <LABEL> -o <PATH.iso> <AUTHOR_DIR>`
  - Blu-ray: `xorriso -as mkisofs -iso-level 3 -udf -V <LABEL> -o <PATH.iso> <AUTHOR_DIR>`

### D. Optical Drive Scanner & Burning (`burner.py`)
- Discovers physical drives (`/dev/sr*`, `/dev/sg*`) using `lsscsi -g` with filesystem fallback.
- Direct burning with buffer underrun protection:
  - DVD: `growisofs -dvd-compat -speed=<X> -Z <DEV>=<ISO>`
  - Blu-ray: `cdrskin -v dev=<DEV> speed=<X> gracetime=2 -dao <ISO>`
- Merges and streams `stdout` and `stderr` directly to the live web log terminal for drive diagnostics.

### E. Asynchronous Job & Queue Orchestrator (`job_manager.py`)
- Coordinates pipeline stages: `ANALYZE` $\rightarrow$ `TRANSCODE` $\rightarrow$ `AUTHOR` $\rightarrow$ `MASTER_ISO` $\rightarrow$ `BURN` $\rightarrow$ `COMPLETED`.
- **Subprocess Suspension (`SIGSTOP`/`SIGCONT`):** Pauses and resumes active FFmpeg/burning processes cleanly without dropping open files.
- **Automatic Queue Pickup:** Automatically resumes the next paused/queued job when an active job finishes or cancels.
- Broadcasts updates via asynchronous WebSocket listener queues.

### F. Frontend Web Application (`src/dvdcompress/static/`)
- Single-page interface built with modern vanilla HTML5, CSS3, and ES6 JavaScript.
- Features: Media browser (`/media`), reorderable playlist, interactive disc capacity gauge, live CPU/RAM/GPU telemetry chips, standalone ISO burner, and active progress console.

---

## 3. Physical Disc Media Capacities

| Media Type | Layers | Physical Capacity | DVDCompress Usable Budget |
| :--- | :---: | :---: | :---: |
| **DVD-5** | Single | 4.7 GB (4.37 GiB) | **4,300 MB** |
| **DVD-9** | Dual | 8.5 GB (7.91 GiB) | **7,850 MB** |
| **BD-25** | Single | 25.0 GB (23.28 GiB) | **23,000 MB** |
| **BD-50** | Dual | 50.0 GB (46.56 GiB) | **46,000 MB** |
| **BD-66** | Dual (UHD) | 66.0 GB (61.46 GiB) | **61,500 MB** |
| **BD-100 (BDXL TL)** | Triple | 100.0 GB (93.13 GiB) | **92,000 MB** |
| **BD-128 (BDXL QL)** | Quad | 128.0 GB (119.20 GiB) | **118,000 MB** |

---

## 4. Key API Endpoints

- `GET /api/health` — Application health check
- `GET /api/files?path=<PATH>` — Directory explorer for `/media` and `/output`
- `POST /api/probe` — Media stream, audio track, subtitle, and chapter analysis via ffprobe
- `POST /api/calculate` — Dynamic bitrate budgeting calculation
- `GET /api/drives` — Optical writer discovery (`/dev/sr*`, `/dev/sg*`)
- `GET /api/system` — CPU %, RAM, GPU %, VRAM, and temperature telemetry
- `POST /api/jobs` — Create and start an authoring/transcode project
- `POST /api/burn-iso` — Burn existing ISO directly to disc
- `POST /api/jobs/{id}/pause` — Suspend running job via `SIGSTOP`
- `POST /api/jobs/{id}/resume` — Resume suspended job via `SIGCONT`
- `POST /api/jobs/{id}/cancel` — Cancel job and terminate child processes
- `WS /ws/jobs/{id}` — Real-time bidirectional WebSocket telemetry stream

---

## 5. Deployment & Configuration

### Standard Docker Run
```bash
docker run -d \
  --name dvdcompress \
  --restart unless-stopped \
  --privileged \
  --gpus all \
  --device /dev/sr0:/dev/sr0 \
  --device /dev/sg0:/dev/sg0 \
  -p 8080:8080 \
  -v /mnt/user/Media:/media:ro \
  -v /mnt/user/Media/dvd_output:/output:rw \
  -v /mnt/user/appdata/dvdcompress:/config:rw \
  -v /tmp/dvdcompress:/tmp/dvdcompress:rw \
  hovee/dvdcompress:latest
```

### Unraid XML Template (`unraid-template.xml`)
- Template URL: `https://raw.githubusercontent.com/hoveeman/DVDCompress/main/unraid-template.xml`
- Icon URL: `https://raw.githubusercontent.com/hoveeman/DVDCompress/main/docs/icon.png`
- Default Mappings: `/media` $\rightarrow$ `/mnt/user/Media`, `/output` $\rightarrow$ `/mnt/user/Media/dvd_output`.
- Privileged: `true`.

---

## 6. Testing Suite & Verification

The test suite covers unit, functional, and end-to-end integration flows:
- **`pytest tests/ -v`** executes **87 test cases** across all components.
- Automated CI on GitHub Actions compiles the Docker image and publishes directly to `hovee/dvdcompress:latest`.
