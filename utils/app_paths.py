"""
Shared helpers for where this app keeps its own small bits of state (just
"what project folder was open last") and what a sensible default project
folder is - used by both main.py (at startup/on close) and utils/gui.py
(whenever the person explicitly picks or creates a project folder).

Kept separate from both of those so neither has to import the other.
"""

import os
import json

APP_NAME = "Delta Pen Plotter Layer Editor"


def app_data_dir():
    """
    Per-user, always-writable location for small app state. %APPDATA% on
    Windows; falls back to the home directory anywhere that isn't set
    (e.g. running from source on another OS during development).
    """
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    path = os.path.join(base, APP_NAME)
    os.makedirs(path, exist_ok=True)
    return path


def default_projects_dir():
    """
    Default project folder for first run / whenever the remembered one is
    no longer usable: a subfolder under the user's Documents folder -
    always writable by a regular user, unlike wherever a packaged .exe
    happens to be installed (e.g. Program Files) or launched from.
    """
    path = os.path.join(os.path.expanduser("~"), "Documents", f"{APP_NAME} Projects")
    os.makedirs(path, exist_ok=True)
    return path


def _last_project_file():
    return os.path.join(app_data_dir(), "last_project_folder.json")


def load_last_project_folder():
    try:
        with open(_last_project_file(), "r") as f:
            folder = json.load(f).get("project_folder")
        if folder and os.path.isdir(folder):
            return folder
    except (OSError, ValueError):
        pass
    return None


def save_last_project_folder(folder):
    try:
        with open(_last_project_file(), "w") as f:
            json.dump({"project_folder": folder}, f)
    except OSError:
        pass  # best-effort only - never let this stop the app from running
