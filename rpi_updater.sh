#!/usr/bin/env bash
set -euo pipefail

REPO_URL="https://github.com/NoCoder4you/CDA-Admin.git"

TARGET="/home/pi/discord-bots/bots/CDA Admin"
CACHE_BASE="/home/pi/discord-bots/.repo_cache"
CACHE="$CACHE_BASE/CDA-Admin"

echo "[Updater] Cache:  $CACHE"
echo "[Updater] Target: $TARGET"
echo "[Updater] Repo:   $REPO_URL"
echo "----------------------------------"

mkdir -p "$TARGET" "$CACHE_BASE"

if [[ ! -d "$CACHE/.git" ]]; then
  echo "[Updater] Creating cache..."
  rm -rf "$CACHE"
  git clone "$REPO_URL" "$CACHE"
else
  echo "[Updater] Updating cache..."
  git -C "$CACHE" fetch --all --prune
fi

# Determine default branch robustly
BRANCH="$(git -C "$CACHE" symbolic-ref --quiet --short refs/remotes/origin/HEAD 2>/dev/null | sed 's@^origin/@@' || true)"
if [[ -z "${BRANCH:-}" ]]; then
  # fallback if origin/HEAD isn't set
  if git -C "$CACHE" show-ref --verify --quiet refs/remotes/origin/main; then
    BRANCH="main"
  elif git -C "$CACHE" show-ref --verify --quiet refs/remotes/origin/master; then
    BRANCH="master"
  else
    BRANCH="main"
  fi
fi

echo "[Updater] Branch: $BRANCH"

git -C "$CACHE" reset --hard "origin/$BRANCH"
git -C "$CACHE" submodule update --init --recursive

echo "----------------------------------"
echo "[Updater] Syncing files..."

rsync -a --delete \
  --filter='P bot.py' \
  --exclude='bot.py' \
  --exclude='.git' \
  --exclude='.repo_cache' \
  "$CACHE/" "$TARGET/"

echo "[Updater] Sync complete -> $TARGET"
