#!/usr/bin/env bash
# Clean stale test artifacts
set -euo pipefail
cd "$(dirname "$0")/.."
find tests -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
find tests -name "*.pyc" -delete 2>/dev/null || true
echo "✓ Test caches cleaned"