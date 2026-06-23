#!/usr/bin/env bash
#
# Install ROOTLESS Docker for the current user on Ubuntu 26.04 (resolute).
#
#   RUN THIS AS YOUR NORMAL USER  -- do NOT prefix with sudo.
#   It calls sudo only for the few root-only steps and will prompt for your
#   password.  The Docker daemon ends up running as YOU (no root daemon).
#
#     bash docker/install_rootless_docker.sh
#
set -euo pipefail

USER_NAME="$(id -un)"
USER_UID="$(id -u)"

if [ "${USER_UID}" = "0" ]; then
  echo "ERROR: run this as your normal user, NOT with sudo." >&2
  echo "It will invoke sudo itself for the steps that need root." >&2
  exit 1
fi

echo "==> [sudo] Installing rootless prerequisites + Docker packages"
sudo apt-get update
sudo apt-get install -y \
  ca-certificates curl gnupg \
  uidmap dbus-user-session slirp4netns fuse-overlayfs

# --- Docker apt repo (codename 'resolute' is published by Docker) ---
sudo install -m 0755 -d /etc/apt/keyrings
if [ ! -f /etc/apt/keyrings/docker.gpg ]; then
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
    | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  sudo chmod a+r /etc/apt/keyrings/docker.gpg
fi
. /etc/os-release
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null

sudo apt-get update
sudo apt-get install -y \
  docker-ce docker-ce-cli containerd.io \
  docker-buildx-plugin docker-compose-plugin \
  docker-ce-rootless-extras

# --- Disable the system-wide (rootful) daemon: we run rootless only ---
sudo systemctl disable --now docker.service docker.socket 2>/dev/null || true

# --- subordinate UID/GID ranges (already present on this host, kept idempotent) ---
if ! grep -q "^${USER_NAME}:" /etc/subuid; then
  sudo usermod --add-subuids 100000-165535 --add-subgids 100000-165535 "${USER_NAME}"
fi

# --- Keep the rootless daemon alive without an active login session ---
sudo loginctl enable-linger "${USER_NAME}"

# --- Allow rootless to bind privileged ports so Traefik can publish :80 ---
echo 'net.ipv4.ip_unprivileged_port_start=80' \
  | sudo tee /etc/sysctl.d/99-rootless-docker.conf >/dev/null
sudo sysctl --system >/dev/null

echo "==> Installing the rootless daemon for ${USER_NAME} (no sudo from here on)"
export XDG_RUNTIME_DIR="/run/user/${USER_UID}"
export PATH="/usr/bin:${PATH}"
export DOCKER_HOST="unix://${XDG_RUNTIME_DIR}/docker.sock"

systemctl --user daemon-reload 2>/dev/null || true
dockerd-rootless-setuptool.sh install
systemctl --user enable --now docker

# --- Persist env for future login shells ---
SHRC="${HOME}/.bashrc"
if ! grep -q 'rootless Docker' "${SHRC}" 2>/dev/null; then
  cat >> "${SHRC}" <<'EOF'

# --- rootless Docker ---
export XDG_RUNTIME_DIR="/run/user/$(id -u)"
export PATH="/usr/bin:$PATH"
export DOCKER_HOST="unix://${XDG_RUNTIME_DIR}/docker.sock"
EOF
fi

echo
echo "================================================================"
echo " Rootless Docker installed for ${USER_NAME}."
echo " Daemon socket: ${DOCKER_HOST}"
echo
echo " Open a NEW shell (or run: source ~/.bashrc), then verify:"
echo "     docker run --rm hello-world"
echo "     docker info --format '{{.SecurityOptions}}'   # should list rootless"
echo "================================================================"
