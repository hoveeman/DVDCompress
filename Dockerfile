FROM nvidia/cuda:12.4.1-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

# Install system dependencies, optical burning tools, and authoring utilities
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-setuptools \
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
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install tsMuxeR for Blu-ray BDMV authoring
RUN curl -L -o /tmp/tsmuxer.tar.gz https://github.com/justdan96/tsMuxer/releases/download/nightly-2024-01-01-02-10-34/tsMuxeR-2.6.12-linux.tar.gz \
    && tar -xzf /tmp/tsmuxer.tar.gz -C /usr/local/bin/ tsMuxeR 2>/dev/null || true \
    && chmod +x /usr/local/bin/tsMuxeR 2>/dev/null || true \
    && rm -f /tmp/tsmuxer.tar.gz

WORKDIR /app

# Copy application files
COPY pyproject.toml /app/
COPY src/ /app/src/
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Install Python requirements
RUN pip3 install --no-cache-dir -e /app

EXPOSE 8080

VOLUME ["/media", "/output", "/config", "/tmp/dvdcompress"]

ENTRYPOINT ["/app/entrypoint.sh"]
