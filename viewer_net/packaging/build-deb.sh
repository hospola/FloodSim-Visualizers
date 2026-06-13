#!/usr/bin/env bash
# Builds a .deb package from the linux-x64 publish output.
#
#   ./build-deb.sh                  → lite package, no bundled data
#                                      (../publish/danasim-viewer_1.0.0_amd64.deb)
#   ./build-deb.sh --with-data DIR  → full package, bundles DIR as
#                                      /opt/danasim-viewer/data — combined with the
#                                      empty Terrain:BasePath default, the app finds
#                                      it with zero configuration
#                                      (../publish/danasim-viewer-full_1.0.0_amd64.deb)
#
# Run from viewer_net/packaging/
set -e

DATA_DIR=""
SUFFIX=""
if [[ "${1:-}" == "--with-data" ]]; then
  DATA_DIR="$2"
  [[ -d "$DATA_DIR" ]] || { echo "Data directory not found: $DATA_DIR" >&2; exit 1; }
  SUFFIX="-full"
fi

VERSION="1.0.0"
ARCH="amd64"
PKG="danasim-viewer${SUFFIX}_${VERSION}_${ARCH}"
SRC="$(cd "$(dirname "$0")/../publish/linux-x64" && pwd)"
OUT="$(cd "$(dirname "$0")/../publish" && pwd)"
WORK="/tmp/${PKG}"

echo "Building from: $SRC"
[[ -n "$DATA_DIR" ]] && echo "Bundling data:  $DATA_DIR"
echo "Output:        $OUT/${PKG}.deb"

# ── Directory structure ────────────────────────────────────────────────────────
rm -rf "$WORK"
mkdir -p \
  "$WORK/DEBIAN" \
  "$WORK/opt/danasim-viewer" \
  "$WORK/usr/bin" \
  "$WORK/usr/share/applications"

# ── Copy application files ─────────────────────────────────────────────────────
cp -r "$SRC"/. "$WORK/opt/danasim-viewer/"
chmod +x "$WORK/opt/danasim-viewer/DanaSim.Viewer.Web"
chmod +x "$WORK/opt/danasim-viewer/run.sh"

if [[ -n "$DATA_DIR" ]]; then
  cp -r "$DATA_DIR" "$WORK/opt/danasim-viewer/data"
fi

# ── Symlink for terminal use ───────────────────────────────────────────────────
ln -s /opt/danasim-viewer/run.sh "$WORK/usr/bin/danasim-viewer"

# ── .desktop launcher ─────────────────────────────────────────────────────────
cat > "$WORK/usr/share/applications/danasim-viewer.desktop" << 'EOF'
[Desktop Entry]
Name=DanaSim Viewer
Comment=Flood Simulation 3D Viewer
Exec=/opt/danasim-viewer/run.sh
Terminal=false
Type=Application
Categories=Science;Education;
EOF

# ── DEBIAN/control ────────────────────────────────────────────────────────────
cat > "$WORK/DEBIAN/control" << EOF
Package: danasim-viewer
Version: ${VERSION}
Architecture: ${ARCH}
Maintainer: DanaSim <danasim@example.com>
Description: DanaSim Flood Simulation 3D Viewer
 Web-based viewer for the DanaSim flood simulation system.
 Connects to an MQTT broker, renders live flood data in 3D,
 and serves the viewer dashboard at http://localhost:5027.
EOF

# ── DEBIAN/postinst ───────────────────────────────────────────────────────────
cat > "$WORK/DEBIAN/postinst" << 'EOF'
#!/bin/bash
chmod +x /opt/danasim-viewer/DanaSim.Viewer.Web
chmod +x /opt/danasim-viewer/run.sh
EOF
chmod 755 "$WORK/DEBIAN/postinst"

# ── Build .deb ────────────────────────────────────────────────────────────────
fakeroot dpkg-deb --build "$WORK" "$OUT/${PKG}.deb"
echo "Done: $OUT/${PKG}.deb"
