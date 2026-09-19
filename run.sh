#!/usr/bin/env bash
# ==============================================================================
# ActivityOS — Linux Desktop Launcher (Review 2 Core MVP)
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=================================================================="
echo "  ActivityOS — Activity-Centric Operating System Layer"
echo "  Review 2 Core MVP (60% Functional Implementation)"
echo "=================================================================="

# Check Python version
if ! command -v python3 &> /dev/null; then
    echo "[Error] python3 could not be found. Please install Python 3.8+."
    exit 1
fi

# Run automated tests first if requested
if [[ "$1" == "--test" ]]; then
    echo "Running automated test suite..."
    python3 run_tests.py
    exit 0
fi

# Launch Desktop Application
echo "Starting ActivityOS Desktop Application..."
python3 main.py "$@"
