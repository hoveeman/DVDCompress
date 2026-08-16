# DVDCompress: Hardware-Accelerated DVD & Blu-ray Authoring and Burning Web Application

**Date:** 2026-08-16  
**Status:** Approved  
**Author:** Antigravity  

## 1. Overview & Goals

DVDCompress is an open-source, containerized web application designed for creating standard, standalone-playable DVD-Video (`VIDEO_TS`) and Blu-ray (`BDMV`) discs or ISO images from arbitrary unencrypted video files (MP4, MKV, AVI, MOV, TS, WebM, etc.).

The system is delivered as a self-contained Docker container suitable for deployment on Docker CLI, Docker Compose, Unraid, TrueNAS SCALE, Synology, and Portainer with GPU hardware acceleration (NVIDIA NVENC/NVDEC) and optical drive pass-through.

### Core Capabilities
- **Universal Video Input:** Accepts unencrypted video files of any container/codec.
- **Smart Target Sizing & Bitrate Calculator:** Automatic duration analysis and budget calculation across 1 to $N$ video files to fit:
  - DVD-5 Single Layer (~4.7 GB nominal / 4.30 GiB target budget)
  - DVD-9 Dual Layer (~8.5 GB nominal / 7.85 GiB target budget)
  - BD-25 Single Layer Blu-ray (~25 GB nominal / 23.00 GiB target budget)
  - BD-50 Dual Layer Blu-ray (~50 GB nominal / 46.00 GiB target budget)
- **Standard-Compliant Authoring:**
  - **DVD-Video:** MPEG-2 video (NTSC 720x480 / PAL 720x576), AC3 audio (Stereo / 5.1), `dvdauthor` VTS structure, standard chapters, and optional menu generation.
  - **Blu-ray (BDMV):** H.264/AVC High Profile 4.1, AC3/PCM audio, `tsMuxeR` BDMV structure.
- **Hardware Acceleration:** NVIDIA NVDEC decode acceleration for all input formats; NVIDIA NVENC encoding for Blu-ray; multi-core CPU encoding for DVD MPEG-2 with matrix optimizations and fallback.
- **Optical Drive Management:** Real-time discovery of passed-through optical drives (`/dev/sr*`, `/dev/sg*`), disc media status detection, and direct burning with buffer underrun protection via `growisofs` and `cdrskin`/`xorriso`.
- **Modern Responsive Web UI:** Real-time WebSocket pipeline tracking, interactive directory browser for `/media`, stream selector (audio/subtitles), bitrate gauge, menu customization, and direct ISO burner.

---

## 2. System Architecture & Docker Deployment

### 2.1 Container Architecture
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
|  |  - mediainfo   |  |  - mkisofs      |  |  - lsscsi       |           |
|  +----------------+  +-----------------+  +-----------------+           |
+-------------------------------------------------------------------------+
       |                                   |                    |
       v (Mounts)                          v (GPU Passthrough)  v (Device)
   /media  (Source Videos)              --gpus all          /dev/sr0, /dev/sg0
   /output (Authored ISOs)             (NVIDIA Container)    (Optical Writer)
   /config (App Settings)
```

### 2.2 Volume & Device Mappings
| Mount / Device | Container Path | Purpose |
| :--- | :--- | :--- |
| `Host /path/to/media` | `/media` | Source video directories (read-only or read-write) |
| `Host /path/to/output` | `/output` | Destination for created `.iso` files |
| `Host /path/to/config` | `/config` | Application configuration & job history |
| `Host /path/to/temp` | `/tmp/dvdcompress` | Scratch directory for transcode and authoring stages |
| `/dev/sr0` | `/dev/sr0` | Optical writer block device |
| `/dev/sg0` | `/dev/sg0` | Optical writer SCSI generic device (required for burning commands) |
| NVIDIA GPU | `--gpus all` | GPU hardware transcoding support |

### 2.3 Docker CLI Execution Example
```bash
docker run -d \
  --name dvdcompress \
  --restart unless-stopped \
  --gpus all \
  --device /dev/sr0:/dev/sr0 \
  --device /dev/sg0:/dev/sg0 \
  -p 8080:8080 \
  -v /mnt/user/media:/media:ro \
  -v /mnt/user/dvd_output:/output \
  -v /mnt/user/appdata/dvdcompress:/config \
  -v /tmp/dvdcompress:/tmp/dvdcompress \
  dvdcompress:latest
