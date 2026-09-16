# Building the Windows .exe

This turns the app into a folder you can zip up and hand to someone else
to run without installing Python. Do this **on a Windows machine** -
PyInstaller doesn't cross-compile, so building here always produces a
binary for whatever OS you build on.

## 1. One-time setup

1. Install Python from **python.org** (not the Microsoft Store version -
   it has historically had issues bundling tkinter correctly). Any
   currently-supported 3.x version is fine. During install, tkinter comes
   along automatically with the default options - nothing extra to check.
2. Open a command prompt in this folder and create a virtual environment:
   ```
   python -m venv build_venv
   build_venv\Scripts\activate
   pip install -r requirements.txt
   ```

## 2. Build

With the venv still active:
```
pyinstaller DeltaPenPlotterLayerEditor.spec
```

This takes a minute or two. When it finishes, your app is at:
```
dist\DeltaPenPlotterLayerEditor\DeltaPenPlotterLayerEditor.exe
```

**Distribute the whole `dist\DeltaPenPlotterLayerEditor` folder** (zip it
up), not just the .exe on its own - it needs the DLLs and data files
sitting alongside it in that folder to run. Rebuilding overwrites `dist\`
and `build\` cleanly each time; both are safe to delete between builds if
you want a completely fresh one.

## 3. Before you send it to anyone

Test the zipped folder on a **different Windows machine that doesn't have
Python installed** - that's the only way to be sure nothing needed got
left behind. A few things to expect the first time:

- **Windows SmartScreen will probably warn** ("Windows protected your PC")
  the first time the .exe runs anywhere, since it isn't code-signed. This
  is normal for an unsigned executable, not a sign anything's wrong -
  clicking "More info" -> "Run anyway" gets through it. If this matters
  for wider distribution later, a code-signing certificate is the real
  fix, but that's a separate, paid step not covered here.
- **Antivirus software occasionally flags PyInstaller-built executables**
  as a false positive (PyInstaller's bootloader pattern is a known source
  of these, unrelated to anything this app's code actually does). If that
  happens, submitting the file to the AV vendor as a false positive
  usually clears it within a few days.

## 4. Where the app stores things

The app no longer depends on being launched from any particular folder.
On first run it creates a project folder under
`Documents\Delta Pen Plotter Layer Editor Projects`, and it remembers the
last project folder you had open (in
`%APPDATA%\Delta Pen Plotter Layer Editor\last_project_folder.json`) so it
reopens there next time. Nothing is written next to the .exe itself.

## Optional tweaks

**Single-file .exe instead of a folder:** open
`DeltaPenPlotterLayerEditor.spec` and, in the `EXE(...)` block, remove the
`exclude_binaries=True,` line, then delete the `coll = COLLECT(...)` block
entirely (pass `a.binaries, a.zipfiles, a.datas` as extra arguments to
`EXE(...)` instead, the same way `COLLECT` currently does). This is the
"single .exe you can email" style people often picture, at the cost of a
few extra seconds of startup time each launch (it self-extracts to a temp
folder first) and being a bit more likely to trip antivirus heuristics.
The folder-based build above is the more reliable default and what's
recommended unless you specifically want a single file.

**App icon:** once you have an `.ico` file, set `icon="your_icon.ico"` in
the `EXE(...)` block (it's currently `icon=None`).

**Smaller build:** this build errs on the side of bundling more than
strictly necessary (see the comment in the .spec file for why). If the
~200-300MB+ folder size becomes a problem, two things help most: swap
`opencv-python` for `opencv-python-headless` in `requirements.txt` (this
app never opens an OpenCV display window, so nothing is lost), and trim
the `collect_all(...)` loop in the .spec file down to just the packages
that actually need it once you've confirmed which ones do.

## Troubleshooting

- **A `shapely`/GEOS-related DLL error at startup:** try a clean
  `pip install --force-reinstall shapely` inside the build venv before
  rebuilding - this has generally been solved by modern shapely versions
  (2.x), which is what `requirements.txt` pins, but a corrupted or
  partial install can still occasionally cause it.
- **Any other "missing module" error on first run:** add the module name
  to the `hiddenimports` list built near the top of the .spec file and
  rebuild. Everything this app imports directly is already covered, but a
  library occasionally imports something dynamically that static analysis
  can't see.
