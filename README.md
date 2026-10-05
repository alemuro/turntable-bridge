# 📻 Turntable Bridge (`phonos`)

> Pont d'àudio Bluetooth per a tocadiscos amb transmissió HTTP Icecast en directe per a Sonos, Home Assistant i reproductors web.

---

## 🚀 Característiques

- **Emparellament i Reconnexió Automàtica**: Detecta quan el tocadiscos s'encén i s'hi connecta immediatament sense intervenció.
- **Emissió en Directe d'Alta Qualitat**: Codificació MP3 256kbps disponible directament a `http://<ip>:8080/sonos.mp3` mitjançant proxy intern.
- **Port Únic per a Tot (8080)**: Interfície web, API REST, Swagger i reproducció d'àudio unificats sota un sol port per facilitar Ingress/Homelab.
- **Panell de Control & Dashboard Web**: Interfície moderna i accessible a `http://<ip>:8080/` amb estat en temps real i animació de vinil.
- **API REST & Swagger UI**: Documentació interactiva OpenAPI a `http://<ip>:8080/docs` i endpoints de control a `/api`.
- **Integració amb Sonos & Home Assistant**: Botons "Enviar a Sonos" i "Aturar Sonos" integrats.
- **Empaquetat per a Docker & Homelab**: Llesta per desplegar amb `docker compose`.

---

## 🛠️ Desplegament amb Docker Compose

### Requisits previs
- Docker & Docker Compose
- Host Linux amb xip/adaptador Bluetooth i dimoni D-Bus actiu (`/var/run/dbus/system_bus_socket`).

### Arrencar el servei
```bash
# Construir i aixecar el contenidor
docker compose up -d

# Veure logs en temps real
docker compose logs -f
```

---

## ☸️ Desplegament amb Kubernetes

Com que el servei interactua directament amb l'adaptador Bluetooth físic del host i el dimoni D-Bus del sistema, el Pod necessita `hostNetwork: true`, mode privilegiat (`privileged: true`), el muntatge del sòcol D-Bus i `/dev`, i s'ha d'executar al node que disposi del maquinari Bluetooth (usant `nodeSelector` o `nodeName`).

### Exemple de Manifest (`turntable-bridge.yaml`)

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: turntable-bridge
  labels:
    app: turntable-bridge
spec:
  replicas: 1
  strategy:
    type: Recreate
  selector:
    matchLabels:
      app: turntable-bridge
  template:
    metadata:
      labels:
        app: turntable-bridge
    spec:
      hostNetwork: true
      dnsPolicy: ClusterFirstWithHostNet
      # Programa el pod al node que tingui l'adaptador Bluetooth físic
      nodeSelector:
        kubernetes.io/hostname: "summer"
      containers:
        - name: turntable-bridge
          image: ghcr.io/alemuro/turntable-bridge:latest
          imagePullPolicy: IfNotPresent
          securityContext:
            privileged: true
          env:
            - name: PORT
              value: "8080"
            - name: TURNTABLE_MAC
              value: "AD:60:17:9B:D5:AC"
            - name: ICECAST_SOURCE_PASSWORD
              value: "canvia_la_contrassenya"
            - name: ICECAST_ADMIN_PASSWORD
              value: "canvia_la_contrassenya"
          volumeMounts:
            - name: dbus-socket
              mountPath: /var/run/dbus/system_bus_socket
            - name: dev-nodes
              mountPath: /dev
          resources:
            requests:
              cpu: 100m
              memory: 128Mi
            limits:
              cpu: 500m
              memory: 512Mi
      volumes:
        - name: dbus-socket
          hostPath:
            path: /var/run/dbus/system_bus_socket
            type: Socket
        - name: dev-nodes
          hostPath:
            path: /dev
            type: Directory
```

> [!NOTE]
> Com que l'aplicació fa proxy intern del flux Icecast, **només cal exposar el port 8080** (interfície web, API i stream d'àudio a `/sonos.mp3`). El port 8000 queda exclusivament per a la comunicació interna entre DarkIce i Icecast.

---

## ⚙️ Variables d'Entorn

| Variable | Descripció | Valor per defecte |
|---|---|---|
| `PORT` | Port del servidor web i API Phonos | `8080` |
| `TURNTABLE_MAC` | Adreça MAC del tocadiscos Bluetooth | `AD:60:17:9B:D5:AC` |
| `ICECAST_HOST` | Hostname/IP per a l'enllaç de streaming Icecast | IP de connexió del client |
| `ICECAST_SOURCE_PASSWORD` | Contrasenya per a la font d'àudio Icecast (i DarkIce) | `hackme` |
| `ICECAST_ADMIN_PASSWORD` | Contrasenya d'administració d'Icecast2 | `hackme` |
| `ICECAST_RELAY_PASSWORD` | Contrasenya de relay d'Icecast2 | Hereta d'`ICECAST_SOURCE_PASSWORD` |
| `ICECAST_ADMIN_USER` | Usuari administrador d'Icecast2 | `admin` |
| `HASS_URL` | URL base de Home Assistant | `http://homeassistant.local:8123` |
| `HASS_TOKEN` | Long-Lived Access Token de Home Assistant | _Buit_ |
| `SONOS_ENTITY_ID` | Entity ID del reproductor Sonos a Home Assistant | `media_player.menjador_sonos_2` |
| `SONOS_STREAM_URL` | URL de l'stream accessible des de Sonos | `http://192.168.1.39:8080/sonos.mp3` |

---

## 📡 Endpoints de l'API

| Mètode | Ruta | Descripció |
|---|---|---|
| `GET` | `/` | Panell de control web interactiu |
| `GET` | `/docs` | Documentació interactiva Swagger UI |
| `GET` | `/openapi.json` | Especificació OpenAPI 3.0 en JSON |
| `GET` | `/api` | Estat complet del sistema (JSON) incloent integració Sonos |
| `GET` | `/sonos.mp3` | Flux d'àudio en directe MP3 (Proxy d'Icecast) |
| `POST` | `/api/connect` | Força la connexió amb el tocadiscos |
| `POST` | `/api/pair` | Activa el mode emparellament i escaneig (30s) |
| `POST` | `/api/disconnect` | Desconnecta el tocadiscos Bluetooth |
| `POST` | `/api/restart-stream` | Reinicia el flux d'àudio DarkIce |
| `POST` | `/api/sonos/play` | Envia l'stream a la barra Sonos via Home Assistant |
| `POST` | `/api/sonos/stop` | Atura la reproducció a Sonos via Home Assistant |

---

## 📂 Estructura del Projecte

```text
turntable-bridge/
├── .github/workflows/
│   └── build.yml               # CI/CD: Multi-arch Docker build & push a GHCR
├── Dockerfile                  # Imatge Docker amb Debian Trixie + Audio + BT
├── docker-compose.yml          # Desplegament amb mode host i D-Bus
├── entrypoint.sh               # Supervisor de processos del contenidor
├── phonos-status-api.py        # Servidor Python API + Swagger + Dashboard
├── bt-turntable-autoconnect.sh # Dimoni de reconnexió automàtica Bluetooth
├── darkice.cfg                 # Configuració DarkIce streamer
├── icecast.xml                 # Configuració Icecast2 server
├── Makefile                    # Dreceres de comandes
├── AGENTS.md                   # Documentació per a assistents d'IA
└── README.md
```
