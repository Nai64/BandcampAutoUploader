"""Shared GUI helpers."""

import ctypes
import logging
import os
import re
import sys
import tkinter as tk
from ctypes import wintypes
from tkinter import font as tkfont
from tkinter import ttk
from pathlib import Path


DESCRIPTION_AUTO_FILL_MODES = [
    "Off",
    "Minimal",
    "Detailed",
    "Tracklist",
    "Full Track Info",
    "Track Comments",
    "Album Details",
    "Metadata Dump",
]

DESCRIPTION_TEMPLATES = {
    "Minimal": "{n}. {title}",
    "Detailed": "{n}. {title} ({length})",
    "Tracklist": "{n}. {artist} - {title}",
    "Full Track Info": "{n}. {title} — {artist}\n   {length} | {format} | {bitrate}",
    "Track Comments": "{n}. {title}: {comment}",
    "Album Details": "{artist} - {album}\n\nRelease: {date}\nTracks: {tracks}\nTags: {tags}",
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


def set_titlebar_dark(root, dark):
    """Set Windows titlebar to dark or light mode."""
    try:
        hwnd = root.winfo_id()
        value = ctypes.c_int(1 if dark else 0)
        for attr in (20, 19):
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, attr, ctypes.byref(value), ctypes.sizeof(value)
            )
        SWP_FRAMECHANGED = 0x0020
        SWP_NOMOVE = 0x0002
        SWP_NOSIZE = 0x0001
        SWP_NOZORDER = 0x0004
        ctypes.windll.user32.SetWindowPos(
            hwnd, 0, 0, 0, 0, 0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED
        )
        WM_THEMECHANGED = 0x031A
        ctypes.windll.user32.SendMessageW(hwnd, WM_THEMECHANGED, 0, 0)
    except Exception:
        pass


def set_window_redraw(root, enabled):
    """Temporarily suspend or resume redraw for smoother bulk UI updates."""
    if sys.platform != "win32":
        return

    def iter_widgets(widget):
        yield widget
        try:
            children = widget.winfo_children()
        except tk.TclError:
            children = ()
        for child in children:
            yield from iter_widgets(child)

    try:
        WM_SETREDRAW = 0x000B
        widgets = list(iter_widgets(root))
        if enabled:
            widgets.reverse()
        for widget in widgets:
            try:
                hwnd = wintypes.HWND(widget.winfo_id())
                ctypes.windll.user32.SendMessageW(hwnd, WM_SETREDRAW, int(enabled), 0)
            except tk.TclError:
                pass
        if enabled:
            hwnd = wintypes.HWND(root.winfo_id())
            RDW_INVALIDATE = 0x0001
            RDW_ALLCHILDREN = 0x0080
            RDW_UPDATENOW = 0x0100
            RDW_FRAME = 0x0400
            ctypes.windll.user32.RedrawWindow(
                hwnd,
                None,
                None,
                RDW_INVALIDATE | RDW_ALLCHILDREN | RDW_UPDATENOW | RDW_FRAME,
            )
    except Exception:
        pass


def preserve_tk_text_colors(widget, **colors):
    """Keep explicit Text widget colors intact across tk_setPalette calls."""
    widget._bau_preserved_text_colors = colors.copy()
    widget.configure(**colors)


def style_multiline_editbox(widget):
    """Mark editable multiline Text widgets for theme-aware field colors."""
    widget._bau_text_color_role = "editbox"
    widget.configure(
        background="#ffffff",
        foreground="#000000",
        insertbackground="#000000",
        selectbackground="#0078d7",
        selectforeground="#ffffff",
        padx=4,
        pady=0,
    )


def _draw_rounded_text_container(container, outer_bg, field_bg, border_color):
    width = max(1, container.winfo_width())
    height = max(1, container.winfo_height())
    radius = 5
    inset = 1
    points = [
        inset + radius, inset,
        width - inset - radius, inset,
        width - inset, inset,
        width - inset, inset + radius,
        width - inset, height - inset - radius,
        width - inset, height - inset,
        width - inset - radius, height - inset,
        inset + radius, height - inset,
        inset, height - inset,
        inset, height - inset - radius,
        inset, inset + radius,
        inset, inset,
    ]
    container.configure(background=outer_bg)
    container.delete("rounded_text_bg")
    container.create_polygon(
        points,
        smooth=True,
        splinesteps=8,
        fill=field_bg,
        outline=border_color,
        width=1,
        tags=("rounded_text_bg",),
    )
    container.tag_lower("rounded_text_bg")
    window_id = getattr(container, "_bau_rounded_text_window", None)
    if window_id is not None:
        pad = 2
        container.coords(window_id, pad, pad)
        container.itemconfigure(
            window_id,
            width=max(1, width - (pad * 2)),
            height=max(1, height - (pad * 2)),
        )


