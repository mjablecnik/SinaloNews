#!/bin/bash
set -euo pipefail

# Build and run the Go backup tool
SCRIPT_DIR="$(dirname "$(realpath "$0")")"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR/scripts/backup-db"
go run . "$PROJECT_DIR" "$@"
