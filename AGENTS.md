# AGENTS.md — turntable-bridge

## Purpose
`turntable-bridge` is a specialized streaming and Bluetooth bridge appliance designed to ingest audio from a Bluetooth turntable (A2DP source, e.g. Fenton recordplayer `AD:60:17:9B:D5:AC`) and stream it over the local network via Icecast (`/sonos.mp3`) for Sonos, Home Assistant, and browser players.

## Architecture
- **Bluetooth Stack**: BlueZ (`bluetoothd`) + `bt-agent` (NoInputNoOutput) + `bt-turntable-autoconnect.sh`
- **Audio Routing**: PulseAudio (`module-switch-on-connect`, `module-bluez5-device`)
- **Streaming Engine**: DarkIce (MP3 live encoder 256kbps) -> Icecast2 (HTTP audio mountpoint on port 8000)
- **Control API & UI**: Python 3 HTTP server (`phonos-status-api.py`) on port 8080 with Swagger UI (`/docs`), OpenAPI 3.0 (`/openapi.json`), REST endpoints (`/api`), Home Assistant/Sonos cast integration (`/api/sonos/play`, `/api/sonos/stop`), and real-time accessible web dashboard (`/`).

## Key Files
- `Dockerfile`: Debian Trixie container containing BlueZ, PulseAudio, DarkIce, Icecast2, and Python API.
- `docker-compose.yml`: Compose definition with host networking and D-Bus pass-through.
- `entrypoint.sh`: Container bootstrap script managing the sub-process lifecycle.
- `phonos-status-api.py`: Accessible single-page app and REST API.
- `bt-turntable-autoconnect.sh`: Resilient auto-reconnect daemon.
- `darkice.cfg`: DarkIce ALSA/Pulse configuration.
- `icecast.xml`: Icecast server settings.