def create_rounded_text_editbox(parent, **text_options):
    """Create a lightly rounded container around a multiline Text editbox."""
    container = tk.Canvas(parent, highlightthickness=0, borderwidth=0)
    text_options.setdefault("relief", tk.FLAT)
    text_options.setdefault("borderwidth", 0)
    text_options.setdefault("highlightthickness", 0)
    text = tk.Text(container, **text_options)
    style_multiline_editbox(text)

    container._bau_rounded_text_container = True
    container._bau_rounded_text_window = container.create_window(2, 2, anchor=tk.NW, window=text)

    def resize(_event=None):
        colors = getattr(container, "_bau_rounded_text_colors", None)
        if colors:
            _draw_rounded_text_container(container, *colors)

    def set_initial_height():
        line_count = int(text.cget("height"))
        line_height = tkfont.Font(font=text.cget("font")).metrics("linespace")
        container.configure(height=(line_height * line_count) + 8)
        resize()

    container.bind("<Configure>", resize)
    container.after_idle(set_initial_height)
    return container, text


def style_tk_text_widgets(root, bg, fg, insertcolor, selectbg, selectfg, edit_bg=None):
    """Style plain tk Text widgets to match the current ttk theme."""
    try:
        for widget in root.winfo_children():
            if isinstance(widget, tk.Text):
                preserved_colors = getattr(widget, "_bau_preserved_text_colors", None)
                if preserved_colors:
                    widget.configure(**preserved_colors)
                elif getattr(widget, "_bau_text_color_role", None) == "editbox":
                    widget.configure(
                        background=edit_bg or bg,
                        foreground=fg,
                        insertbackground=insertcolor,
                        selectbackground=selectbg,
                        selectforeground=selectfg,
                        padx=4,
                        pady=0,
                    )
                else:
                    widget.configure(
                        background=bg, foreground=fg,
                        insertbackground=insertcolor,
                        selectbackground=selectbg,
                        selectforeground=selectfg,
                        relief="flat", borderwidth=1,
                        highlightthickness=1,
                        highlightbackground=bg,
                        highlightcolor=selectbg,
                        padx=4, pady=0
                    )
            elif getattr(widget, "_bau_rounded_text_container", False):
                edit_field_bg = edit_bg or bg
                border_color = "#2b3440" if fg == "#ffffff" else "#d6d6d6"
                widget._bau_rounded_text_colors = (bg, edit_field_bg, border_color)
                _draw_rounded_text_container(widget, bg, edit_field_bg, border_color)
                style_tk_text_widgets(widget, bg, fg, insertcolor, selectbg, selectfg, edit_bg)
            else:
                style_tk_text_widgets(widget, bg, fg, insertcolor, selectbg, selectfg, edit_bg)
    except Exception:
        pass


# Theme path cache
_TKMT_THEME_PATH = None
_TKMT_THEME_LOADED = False
_AZURE_THEME_PATH = None
_AZURE_THEME_LOADED = False
_FOREST_THEME_DARK_PATH = None
_FOREST_THEME_LIGHT_PATH = None
_FOREST_THEME_LOADED = False


def _get_tkmt_theme_path():
    global _TKMT_THEME_PATH
    if _TKMT_THEME_PATH is None:
        try:
            import TKinterModernThemes
            _TKMT_THEME_PATH = str(Path(TKinterModernThemes.__file__).parent / "themes" / "sun-valley" / "sun-valley.tcl")
        except ImportError:
            _TKMT_THEME_PATH = ""
    return _TKMT_THEME_PATH


