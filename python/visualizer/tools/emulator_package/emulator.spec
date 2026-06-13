# PyInstaller spec for the DanaSim MQTT demo emulator.
#
# Build (run from this directory, on the target OS):
#   pyinstaller --clean --noconfirm emulator.spec
#
# Output:
#   dist/floodsim-emulator        (Linux)
#   dist/floodsim-emulator.exe    (Windows)
import os

spec_dir = os.path.dirname(os.path.abspath(SPEC))
tools_dir = os.path.abspath(os.path.join(spec_dir, ".."))

a = Analysis(
    ["emulator_app.py"],
    pathex=[spec_dir, tools_dir],
    binaries=[],
    datas=[(os.path.join(spec_dir, "recording.jsonl"), ".")],
    hiddenimports=["mqtt_replayer"],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="floodsim-emulator",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
)