```

---

## 3. Media Analysis & Bitrate Calculation

### 3.1 Target Disc Capacities
To prevent disc overflow errors and account for filesystem table overhead (ISO 9660 + UDF 1.02 / UDF 2.50) and MPEG-PS / MPEG-TS container overhead (~3.5%):
- **DVD-5 (Single Layer):** $4,300 \text{ MB} = 34,400,000 \text{ kbits}$
- **DVD-9 (Dual Layer):** $7,850 \text{ MB} = 62,800,000 \text{ kbits}$
- **BD-25 (Single Layer Blu-ray):** $23,000 \text{ MB} = 184,000,000 \text{ kbits}$
- **BD-50 (Dual Layer Blu-ray):** $46,000 \text{ MB} = 368,000,000 \text{ kbits}$

### 3.2 Dynamic Bitrate Allocation Formula
For a project with $N$ video files having durations $T_1, T_2, \dots, T_N$:
1. Total Duration: $T_{total} = \sum_{i=1}^N T_i$
2. Audio Bitrate Allocation:
   - AC3 Stereo (2.0): $192 \text{ kbps}$
   - AC3 5.1 Surround: $384 \text{ kbps}$ (or $448 \text{ kbps}$)
   - Total Audio Bits: $B_{audio} = \sum_{i=1}^N (R_{audio, i} \times T_i)$
3. Muxing Overhead Factor: $M_{overhead} = 0.96$
4. Available Video Bit Budget:
   $$B_{video} = (B_{target\_disc} \times M_{overhead}) - B_{audio}$$
5. Target Video Bitrate:
   $$R_{video} = \frac{B_{video}}{T_{total}}$$
6. Standard DVD Constraint Clamping:
   - Minimum: $2,000 \text{ kbps}$
   - Maximum: $8,000 \text{ kbps}$
   - Max Combined Video+Audio+Subtitles: $\le 9,800 \text{ kbps}$

---

## 4. Transcoding & Authoring Pipeline

### 4.1 DVD-Video Workflow (`VIDEO_TS`)
1. **Analysis:** `ffprobe` probes input stream codecs, frame rate, aspect ratio, audio channels, and embedded chapters.
2. **Video Transcoding:**
   - **Decoder:** NVDEC (`-hwaccel cuda`) or multi-threaded CPU.
   - **Encoder:** `mpeg2video` with strict DVD parameters:
     - GOP size: 12 frames (NTSC) or 15 frames (PAL).
     - Framerate: 29.97 fps (NTSC) or 25 fps (PAL).
     - Aspect ratio: 16:9 widescreen anamorphic (or 4:3) with `-aspect 16:9 -vf "scale=720:480:force_original_aspect_ratio=decrease,pad=720:480:(ow-iw)/2:(oh-ih)/2"`.
     - Buffer size: `-bufsize 1835k -maxrate 8500k`.
3. **Audio Transcoding:** `ac3` audio at 48,000 Hz sample rate.
4. **MPEG-2 Program Stream Muxing:** FFmpeg outputs DVD-compliant `.mpg` VOB streams (`-f dvd`).
5. **Authoring with `dvdauthor`:**
   - Generates XML authoring specification specifying chapters, titlesets, and playback sequence.
   - Handles auto-play or menu structure.
   - Runs `dvdauthor -o /tmp/dvdcompress/author_dir -x dvdauthor.xml` to construct `VIDEO_TS` and `AUDIO_TS`.
6. **ISO Creation:**
   - `genisoimage -dvd-video -udf -V "DISC_LABEL" -o /output/disc.iso /tmp/dvdcompress/author_dir`.

### 4.2 Blu-ray Workflow (`BDMV`)
1. **Video Transcoding:**
   - H.264 High Profile Level 4.1 via `h264_nvenc` or `libx264`.
   - GOP structure: `-g 24 -keyint_min 1 -bf 3 -slices 4`.
2. **Audio Transcoding:** AC3 5.1/Stereo or PCM audio.
3. **BDMV Authoring with `tsMuxeR`:**
   - Generates `tsMuxeR.meta` configuration.
   - Produces standard `BDMV` and `CERTIFICATE` folders.
4. **ISO Creation:**
   - `xorriso -as mkisofs -iso-level 3 -udf -V "DISC_LABEL" -o /output/disc.iso /tmp/dvdcompress/author_dir`.

### 4.3 Menu Generation
- **Static / Motion Backdrop:** Auto-generates a clean 16:9 menu canvas containing:
  - Disc Title header.
  - Video thumbnail cards with runtime and title text.
  - "Play All" and individual title select buttons.
- **Button Highlights:** Generated via `spumux` subpictures for interactive remote navigation.

---

## 5. Optical Drive Discovery & Burning Engine

### 5.1 Optical Device Scanner
- Auto-detects connected SATA / USB optical writers via `/sys/block/sr*`, `/dev/sr*`, `/dev/sg*`, and SCSI inquiry (`lsscsi -k`, `cdrskin --devices`).
- Queries drive status for inserted media type: Blank DVD+R, DVD-R, DVD+R DL, BD-R, BD-RE, or No Media.

### 5.2 Burning Pipeline
- **DVD Burning:**
  ```bash
  growisofs -dvd-compat -speed=4 -Z /dev/sr0=/path/to/disc.iso
  ```
- **Blu-ray Burning:**
  ```bash
  cdrskin -v dev=/dev/sr0 speed=4 gracetime=2 -dao /path/to/disc.iso
  ```
- **Features:** Buffer underrun protection enabled, auto-eject on completion, verify step option.

---

## 6. Web Application UI & Features

### 6.1 UI Views
1. **Disc Builder & Project Setup:**
   - Media file picker with search & folder navigation (`/media`).
   - Project playlist queue (drag & drop reorder, multi-file aggregate duration).
   - Target Media Selector: `DVD-5 (4.7 GB)`, `DVD-9 (8.5 GB)`, `BD-25 (25 GB)`, `BD-50 (50 GB)`.
   - Bitrate Capacity Gauge: Visual progress bar showing Disc Utilization %, Video Bitrate, Audio Bitrate, Mux Overhead.
   - Stream Settings: Audio track selection (Stereo / 5.1 Surround), subtitle options.
   - Authoring Settings: TV Standard (Auto / NTSC / PAL), Aspect Ratio (16:9 / 4:3), Menu Mode (Auto-play / Interactive Menu), Disc Label.
   - Action Trigger: `Author & Burn to Disc` or `Create ISO Image Only`.
2. **Real-Time Job Telemetry:**
   - Progress bar with multi-phase tracking:
     1. Probing & Bitrate Planning $\rightarrow$ 2. Transcoding $\rightarrow$ 3. Authoring VTS/BDMV $\rightarrow$ 4. Creating ISO $\rightarrow$ 5. Burning Disc.
   - Real-time transcode FPS, current frame, percentage, elapsed time, ETA.
   - Live hardware status widget (GPU utilization %, VRAM usage, CPU usage).
   - Expandable live log terminal stream.
3. **Standalone ISO Burner:**
   - File picker for existing `.iso` files in `/output`.
   - Drive selector + burn speed + Burn button.
4. **History & Settings:**
   - Completed jobs log, download links for ISOs, default drive selection, hardware acceleration preferences.

---

## 7. Testing & Verification Plan

### 7.1 Automated Unit & Integration Tests
- **Bitrate Calculation Tests:** Verify mathematical accuracy and edge cases (single 5-minute video, 6 episodes totaling 4 hours, dual-layer budgeting).
- **FFmpeg Command Builder Tests:** Validate generated transcode arguments for NTSC/PAL DVD and Blu-ray with and without GPU flags.
- **Authoring XML/Meta Generators:** Validate `dvdauthor.xml` and `tsMuxeR.meta` schema compliance.
- **Drive Discovery Parser:** Test parsing of SCSI/sysfs device outputs.

### 7.2 End-to-End Functional Verification
- Transcode a test video file into standard DVD `VIDEO_TS` structure.
- Verify `VIDEO_TS` contains valid `VIDEO_TS.IFO`, `VTS_01_0.IFO`, and compliant MPEG-2 VOBs.
- Create UDF/ISO 9660 bridge `.iso` image and mount/verify directory structure.
- Test WebSocket real-time progress broadcast.
