#!/usr/bin/env bash
# Install Docker Engine + Compose plugin on Ubuntu 26.04 (resolute) and grant
# the current login user docker access. Run with sudo:  sudo bash docker/install_docker.sh
# (Codename "resolute" is present in Docker's apt repo — verified.)
set -euo pipefail

TARGET_USER="${SUDO_USER:-$USER}"

apt-get update
apt-get install -y ca-certificates curl gnupg

install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg

. /etc/os-release
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" \
  > /etc/apt/sources.list.d/docker.list

apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

systemctl enable --now docker

# Let the normal user run docker without sudo.
usermod -aG docker "$TARGET_USER"

echo
echo "Docker installed. '$TARGET_USER' added to the docker group."
echo "IMPORTANT: that user must start a NEW login session (log out/in, or: newgrp docker)"
echo "for group membership to take effect. Verify with:  docker run --rm hello-world"
