import sys
import os
import tkinter as tk
import matplotlib.pyplot as plt
from utils.gui import LayerEditor
from utils.app_paths import load_last_project_folder, save_last_project_folder, default_projects_dir


def _resolve_startup_project_folder():
    """
    Where the app should start: the last folder the person used, if it
    still exists and is writable, otherwise a fresh default under
    Documents. Never the process's raw launch directory - that's
    unpredictable for a packaged .exe (could be Program Files, the
    desktop, wherever a shortcut's "Start in" happens to point) and isn't
    guaranteed to be writable.
    """
    folder = load_last_project_folder() or default_projects_dir()
    try:
        os.chdir(folder)
    except OSError:
        folder = default_projects_dir()
        os.chdir(folder)
    return folder


def main():
    project_folder = _resolve_startup_project_folder()

    # ---------------- Tk root ----------------
    root = tk.Tk()
    root.title("Delta Pen Plotter Layer Editor")
    try:
        root.state("zoomed")  # maximized - supported on Windows/most Tk builds
    except tk.TclError:
        # Fall back to a large default window rather than crashing, for any
        # Tk build where "zoomed" isn't a recognized state.
        root.geometry("1400x900")

    # No startup folder-selection popup: the editor opens directly in the
    # resolved project folder (creating a default input_parameters.xml
    # there if one doesn't exist yet). Use the "Select Project Folder" /
    # "Create New Project Folder" buttons in the editor to switch to a
    # different project - whichever folder is active when the window
    # closes is remembered for next time.

    def on_close():
        save_last_project_folder(os.getcwd())
        root.quit()
        root.destroy()
        sys.exit(0)

    root.protocol("WM_DELETE_WINDOW", on_close)

    # ---------------- Matplotlib figures ----------------
    fig_source = plt.Figure(figsize=(3, 3))
    fig_preview = plt.Figure(figsize=(6, 6))

    # ---------------- GUI ----------------
    LayerEditor(
        root=root,
        xml_path="input_parameters.xml",  # resolved relative to project_folder (cwd)
        update_callback=lambda *_: None,
        figSource=fig_source,
        figPreview=fig_preview
    )

    root.mainloop()


if __name__ == "__main__":
    main()
