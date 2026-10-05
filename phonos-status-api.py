#!/usr/bin/env python3
import http.server
import json
import os
import re
import socketserver
import subprocess
import threading
import time
from urllib.parse import urlparse

PORT = int(os.environ.get("PORT", "8080"))
TURNTABLE_MAC = os.environ.get("TURNTABLE_MAC", "AD:60:17:9B:D5:AC")

def run_cmd(cmd, timeout=5):
    try:
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return res.stdout.strip()
    except Exception:
        return ""

def restart_darkice():
    run_cmd("pkill -f darkice || true")
    time.sleep(1)
    run_cmd("darkice -c /etc/darkice.cfg >/dev/null 2>&1 &")

def get_service_status(svc_name):
    patterns = {
        "icecast2": "icecast2",
        "darkice": "darkice",
        "bt-agent": "bt-agent",
        "bt_agent": "bt-agent",
        "bt-turntable-autoconnect": "bt-turntable",
        "bt_autoconnect": "bt-turntable",
        "pulseaudio": "pulseaudio",
    }
    pat = patterns.get(svc_name, svc_name)
    out = run_cmd(f"pgrep -f '{pat}'")
    return "active" if out else "inactive"

def get_pulse_status():
    out = run_cmd("pgrep -x pulseaudio")
    return "active" if out else "inactive"

def get_bluetooth_status():
    info_out = run_cmd(f"bluetoothctl info {TURNTABLE_MAC}")
    connected = "Connected: yes" in info_out
    paired = "Paired: yes" in info_out
    trusted = "Trusted: yes" in info_out
    
    name_match = re.search(r"Name:\s*(.*)", info_out)
    name = name_match.group(1) if name_match else "Fenton recordplayer"
    
    show_out = run_cmd("bluetoothctl show")
    ctrl_powered = "Powered: yes" in show_out
    ctrl_discoverable = "Discoverable: yes" in show_out
    ctrl_pairable = "Pairable: yes" in show_out
    ctrl_discovering = "Discovering: yes" in show_out
    
    return {
        "turntable": {
            "name": name,
            "mac": TURNTABLE_MAC,
            "connected": connected,
            "paired": paired,
            "trusted": trusted
        },
        "controller": {
            "powered": ctrl_powered,
            "discoverable": ctrl_discoverable,
            "pairable": ctrl_pairable,
            "scanning": ctrl_discovering
        }
    }

def get_icecast_status():
    icecast_host = os.environ.get("ICECAST_HOST", "")
    mount_url = f"http://{icecast_host}:8000/sonos.mp3" if icecast_host else "/sonos.mp3"
    try:
        raw = run_cmd("curl -s http://127.0.0.1:8000/status-json.xsl", timeout=2)
        if raw:
            data = json.loads(raw)
            icestats = data.get("icestats", {})
            source = icestats.get("source")
            if isinstance(source, dict):
                listen_url = source.get("listenurl") or mount_url
                return {
                    "online": True,
                    "mount": listen_url,
                    "listeners": source.get("listeners", 0),
                    "bitrate": source.get("bitrate", "256"),
                    "audio_format": source.get("server_name", "Raspberry Bridge")
                }
            elif isinstance(source, list) and len(source) > 0:
                s = source[0]
                listen_url = s.get("listenurl") or mount_url
                return {
                    "online": True,
                    "mount": listen_url,
                    "listeners": s.get("listeners", 0),
                    "bitrate": s.get("bitrate", "256"),
                    "audio_format": s.get("server_name", "Raspberry Bridge")
                }
    except Exception:
        pass
    return {"online": False, "mount": mount_url, "listeners": 0, "bitrate": 256}

def get_system_status():
    temp = "N/A"
    if os.path.exists("/sys/class/thermal/thermal_zone0/temp"):
        try:
            with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
                temp_c = float(f.read().strip()) / 1000.0
                temp = f"{temp_c:.1f}'C"
        except Exception:
            pass
    if temp == "N/A":
        temp_raw = run_cmd("vcgencmd measure_temp")
        temp = temp_raw.replace("temp=", "") if temp_raw else "N/A"
    
    uptime = run_cmd("uptime -p")
    
    loadavg = [0.0, 0.0, 0.0]
    try:
        with open("/proc/loadavg", "r") as f:
            parts = f.read().split()
            loadavg = [float(parts[0]), float(parts[1]), float(parts[2])]
    except Exception:
        pass

    mem = {"total_mb": 0, "used_mb": 0, "free_mb": 0}
    try:
        free_out = run_cmd("free -m").splitlines()
        if len(free_out) > 1:
            m = free_out[1].split()
            mem = {"total_mb": int(m[1]), "used_mb": int(m[2]), "free_mb": int(m[3])}
    except Exception:
        pass

    return {
        "hostname": "phonos",
        "temperature": temp,
        "uptime": uptime,
        "load_average": loadavg,
        "memory": mem
    }

