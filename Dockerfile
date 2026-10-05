FROM debian:trixie-slim

ENV DEBIAN_FRONTEND=noninteractive

# Install dependencies: Audio, Icecast, DarkIce, PulseAudio, Bluetooth and Python
RUN apt-get update && apt-get install -y --no-install-recommends \
    icecast2 \
    darkice \
    pulseaudio \
    pulseaudio-module-bluetooth \
    bluez \
    bluez-tools \
    python3 \
    curl \
    procps \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy system configurations
COPY icecast.xml /etc/icecast2/icecast.xml
COPY darkice.cfg /etc/darkice.cfg

# Copy scripts & binaries
COPY phonos-status-api.py /usr/local/bin/phonos-status-api.py
COPY bt-turntable-autoconnect.sh /usr/local/bin/bt-turntable-autoconnect.sh
COPY entrypoint.sh /app/entrypoint.sh

# Permissions setup
RUN chmod +x /usr/local/bin/phonos-status-api.py \
             /usr/local/bin/bt-turntable-autoconnect.sh \
             /app/entrypoint.sh \
    && chown -R icecast2:icecast /etc/icecast2

EXPOSE 8080 8000

ENTRYPOINT ["/app/entrypoint.sh"]
