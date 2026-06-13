#!/usr/bin/env bash
# Build a single-file Windows launcher (floodsim-emulator.exe) from Linux.
#
# Since PyInstaller can't cross-compile, this instead bundles the official
# Python embeddable runtime for Windows + paho-mqtt + the emulator scripts
# + the recording into a self-extracting NSIS archive that silently
# unpacks to %TEMP% and runs the emulator.
#
# Requires: makensis (NSIS), pip, internet access.
set -e
cd "$(dirname "$0")"

PY_VERSION="3.11.9"
PAHO_VERSION="2.1.0"
BUILD_DIR="windows_build"
PAYLOAD="$BUILD_DIR/payload"

rm -rf "$BUILD_DIR"
mkdir -p "$PAYLOAD/python"

echo "Downloading Python $PY_VERSION embeddable runtime..."
curl -sL --fail -o "$BUILD_DIR/python-embed.zip" \
    "https://www.python.org/ftp/python/${PY_VERSION}/python-${PY_VERSION}-embed-amd64.zip"
unzip -q "$BUILD_DIR/python-embed.zip" -d "$PAYLOAD/python"

# Enable site-packages so paho-mqtt can be imported.
PTH_FILE=$(find "$PAYLOAD/python" -maxdepth 1 -name 'python3*._pth')
printf 'python%s.zip\n.\nLib\\site-packages\nimport site\n' \
    "$(echo "$PY_VERSION" | cut -d. -f1,2 | tr -d .)" > "$PTH_FILE"

echo "Downloading paho-mqtt $PAHO_VERSION..."
mkdir -p "$PAYLOAD/python/Lib/site-packages"
pip download --no-deps --only-binary=:all: --python-version 311 --platform any \
    -d "$BUILD_DIR/wheels" "paho-mqtt==${PAHO_VERSION}" >/dev/null
unzip -q "$BUILD_DIR"/wheels/paho_mqtt-*.whl -d "$PAYLOAD/python/Lib/site-packages"

echo "Copying emulator scripts and recording..."
cp emulator_app.py ../mqtt_replayer.py recording.jsonl "$PAYLOAD/"

echo "Building installer with makensis..."
mkdir -p dist
makensis floodsim-emulator.nsi

echo
echo "Built: $(pwd)/dist/floodsim-emulator.exe"
