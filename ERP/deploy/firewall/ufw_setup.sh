#!/usr/bin/env bash
set -euo pipefail

# Allow SSH, HTTP, HTTPS and deny everything else by default.
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

# Keep DB and internal services local-only. No public allow rules for 5432/6432.
sudo ufw enable
sudo ufw status verbose