def get_full_status():
    return {
        "status": "ok",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "bluetooth": get_bluetooth_status(),
        "services": {
            "icecast2": get_service_status("icecast2"),
            "darkice": get_service_status("darkice"),
            "bt_agent": get_service_status("bt-agent"),
            "bt_autoconnect": get_service_status("bt-turntable-autoconnect"),
            "pulseaudio": get_pulse_status()
        },
        "icecast": get_icecast_status(),
        "system": get_system_status()
    }

def start_pairing_mode():
    def _pair():
        run_cmd("bluetoothctl power on")
        run_cmd("bluetoothctl pairable on")
        run_cmd("bluetoothctl discoverable on")
        run_cmd("bluetoothctl --timeout 25 scan on")
        run_cmd(f"bluetoothctl trust {TURNTABLE_MAC}")
        run_cmd(f"bluetoothctl pair {TURNTABLE_MAC}")
        run_cmd(f"bluetoothctl connect {TURNTABLE_MAC}")
        time.sleep(2)
        restart_darkice()
    t = threading.Thread(target=_pair, daemon=True)
    t.start()

def trigger_connect():
    def _conn():
        run_cmd(f"bluetoothctl connect {TURNTABLE_MAC}")
        time.sleep(2)
        restart_darkice()
    t = threading.Thread(target=_conn, daemon=True)
    t.start()

def trigger_disconnect():
    def _disc():
        run_cmd(f"bluetoothctl disconnect {TURNTABLE_MAC}")
    t = threading.Thread(target=_disc, daemon=True)
    t.start()

