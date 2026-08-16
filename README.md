# DVDCompress

<div align="center">

![DVDCompress Banner](https://raw.githubusercontent.com/placeholder/dvdcompress/main/docs/banner.png)

**Hardware-Accelerated DVD-Video & Blu-ray Transcoding, Authoring, and Burning in Docker**

[![Docker Image](https://img.shields.io/badge/docker-ready-blue.svg?logo=docker&logoColor=white)](https://hub.docker.com)
[![CUDA Version](https://img.shields.io/badge/CUDA-12.4.1-76B900.svg?logo=nvidia&logoColor=white)](https://developer.nvidia.com/cuda-toolkit)
[![Python Version](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue.svg?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

[Features](#-features) • [Quick Start](#-quick-start) • [Deployment](#-deployment-guides) • [Hardware Acceleration](#-hardware-acceleration) • [Optical Burning](#-optical-drive-pass-through) • [API & Architecture](#-architecture--api)

</div>

---

## 📖 Overview

**DVDCompress** is an open-source, self-hosted web application that transforms arbitrary modern video files (`.mp4`, `.mkv`, `.avi`, `.mov`, `.ts`, `.webm`, etc.) into 100% standard-compliant, standalone-playable **DVD-Video** (`VIDEO_TS`) and **Blu-ray** (`BDMV`) physical discs or ISO images.

Equipped with a real-time mathematical bitrate budget calculator, NVIDIA GPU decode/encode acceleration, automatic optical drive discovery, and a responsive web interface, DVDCompress eliminates the complexity of optical authoring on modern home servers and NAS systems.

---

## ✨ Features

- 🎞️ **Universal Video Ingest:** Accepts single videos or multi-episode season playlists in any container format, video codec (H.264, HEVC, AV1, VP9, MPEG-4), and audio codec (AC3, AAC, DTS, TrueHD, FLAC).
- 🧮 **Dynamic Bitrate Budgeting Engine:** Calculates optimal video and audio bitrates across $N$ inputs with precision filesystem overhead allocation (UDF/ISO 9660 + MPEG multiplexing factors) to guarantee disc fit without overflow:
  - **DVD-5 (Single Layer):** 4.30 GiB target budget (~4,300 MB)
  - **DVD-9 (Dual Layer):** 7.85 GiB target budget (~7,850 MB)
  - **BD-25 (Single Layer Blu-ray):** 23.00 GiB target budget (~23,000 MB)
  - **BD-50 (Dual Layer Blu-ray):** 46.00 GiB target budget (~46,000 MB)
- 📀 **Standard-Compliant Authoring:**
  - **DVD-Video:** MPEG-2 video (NTSC 720×480 @ 29.97fps / PAL 720×576 @ 25fps), 48kHz AC3 audio, `dvdauthor` VTS titlesets, automatic 16:9 widescreen anamorphic / 4:3 letterboxing, and chapter point preservation.
  - **Blu-ray (BDMV):** H.264/AVC High Profile Level 4.1, `tsMuxeR` BDMV/CERTIFICATE structures, and UDF 2.50 formatting.
- ⚡ **Hardware Acceleration:** Full NVIDIA NVDEC hardware decode for all common formats, NVIDIA NVENC hardware encoding for Blu-ray streams, and multi-core CPU matrix-optimized transcoding with automatic fallback.
- 🔥 **Direct Optical Disc Burning:** Real-time SCSI/SATA/USB optical drive detection (`/dev/sr*`, `/dev/sg*`), disc media status inspection, and rock-solid burning with buffer underrun protection via `growisofs` and `cdrskin`/`xorriso`.
- 🌐 **Modern Real-Time Web Interface:** Live WebSocket pipeline monitoring, interactive media directory navigation, real-time transcoding FPS/ETA telemetry, hardware GPU status gauges, and integrated log terminal stream.
- 💿 **Standalone ISO Burner:** Quickly burn existing ISO files directly to disc with custom burn speeds.

---

## 🏗 Architecture

```
+-------------------------------------------------------------------------+
|                              Docker Container                           |
|                                                                         |
|  +-----------------------+     +-------------------------------------+  |
|  |     Modern Web UI     | <-> | FastAPI Application Server (Python) |  |
|  |  (HTML5/CSS/Vanilla)  |     |  - REST API & WebSocket Handler     |  |
|  +-----------------------+     |  - Async Job Pipeline Engine        |  |
|                                +-------------------------------------+  |
|                                                   |                     |
|           +---------------------------------------+                     |
|           |                   |                   |                     |
|           v                   v                   v                     |
|  +----------------+  +-----------------+  +-----------------+           |
|  | Transcoding    |  | Disc Authoring  |  | Disc Burning    |           |
|  |  - FFmpeg      |  |  - dvdauthor    |  |  - growisofs    |           |
|  |  - NVDEC/CUDA  |  |  - spumux       |  |  - cdrskin      |           |
|  |  - NVENC / CPU |  |  - tsMuxeR      |  |  - xorriso      |           |
|  |  - ffprobe     |  |  - genisoimage  |  |  - lsscsi       |           |
|  +----------------+  +-----------------+  +-----------------+           |
+-------------------------------------------------------------------------+
       |                                   |                    |
       v (Volume Mounts)                   v (GPU Passthrough)  v (Device Pass)
   /media  (Source Videos)              --gpus all          /dev/sr0, /dev/sg0
   /output (Authored ISOs)             (NVIDIA Runtime)      (Optical Writer)
   /config (App Settings)
   /tmp/dvdcompress (Scratch)
```

---

## 🚀 Quick Start

### 1. Docker Compose (Recommended)

Create a `docker-compose.yml` file:

```yaml
services:
  dvdcompress:
    image: dvdcompress:latest
    container_name: dvdcompress
    restart: unless-stopped
    ports:
      - "8080:8080"
    environment:
      - TZ=America/New_York
      - DVDCOMPRESS_LOG_LEVEL=INFO
      - NVIDIA_VISIBLE_DEVICES=all
      - NVIDIA_DRIVER_CAPABILITIES=all,video,compute,utility
    volumes:
      - /path/to/your/media:/media:ro
      - /path/to/your/output:/output
      - /path/to/your/config:/config
      - /path/to/your/temp:/tmp/dvdcompress
    devices:
      - /dev/sr0:/dev/sr0
      - /dev/sg0:/dev/sg0
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu, video, compute, utility]
```

Launch the container:
```bash
docker compose up -d
```

Open your browser and navigate to: **`http://<your-server-ip>:8080`**

---

### 2. Docker CLI

#### GPU-Accelerated Mode (NVIDIA)
```bash
docker run -d \
  --name dvdcompress \
  --restart unless-stopped \
  --gpus all \
  --device /dev/sr0:/dev/sr0 \
  --device /dev/sg0:/dev/sg0 \
  -p 8080:8080 \
  -v /mnt/media:/media:ro \
  -v /mnt/dvd_output:/output \
  -v /mnt/appdata/dvdcompress:/config \
  -v /tmp/dvdcompress:/tmp/dvdcompress \
  -e TZ=UTC \
  dvdcompress:latest
```

#### CPU-Only Mode
```bash
docker run -d \
  --name dvdcompress \
  --restart unless-stopped \
  --device /dev/sr0:/dev/sr0 \
  --device /dev/sg0:/dev/sg0 \
  -p 8080:8080 \
  -v /mnt/media:/media:ro \
  -v /mnt/dvd_output:/output \
  -v /mnt/appdata/dvdcompress:/config \
  -v /tmp/dvdcompress:/tmp/dvdcompress \
  -e TZ=UTC \
  dvdcompress:latest
```

---

## 🖥 Deployment Guides

### Unraid OS
1. Install the **NVIDIA Driver** plugin from Community Applications (if using an NVIDIA GPU).
2. Add a new Docker Container in Unraid:
   - **Repository:** `dvdcompress:latest`
   - **WebUI:** `http://[IP]:[PORT:8080]`
   - **Port:** `8080` $\rightarrow$ `8080`
   - **Path 1 (Media):** `/mnt/user/media` $\rightarrow$ `/media` (Read-only)
   - **Path 2 (Output):** `/mnt/user/data/ISOs` $\rightarrow$ `/output` (Read/Write)
   - **Path 3 (Config):** `/mnt/user/appdata/dvdcompress` $\rightarrow$ `/config`
   - **Path 4 (Scratch):** `/tmp/dvdcompress` $\rightarrow$ `/tmp/dvdcompress`
   - **Device 1:** `/dev/sr0` $\rightarrow$ `/dev/sr0`
   - **Device 2:** `/dev/sg0` $\rightarrow$ `/dev/sg0`
   - **Extra Parameters:** `--gpus all --runtime=nvidia`
   - **Variables:** `NVIDIA_VISIBLE_DEVICES` = `all`, `NVIDIA_DRIVER_CAPABILITIES` = `all,video,compute,utility`

### TrueNAS SCALE
1. Go to **Apps** $\rightarrow$ **Launch Docker Image** (or Custom App).
2. Configure Image: `dvdcompress:latest`.
3. Set Port Forwarding: Host Port `8080` to Container Port `8080`.
4. Configure Host Path Storage Volumes for `/media`, `/output`, `/config`, and `/tmp/dvdcompress`.
5. Under **GPU Resource Allocation**, allocate 1 NVIDIA GPU.
6. Under **Device Passthrough**, add `/dev/sr0` and `/dev/sg0`.

### Synology DSM (Container Manager)
1. Open **Container Manager** $\rightarrow$ **Project** $\rightarrow$ **Create**.
2. Paste the `docker-compose.yml` configuration.
3. If running via Task Scheduler / SSH with optical drive access, pass `--device /dev/sr0:/dev/sr0 --device /dev/sg0:/dev/sg0`.

---

## ⚡ Hardware Acceleration

DVDCompress utilizes NVIDIA CUDA and NVDEC/NVENC to accelerate media transcoding:

| Feature | NVIDIA GPU (NVDEC/NVENC) | CPU (Fallback) |
| :--- | :--- | :--- |
| **Decode Acceleration** | Hardware NVDEC (`-hwaccel cuda`) | Multi-threaded Software |
| **DVD-Video Transcode** | NVDEC decode + MPEG-2 Video Encoder | `mpeg2video` Software Encoder |
| **Blu-ray Transcode** | `h264_nvenc` Hardware Encoder | `libx264` High Profile Level 4.1 |
| **Audio Processing** | Multi-channel AC3 encoder (Stereo / 5.1) | Multi-channel AC3 encoder |

> [!NOTE]
> Ensure the [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html) is installed on your host system for GPU passthrough.

---

## 💿 Optical Drive Pass-Through

To enable physical disc burning from inside Docker, pass both the optical block device (`/dev/sr*`) and the SCSI generic device (`/dev/sg*`):

1. **Identify connected optical drives on the host:**
   ```bash
   lsscsi -k
   # Example output: [2:0:0:0] cd/dvd HL-DT-ST BD-RE WH16NS40 /dev/sr0 /dev/sg0
   ```

2. **Verify host permissions:**
   ```bash
   ls -l /dev/sr0 /dev/sg0
   # If necessary, add container user or chmod:
   sudo usermod -aG cdrom $USER
   ```

3. **Pass devices to container:**
   ```yaml
   devices:
     - /dev/sr0:/dev/sr0
     - /dev/sg0:/dev/sg0
   ```

---

## ⚙️ Configuration & Environment Variables

| Variable | Default | Description |
| :--- | :--- | :--- |
| `DVDCOMPRESS_HOST` / `HOST` | `0.0.0.0` | IP interface to bind the FastAPI web server |
| `DVDCOMPRESS_PORT` / `PORT` | `8080` | Web server listening port |
| `DVDCOMPRESS_MEDIA_DIR` / `MEDIA_DIR` | `/media` | Base directory for scanning source video files |
| `DVDCOMPRESS_OUTPUT_DIR` / `OUTPUT_DIR` | `/output` | Destination directory for generated ISO files |
| `DVDCOMPRESS_CONFIG_DIR` / `CONFIG_DIR` | `/config` | Application persistent storage and configuration |
| `DVDCOMPRESS_TEMP_DIR` / `TEMP_DIR` | `/tmp/dvdcompress` | Working scratch directory for transcode buffers |
| `DVDCOMPRESS_LOG_LEVEL` / `LOG_LEVEL` | `INFO` | Logging verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `NVIDIA_VISIBLE_DEVICES` | `all` | Controls which GPUs are visible to the container |
| `NVIDIA_DRIVER_CAPABILITIES` | `all,video,compute,utility` | Enables NVENC/NVDEC driver capabilities in container |

---

## 📊 Technical Specifications & Capacities

| Disc Format | Physical Type | Target Capacity | Usable Budget | Max Video Bitrate | Audio Spec | Video Standard |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **DVD-5** | Single Layer | 4.7 GB | 4,300 MB | 8,000 kbps | AC3 Stereo/5.1 (48kHz) | MPEG-2 (NTSC 720×480 / PAL 720×576) |
| **DVD-9** | Dual Layer | 8.5 GB | 7,850 MB | 8,000 kbps | AC3 Stereo/5.1 (48kHz) | MPEG-2 (NTSC 720×480 / PAL 720×576) |
| **BD-25** | Single Layer | 25.0 GB | 23,000 MB | 35,000 kbps | AC3 Stereo/5.1 or PCM | H.264/AVC High@L4.1 (1080p/1080i/720p) |
| **BD-50** | Dual Layer | 50.0 GB | 46,000 MB | 35,000 kbps | AC3 Stereo/5.1 or PCM | H.264/AVC High@L4.1 (1080p/1080i/720p) |

---

## 📡 REST API & WebSocket Reference

DVDCompress provides a full REST and WebSocket API:

- `GET /api/health` — Application health check
- `GET /api/files?path=/media/...` — File browser listing playable video files and ISOs
- `POST /api/probe` — FFprobe media analysis (duration, codec, resolution, audio streams, chapters)
- `POST /api/calculate` — Bitrate budget calculation based on input durations and disc target
- `GET /api/drives` — Scan host system for optical drives and query disc media presence
- `GET /api/system` — NVIDIA GPU telemetry (utilization %, VRAM usage, temperature)
- `POST /api/jobs` — Create and start a transcoding/authoring/burning job
- `POST /api/burn-iso` — Directly burn an existing ISO file to an optical drive
- `GET /api/jobs` — Retrieve active and historical jobs
- `GET /api/jobs/{job_id}` — Get single job progress and telemetry
- `POST /api/jobs/{job_id}/cancel` — Cancel an in-progress job and terminate child processes
- `WS /ws/jobs/{job_id}` — Real-time bidirectional WebSocket stream for progress updates and live logs

---

## 🛠 Local Development & Testing

### Running with uv / virtualenv
```bash
# Clone the repository
git clone https://github.com/placeholder/dvdcompress.git
cd DVDCompress

# Create virtual environment and install dependencies
uv venv
source .venv/bin/activate
uv pip install -e ".[dev]"

# Run test suite
pytest tests/ -v

# Run local development server
uvicorn dvdcompress.api:app --host 127.0.0.1 --port 8080 --reload
```

### Building Docker Image Locally
```bash
docker build -t dvdcompress:latest .
```

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

<div align="center">
Built with ❤️ for home lab and physical media enthusiasts.
</div>
