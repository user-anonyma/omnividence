#!/usr/bin/env bash
# Omnividence installer - Downloads and runs the latest release

set -e
export PATH="/usr/local/bin:/usr/bin:/bin:$PATH"

REPO="user-anonyma/omnividence"
INSTALL_DIR="${1:-.}"
VERSION_FILE="VERSION"

echo "📥 Omnividence Installer"
echo "========================"

# Check for Docker
if ! command -v docker &> /dev/null; then
  echo "❌ Docker not found. Install from https://docker.com"
  exit 1
fi

if ! command -v docker-compose &> /dev/null; then
  echo "❌ docker-compose not found. Install from https://docs.docker.com/compose"
  exit 1
fi

echo "✅ Docker and docker-compose found"
echo ""

# Clone the repo
echo "📦 Cloning omnividence..."
if [ -d "$INSTALL_DIR/omnividence" ]; then
  echo "   Directory exists, updating..."
  cd "$INSTALL_DIR/omnividence"
  git pull origin main
else
  git clone https://github.com/$REPO.git "$INSTALL_DIR/omnividence"
  cd "$INSTALL_DIR/omnividence"
fi

# Get version
VERSION=$(cat $VERSION_FILE 2>/dev/null || echo "unknown")
echo "✅ Version: $VERSION"
echo ""

# Start containers
echo "🚀 Starting omnividence..."
docker-compose up -d

echo ""
echo "✅ Omnividence is running!"
echo ""
echo "📍 Open your browser to: http://localhost:3000"
echo ""
echo "To stop: docker-compose down"
echo "To view logs: docker-compose logs -f"
