#!/bin/bash
# package.sh - Automated packaging script for distribution

VERSION=${1:-"1.0.0"}
PACKAGE_NAME="energyid-monitor-v${VERSION}.tar.gz"

# Get the project root directory (parent of scripts/)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Create dist directory if it doesn't exist
DIST_DIR="$PROJECT_ROOT/dist"
mkdir -p "$DIST_DIR"

PACKAGE_PATH="$DIST_DIR/$PACKAGE_NAME"

echo "========================================"
echo "EnergyID Monitor - Distribution Packager"
echo "========================================"
echo ""
echo "Creating package: $PACKAGE_NAME"
echo "Version: $VERSION"
echo ""

# Check if we're in the right directory structure
if [ ! -f "$PROJECT_ROOT/src/energyid_monitor/energyid.py" ]; then
    echo "❌ Error: src/energyid_monitor/energyid.py not found. Please run this script from the project directory."
    exit 1
fi

# Change to project root for tar operations
cd "$PROJECT_ROOT"

# Create the tarball
tar -czf "$PACKAGE_PATH" \
  --exclude='.venv' \
  --exclude='data' \
  --exclude='__pycache__' \
  --exclude='.pytest_cache' \
  --exclude='*.pyc' \
  --exclude='*.pyo' \
  --exclude='.env' \
  --exclude='.git*' \
  --exclude='uv.lock' \
  --exclude='*.tar.gz' \
  --exclude='dist' \
  --exclude='tests' \
  --transform 's,^,energyid-monitor/,' \
  src/energyid_monitor \
  dbscripts \
  pyproject.toml \
  scripts/deploy.sh \
  env.example \
  DEPLOYMENT.md \
  CRONTAB-SETUP.md \
  DISTRIBUTION.md \
  README.md

if [ $? -eq 0 ]; then
    echo "✓ Package created successfully!"
    echo ""
    echo "Package details:"
    echo "  File: $PACKAGE_PATH"
    echo "  Size: $(du -h "$PACKAGE_PATH" | cut -f1)"
    echo ""
    echo "Contents:"
    tar -tzf "$PACKAGE_PATH"
    echo ""
    echo "Next steps:"
    echo "1. Transfer $PACKAGE_NAME to target system"
    echo "2. Extract: tar -xzf $PACKAGE_NAME"
    echo "3. Run: cd energyid-monitor && ./scripts/deploy.sh"
    echo ""
    echo "See DISTRIBUTION.md for more transfer options."
else
    echo "❌ Error creating package"
    exit 1
fi
