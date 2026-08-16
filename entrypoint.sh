#!/bin/bash
set -e

echo "========================================================"
echo "                DVDCompress Container Starting          "
echo "========================================================"
echo "Python:    $(python3 --version 2>&1)"
echo "FFmpeg:    $(ffmpeg -version 2>&1 | head -n 1 || echo 'FFmpeg available')"
echo "dvdauthor: $(dvdauthor --version 2>&1 | head -n 1 || echo 'dvdauthor installed')"
echo "growisofs: $(growisofs --version 2>&1 | head -n 1 || echo 'growisofs installed')"
echo "cdrskin:   $(cdrskin --version 2>&1 | head -n 1 || echo 'cdrskin installed')"
echo "xorriso:   $(xorriso --version 2>&1 | head -n 1 || echo 'xorriso installed')"

# Check tsMuxeR availability
if command -v tsMuxeR &> /dev/null; then
    echo "tsMuxeR:   Installed (/usr/local/bin/tsMuxeR)"
else
    echo "tsMuxeR:   Not found (Blu-ray authoring will require tsMuxeR)"
fi

# Ensure runtime directories exist
mkdir -p "${MEDIA_DIR:-/media}"
mkdir -p "${OUTPUT_DIR:-/output}"
mkdir -p "${CONFIG_DIR:-/config}"
mkdir -p "${SCRATCH_DIR:-${TEMP_DIR:-/tmp/dvdcompress}}"

# Verify GPU access
echo "--------------------------------------------------------"
echo "Hardware Acceleration Telemetry:"
if command -v nvidia-smi &> /dev/null; then
    echo "NVIDIA GPU Detected:"
    nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader || echo "NVIDIA SMI query returned non-zero"
else
    echo "Running in CPU-only mode (No NVIDIA GPU detected or --gpus flag omitted)."
fi
echo "========================================================"

HOST="${DVDCOMPRESS_HOST:-${HOST:-0.0.0.0}}"
PORT="${DVDCOMPRESS_PORT:-${PORT:-8080}}"
LOG_LEVEL="${DVDCOMPRESS_LOG_LEVEL:-${LOG_LEVEL:-info}}"

echo "Launching DVDCompress web server on http://${HOST}:${PORT} (Log Level: ${LOG_LEVEL})"
exec uvicorn dvdcompress.api:app --host "${HOST}" --port "${PORT}" --log-level "$(echo "$LOG_LEVEL" | tr '[:upper:]' '[:lower:]')"
