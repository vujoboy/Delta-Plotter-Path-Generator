# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for Delta Pen Plotter Layer Editor (Windows build).

Build (from this folder, in a Windows venv with requirements.txt installed):
    pyinstaller DeltaPenPlotterLayerEditor.spec

This is a "onedir" build: it produces a folder,
dist/DeltaPenPlotterLayerEditor/, containing DeltaPenPlotterLayerEditor.exe
plus every DLL and data file it needs alongside it. Zip that whole folder
(or wrap it in an installer - see BUILD_WINDOWS.md) to hand it to someone
else; don't just copy the .exe by itself, it won't run without the rest of
the folder.

See BUILD_WINDOWS.md for the full walkthrough, including how to switch
this to a single-file .exe instead, and why onedir is the safer default.
"""

from PyInstaller.utils.hooks import collect_all

block_cipher = None

# shapely, opencv and scipy each ship compiled/binary libraries (GEOS, the
# OpenCV native libs, scipy's compiled extensions) that PyInstaller's
# static import analysis doesn't always find on its own - collect_all()
# pulls in every submodule, binary, and data file the package ships. This
# errs on the side of bundling a bit more than strictly necessary rather
# than risking a missing-DLL crash that only shows up on someone else's
# machine.
datas = []
binaries = []
hiddenimports = []

for pkg in ("shapely", "cv2", "scipy", "matplotlib"):
    pkg_datas, pkg_binaries, pkg_hiddenimports = collect_all(pkg)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hiddenimports

a = Analysis(
    ["main.py"],
    pathex=[SPECPATH],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="DeltaPenPlotterLayerEditor",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # windowed app, no console popup - flip to True temporarily to see startup errors
    icon=None,      # point this at an .ico file once you have one, e.g. "app_icon.ico"
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="DeltaPenPlotterLayerEditor",
)
