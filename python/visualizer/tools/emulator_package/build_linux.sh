#!/usr/bin/env bash
# Build the standalone Linux emulator binary.
# Run on a Linux machine (PyInstaller does not cross-compile).
set -e
cd "$(dirname "$0")"

PYTHON=python3

"$PYTHON" -m pip install --quiet --upgrade pyinstaller paho-mqtt
"$PYTHON" -m PyInstaller --clean --noconfirm emulator.spec

# Some hardened kernels (e.g. Debian 13) refuse to load a bundled
# libpython that has the executable-stack ELF flag set. Detect this and,
# if needed, clear the flag on the source library and rebuild once.
if ! ./dist/floodsim-emulator --help >/dev/null 2>/tmp/floodsim-build-err; then
    if grep -q "cannot enable executable stack" /tmp/floodsim-build-err; then
        echo "Detected exec-stack issue; patching libpython and rebuilding..."
        LIBPYTHON=$("$PYTHON" -c "import sysconfig,glob,os
ld = sysconfig.get_config_var('LIBDIR')
ver = sysconfig.get_config_var('LDVERSION') or sysconfig.get_config_var('VERSION')
matches = glob.glob(os.path.join(ld, f'libpython{ver}.so*'))
print(matches[0] if matches else '')")
        if [ -n "$LIBPYTHON" ]; then
            "$PYTHON" - "$LIBPYTHON" <<'EOF'
import struct, sys
path = sys.argv[1]
with open(path, "rb") as f:
    data = bytearray(f.read())
e_phoff = struct.unpack_from("<Q", data, 0x20)[0]
e_phentsize = struct.unpack_from("<H", data, 0x36)[0]
e_phnum = struct.unpack_from("<H", data, 0x38)[0]
PT_GNU_STACK = 0x6474e551
for i in range(e_phnum):
    off = e_phoff + i * e_phentsize
    if struct.unpack_from("<I", data, off)[0] == PT_GNU_STACK:
        flags = struct.unpack_from("<I", data, off + 4)[0]
        if flags & 0x1:
            struct.pack_into("<I", data, off + 4, flags & ~0x1)
            with open(path, "wb") as fw:
                fw.write(data)
            print(f"Cleared executable-stack flag on {path}")
EOF
            rm -rf build dist
            "$PYTHON" -m PyInstaller --clean --noconfirm emulator.spec
        else
            echo "Could not locate libpython to patch." >&2
            cat /tmp/floodsim-build-err >&2
            exit 1
        fi
    else
        cat /tmp/floodsim-build-err >&2
        exit 1
    fi
fi

echo
echo "Built: $(pwd)/dist/floodsim-emulator"
