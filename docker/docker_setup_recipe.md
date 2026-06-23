# MetViz infrastructure recipe — Docker Compose + Traefik (`/api` + `/panel`)

Plain `docker compose` on one Ubuntu node. **Traefik** sits in front and does
simple path routing on the published port:

```
https://<host>/api/    -> ncapp   (FastAPI / METAPI)
https://<host>/panel/  -> ncview  (Panel / Bokeh apps)
```

FastAPI and Celery are scaled to **use all CPU cores** (this machine: **16**).
TLS/domain/LB upstream are still the sysadmin's external proxy; Traefik speaks
HTTP internally (see §TLS note if Traefik should terminate TLS instead).

> **Canonical files (validated on this server).** The runnable config lives at
> the repo root, not in this doc — use those; the snippets below are explanatory:
> - `docker-compose.prod.yml`, `.env` (gitignored), `docker/entrypoint.sh`
> - `docker/install_rootless_docker.sh` — **rootless Docker** install (no root daemon)
>
> Deployment gotchas we actually hit, baked into those files:
> - **Rootless Docker:** Traefik mounts the rootless socket
>   `/run/user/<uid>/docker.sock` (via `DOCKER_SOCK` in `.env`), not
>   `/var/run/docker.sock`. Binding `:80` needs
>   `net.ipv4.ip_unprivileged_port_start=80` (the install script sets it).
> - **Traefik must be ≥ v3.7** (`traefik:v3.7.5`): v3.3 defaults to Docker API
>   1.24, which Engine 29.x rejects (min 1.40) → all routes 404.
> - **Trajectory app mounts at `/TRJ`** (not `/trj`) to match the served app path.
> - **`ncview` runs `--use-xheaders`** + a configurable `--allow-websocket-origin`
>   (`PANEL_ALLOW_ORIGIN`, default `*`; pin to the public host in production).
> - The upstream ingress **must forward WebSockets** — see the ⚠ section below.

---

## Routing model (how the two prefixes work)

The app currently assumes it's served at the **root**, so mounting it under
`/api` and `/panel` needs both Traefik rules **and** a few app changes (next
section). The mechanism:

- **`/api` → `ncapp`:** Traefik **strips** `/api`, and uvicorn runs with
  `--root-path /api` so the app matches its root routes (`/TSP`, `/process_data`,
  `/results/{token}`, …) while generating correct `/api/…` URLs back to the
  browser.
- **`/panel` → `ncview`:** Traefik does **not** strip; instead `panel serve`
  runs with `--prefix /panel`, so Bokeh emits `/panel/…`-prefixed app,
  WebSocket (`/panel/TSP/ws`) and resource URLs. (Stripping doesn't work here —
  Bokeh would generate root-relative WS URLs that 404.)

Browser flow: user opens `/panel/Catalog` → picks a dataset → catalog redirects
to `/api/TSP?url=…` (the FastAPI embed page) → that page embeds a Bokeh script
from `/panel/TSP` → Bokeh opens a WebSocket to `/panel/TSP/ws`.

---

## ⚠ Upstream proxy / ingress requirements — WebSocket (REQUIRED)

The Panel/Bokeh apps are **not** plain HTTP — every app opens a long-lived
**WebSocket** (`wss://<host>/panel/<App>/ws`). If the upstream proxy/ingress
forwards HTTP but drops the WebSocket upgrade, **the page template renders but
the app stays blank** (browser console: "Could not open websocket"). This was
the single failure we hit in `metsis-dev`: HTTP reached the box, the WS did not.

The upstream proxy that fronts this server (e.g. the k8s ingress for
`metviz.metsis-dev.k8s.met.no`) **must**:

- forward `Upgrade` + `Connection: Upgrade` over **HTTP/1.1** to the backend `:80`;
- **preserve the `Sec-WebSocket-Protocol` header** — Bokeh requires the `bokeh`
  subprotocol and rejects the socket without it (`ProtocolError: Subprotocol
  header is not 'bokeh'`);
- set a long read/idle timeout on `/panel/` (e.g. **3600s**) — the socket stays open;
- keep sending `X-Forwarded-Proto: https` and `X-Forwarded-Host` (the Panel
  server runs with `--use-xheaders` and relies on them to emit `wss://` + the
  public host).

