#!/usr/bin/env bash
set -euo pipefail

REPO_URL="https://github.com/NoCoder4you/CDA-Admin.git"

BASE="/home/pi/discord-bots/bots/CDA Admin"
TARGET="$BASE"
CACHE="$BASE/.repo_cache"
BRANCH=""

echo "[Updater] Cache:  $CACHE"
echo "[Updater] Target: $TARGET"
echo "[Updater] Repo:   $REPO_URL"
echo "----------------------------------"

mkdir -p "$BASE"

if [[ ! -d "$CACHE/.git" ]]; then
  echo "[Updater] Creating cache..."
  rm -rf "$CACHE"
  git clone "$REPO_URL" "$CACHE"
else
  echo "[Updater] Updating cache..."
  git -C "$CACHE" fetch --all --prune
  BRANCH="$(git -C "$CACHE" remote show origin | sed -n 's/.*HEAD branch: //p')"
  [[ -z "$BRANCH" ]] && BRANCH="main"
  git -C "$CACHE" reset --hard "origin/$BRANCH"
  git -C "$CACHE" submodule update --init --recursive
fi

CONTENT_ROOT="$CACHE"

echo "[Updater] Content root: $CONTENT_ROOT"
echo "----------------------------------"

mkdir -p "$TARGET"
rsync -a --delete \
  --exclude ".git" \
  --exclude ".github" \
  --exclude ".gitmodules" \
  --exclude "config.json" \
  --exclude "JSON/admin_settings.json" \
  "$CONTENT_ROOT/" "$TARGET/"

echo "[Updater] Sync complete -> $TARGET"
