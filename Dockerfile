FROM nvidia/cuda:12.4.1-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

# Install runtime dependencies, optical burning tools, and authoring utilities
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
    git \
    cmake \
    g++ \
    make \
    pkg-config \
    zlib1g-dev \
    libfreetype6-dev \
    && git clone --depth 1 https://github.com/justdan96/tsMuxer.git /tmp/tsmuxer-src \
    && cd /tmp/tsmuxer-src && mkdir build && cd build && cmake ../ -DTSMUXER_STATIC_BUILD=ON && make -j$(nproc) \
    && find /tmp/tsmuxer-src -type f -perm /111 \( -name "*tsMux*" -o -name "*tsmuxer*" \) -exec cp {} /usr/local/bin/tsMuxeR \; \
    && ln -sf /usr/local/bin/tsMuxeR /usr/local/bin/tsmuxer \
    && chmod +x /usr/local/bin/tsMuxeR /usr/local/bin/tsmuxer 2>/dev/null || true \
    && cd / && rm -rf /tmp/tsmuxer-src \
    && apt-get purge -y --auto-remove git cmake g++ make pkg-config zlib1g-dev libfreetype6-dev \
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
