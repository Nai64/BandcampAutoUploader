"""Shared GUI helpers."""

import logging
import os
import re
import tkinter as tk
from tkinter import ttk
from pathlib import Path


DESCRIPTION_AUTO_FILL_MODES = [
    "Off",
    "Tracklist",
    "Tracklist + Comments",
    "Track Comments",
    "Album Info",
    "Release Notes",
    "Bandcamp Classic",
    "Technical Details",
    "Metadata Dump",
]

DESCRIPTION_TEMPLATES = {
    "Tracklist": "{n}. {artist} - {title}",
    "Tracklist + Comments": "{n}. {artist} - {title}\n   {comment}",
    "Track Comments": "{n}. {title}: {comment}",
    "Technical Details": "{n}. {title} (length: {length}, format: {format}, bitrate: {bitrate}, size: {size})",
    "Album Info": "Album: {album}\nArtist: {artist}\nRelease Date: {date}\nTracks: {tracks}\nTags: {tags}\n\nTracklist:\n{tracklist}",
    "Release Notes": "{album} by {artist}\n\nReleased: {date}\nTracks: {tracks}\nTags: {tags}\n\nTracklist:\n{tracklist}",
    "Bandcamp Classic": "{artist} - {album}\n\nRelease date: {date}\n\n{tracklist}",
    "Metadata Dump": "{album_info}\n\nTrack Comments:\n{track_comments}\n\nTechnical Details:\n{technical_details}",
}


SENSITIVE_TEXT_PATTERNS = [
    re.compile(r"(?i)(cookie|token|password|secret|api[_-]?key|authorization)(\s*[:=]\s*)[^\s,;]+"),
    re.compile(r"(?i)(Cookie|Authorization)(:\s*).+"),
    re.compile(r"(?i)(crumbs?|csrf|xsrf)(\s*[:=]\s*)[^\s,;}\]]+"),
]

SENSITIVE_JSON_TEXT_PATTERNS = [
    re.compile(
        r'(?i)("(?:cookie|token|password|secret|api[_-]?key|authorization|crumbs?|csrf|xsrf)"\s*:\s*)"[^"]*"'
    ),
]

RAW_PRIVATE_LOG_MARKERS = (
    "<!doctype html",
    "<html",
    "data-crumbs",
    "client_template_globals",
    "js-crumbs-data",
)

MAX_FORMATTED_LOG_CHARS = 8000


def sanitize_log_text(text, max_chars=None):
    """Remove values that should not be pasted into public support issues."""
    if text is None:
        return ""

    sanitized = str(text)
    home = str(os.path.expanduser("~"))
    if home and home != "~":
        sanitized = sanitized.replace(home, "%USERPROFILE%")

    sanitized = re.sub(r"(?i)C:\\Users\\[^\\\r\n]+", r"C:\\Users\\<user>", sanitized)
    sanitized = re.sub(
        r"(?i)\b[A-Z]:\\(?:[^\\\r\n]+\\)+([^\\\r\n\s,;]+)",
        r"<path>\\\1",
        sanitized,
    )
    sanitized = re.sub(r"(?<!\w)/(?:Users|home)/[^/\s]+", "/<home>", sanitized)

    for pattern in SENSITIVE_TEXT_PATTERNS:
        sanitized = pattern.sub(lambda match: f"{match.group(1)}{match.group(2)}<omitted>", sanitized)

    for pattern in SENSITIVE_JSON_TEXT_PATTERNS:
        sanitized = pattern.sub(lambda match: f'{match.group(1)}"<omitted>"', sanitized)

    if max_chars and len(sanitized) > max_chars:
        sanitized = sanitized[:max_chars].rstrip() + "\n...[log message truncated]"

    return sanitized


class PrivacyLogFilter(logging.Filter):
    """Drop raw web responses and other high-risk debug dumps from diagnostics."""

    def filter(self, record):
        try:
            message = record.getMessage()
        except Exception:
            return True

        lowered = message[:12000].lower()
        if any(marker in lowered for marker in RAW_PRIVATE_LOG_MARKERS):
            return False
        return True


class RedactingFormatter(logging.Formatter):
    """Formatter that strips local/private values from GUI and file logs."""

    def format(self, record):
        return sanitize_log_text(super().format(record), max_chars=MAX_FORMATTED_LOG_CHARS)