ingress-nginx forwards WebSockets by default — verify `proxy-read-timeout` /
`proxy-send-timeout` aren't tiny and that no auth layer (oauth2-proxy) or service
mesh (Istio) in front strips the upgrade.

**Diagnose it** — a Bokeh WS handshake returns `101` direct to the box but not
through a broken proxy:

```bash
curl -sS -o /dev/null -w "%{http_code}\n" \
  -H "Connection: Upgrade" -H "Upgrade: websocket" -H "Sec-WebSocket-Version: 13" \
  -H "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==" \
  -H "Sec-WebSocket-Protocol: bokeh, testtoken" \
  https://<public-host>/panel/Catalog/ws        # 101 = WS forwarded; else proxy drops it
```

Server-side confirmation that a real session opened: `ServerConnection created`
in `docker compose -f docker-compose.prod.yml logs ncview`.

---

## Required application changes (mount under `/api` + `/panel`)

These are small but **necessary** — without them the first click 404s. Critical
items block core flows; cosmetic items are nav/logo polish.

| File | Change | Why | Priority |
|------|--------|-----|----------|
| `docker/entrypoint.sh` | add `${PANEL_PREFIX:+--prefix ${PANEL_PREFIX}}` to the `panel serve` line | serve Panel under `/panel`; env-gated so dev (unset) is unchanged | **critical** |
| `ncapp` command (compose) | `uvicorn … --root-path /api --workers <N> --proxy-headers --forwarded-allow-ips='*'` | match root routes behind the strip; correct scheme/links; all cores | **critical** |
| `ncapp/app/templates/download.html:17` | `href="/file_results/{{ token }}"` → `href="{{ request.scope.root_path }}/file_results/{{ token }}"` | the download button must point at `/api/file_results/…`, not `/file_results/…` | **critical** |
| `metviz/catalog/main.py` | `f"/{target_app_for(...)}?url={url}"` → `f"{_PANEL_PREFIX}/{target_app_for(...)}?url={url}"` with `_PANEL_PREFIX=os.environ.get("PANEL_PREFIX","")` | catalog redirects straight to the **Panel app** (`/panel/TSP`), not the FastAPI embed (`/api/TSP`) whose container div has no resolvable height | **critical** |
| env (`.env` / compose) | `DOWNLOAD_ENDPOINT=https://${PUBLIC_HOST}/api`, `PANEL_TSP_URL=https://${PUBLIC_HOST}/panel/TSP`, `PANEL_TRJ_URL=…/panel/TRJ`, `API_BASE=/api`, `PANEL_PREFIX=/panel` | point browser-facing links/embeds at the prefixed paths | **critical** |
| `metviz/assets/custom_index.html:137,139,140,151` | make `/assets/…`, `/`, `/logout` prefix-aware (`/panel/assets/…`, `/panel/`, …) | logo / home / logout links under `/panel` | cosmetic |

> I can apply all of these in one pass — they're the bridge between IT's URL
> scheme and the current root-assuming app. The infra below assumes they're in.

---

## Concurrency — use all cores (16)

- **FastAPI (`ncapp`):** `uvicorn … --workers ${UVICORN_WORKERS:-$(nproc)}`.
  Tokens are stateless and files live on a shared volume, so multiple workers
  are safe. 16 uvicorn workers is memory-hungry for a light embed API — tune
  `UVICORN_WORKERS` down (e.g. 4–8) if RAM is tight; default honors "all cores".
- **Celery (`worker`):** `celery … worker --concurrency ${CELERY_CONCURRENCY:-$(nproc)}`
  (prefork pool — right for the CPU-bound xarray/NetCDF export). Keep a **single**
  worker container running `--beat`, so the periodic sweeper fires once.

---

## 1. Prerequisites — fresh Ubuntu node

```bash
sudo hostnamectl set-hostname metviz
sudo apt-get update && sudo apt-get upgrade -y
sudo apt-get install -y ca-certificates curl gnupg ufw git

PROXY_IP=203.0.113.10            # <-- the sysadmin's proxy source IP
PUBLIC_PORT=80                   # the port the proxy forwards to (Traefik web entrypoint)
sudo ufw allow OpenSSH
sudo ufw allow from "$PROXY_IP" to any port "$PUBLIC_PORT" proto tcp
sudo ufw --force enable
```

> Only Traefik's entrypoint is published; ncapp/ncview/redis stay on the
> internal Docker network.

