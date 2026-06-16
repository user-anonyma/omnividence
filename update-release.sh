#!/usr/bin/env bash
# update-release.sh - Update version and create GitHub release

set -e
export PATH="/usr/local/bin:/usr/bin:/bin:$PATH"

NEW_VERSION="${1:?Usage: ./update-release.sh <version> [release-notes-file]}"
RELEASE_NOTES_FILE="${2:-RELEASE_NOTES.md}"

VERSION_FILE="VERSION"
REPO="user-anonyma/omnividence"

echo "🔄 Omnividence Release Manager"
echo "================================"
echo ""

# Validate version format (semantic versioning)
if ! [[ $NEW_VERSION =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "❌ Invalid version format. Use semantic versioning (e.g., 1.0.1)"
  exit 1
fi

# Get current version
CURRENT_VERSION=$(cat $VERSION_FILE)
echo "Current version: $CURRENT_VERSION"
echo "New version: $NEW_VERSION"
echo ""

# Update VERSION file
echo "$NEW_VERSION" > $VERSION_FILE
echo "✅ Updated VERSION file"

# Commit and tag
echo "📝 Committing changes..."
git add .
git commit -m "Release v$NEW_VERSION" || echo "   (no changes to commit)"

echo "🏷️  Creating git tag..."
git tag -a "v$NEW_VERSION" -m "Release v$NEW_VERSION" || echo "   (tag may already exist)"

# Push to GitHub
echo "📤 Pushing to GitHub..."
git push origin main
git push origin "v$NEW_VERSION" || echo "   (tag push skipped)"

echo ""
echo "✅ Release v$NEW_VERSION created!"
echo ""
echo "📍 View on GitHub: https://github.com/$REPO/releases/tag/v$NEW_VERSION"