class QueueHandler(logging.Handler):
    """Custom logging handler that puts log records into a queue for GUI display."""

    def __init__(self, log_queue):
        super().__init__()
        self.log_queue = log_queue

    def emit(self, record):
        try:
            self.log_queue.put((self.format(record), record.levelno))
        except Exception:
            self.handleError(record)


class ToolTip:
    """Create a tooltip for a given widget."""

    disabled = False

    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tipwindow = None
        self.widget.bind("<Enter>", self.showtip, add="+")
        self.widget.bind("<Leave>", self.hidetip, add="+")

    def showtip(self, event=None):
        """Display the tooltip."""
        if ToolTip.disabled or self.tipwindow or not self.text:
            return

        x, y, _, _ = self.widget.bbox("insert") if hasattr(self.widget, 'bbox') else (0, 0, 0, 0)
        x = x + self.widget.winfo_rootx() + 25
        y = y + self.widget.winfo_rooty() + 25
        self.tipwindow = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        label = tk.Label(
            tw,
            text=self.text,
            justify=tk.LEFT,
            background="#ffffe0",
            relief=tk.SOLID,
            borderwidth=1,
            font=("Segoe UI", 9),
        )
        label.pack(ipadx=5, ipady=3)

    def hidetip(self, event=None):
        """Hide the tooltip."""
        tw = self.tipwindow
        self.tipwindow = None
        if tw:
            tw.destroy()


# Theme path cache
_TKMT_THEME_PATH = None
_TKMT_THEME_LOADED = False


def _get_tkmt_theme_path():
    global _TKMT_THEME_PATH
    if _TKMT_THEME_PATH is None:
        try:
            import TKinterModernThemes
            _TKMT_THEME_PATH = str(Path(TKinterModernThemes.__file__).parent / "themes" / "sun-valley" / "sun-valley.tcl")
        except ImportError:
            _TKMT_THEME_PATH = ""
    return _TKMT_THEME_PATH


def set_ui_theme(root, theme_name):
    global _TKMT_THEME_LOADED
    style = ttk.Style()

    if theme_name == "Sun-Valley Dark":
        if not _TKMT_THEME_LOADED:
            theme_path = _get_tkmt_theme_path()
            if theme_path:
                try:
                    root.tk.call("source", theme_path)
                    _TKMT_THEME_LOADED = True
                except Exception:
                    pass
        try:
            # Direct theme switch - bypasses set_theme proc which sets
            # problematic option add *font that breaks tkinter font parsing
            style.theme_use("sun-valley-dark")
            style.configure(".", background="#1c1c1c", foreground="#ffffff",
                            troughcolor="#1c1c1c", focuscolor="#2f60d8",
                            selectbackground="#2f60d8", selectforeground="#ffffff",
                            insertwidth=1, insertcolor="#ffffff",
                            fieldbackground="#2f60d8", borderwidth=1, relief="flat")
            style.configure(".", font=("Segoe UI", 9))  # 9pt instead of 10pt
            style.map(".", foreground=[("disabled", "#595959")])
            root.tk.eval(
                "tk_setPalette "
                "background #1c1c1c "
                "foreground #ffffff "
                "selectBackground #2f60d8 "
                "selectForeground #ffffff "
                "highlightColor #2f60d8 "
                "activeBackground #2f60d8 "
                "activeForeground #ffffff"
            )
            root.tk.eval("option add *Menu.selectcolor #ffffff startup")
            root.tk.eval("option add *Menu.background #2f2f2f startup")
            # Compact sizing overrides
            style.configure("TButton", padding=(6, 2))
            style.configure("TCheckbutton", padding=2)
            style.configure("TRadiobutton", padding=2)
            style.configure("TNotebook.Tab", padding=(12, 8, 12, 4), height=26)
            style.configure("Treeview", rowheight=22)
            style.configure("TEntry", padding=(4, 2))
        except Exception:
            pass
    else:
        try:
            style.theme_use("vista")
            root.tk.eval(
                "tk_setPalette "
                "background #f0f0f0 "
                "foreground #000000 "
                "selectBackground #0078d7 "
                "selectForeground #ffffff "
                "highlightColor #0078d7 "
                "activeBackground #0078d7 "
                "activeForeground #ffffff"
            )
            root.tk.eval("option add *Menu.selectcolor #000000 startup")
            root.tk.eval("option add *Menu.background #f0f0f0 startup")
        except Exception:
            try:
                style.theme_use("clam")
            except Exception:
                pass