---

## 2. Install Docker Engine + Compose plugin

```bash
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | \
  sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io \
  docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker "$USER"; newgrp docker
sudo systemctl enable docker        # survive reboots
docker version
```

---

## 3. Code + `.env`

```bash
sudo mkdir -p /opt/metviz && sudo chown "$USER" /opt/metviz
git clone <your-repo-url> /opt/metviz
cd /opt/metviz

KEY=$(openssl rand -hex 32)
cat > .env <<EOF
DOWNLOAD_SIGNING_KEY=$KEY
PUBLIC_HOST=metviz.example.org      # public name the proxy exposes (placeholder OK)
PUBLIC_PORT=80
API_BASE=/api
PANEL_PREFIX=/panel
# UVICORN_WORKERS=8                 # uncomment to cap below nproc
EOF
chmod 600 .env
grep -q '^\.env$' .gitignore 2>/dev/null || echo '.env' >> .gitignore
```

> App code is bind-mounted (the images bake only deps), so the repo must live on
> the machine.

---

## 4. `docker-compose.prod.yml`

```yaml
# Production: Traefik front, /api -> ncapp, /panel -> ncview, all cores.
services:
  traefik:
    image: traefik:v3.3
    command:
      - --providers.docker=true
      - --providers.docker.exposedbydefault=false
      - --entrypoints.web.address=:80
      # - --api.dashboard=true --api.insecure=true   # optional, internal only
    ports:
      - "${PUBLIC_PORT:-80}:80"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
    restart: unless-stopped

  ncview:
    image: epinux/ncmet:latest
    build:
      context: ./docker
    environment:
      PORT: '7000'
      LOG_LEVEL: 'info'
      PANEL_PREFIX: '${PANEL_PREFIX}'                   # -> panel serve --prefix /panel
      TSPLOT_DOWNLOAD: '/tspt/Download'
      PROCESSING_ENDPOINT: 'http://ncapp:8000'
      DOWNLOAD_ENDPOINT: 'https://${PUBLIC_HOST}/api'
      DOWNLOAD_SIGNING_KEY: '${DOWNLOAD_SIGNING_KEY}'
      API_BASE: '${API_BASE}'                            # catalog redirects -> /api/...
      PYTHONUNBUFFERED: '1'
      PYTHONPATH: '/app:/seaice:/seaicemod:/opt/metviz'
      SEAICE_APP_ROOT: '/seaice'
      SEAICEMOD_APP_ROOT: '/seaicemod'
    volumes:
      - ./metviz/trj:/trj
      - ./metviz/TSP:/TSP
      - ./metviz/catalog:/Catalog
      - ./metviz/OGC_client:/OGC_client
      - ./metviz/common:/opt/metviz/common
      - ./metviz/assets:/assets
      - ./docker/entrypoint.sh:/entrypoint.sh
    entrypoint: ["/entrypoint.sh"]
    labels:
      - traefik.enable=true
      - traefik.http.routers.panel.rule=PathPrefix(`/panel`)
      - traefik.http.routers.panel.entrypoints=web
      - traefik.http.services.panel.loadbalancer.server.port=7000
    restart: unless-stopped

  ncapp:
    build:
      context: ./ncapp
    environment:
      TSPLOT_DOWNLOAD: '/data/Download'
      DOWNLOAD_SIGNING_KEY: '${DOWNLOAD_SIGNING_KEY}'
      DOWNLOAD_TTL_SECONDS: '600'
      CELERY_BROKER_URL: 'redis://redis:6379/0'
      CELERY_RESULT_BACKEND: 'redis://redis:6379/0'
      PANEL_TSP_URL: 'https://${PUBLIC_HOST}/panel/TSP'
      PANEL_TRJ_URL: 'https://${PUBLIC_HOST}/panel/TRJ'
      PYTHONUNBUFFERED: '1'
      PYTHONPATH: '/app:/opt/metviz'
    volumes:
      - ./ncapp/app:/app
      - ./metviz/common:/opt/metviz/common
      - download-data:/data/Download
    command: >
      sh -c 'exec uvicorn main:app --host 0.0.0.0 --port 8000
      --workers ${UVICORN_WORKERS:-$(nproc)}
      --proxy-headers --forwarded-allow-ips=* --root-path /api'
    labels:
      - traefik.enable=true
      - traefik.http.routers.api.rule=PathPrefix(`/api`)
      - traefik.http.routers.api.entrypoints=web
      - traefik.http.routers.api.middlewares=api-strip
      - traefik.http.middlewares.api-strip.stripprefix.prefixes=/api
      - traefik.http.services.api.loadbalancer.server.port=8000
    depends_on:
      - redis
    restart: unless-stopped

  worker:
    build:
      context: ./ncapp
    working_dir: /app
    environment:
      TSPLOT_DOWNLOAD: '/data/Download'
      DOWNLOAD_SIGNING_KEY: '${DOWNLOAD_SIGNING_KEY}'
      DOWNLOAD_TTL_SECONDS: '600'
      CELERY_BROKER_URL: 'redis://redis:6379/0'
      CELERY_RESULT_BACKEND: 'redis://redis:6379/0'
      PYTHONUNBUFFERED: '1'
      PYTHONPATH: '/app:/opt/metviz'
    volumes:
      - ./ncapp/app:/app
      - ./metviz/common:/opt/metviz/common
      - download-data:/data/Download
    command: >
      sh -c 'exec celery -A worker.celery worker --beat --loglevel=info
      --concurrency=${CELERY_CONCURRENCY:-$(nproc)}'
    depends_on:
      - redis
    restart: unless-stopped

  redis:
    image: redis:7
    command: ["redis-server", "--appendonly", "yes"]
    volumes:
      - redis-data:/data
    restart: unless-stopped

volumes:
  download-data:
  redis-data:
```

