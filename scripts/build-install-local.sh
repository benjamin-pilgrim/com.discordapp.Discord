#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${repo_root}"

flatpak-builder \
  --force-clean \
  --user \
  --install \
  --install-deps-from=flathub \
  -y \
  build-dir \
  com.discordapp.Discord.yaml

installed_root="$(flatpak info --user --show-location com.discordapp.Discord)"
python3 scripts/verify-linux-lock-bridge.py \
  "${installed_root}/files/discord/modules/discord_desktop_core/core.asar"

echo "Installed patched Discord from ${repo_root}"