def _get_azure_theme_path():
    global _AZURE_THEME_PATH
    if _AZURE_THEME_PATH is None:
        if getattr(sys, "frozen", False):
            base_dir = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
            theme_path = base_dir / "bandcamp_auto_uploader" / "themes" / "azure" / "azure.tcl"
        else:
            theme_path = Path(__file__).resolve().parents[1] / "themes" / "azure" / "azure.tcl"
        _AZURE_THEME_PATH = str(theme_path) if theme_path.exists() else ""
    return _AZURE_THEME_PATH


def _get_forest_theme_path(dark=True):
    global _FOREST_THEME_DARK_PATH, _FOREST_THEME_LIGHT_PATH
    if dark and _FOREST_THEME_DARK_PATH is not None:
        return _FOREST_THEME_DARK_PATH
    if not dark and _FOREST_THEME_LIGHT_PATH is not None:
        return _FOREST_THEME_LIGHT_PATH
    if getattr(sys, "frozen", False):
        base_dir = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
        theme_dir = base_dir / "bandcamp_auto_uploader" / "themes" / "forest"
    else:
        theme_dir = Path(__file__).resolve().parents[1] / "themes" / "forest"
    variant = "forest-dark" if dark else "forest-light"
    theme_path = theme_dir / f"{variant}.tcl"
    result = str(theme_path) if theme_path.exists() else ""
    if dark:
        _FOREST_THEME_DARK_PATH = result
    else:
        _FOREST_THEME_LIGHT_PATH = result
    return result


def _use_azure_theme(root, style, dark):
    bg = "#333333" if dark else "#ffffff"
    fg = "#ffffff" if dark else "#000000"
    disabled_fg = "#ffffff" if dark else "#737373"
    select_bg = "#007fff"
    style.theme_use("azure-dark" if dark else "azure-light")
    style.configure(
        ".",
        background=bg,
        foreground=fg,
        troughcolor=bg,
        focuscolor=select_bg,
        selectbackground=select_bg,
        selectforeground="#ffffff",
        insertcolor=fg,
        insertwidth=1,
        fieldbackground=select_bg,
        borderwidth=1,
        relief="flat",
    )
    style.map(".", foreground=[("disabled", disabled_fg)])
    root.tk.eval(
        "tk_setPalette "
        f"background {bg} "
        f"foreground {fg} "
        f"highlightColor {select_bg} "
        f"selectBackground {select_bg} "
        "selectForeground #ffffff "
        f"activeBackground {select_bg} "
        "activeForeground #ffffff"
    )
    root.tk.eval(f"option add *Menu.selectcolor {fg} startup")


