#!/usr/bin/env bash
# Bundle the local ADTOF audio-to-score engine (scripts + models + Python) into DB Score.
#
# This re-configures an existing build directory with the bundling paths and
# rebuilds/installs so that "Import Audio to Score" works offline on any machine.
#
# Usage:
#   ./buildscripts/bundle_adtof.sh [--build <build_dir>] [--adtof <dir>] [--python <dir>]
#
# Defaults (edit or override):
#   ADTOF dir:  $HOME/Documents/Codex/2026-09-04/wo/work/sources/desktop/adtof
#   Python dir: $HOME/.workbuddy/binaries/python/envs/adtof

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

DEFAULT_ADTOF_DIR="$HOME/Documents/Codex/2026-09-04/wo/work/sources/desktop/adtof"
DEFAULT_PYTHON_DIR="$HOME/.workbuddy/binaries/python/envs/adtof"

ADTOF_DIR="${DEFAULT_ADTOF_DIR}"
PYTHON_DIR="${DEFAULT_PYTHON_DIR}"
BUILD_DIR=""

while [[ "$#" -gt 0 ]]; do
    case "$1" in
        --build)  BUILD_DIR="$2"; shift ;;
        --adtof)  ADTOF_DIR="$2"; shift ;;
        --python) PYTHON_DIR="$2"; shift ;;
        --help|-h)
            echo "Usage: $0 [--build <build_dir>] [--adtof <dir>] [--python <dir>]"
            exit 0
            ;;
        *) echo "Unknown argument: $1" >&2; exit 1 ;;
    esac
    shift
done

# Resolve the build directory if not provided.
if [[ -z "$BUILD_DIR" ]]; then
    BUILD_DIR="$(find "$ROOT_DIR/builds" -maxdepth 1 -type d -name 'Mac-*-Ninja-*' 2>/dev/null | head -n 1)"
fi

if [[ -z "$BUILD_DIR" || ! -f "$BUILD_DIR/CMakeCache.txt" ]]; then
    echo "error: could not find a configured build directory (pass --build <dir>)" >&2
    exit 1
fi

# Validate the engine sources.
if [[ ! -f "$ADTOF_DIR/transcribe_mdx.py" ]]; then
    echo "error: transcribe_mdx.py not found in ADTOF dir: $ADTOF_DIR" >&2
    exit 1
fi

if [[ -n "$PYTHON_DIR" && ! -x "$PYTHON_DIR/bin/python" && ! -x "$PYTHON_DIR/bin/python3" ]]; then
    echo "error: python executable not found in Python dir: $PYTHON_DIR" >&2
    exit 1
fi

echo "Bundling ADTOF engine into build:"
echo "  build : $BUILD_DIR"
echo "  adtof : $ADTOF_DIR"
echo "  python: ${PYTHON_DIR:-<not bundled>}"
echo

CMAKE_ARGS=("-DMUSE_ADTOF_SOURCE_DIR=$ADTOF_DIR")
if [[ -n "$PYTHON_DIR" ]]; then
    CMAKE_ARGS+=("-DMUSE_ADTOF_PYTHON_DIR=$PYTHON_DIR")
fi

# Re-configure, build and install.
cmake "${CMAKE_ARGS[@]}" "$BUILD_DIR"
cmake --build "$BUILD_DIR" --target install -j "$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 4)"

echo
echo "Done. Verify the bundled files below:"
INSTALL_DIR="${MUSESCORE_INSTALL_DIR:-$ROOT_DIR/build.install}"
if [[ -d "$INSTALL_DIR/dbscore.app" ]]; then
    ls -la "$INSTALL_DIR/dbscore.app/Contents/Resources/adtof" 2>/dev/null | head
    [[ -n "$PYTHON_DIR" ]] && ls -la "$INSTALL_DIR/dbscore.app/Contents/Resources/python/bin" 2>/dev/null | head
fi