> **`entrypoint.sh` edit (one line):** append `${PANEL_PREFIX:+--prefix ${PANEL_PREFIX}}`
> to the `panel serve …` command so prod serves under `/panel` while dev (no
> `PANEL_PREFIX`) is unchanged.

---

## TLS note

IT wrote `https://…`. Two readings:
- **External proxy terminates TLS (assumed here):** Traefik runs HTTP on the
  published port; the proxy forwards over the internal network. The
  `--proxy-headers`/`X-Forwarded-Proto` wiring makes the app emit `https`/`wss`
  URLs. Nothing else to do.
- **Traefik should terminate TLS:** add a `websecure` entrypoint on `:443`, a
  cert (Let's Encrypt resolver or a cert the org provides), and
  `entrypoints=websecure` + `tls=true` on both routers. Tell me if IT wants this
  and I'll add the block.

---

## 5. Bring it up + smoke test

```bash
cd /opt/metviz
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml ps

# Cores in use:
docker compose -f docker-compose.prod.yml exec ncapp  sh -c 'ps -e | grep -c uvicorn'   # ~workers+1
docker compose -f docker-compose.prod.yml exec worker celery -A worker.celery inspect stats | grep -i concurrency

# Routing (through the proxy, or locally if the port is open):
curl -i "http://<host>/api/TSP?url=<opendap-url>"     # 200 HTML (FastAPI embed page)
curl -i "http://<host>/panel/Catalog"                 # 200 (Panel app)
```

Then open `https://<public-host>/panel/Catalog` in a browser, pick a dataset,
confirm it redirects to `/api/TSP?url=…`, the plot renders (WebSocket 101 to
`/panel/TSP/ws` in the network tab), and a download link works end-to-end.

---

## 6. Day-2

```bash
cd /opt/metviz; C="docker compose -f docker-compose.prod.yml"
$C ps; $C logs -f traefik ncapp ncview
git pull && $C up -d --build        # deploy code (bind-mounted)
$C down
```

**Back up:** `redis-data` + `.env` (the signing key). `download-data` is
TTL-swept and ephemeral.

---

## Open items

- [ ] **Apply the app changes** in the "Required application changes" table
      (entrypoint `--prefix`, download.html link, catalog redirect, env). Say
      the word and I'll do them.
- [ ] **TLS termination location** — external proxy (default) vs Traefik.
- [ ] **Entry path** — give the sysadmin `/panel/Catalog` as the landing URL
      (ncapp has no `/` route; optionally add a Traefik redirect `/` → it).
- [ ] **`UVICORN_WORKERS`** — keep at 16 or cap for RAM.
- [ ] **Proxy source IP** for the UFW rule; **`PUBLIC_HOST`** once the domain is
      assigned.
```