def set_ui_theme(root, theme_name):
    global _TKMT_THEME_LOADED, _AZURE_THEME_LOADED, _FOREST_THEME_LOADED
    style = ttk.Style()
    set_window_redraw(root, False)

    if theme_name == "Azure Dark":
        if not _AZURE_THEME_LOADED:
            theme_path = _get_azure_theme_path()
            if theme_path:
                try:
                    root.tk.call("source", theme_path)
                    _AZURE_THEME_LOADED = True
                except Exception:
                    pass
        try:
            _use_azure_theme(root, style, True)
            style.configure(".", font=("Segoe UI", 8))
            root.tk.eval("option add *Menu.background #333333 startup")
            root.tk.eval("option add *Menu.selectcolor #ffffff startup")
            style.configure("TButton", padding=(2, 0))
            style.configure("TCheckbutton", padding=0)
            style.configure("TRadiobutton", padding=0)
            try:
                root.tk.eval("ttk::style element create Notebook.border from default")
            except Exception:
                pass
            style.configure("TNotebook", background="#333333")
            style.configure("TNotebook.Tab", padding=(4, 2, 4, 1), height=20)
            style.configure("Treeview", rowheight=20)
            style.configure("TEntry", padding=(2, 1))
            style_tk_text_widgets(root, "#333333", "#ffffff", "#ffffff", "#007fff", "#ffffff", "#333333")
            set_titlebar_dark(root, True)
        except Exception:
            pass
    elif theme_name == "Azure Light":
        if not _AZURE_THEME_LOADED:
            theme_path = _get_azure_theme_path()
            if theme_path:
                try:
                    root.tk.call("source", theme_path)
                    _AZURE_THEME_LOADED = True
                except Exception:
                    pass
        try:
            _use_azure_theme(root, style, False)
            style.configure(".", font=("Segoe UI", 8))
            root.tk.eval("option add *Menu.background #ffffff startup")
            root.tk.eval("option add *Menu.selectcolor #000000 startup")
            style.configure("TButton", padding=(2, 0))
            style.configure("TCheckbutton", padding=0)
            style.configure("TRadiobutton", padding=0)
            try:
                root.tk.eval("ttk::style element create Notebook.border from default")
            except Exception:
                pass
            style.configure("TNotebook", background="#ffffff")
            style.configure("TNotebook.Tab", padding=(4, 2, 4, 1), height=20)
            style.configure("Treeview", rowheight=20)
            style.configure("TEntry", padding=(2, 1))
            style_tk_text_widgets(root, "#ffffff", "#000000", "#000000", "#007fff", "#ffffff", "#ffffff")
            set_titlebar_dark(root, False)
        except Exception:
            pass
    elif theme_name == "Sun-Valley Dark":
        if not _TKMT_THEME_LOADED:
            theme_path = _get_tkmt_theme_path()
            if theme_path:
                try:
                    root.tk.call("source", theme_path)
                    _TKMT_THEME_LOADED = True
                except Exception:
                    pass
        try:
            style.theme_use("sun-valley-dark")
            style.configure(".", background="#1c1c1c", foreground="#ffffff",
                            troughcolor="#1c1c1c", focuscolor="#2f60d8",
                            selectbackground="#2f60d8", selectforeground="#ffffff",
                            insertwidth=1, insertcolor="#ffffff",
                            fieldbackground="#2f60d8", borderwidth=1, relief="flat")
            style.configure(".", font=("Segoe UI", 8))
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
            style.configure("TButton", padding=(2, 0))
            style.configure("TCheckbutton", padding=0)
            style.configure("TRadiobutton", padding=0)
            try:
                root.tk.eval("ttk::style element create Notebook.border from default")
            except Exception:
                pass
            style.configure("TNotebook", background="#1c1c1c")
            style.configure("TNotebook.Tab", padding=(4, 2, 4, 1), height=20)
            style.configure("Treeview", rowheight=20)
            style.configure("TEntry", padding=(2, 1))
            style_tk_text_widgets(root, "#1c1c1c", "#ffffff", "#ffffff", "#2f60d8", "#ffffff", "#2f2f2f")
            set_titlebar_dark(root, True)
        except Exception:
            pass
    elif theme_name == "Forest Dark":
        if not _FOREST_THEME_LOADED:
            theme_path = _get_forest_theme_path(dark=True)
            if theme_path:
                try:
                    root.tk.call("source", theme_path)
                    _FOREST_THEME_LOADED = True
                except Exception:
                    pass
        try:
            style.theme_use("forest-dark")
            style.configure(".", background="#313131", foreground="#eeeeee",
                            troughcolor="#313131", focuscolor="#217346",
                            selectbackground="#217346", selectforeground="#ffffff",
                            insertwidth=1, insertcolor="#eeeeee",
                            fieldbackground="#217346", borderwidth=1, relief="flat")
            style.configure(".", font=("Segoe UI", 8))
            style.map(".", foreground=[("disabled", "#595959")])
            root.tk.eval(
                "tk_setPalette "
                "background #313131 "
                "foreground #eeeeee "
                "selectBackground #217346 "
                "selectForeground #ffffff "
                "highlightColor #217346 "
                "activeBackground #217346 "
                "activeForeground #ffffff"
            )
            root.tk.eval("option add *Menu.selectcolor #eeeeee startup")
            root.tk.eval("option add *Menu.background #313131 startup")
            style.configure("TButton", padding=(2, 0))
            style.configure("TCheckbutton", padding=0)
            style.configure("TRadiobutton", padding=0)
            try:
                root.tk.eval("ttk::style element create Notebook.border from default")
            except Exception:
                pass
            style.configure("TNotebook", background="#313131")
            style.configure("TNotebook.Tab", padding=(4, 2, 4, 1), height=20)
            style.configure("Treeview", rowheight=20)
            style.configure("TEntry", padding=(2, 1))
            style_tk_text_widgets(root, "#313131", "#eeeeee", "#eeeeee", "#217346", "#ffffff", "#313131")
            set_titlebar_dark(root, True)
        except Exception:
            pass
    elif theme_name == "Forest Light":
        if not _FOREST_THEME_LOADED:
            theme_path = _get_forest_theme_path(dark=False)
            if theme_path:
                try:
                    root.tk.call("source", theme_path)
                    _FOREST_THEME_LOADED = True
                except Exception:
                    pass
        try:
            style.theme_use("forest-light")
            style.configure(".", background="#ffffff", foreground="#313131",
                            troughcolor="#ffffff", focuscolor="#217346",
                            selectbackground="#217346", selectforeground="#ffffff",
                            insertwidth=1, insertcolor="#313131",
                            fieldbackground="#217346", borderwidth=1, relief="flat")
            style.configure(".", font=("Segoe UI", 8))
            style.map(".", foreground=[("disabled", "#a0a0a0")])
            root.tk.eval(
                "tk_setPalette "
                "background #ffffff "
                "foreground #313131 "
                "selectBackground #217346 "
                "selectForeground #ffffff "
                "highlightColor #217346 "
                "activeBackground #217346 "
                "activeForeground #ffffff"
            )
            root.tk.eval("option add *Menu.selectcolor #313131 startup")
            root.tk.eval("option add *Menu.background #e7e7e7 startup")
            style.configure("TButton", padding=(2, 0))
            style.configure("TCheckbutton", padding=0)
            style.configure("TRadiobutton", padding=0)
            try:
                root.tk.eval("ttk::style element create Notebook.border from default")
            except Exception:
                pass
            style.configure("TNotebook", background="#ffffff")
            style.configure("TNotebook.Tab", padding=(4, 2, 4, 1), height=20)
            style.configure("Treeview", rowheight=20)
            style.configure("TEntry", padding=(2, 1))
            style_tk_text_widgets(root, "#ffffff", "#313131", "#313131", "#217346", "#ffffff", "#ffffff")
            set_titlebar_dark(root, False)
        except Exception:
            pass
    elif theme_name == "Sun-Valley Light":
        if not _TKMT_THEME_LOADED:
            theme_path = _get_tkmt_theme_path()
            if theme_path:
                try:
                    root.tk.call("source", theme_path)
                    _TKMT_THEME_LOADED = True
                except Exception:
                    pass
        try:
            style.theme_use("sun-valley-light")
            style.configure(".", background="#fafafa", foreground="#202020",
                            troughcolor="#fafafa", focuscolor="#2f60d8",
                            selectbackground="#2f60d8", selectforeground="#ffffff",
                            insertwidth=1, insertcolor="#202020",
                            fieldbackground="#2f60d8", borderwidth=1, relief="flat")
            style.configure(".", font=("Segoe UI", 8))
            style.map(".", foreground=[("disabled", "#a0a0a0")])
            root.tk.eval(
                "tk_setPalette "
                "background #fafafa "
                "foreground #202020 "
                "selectBackground #2f60d8 "
                "selectForeground #ffffff "
                "highlightColor #2f60d8 "
                "activeBackground #2f60d8 "
                "activeForeground #ffffff"
            )
            root.tk.eval("option add *Menu.selectcolor #202020 startup")
            root.tk.eval("option add *Menu.background #e7e7e7 startup")
            style.configure("TButton", padding=(2, 0))
            style.configure("TCheckbutton", padding=0)
            style.configure("TRadiobutton", padding=0)
            try:
                root.tk.eval("ttk::style element create Notebook.border from default")
            except Exception:
                pass
            style.configure("TNotebook", background="#fafafa")
            style.configure("TNotebook.Tab", padding=(4, 2, 4, 1), height=20)
            style.configure("Treeview", rowheight=20)
            style.configure("TEntry", padding=(2, 1))
            style_tk_text_widgets(root, "#fafafa", "#202020", "#202020", "#2f60d8", "#ffffff", "#ffffff")
            set_titlebar_dark(root, False)
        except Exception:
            pass
    else:
        try:
            style.theme_use("vista")
            set_titlebar_dark(root, False)
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
            style_tk_text_widgets(root, "#f0f0f0", "#000000", "#000000", "#0078d7", "#ffffff", "#ffffff")
        except Exception:
            try:
                style.theme_use("clam")
            except Exception:
                pass
    set_window_redraw(root, True)
