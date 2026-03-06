#!/bin/bash
# ─── Deploy Script for Trail Planner ───────────────────────────────
# Connects to the server, pulls latest code, rebuilds and restarts Docker.
# Usage: ./deploy.sh

set -e

SERVER="falcon@217.154.206.236"
KEY="~/.ssh/id_rsa"
PROJECT_DIR="/home/falcon/trail-planner"

echo "🚀 Connecting to server and deploying..."

ssh -i "$KEY" "$SERVER" << 'EOF'
  set -e
  cd /home/falcon/trail-planner

  echo "⏬ Stopping containers..."
  docker compose down

  echo "📥 Pulling latest code..."
  git pull

  echo "🔨 Building containers..."
  docker compose build

  echo "🟢 Starting containers..."
  docker compose up -d

  echo "✅ Deployment complete!"
EOF