OPENAPI_SPEC = {
    "openapi": "3.0.3",
    "info": {
        "title": "Phonos Turntable Bridge API",
        "description": "API REST per al control i monitoratge del tocadiscos Bluetooth i streaming d'àudio Icecast a Raspberry Pi.",
        "version": "1.0.0"
    },
    "servers": [
        {"url": "/", "description": "Servidor local Phonos"}
    ],
    "paths": {
        "/api": {
            "get": {
                "summary": "Consultar estat complet del sistema",
                "description": "Retorna l'estat del tocadiscos Bluetooth, serveis del sistema, emissió d'àudio Icecast i dades de maquinari.",
                "responses": {
                    "200": {
                        "description": "Estat complet retornat amb èxit",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "status": {"type": "string", "example": "ok"},
                                        "timestamp": {"type": "string", "example": "2026-10-04T17:15:00Z"},
                                        "bluetooth": {
                                            "type": "object",
                                            "properties": {
                                                "turntable": {
                                                    "type": "object",
                                                    "properties": {
                                                        "name": {"type": "string", "example": "Fenton recordplayer"},
                                                        "mac": {"type": "string", "example": "AD:60:17:9B:D5:AC"},
                                                        "connected": {"type": "boolean", "example": True},
                                                        "paired": {"type": "boolean", "example": True},
                                                        "trusted": {"type": "boolean", "example": True}
                                                    }
                                                },
                                                "controller": {
                                                    "type": "object",
                                                    "properties": {
                                                        "powered": {"type": "boolean", "example": True},
                                                        "discoverable": {"type": "boolean", "example": True},
                                                        "pairable": {"type": "boolean", "example": True},
                                                        "scanning": {"type": "boolean", "example": False}
                                                    }
                                                }
                                            }
                                        },
                                        "services": {
                                            "type": "object",
                                            "properties": {
                                                "icecast2": {"type": "string", "example": "active"},
                                                "darkice": {"type": "string", "example": "active"},
                                                "bt_agent": {"type": "string", "example": "active"},
                                                "bt_autoconnect": {"type": "string", "example": "active"},
                                                "pulseaudio": {"type": "string", "example": "active"}
                                            }
                                        },
                                        "icecast": {
                                            "type": "object",
                                            "properties": {
                                                "online": {"type": "boolean", "example": True},
                                                "mount": {"type": "string", "example": "http://192.168.1.39:8000/sonos.mp3"},
                                                "listeners": {"type": "integer", "example": 1},
                                                "bitrate": {"type": "integer", "example": 256}
                                            }
                                        },
                                        "system": {
                                            "type": "object",
                                            "properties": {
                                                "hostname": {"type": "string", "example": "phonos"},
                                                "temperature": {"type": "string", "example": "56.0'C"},
                                                "uptime": {"type": "string", "example": "up 20 minutes"}
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        },
        "/api/connect": {
            "post": {
                "summary": "Connectar al tocadiscos",
                "description": "Força una connexió immediata amb el tocadiscos Fenton (AD:60:17:9B:D5:AC) i reinicia DarkIce.",
                "responses": {
                    "200": {
                        "description": "Sol·licitud de connexió enviada",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "status": {"type": "string", "example": "ok"},
                                        "message": {"type": "string", "example": "Sol·licitud de connexió al tocadiscos enviada"}
                                    }
                                }
                            }
                        }
                    }
                }
            }
        },
        "/api/pair": {
            "post": {
                "summary": "Iniciar mode emparellament i escaneig",
                "description": "Activa mode detectable i emparellable, escaneja durant 30s i enllaça el tocadiscos.",
                "responses": {
                    "200": {
                        "description": "Mode emparellament iniciat",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "status": {"type": "string", "example": "ok"},
                                        "message": {"type": "string", "example": "Iniciat mode emparellament i escaneig Bluetooth (30s)"}
                                    }
                                }
                            }
                        }
                    }
                }
            }
        },
        "/api/disconnect": {
            "post": {
                "summary": "Desconnectar tocadiscos",
                "description": "Talla la connexió Bluetooth activa amb el tocadiscos.",
                "responses": {
                    "200": {
                        "description": "Desconnexió completada",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "status": {"type": "string", "example": "ok"},
                                        "message": {"type": "string", "example": "Tocadiscos desconnectat"}
                                    }
                                }
                            }
                        }
                    }
                }
            }
        },
        "/api/restart-stream": {
            "post": {
                "summary": "Reiniciar flux d'àudio DarkIce",
                "description": "Reinicia el servei DarkIce per reconnectar el flux cap a Icecast.",
                "responses": {
                    "200": {
                        "description": "Flux reiniciat",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "status": {"type": "string", "example": "ok"},
                                        "message": {"type": "string", "example": "DarkIce reiniciat correctament"}
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

SWAGGER_HTML = """<!DOCTYPE html>
<html lang="ca">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Phonos API - Swagger Docs</title>
    <link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css">
    <style>
        body { margin: 0; background: #0f172a; color: #f8fafc; }
        .swagger-ui .topbar { display: none; }
        .swagger-ui { filter: invert(88%) hue-rotate(180deg); }
        .swagger-ui .highlight-code { filter: invert(100%) hue-rotate(180deg); }
    </style>
</head>
<body>
    <div id="swagger-ui"></div>
    <script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
    <script>
        window.onload = function() {
            window.ui = SwaggerUIBundle({
                url: "/openapi.json",
                dom_id: '#swagger-ui',
                presets: [
                    SwaggerUIBundle.presets.apis,
                    SwaggerUIBundle.SwaggerUIStandalonePreset
                ],
                layout: "BaseLayout"
            });
        };
    </script>
</body>
</html>
"""

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="ca">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Phonos — Panell de Control</title>
    <style>
        :root {
            --bg-base: #090d16;
            --bg-surface: #111827;
            --bg-surface-elevated: #1a2234;
            --border-subtle: #1f293d;
            --border-strong: #334155;
            
            --text-primary: #f8fafc;
            --text-secondary: #cbd5e1;
            --text-muted: #94a3b8;
            --text-faint: #64748b;
            
            --emerald-bg: rgba(16, 185, 129, 0.12);
            --emerald-border: rgba(16, 185, 129, 0.35);
            --emerald-text: #34d399;
            --emerald-dot: #10b981;
            
            --rose-bg: rgba(244, 63, 94, 0.12);
            --rose-border: rgba(244, 63, 94, 0.35);
            --rose-text: #fb7185;
            --rose-dot: #f43f5e;
            
            --amber-bg: rgba(245, 158, 11, 0.12);
            --amber-border: rgba(245, 158, 11, 0.35);
            --amber-text: #fbbf24;
            
            --sky-accent: #38bdf8;
            --indigo-accent: #6366f1;
            
            --focus-ring: 0 0 0 3px rgba(56, 189, 248, 0.5);
            --radius-card: 16px;
            --radius-elem: 10px;
            --radius-pill: 9999px;
            
            --font-sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            --font-mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
        }

        *, *::before, *::after {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        body {
            font-family: var(--font-sans);
            background-color: var(--bg-base);
            color: var(--text-primary);
            line-height: 1.5;
            min-height: 100vh;
            display: flex;
            justify-content: center;
            padding: 32px 16px;
            -webkit-font-smoothing: antialiased;
        }

        .layout {
            max-width: 680px;
            width: 100%;
            display: flex;
            flex-direction: column;
            gap: 20px;
        }

        /* Skip link for keyboard a11y */
        .skip-link {
            position: absolute;
            top: -40px;
            left: 16px;
            background: var(--sky-accent);
            color: #000;
            padding: 8px 16px;
            font-weight: 700;
            border-radius: var(--radius-elem);
            z-index: 10000;
            text-decoration: none;
            transition: top 0.15s ease;
        }
        .skip-link:focus {
            top: 16px;
        }

        /* Header */
        header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding-bottom: 4px;
        }

        .branding {
            display: flex;
            align-items: center;
            gap: 14px;
        }

        .brand-icon {
            width: 44px;
            height: 44px;
            border-radius: 12px;
            background: linear-gradient(135deg, #1e293b, #0f172a);
            border: 1px solid var(--border-strong);
            display: flex;
            align-items: center;
            justify-content: center;
            color: var(--sky-accent);
            box-shadow: 0 4px 12px rgba(0,0,0,0.3);
        }

        .branding h1 {
            font-size: 19px;
            font-weight: 700;
            letter-spacing: -0.02em;
            color: var(--text-primary);
        }

        .branding-meta {
            font-size: 12px;
            color: var(--text-muted);
            display: flex;
            align-items: center;
            gap: 8px;
            font-variant-numeric: tabular-nums;
        }

        .nav-actions {
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .nav-btn {
            font-size: 12px;
            font-weight: 600;
            color: var(--text-secondary);
            background: var(--bg-surface);
            border: 1px solid var(--border-subtle);
            padding: 6px 12px;
            border-radius: var(--radius-elem);
            text-decoration: none;
            display: inline-flex;
            align-items: center;
            gap: 6px;
            transition: all 0.15s ease;
        }

        .nav-btn:hover {
            background: var(--bg-surface-elevated);
            color: var(--text-primary);
            border-color: var(--border-strong);
        }

        .nav-btn:focus-visible {
            outline: none;
            box-shadow: var(--focus-ring);
        }

        /* Card Primitive */
        .card {
            background: var(--bg-surface);
            border: 1px solid var(--border-subtle);
            border-radius: var(--radius-card);
            padding: 22px;
            box-shadow: 0 4px 16px rgba(0, 0, 0, 0.25);
            display: flex;
            flex-direction: column;
            gap: 16px;
        }

        .card-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
        }

        .card-title {
            font-size: 12px;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.07em;
            color: var(--text-muted);
            display: flex;
            align-items: center;
            gap: 8px;
        }

        /* Hero Turntable Visual Card */
        .hero-layout {
            display: flex;
            align-items: center;
            gap: 20px;
        }

        .turntable-chassis {
            width: 80px;
            height: 80px;
            background: radial-gradient(circle, #1e293b 25%, #0f172a 75%);
            border: 2px solid #334155;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            position: relative;
            flex-shrink: 0;
            box-shadow: inset 0 2px 6px rgba(255,255,255,0.08), 0 6px 16px rgba(0,0,0,0.6);
        }

        .vinyl-record {
            width: 70px;
            height: 70px;
            border-radius: 50%;
            background: repeating-radial-gradient(
                #111827,
                #111827 4px,
                #1f2937 5px,
                #111827 6px
            );
            border: 1px solid #374151;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: transform 0.5s ease;
        }

        .vinyl-label {
            width: 26px;
            height: 26px;
            background: #ef4444;
            border-radius: 50%;
            border: 2px solid #ffffff;
            display: flex;
            align-items: center;
            justify-content: center;
            box-shadow: 0 0 4px rgba(0,0,0,0.4);
        }

        .vinyl-center-hole {
            width: 6px;
            height: 6px;
            background: #000000;
            border-radius: 50%;
        }

        .turntable-chassis.spinning .vinyl-record {
            animation: spin 2.8s linear infinite;
        }

        @keyframes spin {
            100% { transform: rotate(360deg); }
        }

        .hero-info {
            flex: 1;
            min-width: 0;
            display: flex;
            flex-direction: column;
            gap: 4px;
        }

        .device-heading {
            font-size: 19px;
            font-weight: 700;
            letter-spacing: -0.01em;
            color: var(--text-primary);
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }

        .device-address {
            font-family: var(--font-mono);
            font-size: 12px;
            color: var(--text-muted);
            letter-spacing: 0.03em;
        }

        /* Badges */
        .status-pill {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 4px 10px;
            border-radius: var(--radius-pill);
            font-size: 12px;
            font-weight: 600;
            line-height: 1;
        }

        .status-pill.active {
            background: var(--emerald-bg);
            border: 1px solid var(--emerald-border);
            color: var(--emerald-text);
        }

        .status-pill.inactive {
            background: var(--rose-bg);
            border: 1px solid var(--rose-border);
            color: var(--rose-text);
        }

        .pill-dot {
            width: 6px;
            height: 6px;
            border-radius: 50%;
            background: currentColor;
        }

        .pulse-emerald {
            box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.7);
            animation: pulse-ring 2s infinite;
        }

        @keyframes pulse-ring {
            0% { box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.7); }
            70% { box-shadow: 0 0 0 6px rgba(16, 185, 129, 0); }
            100% { box-shadow: 0 0 0 0 rgba(16, 185, 129, 0); }
        }

        /* Action Buttons */
        .button-bar {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 8px;
        }

        @media (max-width: 520px) {
            .button-bar {
                grid-template-columns: repeat(2, 1fr);
            }
        }

        button {
            font-family: var(--font-sans);
            font-size: 13px;
            font-weight: 600;
            padding: 10px 14px;
            border-radius: var(--radius-elem);
            border: 1px solid transparent;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 6px;
            transition: all 0.15s ease;
        }

        button:focus-visible {
            outline: none;
            box-shadow: var(--focus-ring);
        }

        button:active {
            transform: translateY(1px);
        }

        .btn-action-primary {
            background: #2563eb;
            color: #ffffff;
            box-shadow: 0 2px 6px rgba(37, 99, 235, 0.35);
        }
        .btn-action-primary:hover { background: #1d4ed8; }

        .btn-action-amber {
            background: var(--amber-bg);
            border-color: var(--amber-border);
            color: var(--amber-text);
        }
        .btn-action-amber:hover {
            background: rgba(245, 158, 11, 0.22);
        }

        .btn-action-danger {
            background: var(--rose-bg);
            border-color: var(--rose-border);
            color: var(--rose-text);
        }
        .btn-action-danger:hover {
            background: rgba(244, 63, 94, 0.22);
        }

        .btn-action-neutral {
            background: var(--bg-surface-elevated);
            border-color: var(--border-strong);
            color: var(--text-secondary);
        }
        .btn-action-neutral:hover {
            background: #243048;
            color: var(--text-primary);
        }

        /* Audio Player Container */
        .audio-container {
            background: #080c14;
            border: 1px solid var(--border-subtle);
            border-radius: var(--radius-elem);
            padding: 12px 14px;
            display: flex;
            flex-direction: column;
            gap: 8px;
        }

        audio {
            width: 100%;
            height: 38px;
            outline: none;
            border-radius: 6px;
        }

        .stream-meta-row {
            display: flex;
            align-items: center;
            justify-content: space-between;
            font-size: 12px;
            color: var(--text-muted);
            font-variant-numeric: tabular-nums;
        }

        .stream-url {
            color: var(--sky-accent);
            text-decoration: none;
            font-family: var(--font-mono);
            font-size: 11.5px;
        }
        .stream-url:hover { text-decoration: underline; }
        .stream-url:focus-visible { outline: none; box-shadow: var(--focus-ring); border-radius: 4px; }

        /* Metric Grid */
        .dual-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 16px;
        }

        @media (max-width: 560px) {
            .dual-grid {
                grid-template-columns: 1fr;
            }
        }

        .data-list {
            display: flex;
            flex-direction: column;
        }

        .data-item {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 8px 0;
            border-bottom: 1px solid rgba(255, 255, 255, 0.05);
            font-size: 13px;
        }

        .data-item:last-child {
            border-bottom: none;
        }

        .data-label {
            color: var(--text-muted);
            display: flex;
            align-items: center;
            gap: 6px;
        }

        .data-value {
            font-weight: 600;
            color: var(--text-primary);
            font-variant-numeric: tabular-nums;
        }

        .state-tag {
            display: inline-flex;
            align-items: center;
            gap: 5px;
            font-size: 11px;
            font-weight: 600;
            padding: 2px 8px;
            border-radius: 6px;
        }

        .state-tag.active {
            background: var(--emerald-bg);
            color: var(--emerald-text);
        }

        .state-tag.inactive {
            background: var(--rose-bg);
            color: var(--rose-text);
        }

        /* JSON Details Area */
        details.json-drawer {
            background: var(--bg-surface);
            border: 1px solid var(--border-subtle);
            border-radius: var(--radius-card);
            padding: 16px 20px;
        }

        summary.json-summary {
            cursor: pointer;
            font-size: 12px;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.06em;
            color: var(--text-muted);
            user-select: none;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }

        summary.json-summary:focus-visible {
            outline: none;
            box-shadow: var(--focus-ring);
            border-radius: 4px;
        }

        pre.code-block {
            margin-top: 12px;
            background: #060910;
            padding: 14px;
            border-radius: var(--radius-elem);
            font-family: var(--font-mono);
            font-size: 11.5px;
            color: var(--sky-accent);
            overflow-x: auto;
            border: 1px solid var(--border-subtle);
            max-height: 280px;
            line-height: 1.45;
        }

        /* Toast UI */
        #toast {
            position: fixed;
            bottom: 24px;
            left: 50%;
            transform: translateX(-50%) translateY(100px);
            background: var(--bg-surface-elevated);
            color: var(--text-primary);
            border: 1px solid var(--sky-accent);
            padding: 10px 20px;
            border-radius: var(--radius-pill);
            font-size: 13px;
            font-weight: 500;
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.7);
            transition: transform 0.25s cubic-bezier(0.16, 1, 0.3, 1);
            z-index: 9999;
            display: flex;
            align-items: center;
            gap: 8px;
            pointer-events: none;
        }

        #toast.visible {
            transform: translateX(-50%) translateY(0);
        }

        /* SVG Icon styling */
        .icon-svg {
            width: 14px;
            height: 14px;
            fill: none;
            stroke: currentColor;
            stroke-width: 2;
            stroke-linecap: round;
            stroke-linejoin: round;
            flex-shrink: 0;
        }
    </style>
</head>
<body>
    <a href="#main-content" class="skip-link">Saltar al contingut principal</a>

    <div class="layout" id="main-content">
        <!-- Header -->
        <header role="banner">
            <div class="branding">
                <div class="brand-icon" aria-hidden="true">
                    <svg class="icon-svg" style="width:22px;height:22px" viewBox="0 0 24 24">
                        <circle cx="12" cy="12" r="10"></circle>
                        <circle cx="12" cy="12" r="3"></circle>
                        <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10"></path>
                    </svg>
                </div>
                <div>
                    <h1>Phonos Bridge</h1>
                    <div class="branding-meta">
                        <span id="hostname-display">phonos</span> • 
                        <span id="uptime-display">Carregant...</span>
                    </div>
                </div>
            </div>

            <nav class="nav-actions" aria-label="Navegació ràpida">
                <a href="/docs" class="nav-btn" target="_blank" rel="noopener">
                    <svg class="icon-svg" viewBox="0 0 24 24" aria-hidden="true"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline></svg>
                    Swagger UI
                </a>
                <a href="/api" class="nav-btn" target="_blank" rel="noopener">
                    <svg class="icon-svg" viewBox="0 0 24 24" aria-hidden="true"><polyline points="16 18 22 12 16 6"></polyline><polyline points="8 6 2 12 8 18"></polyline></svg>
                    JSON
                </a>
            </nav>
        </header>

        <!-- Main Content -->
        <main style="display:flex;flex-direction:column;gap:20px;">
            <!-- Hero Turntable Card -->
            <section class="card" aria-labelledby="hero-title">
                <div class="card-header">
                    <h2 class="card-title" id="hero-title">
                        <svg class="icon-svg" viewBox="0 0 24 24" aria-hidden="true"><path d="M6.5 6.5l11 11"></path><circle cx="6.5" cy="6.5" r="2.5"></circle><circle cx="17.5" cy="17.5" r="2.5"></circle><path d="M12 2a10 10 0 1 0 10 10"></path></svg>
                        Estat del Tocadiscos
                    </h2>
                    <div class="status-pill inactive" id="turntable-badge" role="status" aria-live="polite">
                        <span class="pill-dot" id="turntable-dot"></span>
                        <span id="turntable-status-text">Desconnectat</span>
                    </div>
                </div>

                <div class="hero-layout">
                    <div class="turntable-chassis" id="turntable-chassis" aria-hidden="true">
                        <div class="vinyl-record">
                            <div class="vinyl-label">
                                <div class="vinyl-center-hole"></div>
                            </div>
                        </div>
                    </div>

                    <div class="hero-info">
                        <div class="device-heading" id="device-name">Fenton recordplayer</div>
                        <div class="device-address" id="device-mac">AD:60:17:9B:D5:AC</div>
                    </div>
                </div>

                <!-- Control Buttons -->
                <div class="button-bar" role="group" aria-label="Controls de connexió">
                    <button type="button" class="btn-action-primary" onclick="executePost('/api/connect', 'Sol·licitant connexió...')">
                        <svg class="icon-svg" viewBox="0 0 24 24" aria-hidden="true"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"></path><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"></path></svg>
                        Connectar
                    </button>
                    <button type="button" class="btn-action-amber" onclick="executePost('/api/pair', 'Iniciant mode emparellament (30s)...')">
                        <svg class="icon-svg" viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12.55a11 11 0 0 1 14.08 0"></path><path d="M1.42 9a16 16 0 0 1 21.16 0"></path><path d="M8.53 16.11a6 6 0 0 1 6.95 0"></path><line x1="12" y1="20" x2="12.01" y2="20"></line></svg>
                        Emparellar
                    </button>
                    <button type="button" class="btn-action-danger" onclick="executePost('/api/disconnect', 'Desconnectant tocadiscos...')">
                        <svg class="icon-svg" viewBox="0 0 24 24" aria-hidden="true"><path d="M18.36 6.64a9 9 0 1 1-12.73 0"></path><line x1="12" y1="2" x2="12" y2="12"></line></svg>
                        Desconnectar
                    </button>
                    <button type="button" class="btn-action-neutral" onclick="executePost('/api/restart-stream', 'Reiniciant streaming DarkIce...')">
                        <svg class="icon-svg" viewBox="0 0 24 24" aria-hidden="true"><polyline points="23 4 23 10 17 10"></polyline><polyline points="1 20 1 14 7 14"></polyline><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"></path></svg>
                        Reiniciar
                    </button>
                </div>
            </section>

            <!-- Live Audio Stream -->
            <section class="card" aria-labelledby="audio-title">
                <div class="card-header">
                    <h2 class="card-title" id="audio-title">
                        <svg class="icon-svg" viewBox="0 0 24 24" aria-hidden="true"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon><path d="M19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07"></path></svg>
                        Emissió d'Àudio en Directe
                    </h2>
                    <div class="status-pill inactive" id="icecast-badge" role="status" aria-live="polite">
                        <span class="pill-dot"></span>
                        <span id="icecast-status-text">En espera</span>
                    </div>
                </div>

                <div class="audio-container">
                    <audio id="audio-player" controls preload="none" aria-label="Reproductor d'àudio del tocadiscos">
                        <source src="" type="audio/mpeg">
                        El teu navegador no és compatible amb la reproducció HTML5.
                    </audio>
                    <div class="stream-meta-row">
                        <span>Enllaç: <a class="stream-url" href="#" target="_blank" rel="noopener">Carregant flux...</a></span>
                        <span>Oients: <strong id="listener-count">0</strong> | Bitrate: <strong id="bitrate-display">256</strong> kbps</span>
                    </div>
                </div>
            </section>

            <!-- 2-Column Metrics -->
            <div class="dual-grid">
                <!-- System Services -->
                <section class="card" aria-labelledby="services-title">
                    <h2 class="card-title" id="services-title">
                        <svg class="icon-svg" viewBox="0 0 24 24" aria-hidden="true"><rect x="2" y="2" width="20" height="8" rx="2" ry="2"></rect><rect x="2" y="14" width="20" height="8" rx="2" ry="2"></rect><line x1="6" y1="6" x2="6.01" y2="6"></line><line x1="6" y1="18" x2="6.01" y2="18"></line></svg>
                        Serveis del Sistema
                    </h2>
                    <div class="data-list">
                        <div class="data-item">
                            <span class="data-label">DarkIce Streamer</span>
                            <span class="state-tag inactive" id="pill-darkice">--</span>
                        </div>
                        <div class="data-item">
                            <span class="data-label">Icecast2 Server</span>
                            <span class="state-tag inactive" id="pill-icecast2">--</span>
                        </div>
                        <div class="data-item">
                            <span class="data-label">PulseAudio</span>
                            <span class="state-tag inactive" id="pill-pulseaudio">--</span>
                        </div>
                        <div class="data-item">
                            <span class="data-label">BT Auto-Connect</span>
                            <span class="state-tag inactive" id="pill-bt-autoconnect">--</span>
                        </div>
                        <div class="data-item">
                            <span class="data-label">BT Agent (NoInput)</span>
                            <span class="state-tag inactive" id="pill-bt-agent">--</span>
                        </div>
                    </div>
                </section>

                <!-- Hardware Telemetry -->
                <section class="card" aria-labelledby="hardware-title">
                    <h2 class="card-title" id="hardware-title">
                        <svg class="icon-svg" viewBox="0 0 24 24" aria-hidden="true"><rect x="4" y="4" width="16" height="16" rx="2" ry="2"></rect><rect x="9" y="9" width="6" height="6"></rect><line x1="9" y1="1" x2="9" y2="4"></line><line x1="15" y1="1" x2="15" y2="4"></line><line x1="9" y1="20" x2="9" y2="23"></line><line x1="15" y1="20" x2="15" y2="23"></line><line x1="20" y1="9" x2="23" y2="9"></line><line x1="20" y1="14" x2="23" y2="14"></line><line x1="1" y1="9" x2="4" y2="9"></line><line x1="1" y1="14" x2="4" y2="14"></line></svg>
                        Telemetria Hardware
                    </h2>
                    <div class="data-list">
                        <div class="data-item">
                            <span class="data-label">Temperatura CPU</span>
                            <span class="data-value" id="val-temp">--</span>
                        </div>
                        <div class="data-item">
                            <span class="data-label">Memòria RAM</span>
                            <span class="data-value" id="val-mem">--</span>
                        </div>
                        <div class="data-item">
                            <span class="data-label">Càrrega (1m, 5m, 15m)</span>
                            <span class="data-value" id="val-load">--</span>
                        </div>
                        <div class="data-item">
                            <span class="data-label">Adaptador BT</span>
                            <span class="data-value" id="val-bt-ctrl">--</span>
                        </div>
                        <div class="data-item">
                            <span class="data-label">Darrera Sincronització</span>
                            <span class="data-value" id="val-sync-time" style="color:var(--text-muted);font-size:12px;">--</span>
                        </div>
                    </div>
                </section>
            </div>

            <!-- Collapsible JSON -->
            <details class="json-drawer">
                <summary class="json-summary">
                    <span>{ } Resposta de l'API (/api)</span>
                    <span style="font-size:11px;color:var(--text-muted)">Clica per inspeccionar</span>
                </summary>
                <pre class="code-block" id="raw-json" tabindex="0">Carregant dades...</pre>
            </details>
        </main>
    </div>

    <!-- Notification Toast -->
    <div id="toast" role="alert" aria-live="assertive">
        <span id="toast-message">Acció executada</span>
    </div>

    <script>
        let toastTimeout = null;
        function displayToast(msg) {
            const toast = document.getElementById('toast');
            document.getElementById('toast-message').innerText = msg;
            toast.classList.add('visible');
            clearTimeout(toastTimeout);
            toastTimeout = setTimeout(() => {
                toast.classList.remove('visible');
            }, 3000);
        }

        async function executePost(url, pendingMsg) {
            try {
                displayToast(pendingMsg);
                const res = await fetch(url, { method: 'POST' });
                const json = await res.json();
                if (json.status === 'ok') {
                    displayToast(json.message || 'Acció completada amb èxit');
                } else {
                    displayToast(json.message || 'Error en processar');
                }
                setTimeout(refreshData, 1000);
            } catch (err) {
                displayToast('Error de xarxa en contactar amb el servidor');
            }
        }

        function setServiceTag(tagId, status) {
            const el = document.getElementById(tagId);
            if (!el) return;
            const active = status === 'active';
            el.className = `state-tag ${active ? 'active' : 'inactive'}`;
            el.innerText = active ? 'Actiu' : 'Inactiu';
        }

        async function refreshData() {
            try {
                const res = await fetch('/api');
                if (!res.ok) return;
                const data = await res.json();

                // Turntable status
                const tt = data.bluetooth?.turntable || {};
                const isConnected = tt.connected === true;
                
                document.getElementById('device-name').innerText = tt.name || 'Fenton recordplayer';
                document.getElementById('device-mac').innerText = tt.mac || 'AD:60:17:9B:D5:AC';
                
                const ttBadge = document.getElementById('turntable-badge');
                const ttDot = document.getElementById('turntable-dot');
                const ttChassis = document.getElementById('turntable-chassis');
                
                if (isConnected) {
                    ttBadge.className = 'status-pill active';
                    ttDot.className = 'pill-dot pulse-emerald';
                    document.getElementById('turntable-status-text').innerText = 'Connectat';
                    ttChassis.classList.add('spinning');
                } else {
                    ttBadge.className = 'status-pill inactive';
                    ttDot.className = 'pill-dot';
                    document.getElementById('turntable-status-text').innerText = 'Desconnectat (esperant)';
                    ttChassis.classList.remove('spinning');
                }

                // Icecast status
                const ice = data.icecast || {};
                const isOnline = ice.online === true;
                const iceBadge = document.getElementById('icecast-badge');
                
                iceBadge.className = `status-pill ${isOnline ? 'active' : 'inactive'}`;
                document.getElementById('icecast-status-text').innerText = isOnline ? 'Emetent en directe' : 'En espera';
                document.getElementById('listener-count').innerText = ice.listeners ?? 0;
                document.getElementById('bitrate-display').innerText = ice.bitrate ?? 256;

                const defaultStream = `${window.location.protocol}//${window.location.hostname}:8000/sonos.mp3`;
                const streamUrl = (ice.mount && !ice.mount.startsWith('/')) ? ice.mount : (ice.mount ? `${window.location.protocol}//${window.location.hostname}:8000${ice.mount}` : defaultStream);
                document.querySelectorAll('.stream-url').forEach(el => {
                    el.href = streamUrl;
                    el.innerText = streamUrl;
                });
                const audioPlayer = document.getElementById('audio-player');
                const audioSource = audioPlayer ? audioPlayer.querySelector('source') : null;
                if (audioSource && audioSource.src !== streamUrl) {
                    audioSource.src = streamUrl;
                    audioPlayer.load();
                }

                // Services
                const svc = data.services || {};
                setServiceTag('pill-darkice', svc.darkice);
                setServiceTag('pill-icecast2', svc.icecast2);
                setServiceTag('pill-pulseaudio', svc.pulseaudio);
                setServiceTag('pill-bt-autoconnect', svc.bt_autoconnect);
                setServiceTag('pill-bt-agent', svc.bt_agent);

                // Hardware & System
                const sys = data.system || {};
                document.getElementById('hostname-display').innerText = sys.hostname || 'phonos';
                document.getElementById('uptime-display').innerText = sys.uptime || '--';
                document.getElementById('val-temp').innerText = sys.temperature || '--';
                
                if (sys.memory) {
                    document.getElementById('val-mem').innerText = `${sys.memory.used_mb} MB / ${sys.memory.total_mb} MB`;
                }
                if (sys.load_average) {
                    document.getElementById('val-load').innerText = sys.load_average.join(', ');
                }

                const ctrl = data.bluetooth?.controller || {};
                document.getElementById('val-bt-ctrl').innerText = ctrl.scanning ? 'Escanejant...' : (ctrl.discoverable ? 'Visible / Connectable' : 'Actiu');

                // Timestamp
                const date = new Date(data.timestamp);
                document.getElementById('val-sync-time').innerText = date.toLocaleTimeString();

                // Raw JSON
                document.getElementById('raw-json').innerText = JSON.stringify(data, null, 2);

            } catch (err) {
                console.error('Error refreshing status:', err);
            }
        }

        // Initialize polling
        refreshData();
        setInterval(refreshData, 2500);
    </script>
</body>
</html>
"""

class StatusHandler(http.server.BaseHTTPRequestHandler):
    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        
        response_data = {"status": "ok"}
        
        if path == "/api/pair" or path == "/api/scan":
            start_pairing_mode()
            response_data["message"] = "Iniciat mode emparellament i escaneig Bluetooth (30s)"
        elif path == "/api/connect":
            trigger_connect()
            response_data["message"] = "Sol·licitud de connexió al tocadiscos enviada"
        elif path == "/api/disconnect":
            trigger_disconnect()
            response_data["message"] = "Tocadiscos desconnectat"
        elif path == "/api/restart-stream":
            restart_darkice()
            response_data["message"] = "DarkIce reiniciat correctament"
        else:
            self.send_response(404)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "error", "message": "Ruta desconeguda"}).encode("utf-8"))
            return

        body = json.dumps(response_data, indent=2).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        
        # OpenAPI Schema
        if path == "/openapi.json" or path == "/swagger.json":
            body = json.dumps(OPENAPI_SPEC, indent=2).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        # Swagger UI Documentation Page
        if path == "/docs" or path == "/swagger":
            body = SWAGGER_HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        # Status JSON
        accept_header = self.headers.get("Accept", "")
        if path.startswith("/api") or path == "/json" or "application/json" in accept_header:
            status_data = get_full_status()
            body = json.dumps(status_data, indent=2).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        # Dashboard Single-Page App HTML
        body = DASHBOARD_HTML.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass

if __name__ == "__main__":
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), StatusHandler) as httpd:
        httpd.serve_forever()
