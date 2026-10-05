# 📻 Turntable Bridge (`phonos`)

> Pont d'àudio Bluetooth per a tocadiscos amb transmissió HTTP Icecast en directe per a Sonos, Home Assistant i reproductors web.

---

## 🚀 Característiques

- **Emparellament i Reconnexió Automàtica**: Detecta quan el tocadiscos s'encén i s'hi connecta immediatament sense intervenció.
- **Emissió en Directe d'Alta Qualitat**: Codificació MP3 256kbps a `http://<ip>:8000/sonos.mp3`.
- **Panell de Control & Dashboard Web**: Interfície moderna i accessible a `http://<ip>/` amb estat en temps real i animació de vinil.
- **API REST & Swagger UI**: Documentació interactiva OpenAPI a `http://<ip>/docs` i endpoints de control a `/api`.
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
      # nodeSelector:
      #   kubernetes.io/hostname: "nom-del-node-bluetooth"
      containers:
        - name: turntable-bridge
          image: ghcr.io/alemuro/turntable-bridge:latest
          imagePullPolicy: IfNotPresent
          securityContext:
            privileged: true
          env:
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
> Com que s'utilitza `hostNetwork: true`, els ports 80 (API i Dashboard Web) i 8000 (Stream Icecast) s'exposen directament a la IP del node del clúster.

---

## ⚙️ Variables d'Entorn

| Variable | Descripció | Valor per defecte |
|---|---|---|
| `TURNTABLE_MAC` | Adreça MAC del tocadiscos Bluetooth | `AD:60:17:9B:D5:AC` |
| `ICECAST_SOURCE_PASSWORD` | Contrasenya per a la font d'àudio Icecast (i DarkIce) | `hackme` |
| `ICECAST_ADMIN_PASSWORD` | Contrasenya d'administració d'Icecast2 | `hackme` |
| `ICECAST_RELAY_PASSWORD` | Contrasenya de relay d'Icecast2 | Hereta d'`ICECAST_SOURCE_PASSWORD` |
| `ICECAST_ADMIN_USER` | Usuari administrador d'Icecast2 | `admin` |



---

## 📡 Endpoints de l'API

| Mètode | Ruta | Descripció |
|---|---|---|
| `GET` | `/` | Panell de control web interactiu |
| `GET` | `/docs` | Documentació interactiva Swagger UI |
| `GET` | `/openapi.json` | Especificació OpenAPI 3.0 en JSON |
| `GET` | `/api` | Estat complet del sistema (JSON) |
| `POST` | `/api/connect` | Força la connexió amb el tocadiscos |
| `POST` | `/api/pair` | Activa el mode emparellament i escaneig (30s) |
| `POST` | `/api/disconnect` | Desconnecta el tocadiscos Bluetooth |
| `POST` | `/api/restart-stream` | Reinicia el flux d'àudio DarkIce |

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
