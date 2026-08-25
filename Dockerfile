FROM nvidia/cuda:12.4.1-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

# Install repository keys, Jellyfin hardware-accelerated FFmpeg (with tonemap_cuda, scale_cuda), optical burning tools, and authoring utilities
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    gnupg \
    && install -m 0755 -d /etc/apt/keyrings \
    && curl -fsSL https://repo.jellyfin.org/jellyfin_team.gpg.key | gpg --dearmor -o /etc/apt/keyrings/jellyfin.gpg \
    && chmod 644 /etc/apt/keyrings/jellyfin.gpg \
    && echo "deb [signed-by=/etc/apt/keyrings/jellyfin.gpg] https://repo.jellyfin.org/ubuntu jammy main" > /etc/apt/sources.list.d/jellyfin.list \
    && apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-setuptools \
    jellyfin-ffmpeg6 \
    ffmpeg \
    dvdauthor \
    genisoimage \
    dvd+rw-tools \
    cdrskin \
    xorriso \
    wodim \
    lsscsi \
    sg3-utils \
    pciutils \
    fonts-dejavu-core \
    fonts-liberation \
    unzip \
    && ln -sf /usr/lib/jellyfin-ffmpeg/ffmpeg /usr/local/bin/ffmpeg \
    && ln -sf /usr/lib/jellyfin-ffmpeg/ffprobe /usr/local/bin/ffprobe \
    && curl -fsSL -o /tmp/tsmuxer.zip https://github.com/justdan96/tsMuxer/releases/download/2.7.0/tsMuxer-2.7.0-linux.zip \
    && unzip -q /tmp/tsmuxer.zip -d /usr/local/bin/ \
    && ln -sf /usr/local/bin/tsMuxeR /usr/local/bin/tsmuxer \
    && chmod +x /usr/local/bin/tsMuxeR /usr/local/bin/tsmuxer \
    && rm -f /tmp/tsmuxer.zip \
    && apt-get purge -y --auto-remove unzip \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy application source and configuration
COPY pyproject.toml /app/
COPY src/ /app/src/
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Upgrade pip tooling and install Python package with static web assets
RUN pip3 install --no-cache-dir --upgrade pip setuptools wheel && pip3 install --no-cache-dir /app

EXPOSE 8080

VOLUME ["/media", "/output", "/config", "/tmp/dvdcompress"]

ENTRYPOINT ["/app/entrypoint.sh"]
