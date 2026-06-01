"""
Bandcamp Auto Uploader GUI
A modern graphical interface for uploading albums to Bandcamp
"""

import http.cookiejar
import json
import logging
import queue
import threading
import tkinter as tk
import dataclasses
import os
import subprocess
import sys
import re
import time
import webbrowser
from pathlib import Path
from tkinter import ttk, filedialog, messagebox, scrolledtext
from typing import Optional
from urllib.parse import urljoin
from mutagen.flac import FLAC
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4
from mutagen.oggvorbis import OggVorbis
from mutagen.oggopus import OggOpus
from mutagen.wave import WAVE
from mutagen.aiff import AIFF

# Enable high DPI awareness for sharper fonts on Windows
if sys.platform == "win32":
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        pass  # Not all Windows versions support this

import requests
from browser_cookie3 import (
    BrowserCookieError,
    brave,
    chrome,
    chromium,
    edge,
    firefox,
    opera,
    opera_gx,
    safari,
    vivaldi,
)

# Try to import drag & drop support (optional)
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    DRAG_DROP_AVAILABLE = True
except ImportError:
    DRAG_DROP_AVAILABLE = False

from bandcamp_auto_uploader.bandcamp_http_adapter import BandcampHTTPAdapter
from bandcamp_auto_uploader.config import Config, load_config, save_config
from bandcamp_auto_uploader.gui.common import PrivacyLogFilter, QueueHandler, RedactingFormatter, ToolTip, DESCRIPTION_TEMPLATES
from bandcamp_auto_uploader.gui import image_scaling
from bandcamp_auto_uploader.gui.logs_mixin import LogsMixin
from bandcamp_auto_uploader.gui.settings_mixin import SettingsMixin
from bandcamp_auto_uploader.upload import Album, Track, UploadCancelled, get_metadata_track_number
from bandcamp_auto_uploader import __version__

# Configure logging
logger = logging.getLogger("bandcamp-auto-uploader")


def set_windows_app_user_model_id():
    """Set a Windows AppUserModelID before Tk creates the taskbar button."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "Nai64.BandcampAutoUploaderGUI"
        )
    except Exception as e:
        logger.debug(f"Failed to set Windows app identity: {e}")


class BandcampUploaderGUI(SettingsMixin, LogsMixin):
    def __init__(self, root):
        self.root = root

        self.root.title("Bandcamp Auto Uploader")
        set_windows_app_user_model_id()
        
        # Load saved window geometry or use default
        self.config = load_config() or Config()
        ToolTip.disabled = bool(getattr(self.config, 'disable_tooltips', True))
        if hasattr(self.config, 'window_geometry') and self.config.window_geometry:
            self.root.geometry(self.config.window_geometry)
        else:
            self.root.geometry("1000x750")
        self.root.minsize(900, 650)
        
        # Maximize on open if setting is enabled
        if getattr(self.config, 'maximize_on_open', False):
            self.root.state('zoomed')

        self.log_poll_interval_ms = 100
        self.toast_poll_interval_ms = 100
        
        # Check if windows-toasts is available
        self.windows_toasts_available = False
        if sys.platform == "win32":
            try:
                from windows_toasts import Toast, WindowsToaster
                self.windows_toasts_available = True
            except ImportError:
                # Disable Windows notifications if library not available
                if getattr(self.config, 'windows_notifications', False):
                    self.config.windows_notifications = False
                    save_config(self.config)
                    logger.info("windows-toasts library not installed, Windows notifications disabled")
        
        # Save window geometry on close
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.root.report_callback_exception = self.handle_tk_callback_exception
        
        self.set_window_icon()
        
        # Variables
        self.urls = {}
        self.session = None
        self.selected_artist_url = None
        self.upload_thread = None
        self.upload_cancel_event = threading.Event()
        self.log_queue = queue.Queue()
        
        # Advanced album metadata
        self.album_description_var = tk.StringVar()
        self.album_credits_var = tk.StringVar()
        self.album_license_var = tk.StringVar(value="All Rights Reserved")
        self.album_publish_date_var = tk.StringVar()
        self.album_upc_var = tk.StringVar()
        self.album_catalog_number_var = tk.StringVar()
        self.album_record_label_var = tk.StringVar()
        self.album_download_desc_var = tk.StringVar()
        self.album_release_message_var = tk.StringVar()

        # Toast queue
        self.toast_queue = queue.Queue()
        self.context_sort_directions = {}

        # Undo functionality
        self.undo_buffer = []
        self.redo_buffer = []
        
        # Browser cache for faster cookie loading
        self.last_successful_browser = None

        # Context menu icons are optional and controlled by preferences.
        self.icon_images = {}
        self.context_menu_icons = {}
        self._active_track_context_menu = None
        self._active_track_sort_menu = None
        self.locked_track_keys = set()
        self._album_session_loading = False
        self._album_session_save_job = None
        self._album_session_autosave_ready = False

        self._auto_fit_columns_job = None

        # Setup logging
        self.setup_logging()

        # Load context menu icons before menus are opened.
        self.load_context_menu_icons()

        # Create UI.
        self.create_widgets()
        
        # Bind keyboard shortcuts
        self.bind_keyboard_shortcuts()
        
        # Global shortcuts
        self.root.bind('<Control-Return>', lambda e: self.start_upload() if self.upload_btn['state'] == tk.NORMAL else None)
        self.root.bind('<Escape>', lambda e: self.cancel_upload() if self.cancel_btn['state'] == tk.NORMAL else None)
        
        # Load initial data
        self.root.after(100, self.initialize_app)
        
        # Start log monitor
        self.monitor_logs()
        
    def setup_logging(self):
        """Configure logging to capture output for GUI display"""
        logger.setLevel(logging.DEBUG if (self.config.debug or getattr(self.config, 'log_to_file', True)) else logging.INFO)
        for handler in list(logger.handlers):
            if getattr(handler, '_bau_gui_handler', False) or getattr(handler, '_bau_file_handler', False):
                logger.removeHandler(handler)
                try:
                    handler.close()
                except Exception:
                    pass
        
        privacy_filter = PrivacyLogFilter()

        # Add queue handler
        queue_handler = QueueHandler(self.log_queue)
        queue_handler.setLevel(logging.INFO if not self.config.debug else logging.DEBUG)
        queue_handler._bau_gui_handler = True
        queue_handler.addFilter(privacy_filter)
        gui_formatter = RedactingFormatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%H:%M:%S')
        queue_handler.setFormatter(gui_formatter)
        logger.addHandler(queue_handler)

        if getattr(self.config, 'log_to_file', True):
            log_path = self.get_app_log_file_path()
            log_path.parent.mkdir(parents=True, exist_ok=True)
            file_handler = logging.FileHandler(
                log_path,
                encoding="utf-8",
            )
            file_level_name = str(getattr(self.config, 'log_file_level', 'INFO')).upper()
            file_handler.setLevel(getattr(logging, file_level_name, logging.INFO))
            file_handler._bau_file_handler = True
            file_handler.addFilter(privacy_filter)
            file_formatter = RedactingFormatter(
                '%(asctime)s.%(msecs)03d | %(levelname)-8s | %(threadName)s | %(name)s | %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S',
            )
            file_handler.setFormatter(file_formatter)
            logger.addHandler(file_handler)

        logger.info("Logging initialized")

    def handle_tk_callback_exception(self, exc_type, exc_value, exc_traceback):
        """Route Tk callback exceptions into the persistent diagnostic log."""
        logger.error("Unhandled Tkinter callback exception", exc_info=(exc_type, exc_value, exc_traceback))
        self.show_bug_log_prompt(
            "Application Error",
            "An unexpected error occurred.",
            error_text=str(exc_value),
            exc_info=(exc_type, exc_value, exc_traceback),
        )

    def find_app_icon_path(self):
        """Find the bundled app icon in script and frozen builds."""
        candidate_paths = []
        if getattr(sys, 'frozen', False):
            bundle_root = Path(getattr(sys, '_MEIPASS', Path(sys.executable).parent))
            candidate_paths.extend([
                bundle_root / "bandcamp_auto_uploader" / "img" / "icon.ico",
                Path(sys.executable).parent / "bandcamp_auto_uploader" / "img" / "icon.ico",
                Path(sys.executable).parent / "icon.ico",
            ])

        package_root = Path(__file__).resolve().parent.parent
        project_root = package_root.parent
        candidate_paths.extend([
            package_root / "img" / "icon.ico",
            project_root / "bandcamp_auto_uploader" / "img" / "icon.ico",
            Path.cwd() / "bandcamp_auto_uploader" / "img" / "icon.ico",
        ])

        return next((path for path in candidate_paths if path.exists()), None)

    def set_window_icon(self):
        """Set the window and taskbar icon when an app icon is available."""
        icon_path = self.find_app_icon_path()
        if icon_path is None:
            logger.warning("Application icon not found")
            return

        try:
            self.root.iconbitmap(default=str(icon_path))
        except Exception as e:
            logger.warning(f"Failed to set application icon {icon_path}: {e}")

    def load_context_menu_icons(self):
        """Load optional icons for track context menu commands."""
        icon_files = {
            "Play": "media-player.png",
            "Remove Track": "bin.png",
            "Move Up": "arrow-090.png",
            "Move Down": "arrow-270.png",
            "Move to Top": "arrow-stop-090.png",
            "Move to Bottom": "arrow-stop-270.png",
            "Open File Location": "folder-open.png",
            "Replace File": "blue-document.png",
            "Extract Cover Art": "image-export.png",
            "Extract Tracklist": "document-text.png",
            "Open session.txt": "notebook--arrow.png",
            "Set Track Cover as Album Cover": "image-export.png",
            "Undo": "arrow-return-180.png",
            "Redo": "arrow-curve.png",
            "Extract Track Information": "information.png",
            "Copy Metadata": "clipboard.png",
            "Paste Metadata": "clipboard-paste.png",
            "Revert to Original": "arrow-return-180.png",
            "Lock Track": "lock.png",
            "Unlock Track": "lock-unlock.png",
            "Randomize": "layout-3-mix.png",
            "Smart Randomize": "wand-magic.png",
            "Sort By": "sort.png",
            "Clear Metadata": "broom.png",
            "Clear All Metadata": "eraser--minus.png",
            "Clear All Tracks": "eraser.png",
        }

        candidate_dirs = []
        if getattr(sys, 'frozen', False):
            candidate_dirs.extend([
                Path(getattr(sys, '_MEIPASS', Path(sys.executable).parent)) / "context_menu_icons",
                Path(sys.executable).parent / "context_menu_icons",
            ])

        project_root = Path(__file__).resolve().parent.parent.parent
        candidate_dirs.extend([
            project_root / "context_menu_icons",
            Path.cwd() / "context_menu_icons",
        ])

        icons_dir = next((path for path in candidate_dirs if path.exists()), None)
        self.context_menu_icons = {}
        self.icon_images = {}

        if icons_dir is None:
            logger.warning("Context menu icons folder not found")
            return

        for label, filename in icon_files.items():
            icon_path = icons_dir / filename
            self.context_menu_icons[label] = icon_path
            if not icon_path.exists():
                logger.warning(f"Context menu icon not found: {icon_path}")
                self.icon_images[label] = None
                continue

            try:
                self.icon_images[label] = tk.PhotoImage(master=self.root, file=str(icon_path))
            except Exception as e:
                logger.warning(f"Failed to load context menu icon {icon_path}: {e}")
                self.icon_images[label] = None

    def refresh_context_menu_icons(self):
        """Reload or clear context menu icons after the icon preference changes."""
        if getattr(self.config, 'show_context_menu_icons', True):
            self.load_context_menu_icons()
        else:
            self.icon_images = {}
    
    def create_widgets(self):
        """Create all GUI widgets"""
        # Initialize tracking variables
        self.manual_tracks = []  # Store manually added tracks for current album
        
        # Main container
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Notebook for tabs
        self.notebook = ttk.Notebook(main_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True)
        
        # Upload Tab (hidden from notebook tabs)
        upload_frame = ttk.Frame(self.notebook)
        self.notebook.add(upload_frame, text="Upload")
        self.notebook.tab(upload_frame, state="hidden")  # Hide the tab from view
        self.create_upload_tab(upload_frame)

        # Settings Tab
        settings_frame = ttk.Frame(self.notebook)
        self.notebook.add(settings_frame, text="Settings")
        self.create_settings_tab(settings_frame)

        # Log Tab
        log_frame = ttk.Frame(self.notebook)
        self.notebook.add(log_frame, text="Logs")
        self.create_log_tab(log_frame)

        # About Tab
        about_frame = ttk.Frame(self.notebook)
        self.notebook.add(about_frame, text="About")
        self.create_about_tab(about_frame)

        # Hide all tabs except Upload and Logs (keep functionality but hide tab bar)
        for tab_id in self.notebook.tabs():
            tab_text = self.notebook.tab(tab_id, "text")
            if tab_text not in ["Upload", "Logs"]:
                self.notebook.tab(tab_id, state="hidden")
        # Select Upload tab (index 0) so it's the active/visible content
        self.notebook.select(0)



        # Initialize manual tracks preview
        self.update_manual_tracks_preview()

        # Start toast monitor
        self.monitor_toasts()



    def create_upload_tab(self, parent):
        """Create the main upload interface - redesigned for better usability"""
        
        # Main container - single-window compact layout (no scrolling)
        scrollable_frame = ttk.Frame(parent)
        scrollable_frame.pack(fill=tk.BOTH, expand=True)
        
        # TOP SECTION: Artist & Album in one row
        top_section = ttk.Frame(scrollable_frame)
        top_section.pack(fill=tk.X, padx=12, pady=(6, 4))
        
        # Artist Selection - Left half
        artist_frame = ttk.LabelFrame(top_section, text="Artist / Band", padding=10)
        artist_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 8))
        
        self.artist_var = tk.StringVar()
        self.artist_dropdown = ttk.Combobox(
            artist_frame, 
            textvariable=self.artist_var, 
            state="readonly",
            font=("Segoe UI", 10)
        )
        self.artist_dropdown.pack(fill=tk.X, pady=(0, 8))
        self.artist_dropdown.bind('<<ComboboxSelected>>', self.on_artist_selected)
        
        # Button row for Refresh Artists and Load Cookies
        button_row = ttk.Frame(artist_frame)
        button_row.pack(fill=tk.X)
        
        self.refresh_btn = ttk.Button(
            button_row,
            text="Refresh Artists",
            command=self.load_artists,
            style="Subtle.TButton"
        )
        self.refresh_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))
        ToolTip(self.refresh_btn, "Reload artists from all browsers.\nIf new artist not showing: close browser first, then click this.")

        self.load_cookies_btn = ttk.Button(
            button_row,
            text="Load Cookies",
            command=self.manual_load_cookies,
            style="Subtle.TButton"
        )
        self.load_cookies_btn.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ToolTip(self.load_cookies_btn, "Manually load cookies from file")
        
        # Album Directory - Right half
        album_frame = ttk.LabelFrame(top_section, text="Album Folder", padding=10)
        album_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(8, 0))
        
        self.album_path_var = tk.StringVar()
        self.album_path_entry = ttk.Entry(album_frame, textvariable=self.album_path_var, font=("Segoe UI", 10))
        self.album_path_entry.pack(fill=tk.X, pady=(0, 8))
        
        # Double-click to browse
        self.album_path_entry.bind('<Double-Button-1>', lambda e: self.browse_album())
        # Ctrl+V to paste path
        self.album_path_entry.bind('<Control-v>', lambda e: self.paste_album_path())
        # Enter to browse
        self.album_path_entry.bind('<Return>', lambda e: self.browse_album())
        # Right-click context menu
        self.album_path_entry.bind('<Button-3>', lambda e: self.show_album_context_menu(e))
        
        # Enable drag & drop for album folder (if available)
        if DRAG_DROP_AVAILABLE:
            try:
                album_entry.drop_target_register(DND_FILES)
                album_entry.dnd_bind('<<Drop>>', lambda e: self.on_drop_folder(e))
            except:
                pass  # Silently fail if drag & drop setup fails
        
        # Button rows
        album_btn_row1 = ttk.Frame(album_frame)
        album_btn_row1.pack(fill=tk.X, pady=(0, 3))
        
        self.album_browse_btn = ttk.Button(
            album_btn_row1, 
            text="Browse...", 
            command=self.browse_album,
            style="Subtle.TButton"
        )
        self.album_browse_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 3))

        self.open_folder_btn = ttk.Button(
            album_btn_row1,
            text="Open Folder",
            command=self.open_album_folder,
            style="Subtle.TButton"
        )
        self.open_folder_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 3))

        self.reload_album_btn = ttk.Button(
            album_btn_row1,
            text="Reload Album",
            command=self.reload_album,
            style="Subtle.TButton"
        )
        self.reload_album_btn.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Second row removed to keep layout compact
        
        # MIDDLE SECTION: Three columns for details
        middle_section = ttk.Frame(scrollable_frame)
        middle_section.pack(fill=tk.BOTH, expand=True, padx=12, pady=4)
        
        # Left column - Basic Details
        left_column = ttk.Frame(middle_section, width=300)
        left_column.pack(side=tk.LEFT, fill=tk.BOTH, padx=(0, 5))
        left_column.pack_propagate(False)  # Maintain fixed width
        
        details_frame = ttk.LabelFrame(left_column, text="Album Details", padding=8)
        details_frame.pack(fill=tk.BOTH, expand=True)
        
        # Album Name
        name_row = ttk.Frame(details_frame)
        name_row.pack(fill=tk.X, pady=(0, 6))
        
        ttk.Label(name_row, text="Album Name:", font=("Segoe UI", 8, "bold")).pack(anchor=tk.W, pady=(0, 2))
        
        name_inner = ttk.Frame(name_row)
        name_inner.pack(fill=tk.X)
        
        self.album_name_var = tk.StringVar()
        self.album_name_entry = ttk.Entry(name_inner, textvariable=self.album_name_var, font=("Segoe UI", 8))
        self.album_name_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 3))

        self.album_name_auto_btn = ttk.Button(
            name_inner,
            text="Auto",
            command=self.auto_fill_album_name,
            width=5
        )
        self.album_name_auto_btn.pack(side=tk.LEFT)
        ToolTip(name_inner.winfo_children()[-1], "Auto-fill from folder name")
        
        # Artist
        artist_row = ttk.Frame(details_frame)
        artist_row.pack(fill=tk.X, pady=(0, 6))
        
        ttk.Label(artist_row, text="Artist:", font=("Segoe UI", 8, "bold")).pack(anchor=tk.W, pady=(0, 2))
        
        artist_inner = ttk.Frame(artist_row)
        artist_inner.pack(fill=tk.X)
        
        self.album_artist_var = tk.StringVar()
        self.album_artist_entry = ttk.Entry(artist_inner, textvariable=self.album_artist_var, font=("Segoe UI", 8))
        self.album_artist_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 3))

        self.album_artist_auto_btn = ttk.Button(
            artist_inner,
            text="Auto",
            command=self.auto_fill_artist_name,
            width=5
        )
        self.album_artist_auto_btn.pack(side=tk.LEFT)
        ToolTip(artist_inner.winfo_children()[-1], "Auto-fill from track metadata")

        # Release Date
        release_date_row = ttk.Frame(details_frame)
        release_date_row.pack(fill=tk.X, pady=(0, 6))

        ttk.Label(release_date_row, text="Release Date:", font=("Segoe UI", 8, "bold")).pack(anchor=tk.W, pady=(0, 2))

        release_date_inner = ttk.Frame(release_date_row)
        release_date_inner.pack(fill=tk.X)

        self.album_release_date_entry = ttk.Entry(release_date_inner, textvariable=self.album_publish_date_var, font=("Segoe UI", 8))
        self.album_release_date_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 3))

        self.album_release_date_btn = ttk.Button(
            release_date_inner,
            text="Edit",
            command=self.show_release_date_calendar,
            width=5
        )
        self.album_release_date_btn.pack(side=tk.LEFT)
        ToolTip(release_date_inner.winfo_children()[-1], "Choose release date from calendar")

        # Tags
        ttk.Label(details_frame, text="Tags:", font=("Segoe UI", 8, "bold")).pack(anchor=tk.W, pady=(0, 2))
        self.album_tags_var = tk.StringVar()
        self.create_tag_input(details_frame)
        
        # Description
        ttk.Label(details_frame, text="Description:", font=("Segoe UI", 8, "bold")).pack(anchor=tk.W, pady=(0, 2))
        self.desc_text = scrolledtext.ScrolledText(details_frame, height=2, wrap=tk.WORD, font=("Segoe UI", 8))
        self.desc_text.pack(fill=tk.X, pady=(0, 6))
        self.desc_text.insert("1.0", self.album_description_var.get())
        self.desc_text.bind('<KeyRelease>', lambda e: self.album_description_var.set(self.desc_text.get("1.0", "end-1c")))
        # Hide vertical scrollbar
        self.desc_text.vbar.pack_forget()

        # Credits
        ttk.Label(details_frame, text="Credits:", font=("Segoe UI", 8, "bold")).pack(anchor=tk.W, pady=(0, 2))
        self.credits_text = scrolledtext.ScrolledText(details_frame, height=2, wrap=tk.WORD, font=("Segoe UI", 8))
        self.credits_text.pack(fill=tk.X, pady=(0, 6))
        # Hide vertical scrollbar
        self.credits_text.vbar.pack_forget()
        self.credits_text.insert("1.0", self.album_credits_var.get())
        self.credits_text.bind('<KeyRelease>', lambda e: self.album_credits_var.set(self.credits_text.get("1.0", "end-1c")))

        # License
        ttk.Label(details_frame, text="License:", font=("Segoe UI", 8, "bold")).pack(anchor=tk.W, pady=(0, 2))
        self.album_license_combo = ttk.Combobox(
            details_frame,
            textvariable=self.album_license_var,
            values=[
                "All Rights Reserved",
                "CC Attribution",
                "CC Attribution-ShareAlike",
                "CC Attribution-NoDerivatives",
                "CC Attribution-NonCommercial",
                "CC Attribution-NonCommercial-ShareAlike",
                "CC Attribution-NonCommercial-NoDerivatives",
                "Public Domain"
            ],
            state="readonly",
            font=("Segoe UI", 8)
        )
        self.album_license_combo.pack(fill=tk.X, pady=(0, 6))

        ttk.Label(details_frame, text="Download Description:", font=("Segoe UI", 8, "bold")).pack(anchor=tk.W, pady=(0, 2))
        self.album_download_desc_entry = ttk.Entry(details_frame, textvariable=self.album_download_desc_var, font=("Segoe UI", 8))
        self.album_download_desc_entry.pack(fill=tk.X, pady=(0, 6))

        ttk.Label(details_frame, text="Release Message:", font=("Segoe UI", 8, "bold")).pack(anchor=tk.W, pady=(0, 2))
        self.album_release_message_entry = ttk.Entry(details_frame, textvariable=self.album_release_message_var, font=("Segoe UI", 8))
        self.album_release_message_entry.pack(fill=tk.X, pady=(0, 6))

        ttk.Label(details_frame, text="Record Label:", font=("Segoe UI", 8, "bold")).pack(anchor=tk.W, pady=(0, 2))
        self.album_record_label_entry = ttk.Entry(details_frame, textvariable=self.album_record_label_var, font=("Segoe UI", 8))
        self.album_record_label_entry.pack(fill=tk.X, pady=(0, 6))

        ttk.Label(details_frame, text="Catalog #:", font=("Segoe UI", 8, "bold")).pack(anchor=tk.W, pady=(0, 2))
        self.album_catalog_number_entry = ttk.Entry(details_frame, textvariable=self.album_catalog_number_var, font=("Segoe UI", 8))
        self.album_catalog_number_entry.pack(fill=tk.X, pady=(0, 6))

        ttk.Label(details_frame, text="UPC/EAN:", font=("Segoe UI", 8, "bold")).pack(anchor=tk.W, pady=(0, 2))
        self.album_upc_entry = ttk.Entry(details_frame, textvariable=self.album_upc_var, font=("Segoe UI", 8))
        self.album_upc_entry.pack(fill=tk.X)
        self.setup_album_session_autosave()
        
        # Middle column - Preview
        middle_column = ttk.Frame(middle_section)
        middle_column.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(5, 5))
        
        # Album Preview
        preview_frame = ttk.LabelFrame(middle_column, text="Preview", padding=8)
        preview_frame.pack(fill=tk.BOTH, expand=True)
        
        # Main container with side-by-side layout
        preview_container = ttk.Frame(preview_frame)
        preview_container.pack(fill=tk.BOTH, expand=True)

        # Checkboxes row
        checkbox_frame = ttk.Frame(preview_container)
        checkbox_frame.pack(fill=tk.X, pady=(0, 4))

        self.ignore_artist_var = tk.BooleanVar(value=getattr(self.config, 'ignore_artist_name', False))
        self.filename_as_title_var = tk.BooleanVar(value=getattr(self.config, 'use_filename_as_title', False))
        self.ignore_metadata_var = tk.BooleanVar(value=getattr(self.config, 'ignore_all_metadata', False))

        self.ignore_artist_check = ttk.Checkbutton(checkbox_frame, text="Ignore artist", variable=self.ignore_artist_var, command=self.on_ignore_artist_changed)
        self.ignore_artist_check.pack(side=tk.LEFT, padx=(0, 10))
        self.filename_as_title_check = ttk.Checkbutton(checkbox_frame, text="Filename as title", variable=self.filename_as_title_var, command=self.on_filename_as_title_changed)
        self.filename_as_title_check.pack(side=tk.LEFT, padx=(0, 10))
        self.ignore_metadata_check = ttk.Checkbutton(checkbox_frame, text="Ignore metadata", variable=self.ignore_metadata_var, command=self.on_ignore_metadata_changed)
        self.ignore_metadata_check.pack(side=tk.LEFT, padx=(0, 10))

        ttk.Frame(checkbox_frame).pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.guess_case_preview_values = None
        self.guess_case_btn = ttk.Button(
            checkbox_frame,
            text="Guess Case",
            command=self.apply_guess_case_to_track_titles,
            style="Subtle.TButton"
        )
        self.guess_case_btn.pack(side=tk.RIGHT)
        self.guess_case_btn.bind("<Enter>", self.preview_guess_case_track_titles)
        self.guess_case_btn.bind("<Leave>", self.restore_guess_case_track_titles)

        self.extract_filename_preview_values = None
        self.extract_filename_btn = ttk.Button(
            checkbox_frame,
            text="Extract from Filename",
            command=self.apply_extract_from_filename,
            style="Subtle.TButton"
        )
        self.extract_filename_btn.pack(side=tk.RIGHT, padx=(0, 6))
        self.extract_filename_btn.bind("<Enter>", self.preview_extract_from_filename)
        self.extract_filename_btn.bind("<Leave>", self.restore_extract_from_filename)
        ToolTip(self.extract_filename_btn, "Parse track number and title from filename patterns\nHover to preview")

        self.add_track_btn = ttk.Button(
            checkbox_frame,
            text="Add Track",
            command=self.add_track_to_album,
            style="Subtle.TButton"
        )
        self.add_track_btn.pack(side=tk.RIGHT, padx=(0, 6))
        ToolTip(self.add_track_btn, "Add individual tracks to build the current album\n(Tracks shown in Preview area - right-click to manage)")

        # Track table (Treeview)
        table_frame = ttk.Frame(preview_container, width=1120)
        table_frame.pack(fill=tk.BOTH, expand=True)
        table_frame.pack_propagate(False)  # Maintain fixed width

        # Treeview (no scrollbars)
        self.track_table = ttk.Treeview(
            table_frame,
            columns=(
                "track_no", "artist", "track_name", "comment", "length", "extension",
                "price", "nyp", "year", "genre", "bitrate", "file_size", "file_path",
                "sample_rate", "channels", "bit_depth", "album_metadata",
                "album_artist_metadata", "composer", "isrc"
            ),
            show="headings",
            selectmode="browse"
        )
        self.track_table.pack(fill=tk.BOTH, expand=True)
        self.track_table.bind('<Configure>', self.on_track_table_configure)
        
        # Bind right-click for context menu
        self.track_table.bind('<Button-3>', self.show_track_context_menu)
        
        # Store copied metadata for paste functionality
        self.copied_track_metadata = None

        # Configure columns
        self.track_table.heading("track_no", text="Track No.")
        self.track_table.heading("artist", text="Artist")
        self.track_table.heading("track_name", text="Track Name")
        self.track_table.heading("comment", text="Comment")
        self.track_table.heading("length", text="Length")
        self.track_table.heading("extension", text="Extension")
        self.track_table.heading("price", text="Price")
        self.track_table.heading("nyp", text="NYP")
        self.track_table.heading("year", text="Year")
        self.track_table.heading("genre", text="Genre")
        self.track_table.heading("bitrate", text="Bitrate")
        self.track_table.heading("file_size", text="File Size")
        self.track_table.heading("file_path", text="File Path")
        self.track_table.heading("sample_rate", text="Sample Rate")
        self.track_table.heading("channels", text="Channels")
        self.track_table.heading("bit_depth", text="Bit Depth")
        self.track_table.heading("album_metadata", text="Album")
        self.track_table.heading("album_artist_metadata", text="Album Artist")
        self.track_table.heading("composer", text="Composer")
        self.track_table.heading("isrc", text="ISRC")
        self.configure_track_table_heading_commands()

        self.track_table.column("track_no", width=50, anchor=tk.CENTER)
        self.track_table.column("artist", width=150, anchor=tk.W)
        self.track_table.column("track_name", width=200, anchor=tk.W)
        self.track_table.column("comment", width=150, anchor=tk.W)
        self.track_table.column("length", width=80, anchor=tk.CENTER)
        self.track_table.column("extension", width=80, anchor=tk.CENTER)
        self.track_table.column("price", width=60, anchor=tk.CENTER)
        self.track_table.column("nyp", width=40, anchor=tk.CENTER)
        self.track_table.column("year", width=60, anchor=tk.CENTER)
        self.track_table.column("genre", width=100, anchor=tk.CENTER)
        self.track_table.column("bitrate", width=70, anchor=tk.CENTER)
        self.track_table.column("file_size", width=80, anchor=tk.CENTER)
        self.track_table.column("file_path", width=0, stretch=False)  # Hide file path column
        self.track_table.column("sample_rate", width=95, anchor=tk.CENTER)
        self.track_table.column("channels", width=70, anchor=tk.CENTER)
        self.track_table.column("bit_depth", width=75, anchor=tk.CENTER)
        self.track_table.column("album_metadata", width=140, anchor=tk.W)
        self.track_table.column("album_artist_metadata", width=140, anchor=tk.W)
        self.track_table.column("composer", width=120, anchor=tk.W)
        self.track_table.column("isrc", width=110, anchor=tk.CENTER)
        
        # Store original column widths for restoration
        self.column_widths = {
            "track_no": 50,
            "artist": 150,
            "track_name": 200,
            "comment": 150,
            "length": 80,
            "extension": 80,
            "price": 60,
            "nyp": 40,
            "year": 60,
            "genre": 100,
            "bitrate": 70,
            "file_size": 80,
            "file_path": 0,
            "sample_rate": 95,
            "channels": 70,
            "bit_depth": 75,
            "album_metadata": 140,
            "album_artist_metadata": 140,
            "composer": 120,
            "isrc": 110
        }
        
        # Calculate total width
        total_width = sum(self.column_widths.values())
        
        # Apply column visibility settings from config
        self.apply_column_visibility()

        # Font
        self.configure_track_table_tags()

        # Double-click to edit cells
        self.track_table.bind('<Double-Button-1>', self.on_table_double_click)

        # Drag and drop for reordering
        self.drag_data = {"item": None, "y": 0, "x": 0, "started": False, "highlight": None}
        self.track_table.bind('<Button-1>', self.on_drag_start)
        self.track_table.bind('<B1-Motion>', self.on_drag_motion)
        self.track_table.bind('<ButtonRelease-1>', self.on_drag_release)

        # Enable drag & drop for adding audio files (if available)
        try:
            table_frame.drop_target_register(DND_FILES)
            table_frame.dnd_bind('<<Drop>>', self.on_drop_track_files)
            self.track_table.drop_target_register(DND_FILES)
            self.track_table.dnd_bind('<<Drop>>', self.on_drop_track_files)
        except:
            pass  # Silently fail if drag & drop setup fails

        # Right column - Cover Art
        right_column = ttk.Frame(middle_section)
        right_column.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(5, 0))

        cover_frame = ttk.LabelFrame(right_column, text="Cover Art", padding=(6, 5))
        cover_frame.pack(fill=tk.X, anchor=tk.NW)

        cover_content_frame = ttk.Frame(cover_frame)
        cover_content_frame.pack(fill=tk.X, anchor=tk.W)

        # Cover art image preview
        self.cover_preview_frame = ttk.Frame(cover_content_frame, relief="sunken", borderwidth=1, width=156, height=156)
        self.cover_preview_frame.pack(side=tk.LEFT, anchor=tk.NW, padx=(0, 7))
        self.cover_preview_frame.pack_propagate(False)  # Maintain fixed square size

        self.cover_preview_label = ttk.Label(
            self.cover_preview_frame,
            text="No cover art\n\nClick Browse",
            anchor="center",
            justify="center",
            font=("Segoe UI", 9)
        )
        self.cover_preview_label.pack(expand=True, fill=tk.BOTH)

        # Right-click to clear cover art
        self.cover_preview_label.bind('<Button-3>', self.show_cover_context_menu)
        self.cover_preview_frame.bind('<Button-3>', self.show_cover_context_menu)

        # Double-click to view cover art
        self.cover_preview_label.bind('<Double-Button-1>', lambda e: self.view_cover_art())
        self.cover_preview_frame.bind('<Double-Button-1>', lambda e: self.view_cover_art())
        self.cover_preview_label.bind('<Configure>', lambda e: self.update_cover_preview())

        cover_controls_frame = ttk.Frame(cover_content_frame)
        cover_controls_frame.pack(side=tk.LEFT, fill=tk.X, expand=True, anchor=tk.NW)

        # Cover path entry
        self.cover_path_var = tk.StringVar()
        self.cover_path_var.trace_add('write', lambda *args: self.update_cover_preview())
        self.cover_path_var.trace_add('write', lambda *args: self.queue_album_session_save())
        self.cover_entry = ttk.Entry(cover_controls_frame, textvariable=self.cover_path_var, font=("Segoe UI", 7))
        self.cover_entry.pack(fill=tk.X, pady=(0, 3))

        # Double-click to browse cover
        self.cover_entry.bind('<Double-Button-1>', lambda e: self.browse_cover())
        # Enter to browse
        self.cover_entry.bind('<Return>', lambda e: self.browse_cover())

        # Enable drag & drop for cover art (if available)
        if DRAG_DROP_AVAILABLE:
            try:
                self.cover_entry.drop_target_register(DND_FILES)
                self.cover_entry.dnd_bind('<<Drop>>', lambda e: self.on_drop_image(e))
                self.cover_preview_label.drop_target_register(DND_FILES)
                self.cover_preview_label.dnd_bind('<<Drop>>', lambda e: self.on_drop_image(e))
            except:
                pass  # Silently fail if drag & drop setup fails

        # Cover buttons
        cover_btn_frame = ttk.Frame(cover_controls_frame)
        cover_btn_frame.pack(fill=tk.X, pady=(0, 3))

        self.browse_cover_btn = ttk.Button(
            cover_btn_frame,
            text="Browse",
            command=self.browse_cover
        )
        self.browse_cover_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 2))

        self.view_cover_btn = ttk.Button(
            cover_btn_frame,
            text="View",
            command=self.view_cover_art
        )
        self.view_cover_btn.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Library and Detect buttons side by side
        library_detect_frame = ttk.Frame(cover_controls_frame)
        library_detect_frame.pack(fill=tk.X, pady=(0, 3))

        self.library_cover_btn = ttk.Button(
            library_detect_frame,
            text="Library",
            command=self.manage_cover_art_library
        )
        self.library_cover_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 2))

        self.detect_cover_btn = ttk.Button(
            library_detect_frame,
            text="Detect",
            command=self.detect_cover_from_tracks
        )
        self.detect_cover_btn.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Auto-scale checkbox
        self.scale_cover_var = tk.BooleanVar(value=getattr(self.config, 'always_auto_scale_cover', True))
        self.scale_cover_check = ttk.Checkbutton(
            cover_controls_frame,
            text="Auto-scale to Bandcamp specs",
            variable=self.scale_cover_var,
            command=self.on_scale_cover_changed
        )
        self.scale_cover_check.pack(anchor=tk.W, pady=(0, 2))

        # Scale size and method dropdowns on same line
        scale_method_frame = ttk.Frame(cover_controls_frame)
        scale_method_frame.pack(fill=tk.X, pady=(0, 1))

        ttk.Label(scale_method_frame, text="Size:", font=("Segoe UI", 8)).pack(side=tk.LEFT, padx=(0, 3))

        self.scale_size_var = tk.StringVar(value="1400x1400")
        self.scaling_method_var = tk.StringVar(value=getattr(self.config, 'cover_scaling_method', 'Lanczos'))
        self.scale_size_combo = ttk.Combobox(
            scale_method_frame,
            textvariable=self.scale_size_var,
            values=["1400x1400", "2000x2000", "3000x3000"],
            state="readonly",
            width=10,
            font=("Segoe UI", 8)
        )
        self.scale_size_combo.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))

        self.create_upload_progress_section(right_column)

        # BOTTOM SECTION: Upload actions
        bottom_section = ttk.Frame(scrollable_frame)
        bottom_section.pack(fill=tk.X, padx=12, pady=(4, 6), side=tk.BOTTOM)

        # Action Buttons
        button_frame = ttk.Frame(bottom_section)
        button_frame.pack(fill=tk.X)
        
        # Preferences button
        prefs_btn = ttk.Button(
            button_frame,
            text="Preferences",
            command=self.open_preferences_dialog,
            style="Subtle.TButton"
        )
        prefs_btn.pack(side=tk.LEFT, padx=(0, 10))
        ToolTip(prefs_btn, "Open preferences dialog")
        
        self.upload_btn = ttk.Button(
            button_frame,
            text="UPLOAD ALBUM",
            command=self.start_upload,
            style="Primary.TButton",
            state=tk.DISABLED
        )
        self.upload_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        ToolTip(self.upload_btn, "Upload the selected album to Bandcamp (Keyboard: Ctrl+S)")
        
        self.cancel_btn = ttk.Button(
            button_frame,
            text="Cancel Upload",
            command=self.cancel_upload,
            style="Subtle.TButton",
            state=tk.DISABLED
        )
        self.cancel_btn.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ToolTip(self.cancel_btn, "Cancel the current upload operation")

    def create_upload_progress_section(self, parent):
        """Create the per-track upload progress section below cover art."""
        self.configure_upload_progress_styles()

        progress_title = ttk.Frame(parent)
        self.upload_progress_title_label = ttk.Label(
            progress_title,
            text="Progress",
            font=("Segoe UI", 9, "bold")
        )
        self.upload_progress_title_label.pack(side=tk.LEFT)
        self.upload_progress_remaining_label = ttk.Label(
            progress_title,
            text="",
            font=("Segoe UI", 8),
            foreground="#64748b"
        )
        self.upload_progress_remaining_label.pack(side=tk.LEFT, padx=(5, 0))

        progress_frame = ttk.LabelFrame(parent, labelwidget=progress_title, padding=(6, 5))
        progress_frame.pack(fill=tk.BOTH, expand=True, pady=(6, 0), anchor=tk.NW)
        self.upload_progress_frame = progress_frame

        self.upload_progress_canvas = tk.Canvas(progress_frame, highlightthickness=0, height=180)
        self.upload_progress_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        progress_scrollbar = ttk.Scrollbar(
            progress_frame,
            orient=tk.VERTICAL,
            command=self.upload_progress_canvas.yview
        )
        progress_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.upload_progress_canvas.configure(yscrollcommand=progress_scrollbar.set)

        self.upload_progress_content = ttk.Frame(self.upload_progress_canvas)
        self.upload_progress_canvas_window = self.upload_progress_canvas.create_window(
            (0, 0),
            window=self.upload_progress_content,
            anchor=tk.NW
        )

        def configure_progress_content(_event=None):
            self.upload_progress_canvas.configure(scrollregion=self.upload_progress_canvas.bbox("all"))

        def configure_progress_canvas(event):
            self.upload_progress_canvas.itemconfig(self.upload_progress_canvas_window, width=event.width)

        self.upload_progress_content.bind("<Configure>", configure_progress_content)
        self.upload_progress_canvas.bind("<Configure>", configure_progress_canvas)
        self.upload_progress_canvas.bind("<Enter>", self.bind_upload_progress_mousewheel)
        self.upload_progress_canvas.bind("<Leave>", self.unbind_upload_progress_mousewheel)
        self.upload_progress_content.bind("<Enter>", self.bind_upload_progress_mousewheel)
        self.upload_progress_content.bind("<Leave>", self.unbind_upload_progress_mousewheel)
        self.upload_progress_rows = []
        self.clear_upload_progress("No upload in progress")
        self.upload_progress_timing_job = None
        self.upload_progress_started_at = None
        self.upload_progress_active_index = None
        self.upload_progress_completed_count = 0
        self.upload_progress_total = 0

    def configure_upload_progress_styles(self):
        """Configure progress row styles used by the upload progress list."""
        style = ttk.Style()
        style.configure(
            "Failed.Horizontal.TProgressbar",
            background="#ef4444",
            troughcolor="#fee2e2",
            bordercolor="#ef4444",
            lightcolor="#ef4444",
            darkcolor="#dc2626",
        )

    def bind_upload_progress_mousewheel(self, _event=None):
        """Enable wheel scrolling while the pointer is over the progress list."""
        if not hasattr(self, 'upload_progress_canvas'):
            return

        widget = getattr(_event, "widget", self.upload_progress_canvas)
        widget.bind("<MouseWheel>", self.on_upload_progress_mousewheel)
        widget.bind("<Button-4>", self.on_upload_progress_mousewheel)
        widget.bind("<Button-5>", self.on_upload_progress_mousewheel)

    def unbind_upload_progress_mousewheel(self, _event=None):
        """Release progress-list wheel bindings when the pointer leaves."""
        if not hasattr(self, 'upload_progress_canvas'):
            return

        widget = getattr(_event, "widget", self.upload_progress_canvas)
        widget.unbind("<MouseWheel>")
        widget.unbind("<Button-4>")
        widget.unbind("<Button-5>")

    def on_upload_progress_mousewheel(self, event):
        """Scroll the upload progress list with the mouse wheel."""
        if not hasattr(self, 'upload_progress_canvas'):
            return

        if getattr(event, 'num', None) == 4:
            delta = -1
        elif getattr(event, 'num', None) == 5:
            delta = 1
        else:
            delta = -1 * int(event.delta / 120) if event.delta else 0

        if delta:
            self.upload_progress_canvas.yview_scroll(delta, "units")
        return "break"

    def clear_upload_progress(self, message="No upload in progress"):
        """Clear per-track progress rows and show a placeholder."""
        if not hasattr(self, 'upload_progress_content'):
            return

        self.stop_upload_progress_timer()

        for child in self.upload_progress_content.winfo_children():
            child.destroy()

        self.upload_progress_rows = []
        self.update_upload_progress_title_remaining("")
        placeholder = ttk.Label(
            self.upload_progress_content,
            text=message,
            font=("Segoe UI", 8),
            foreground="#64748b"
        )
        placeholder.pack(anchor=tk.W, padx=2, pady=4)
        placeholder.bind("<Enter>", self.bind_upload_progress_mousewheel)
        placeholder.bind("<Leave>", self.unbind_upload_progress_mousewheel)

    def prepare_upload_progress_tracks(self, tracks):
        """Create per-track progress rows for the current upload."""
        labels = []
        for index, track in enumerate(tracks):
            labels.append(self.format_upload_progress_track_label(track, index))
        self.prepare_upload_progress_labels(labels)

    def format_upload_progress_track_label(self, track, index):
        """Return a compact or detailed label for upload progress rows."""
        title = getattr(track.track_data, 'title', '') or getattr(track.path, 'stem', f'Track {index + 1}')
        if not getattr(self.config, 'detailed_progress_track_info', False):
            return title

        details = []
        artist = getattr(track.track_data, 'artist', '')
        if artist:
            details.append(str(artist))
        track_number = getattr(track.track_data, 'track_number', None)
        if track_number:
            details.append(f"#{track_number}")
        path = getattr(track, 'path', None)
        if path:
            details.append(path.name)
            try:
                size_mb = path.stat().st_size / (1024 ** 2)
                details.append(f"{size_mb:.1f} MB")
            except OSError:
                pass

        return f"{title} ({' | '.join(details)})" if details else title

    def prepare_upload_progress_labels(self, labels):
        """Create per-track progress rows from display labels."""
        if not hasattr(self, 'upload_progress_content'):
            return
        if getattr(self, 'upload_progress_started_at', None) is not None and self.is_upload_in_progress():
            return

        self.stop_upload_progress_timer()
        self.upload_progress_started_at = None
        self.upload_progress_active_index = None
        self.upload_progress_completed_count = 0
        self.upload_progress_total = len(labels)
        self.update_upload_progress_title_remaining("")

        for child in self.upload_progress_content.winfo_children():
            child.destroy()

        self.upload_progress_rows = []
        if not labels:
            self.clear_upload_progress("No tracks queued")
            return

        for index, title in enumerate(labels):
            row = ttk.Frame(self.upload_progress_content)
            row.pack(fill=tk.X, padx=2, pady=(0, 7))

            header = ttk.Frame(row)
            header.pack(fill=tk.X)

            title_label = ttk.Label(
                header,
                text=f"{index + 1}. {title}",
                font=("Segoe UI", 8)
            )
            title_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

            status_label = ttk.Label(
                header,
                text="Waiting",
                font=("Segoe UI", 8),
                foreground="#64748b"
            )
            status_label.pack(side=tk.RIGHT, padx=(6, 0))

            progress = ttk.Progressbar(row, maximum=100, value=0, mode='determinate')
            progress.pack(fill=tk.X, pady=(2, 0))

            for widget in (row, header, title_label, status_label, progress):
                widget.bind("<Enter>", self.bind_upload_progress_mousewheel)
                widget.bind("<Leave>", self.unbind_upload_progress_mousewheel)

            self.upload_progress_rows.append({
                "title": title_label,
                "status": status_label,
                "base_status": "Waiting",
                "progress": progress,
                "started_at": None,
                "finished_at": None,
            })

    def format_progress_duration(self, seconds):
        """Format a short elapsed/remaining duration."""
        seconds = max(0, int(seconds))
        minutes, sec = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        if hours:
            return f"{hours}h {minutes}m"
        if minutes:
            return f"{minutes}m {sec:02d}s"
        return f"{sec}s"

    def compose_progress_status_text(self, index):
        """Build status text with elapsed and remaining time."""
        row = self.upload_progress_rows[index]
        status = row.get("base_status", "") or ""
        if not getattr(self.config, 'show_progress_timing_details', False):
            return status

        now = time.monotonic()
        parts = [status] if status else []

        if row.get("started_at") and not row.get("finished_at"):
            elapsed = now - row["started_at"]
            parts.append(f"elapsed {self.format_progress_duration(elapsed)}")
            if self.upload_progress_completed_count:
                avg = (now - self.upload_progress_started_at) / max(1, self.upload_progress_completed_count)
                current_eta = max(0, avg - elapsed)
                parts.append(f"ETA {self.format_progress_duration(current_eta)}")

        if (
            self.upload_progress_started_at
            and self.upload_progress_completed_count
            and self.upload_progress_total
        ):
            avg = (now - self.upload_progress_started_at) / max(1, self.upload_progress_completed_count)
            remaining = max(0, self.upload_progress_total - self.upload_progress_completed_count)
            parts.append(f"remaining {self.format_progress_duration(avg * remaining)}")

        return " | ".join(parts)

    def calculate_upload_progress_remaining_seconds(self):
        """Return estimated album upload seconds remaining, or None until enough data exists."""
        if (
            not getattr(self, 'upload_progress_started_at', None)
            or not getattr(self, 'upload_progress_completed_count', 0)
            or not getattr(self, 'upload_progress_total', 0)
        ):
            return None

        now = time.monotonic()
        avg = (now - self.upload_progress_started_at) / max(1, self.upload_progress_completed_count)
        remaining_tracks = max(0, self.upload_progress_total - self.upload_progress_completed_count)

        active_extra = 0
        if (
            self.upload_progress_active_index is not None
            and 0 <= self.upload_progress_active_index < len(self.upload_progress_rows)
        ):
            row = self.upload_progress_rows[self.upload_progress_active_index]
            if row.get("started_at") and not row.get("finished_at"):
                active_extra = max(0, avg - (now - row["started_at"]))
                remaining_tracks = max(0, remaining_tracks - 1)

        return active_extra + (avg * remaining_tracks)

    def update_upload_progress_title_remaining(self, text=None):
        """Refresh the muted remaining-time suffix in the Progress title."""
        if not hasattr(self, 'upload_progress_remaining_label'):
            return

        if text is None:
            remaining = self.calculate_upload_progress_remaining_seconds()
            if remaining is None:
                text = "remaining calculating..."
            else:
                text = f"remaining {self.format_progress_duration(remaining)}"

        self.upload_progress_remaining_label.configure(text=text)

    def refresh_upload_progress_timing_labels(self):
        """Update live ETA/elapsed labels while upload runs."""
        if (
            self.upload_progress_active_index is not None
            and 0 <= self.upload_progress_active_index < len(self.upload_progress_rows)
        ):
            row = self.upload_progress_rows[self.upload_progress_active_index]
            row["status"].configure(text=self.compose_progress_status_text(self.upload_progress_active_index))

        if self.is_upload_in_progress():
            self.update_upload_progress_title_remaining(None)
            self.upload_progress_timing_job = self.root.after(1000, self.refresh_upload_progress_timing_labels)
        else:
            self.upload_progress_timing_job = None

    def start_upload_progress_timer(self):
        """Start the live upload timing updater."""
        if self.upload_progress_timing_job is None:
            self.upload_progress_timing_job = self.root.after(1000, self.refresh_upload_progress_timing_labels)

    def stop_upload_progress_timer(self):
        """Stop the live upload timing updater."""
        job = getattr(self, 'upload_progress_timing_job', None)
        if job is not None:
            try:
                self.root.after_cancel(job)
            except tk.TclError:
                pass
        self.upload_progress_timing_job = None

    def prepare_upload_progress_from_table(self):
        """Prime progress rows from the visible preview table before upload starts."""
        rows = self.get_track_table_rows()
        labels = []
        for index, row in enumerate(rows, 1):
            title = str(row[2]).strip() if len(row) > 2 else ""
            artist = str(row[1]).strip() if len(row) > 1 else ""
            label = f"{artist} - {title}" if artist and title else title or f"Track {index}"
            if getattr(self.config, 'detailed_progress_track_info', False):
                details = []
                length = str(row[4]).strip() if len(row) > 4 else ""
                extension = str(row[5]).strip() if len(row) > 5 else ""
                size = str(row[11]).strip() if len(row) > 11 else ""
                path = Path(row[12]).name if len(row) > 12 and row[12] else ""
                for value in (length, extension, size, path):
                    if value:
                        details.append(value)
                if details:
                    label = f"{label} ({' | '.join(details)})"
            labels.append(label)
        self.prepare_upload_progress_labels(labels)

    def handle_upload_progress_event(self, event, payload):
        """Update per-track progress rows from upload callbacks."""
        if event == "album_start":
            self.upload_progress_started_at = time.monotonic()
            self.upload_progress_completed_count = 0
            self.upload_progress_total = int(payload.get("total", len(getattr(self, 'upload_progress_rows', []))) or 0)
            self.update_upload_progress_title_remaining("remaining calculating...")
            self.start_upload_progress_timer()
            return

        if event == "album_done":
            self.stop_upload_progress_timer()
            self.upload_progress_active_index = None
            self.update_upload_progress_title_remaining("")
            successful = payload.get("successful", 0)
            total = payload.get("total", 0)
            skipped = payload.get("skipped", 0)
            self.update_status(f"Tracks uploaded: {successful}/{total} (skipped {skipped})", 100)
            return

        if event == "album_cancelled":
            self.stop_upload_progress_timer()
            self.upload_progress_active_index = None
            self.update_upload_progress_title_remaining("")
            for row in getattr(self, 'upload_progress_rows', []):
                if int(row["progress"]["value"]) < 100:
                    row["base_status"] = "Cancelled"
                    row["status"].configure(text="Cancelled")
            return

        index = payload.get("index")
        if index is None or not hasattr(self, 'upload_progress_rows'):
            return
        if index < 0 or index >= len(self.upload_progress_rows):
            return

        row = self.upload_progress_rows[index]
        progress_value = int(payload.get("progress", 0))
        status = payload.get("status", "")
        row["progress"]["value"] = max(0, min(100, progress_value))
        row["base_status"] = status
        row["status"].configure(foreground="#64748b")
        row["progress"].configure(style="Horizontal.TProgressbar")

        if event == "conversion_done":
            if getattr(self.config, 'notify_on_conversion_complete', False):
                self.show_toast(f"Converted: {payload.get('title', '')}", 2000, "success", trigger="conversion_complete")
            return

        if event == "track_start":
            if self.upload_progress_started_at is None:
                self.upload_progress_started_at = time.monotonic()
            row["started_at"] = time.monotonic()
            row["finished_at"] = None
            self.upload_progress_active_index = index
            self.start_upload_progress_timer()
        elif event in ("track_done", "track_skipped"):
            row["finished_at"] = time.monotonic()
            self.upload_progress_completed_count = min(
                len(self.upload_progress_rows),
                self.upload_progress_completed_count + 1
            )
            if self.upload_progress_active_index == index:
                self.upload_progress_active_index = None

            if event == "track_skipped":
                row["status"].configure(foreground="#dc2626")
                row["progress"].configure(style="Failed.Horizontal.TProgressbar")
                if getattr(self.config, 'notify_on_track_error', True):
                    self.root.after(0, lambda t=payload.get('title', ''): self.show_toast(f"Track skipped: {t}", 2500, "error", trigger="track_error"))

        row["status"].configure(text=self.compose_progress_status_text(index))

        if event == "track_start":
            self.update_status(
                f"Uploading track {index + 1}/{payload.get('total', len(self.upload_progress_rows))}: {payload.get('title', '')}",
                60
            )
        elif event == "track_done":
            self.update_status(
                f"Uploaded track {index + 1}/{payload.get('total', len(self.upload_progress_rows))}",
                None
            )
        elif event == "track_skipped":
            self.update_status(
                f"Skipped track {index + 1}/{payload.get('total', len(self.upload_progress_rows))}",
                None
            )

        self.update_upload_progress_title_remaining(None)

    def get_cover_preview_size(self):
        """Return the current square preview size, falling back before layout finishes."""
        if not hasattr(self, 'cover_preview_label'):
            return 156

        width = self.cover_preview_label.winfo_width()
        height = self.cover_preview_label.winfo_height()

        if width <= 1 or height <= 1:
            width = self.cover_preview_frame.winfo_width() if hasattr(self, 'cover_preview_frame') else 156
            height = self.cover_preview_frame.winfo_height() if hasattr(self, 'cover_preview_frame') else 156

        if width <= 1 or height <= 1:
            return 156

        return max(32, min(width, height))

    def get_cover_preview_background(self):
        """Return the neutral background used behind transparent cover previews."""
        return "#ffffff"

    def normalize_cover_image(self, cover_path, background="#ffffff"):
        """Load cover art with orientation fixed and alpha composited."""
        from PIL import Image, ImageOps

        with Image.open(cover_path) as source:
            img = ImageOps.exif_transpose(source)
            if img.mode in ("RGBA", "LA") or "transparency" in img.info:
                rgba = img.convert("RGBA")
                backdrop = Image.new("RGBA", rgba.size, background)
                backdrop.alpha_composite(rgba)
                return backdrop.convert("RGB")

            return img.convert("RGB")

    def crop_cover_to_square(self, img):
        """Crop from the center so cover art fills a square background cleanly."""
        width, height = img.size
        square_size = min(width, height)
        left = (width - square_size) // 2
        top = (height - square_size) // 2
        return img.crop((left, top, left + square_size, top + square_size))

    def make_cover_preview_image(self, cover_path, preview_size):
        """Render cover art as an exact square preview image."""
        from PIL import Image, ImageOps

        img = self.normalize_cover_image(cover_path, self.get_cover_preview_background())
        return ImageOps.fit(
            img,
            (preview_size, preview_size),
            method=Image.Resampling.LANCZOS,
            centering=(0.5, 0.5),
        )

    def update_cover_preview(self):
        """Update the cover art preview image"""
        if not hasattr(self, 'cover_preview_label') or not hasattr(self, 'cover_path_var'):
            return

        cover_path = self.cover_path_var.get()

        if not cover_path or not Path(cover_path).exists():
            # No cover or invalid path - show placeholder
            self.cover_preview_label.configure(
                image='',
                text="No cover art selected\n\nClick Browse to add"
            )
            if hasattr(self, '_cover_photo'):
                delattr(self, '_cover_photo')
            return

        try:
            from PIL import ImageTk

            preview_size = self.get_cover_preview_size()
            img = self.make_cover_preview_image(cover_path, preview_size)
            photo = ImageTk.PhotoImage(img)

            # Keep a reference to prevent garbage collection
            self._cover_photo = photo

            # Update label
            self.cover_preview_label.configure(image=photo, text='')

        except Exception as e:
            self.cover_preview_label.configure(
                image='',
                text=f"Error loading image:\n{str(e)}"
            )
            if hasattr(self, '_cover_photo'):
                delattr(self, '_cover_photo')

    def get_resampling_method(self):
        """Convert scaling method string to a PIL resampling constant."""
        return image_scaling.get_resampling_method(self.scaling_method_var)

    def apply_custom_scaling(self, img, target_size):
        """Apply the selected cover-art scaling method."""
        return image_scaling.apply_custom_scaling(img, target_size, self.scaling_method_var)

    def create_about_tab(self, parent):
        """Create about information tab"""
        container = ttk.Frame(parent)
        container.pack(fill=tk.BOTH, expand=True)

        content = ttk.Frame(container)
        content.place(relx=0.5, rely=0.5, anchor=tk.CENTER)

        ttk.Label(content, text="Bandcamp Auto Uploader",
                  font=("Segoe UI", 20, "bold")).pack()

        ttk.Label(content, text=f"Version {__version__}",
                  font=("Segoe UI", 11)).pack(pady=(5, 15))

        link = ttk.Label(content,
                         text="github.com/7x11x13/bandcamp-auto-uploader",
                         font=("Segoe UI", 9), foreground="#4a90e2", cursor="hand2")
        link.pack()
        link.bind("<Button-1>", lambda e: webbrowser.open("https://github.com/7x11x13/bandcamp-auto-uploader"))

        ttk.Label(content, text="By Nai64",
                  font=("Segoe UI", 10), foreground="gray").pack(pady=(0, 20))

        btn_frame = ttk.Frame(content)
        btn_frame.pack()
        ttk.Button(btn_frame, text="GitHub Repository",
                   command=lambda: webbrowser.open("https://github.com/Nai64/BandcampAutoUploader"),
                   width=22).pack(pady=3)
        ttk.Button(btn_frame, text="Follow on Twitter",
                   command=lambda: webbrowser.open("https://x.com/naii_dev"),
                   width=22).pack(pady=3)
        ttk.Button(btn_frame, text="Privacy Policy",
                   command=self.show_privacy_policy,
                   width=22).pack(pady=3)

        ttk.Label(content, text="Made with ❤ for the Bandcamp community",
                  font=("Segoe UI", 9), foreground="gray").pack(pady=(20, 5))
        ttk.Label(content, text="© 2026 Bandcamp Auto Uploader",
                  font=("Segoe UI", 8), foreground="gray").pack()
    
    def show_privacy_policy(self):
        """Show privacy policy dialog"""
        import sys
        
        dialog = tk.Toplevel(self.root)
        dialog.title("Privacy Policy")
        dialog.geometry("800x600")
        dialog.transient(self.root)
        
        # Center dialog
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (800 // 2)
        y = (dialog.winfo_screenheight() // 2) - (600 // 2)
        dialog.geometry(f"+{x}+{y}")
        
        # Main container with scroll
        main_frame = ttk.Frame(dialog)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        # Scrollable text area
        canvas = tk.Canvas(main_frame)
        scrollbar = ttk.Scrollbar(main_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Try to load privacy policy from file
        privacy_text = ""
        try:
            # Try to load from the application directory
            if getattr(sys, 'frozen', False):
                # Running as compiled exe
                app_dir = Path(sys._MEIPASS)
            else:
                # Running as script
                app_dir = Path(__file__).parent.parent.parent
            
            privacy_file = app_dir / "PRIVACY_POLICY.txt"
            if privacy_file.exists():
                with open(privacy_file, 'r', encoding='utf-8') as f:
                    privacy_text = f.read()
            else:
                # Fallback to basic policy if file not found
                privacy_text = "Privacy policy file not found. Please visit our GitHub repository for the full privacy policy."
        except Exception as e:
            logger.warning(f"Failed to load privacy policy file: {e}")
            privacy_text = "Unable to load privacy policy. Please visit our GitHub repository for the full privacy policy."
        
        text_widget = tk.Text(scrollable_frame, wrap=tk.WORD, font=("Segoe UI", 9), padx=10, pady=10)
        text_widget.insert("1.0", privacy_text)
        text_widget.config(state=tk.DISABLED)
        text_widget.pack(fill=tk.BOTH, expand=True)
        
        # Close button
        close_btn = ttk.Button(main_frame, text="Close", command=dialog.destroy, width=15)
        close_btn.pack(pady=(10, 0))
    
    def initialize_app(self):
        """Initialize the application"""
        self.update_status("Initializing...", 10)
        
        def init():
            try:
                # Auto-load cookies on startup if enabled
                if getattr(self.config, 'auto_load_cookies', False) and self.config.cookies_file:
                    self.update_status("Loading cookies...", 20)
                    try:
                        cj = http.cookiejar.MozillaCookieJar(self.config.cookies_file)
                        cj.load()
                        logger.info(f"Auto-loaded cookies from: {self.config.cookies_file}")
                        self.log_queue.put(f"Cookies loaded from: {self.config.cookies_file}")
                    except Exception as e:
                        logger.warning(f"Failed to auto-load cookies: {e}")
                
                # Load artists
                self.update_status("Loading artists...", 30)
                self.load_artists()
                self.log_queue.put("Application initialized successfully")

                self.update_status("Ready", 100)
            except Exception as e:
                exc_info = sys.exc_info()
                error_message = str(e)
                self.log_queue.put(f"ERROR: Initialization failed: {e}")
                self.root.after(
                    0,
                    lambda msg=error_message, info=exc_info: self.show_bug_log_prompt(
                        "Initialization Error",
                        msg,
                        error_text=msg,
                        exc_info=info,
                    )
                )
                self.update_status("Error", None)
            finally:
                self.update_status("Ready", None)
        
        threading.Thread(target=init, daemon=True).start()
    
    
    def load_artists(self):
        """Load available artists/bands from cookies"""
        self.artist_dropdown['values'] = ()
        
        def load():
            try:
                # Clear cache to detect new accounts
                self.urls = {}
                all_urls = {}
                
                # Try cookies file first
                if self.config.cookies_file:
                    urls = self.try_get_owned_bands_from_cookies_file(self.config.cookies_file)
                    if urls:
                        all_urls.update(urls)
                        logger.info(f"Loaded {len(urls)} artist(s) from cookies file")
                
                # ALWAYS check browsers for new accounts (not just when cookies file fails)
                browser_urls = self.try_get_owned_bands_from_browsers()
                if browser_urls:
                    # Merge with existing URLs (browser data can add new accounts)
                    new_accounts = 0
                    for url, cookies in browser_urls.items():
                        if url not in all_urls:
                            new_accounts += 1
                        all_urls[url] = cookies  # Browser cookies take priority (fresher)
                
                # Use merged results
                if all_urls:
                    self.urls = all_urls
                
                if self.urls:
                    self.root.after(0, self.update_artist_dropdown)
                    artist_count = len(self.urls)
                    self.root.after(0, lambda: self.show_toast(f"{artist_count} artist(s) loaded", 2500, "success", trigger="artists_load"))
                else:
                    self.log_queue.put("No artists found. Please log in to Bandcamp in your browser.")
                    self.root.after(0, lambda: messagebox.showwarning(
                        "No Artists Found",
                        "Could not find any Bandcamp artists.\n\n"
                        "Please make sure you're logged in to Bandcamp in at least one browser:\n"
                        "• Chrome, Firefox (Stable/Nightly/Developer/ESR), Edge, Brave\n"
                        "• Opera, Opera GX, Vivaldi, Safari\n\n"
                        "Steps to fix:\n"
                        "1. Log in to your Bandcamp account in your browser\n"
                        "2. Visit your artist/label page\n"
                        "3. CLOSE the browser completely (to save cookies to disk)\n"
                        "4. Click 'Refresh Artists' in this app\n\n"
                        "If still not working, export cookies.txt and configure it in Settings."
                    ))
            except Exception as e:
                logger.exception(e)
                self.log_queue.put(f"ERROR: Failed to load artists: {e}")
        
        threading.Thread(target=load, daemon=True).start()
    
    def update_artist_dropdown(self):
        """Update artist dropdown with loaded artists"""
        self.artist_dropdown['values'] = list(self.urls.keys())
        
        if self.urls:
            # Try to restore last selected artist from config
            last_artist = getattr(self.config, 'last_selected_artist', None)
            if last_artist and last_artist in self.urls:
                self.artist_dropdown.set(last_artist)
                self.on_artist_selected(None)
            else:
                self.artist_dropdown.current(0)
                self.on_artist_selected(None)
    
    def try_get_owned_bands_from_cookies_file(self, cookies_file: str) -> Optional[dict]:
        """Load artists from cookies.txt file"""
        try:
            cj = http.cookiejar.MozillaCookieJar(cookies_file)
            cj.load()
            bands = self.get_owned_bands(cj)
            return {url: cj for url in bands} if bands else None
        except Exception as e:
            logger.error(f"Failed to load cookies file: {e}")
            return None
    
    def try_get_owned_bands_from_browsers(self) -> Optional[dict]:
        """Try to get artists from browser cookies - loads from ALL browsers with accounts"""
        try:
            # Note: firefox() function automatically checks all Firefox profiles including Nightly, Developer Edition, ESR
            browsers = [
                (brave, "Brave"),
                (chrome, "Chrome"),
                (chromium, "Chromium"),
                (edge, "Edge"),
                (firefox, "Firefox"),  # Scans all Firefox profiles (Stable/Nightly/Developer/ESR)
                (opera, "Opera"),
                (opera_gx, "Opera GX"),
                (safari, "Safari"),
                (vivaldi, "Vivaldi")
            ]
            
            # Check ALL browsers in parallel and merge results
            self.update_status("Detecting browsers...", None)
            from concurrent.futures import ThreadPoolExecutor, as_completed
            
            all_bands = {}  # Will contain all bands from all browsers
            found_browsers = []
            
            with ThreadPoolExecutor(max_workers=5) as executor:
                future_to_browser = {
                    executor.submit(self._try_browser, cookie_fn, name): name 
                    for cookie_fn, name in browsers
                }
                
                for future in as_completed(future_to_browser):
                    browser_name = future_to_browser[future]
                    try:
                        result = future.result()
                        if result:
                            # Merge bands from this browser
                            if browser_name not in found_browsers:  # Avoid duplicate browser names
                                found_browsers.append(browser_name)
                            
                            # Merge into all_bands (later cookies override earlier ones)
                            for band_url, cookies in result.items():
                                all_bands[band_url] = cookies  # Always update to get freshest cookies
                    except Exception as e:
                        logger.debug(f"[{browser_name}] {e}")
            
            if all_bands:
                # Show which browsers we loaded from
                browser_list = ", ".join(found_browsers)
                self.update_status(f"Loaded from {len(found_browsers)} browser(s)", None)
                self.show_toast(f"Loaded {len(all_bands)} bands from {browser_list}", 3500, "success")
                
                # Cache the first successful browser for faster startup next time
                if found_browsers:
                    self.last_successful_browser = found_browsers[0]
                
                return all_bands
            
            # No bands found in any browser
            logger.warning("No logged-in Bandcamp accounts found in any browser")
            return None
        except Exception as e:
            logger.exception(e)
            return None
    
    def _try_browser(self, cookie_fn, browser_name: str) -> Optional[dict]:
        """Try to load cookies from a specific browser"""
        try:
            cj = http.cookiejar.CookieJar()
            logged_in = False
            
            for cookie in cookie_fn(domain_name="bandcamp.com"):
                cj.set_cookie(cookie)
                if cookie.name == "js_logged_in" and cookie.value == "1":
                    logged_in = True
            
            if not logged_in:
                return None
            
            logger.info(f"{browser_name}: Found active session, attempting to get bands...")
            bands = self.get_owned_bands(cj)
            if not bands:
                return None
            
            logger.info(f"{browser_name}: Successfully found {len(bands)} band(s)")
            return {url: cj for url in bands}
            
        except BrowserCookieError:
            return None
        except Exception as e:
            logger.debug(f"[{browser_name}] Error: {e}")
            return None
    
    def get_owned_bands(self, cj: http.cookiejar.CookieJar) -> list:
        """Get list of bands owned by the user"""
        session = requests.Session()
        session.mount("https://", BandcampHTTPAdapter())
        
        # Filter cookies to only include essential authentication cookies
        # This prevents "Request Header Or Cookie Too Large" errors
        essential_cookies = http.cookiejar.CookieJar()
        essential_cookie_names = {
            'js_logged_in',  # Session indicator
            'client_id',     # Client identifier
            'session',       # Session token
            'logged_in',     # Login status
            'BACKENDID',     # Backend identifier
            'customer_id',   # Customer identifier
        }
        
        for cookie in cj:
            # Only include cookies for bandcamp.com domain
            if 'bandcamp.com' in cookie.domain:
                # Include essential cookies by name
                if cookie.name in essential_cookie_names:
                    essential_cookies.set_cookie(cookie)
                # Also include cookies that look like session/auth cookies
                elif any(keyword in cookie.name.lower() for keyword in ['session', 'auth', 'token', 'login', 'id']):
                    essential_cookies.set_cookie(cookie)
        
        session.cookies.update(essential_cookies)
        
        # Try with proper headers that Bandcamp expects
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'Origin': 'https://bandcamp.com',
            'Referer': 'https://bandcamp.com/'
        }
        
        try:
            r = session.post("https://bandcamp.com/api/design_system/1/menubar", headers=headers)
            
            if r.status_code != 200:
                logger.error(f"API call failed with status {r.status_code}")
                logger.error(
                    "Response summary: bytes=%s content_type=%s",
                    len(r.content or b""),
                    r.headers.get("content-type", "unknown"),
                )
                r.raise_for_status()
            
            data = r.json()
            
            bands = [data.get("activeBand")]
            if data.get("labelBands"):
                bands.extend(data["labelBands"])
            if data.get("additionalLabelBands"):
                bands.extend(data["additionalLabelBands"])
            if data.get("connectedBands"):
                bands.extend(data["connectedBands"])
            # Also check pageOwnerBand in case artist accounts are there
            if data.get("pageOwnerBand"):
                bands.append(data.get("pageOwnerBand"))
            
            band_urls = []
            for band in bands:
                if band and band.get("url"):
                    band_name = band.get("name", "Unknown")
                    band_url = band["url"]
                    band_urls.append(band_url)
            
            result = list(set(band_urls))
            return result
            
        except Exception as e:
            logger.error(f"API call failed: {e}")
            raise
    
    def on_artist_selected(self, event):
        """Handle artist selection"""
        selected = self.artist_var.get()
        if selected and selected in self.urls:
            self.selected_artist_url = selected
            self.setup_session()
            
            # Save last selected artist for next session
            self.config.last_selected_artist = selected
            
            # Add to recent artists list
            if not hasattr(self.config, 'recent_artists'):
                self.config.recent_artists = []
            
            if selected not in self.config.recent_artists:
                self.config.recent_artists.insert(0, selected)
                self.config.recent_artists = self.config.recent_artists[:5]  # Keep last 5
            
            try:
                save_config(self.config)
            except:
                pass  # Non-critical if save fails
            self.upload_btn['state'] = tk.NORMAL if self.album_path_var.get() else tk.DISABLED


            logger.info(f"Selected artist: {selected}")
    
    def setup_session(self):
        """Setup requests session with selected artist's cookies"""
        if self.selected_artist_url and self.selected_artist_url in self.urls:
            self.session = requests.Session()
            self.session.mount("https://", BandcampHTTPAdapter())
            
            # Filter cookies to only include essential authentication cookies
            # This prevents "Request Header Or Cookie Too Large" errors
            cj = self.urls[self.selected_artist_url]
            essential_cookies = http.cookiejar.CookieJar()
            essential_cookie_names = {
                'js_logged_in',  # Session indicator
                'client_id',     # Client identifier
                'session',       # Session token
                'logged_in',     # Login status
                'BACKENDID',     # Backend identifier
                'customer_id',   # Customer identifier
            }
            
            for cookie in cj:
                # Only include cookies for bandcamp.com domain
                if 'bandcamp.com' in cookie.domain:
                    # Include essential cookies by name
                    if cookie.name in essential_cookie_names:
                        essential_cookies.set_cookie(cookie)
                    # Also include cookies that look like session/auth cookies
                    elif any(keyword in cookie.name.lower() for keyword in ['session', 'auth', 'token', 'login', 'id']):
                        essential_cookies.set_cookie(cookie)
            
            self.session.cookies = essential_cookies
            self.session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            })
            
            # Verify session
            def verify():
                try:
                    test_url = urljoin(self.selected_artist_url, "edit_album")
                    test_response = self.session.get(test_url, timeout=10)
                    if "login" in test_response.url.lower() or "signin" in test_response.url.lower():
                        self.log_queue.put("WARNING: Session may be invalid - redirected to login")
                        self.root.after(0, lambda: messagebox.showwarning(
                            "Session Warning",
                            "Your session may have expired. Please log in to Bandcamp again."
                        ))
                    else:
                        self.log_queue.put("Session verified successfully")
                except Exception as e:
                    self.log_queue.put(f"Session verification failed: {e}")
            
            threading.Thread(target=verify, daemon=True).start()
    
    def auto_detect_cover_art(self, album_path):
        """Auto-detect cover art from album folder"""
        if not album_path or not Path(album_path).exists():
            return False

        path = Path(album_path)
        # Common cover art filenames
        cover_names = ['cover.jpg', 'cover.png', 'cover.jpeg', 'cover.gif',
                      'folder.jpg', 'folder.png', 'folder.jpeg',
                      'front.jpg', 'front.png', 'front.jpeg',
                      'album.jpg', 'album.png', 'album.jpeg',
                      'artwork.jpg', 'artwork.png', 'artwork.jpeg']

        for cover_name in cover_names:
            cover_file = path / cover_name
            if cover_file.exists():
                self.cover_path_var.set(str(cover_file))
                logger.info(f"Auto-detected cover art: {cover_name}")
                self.show_toast(f"Auto-detected cover: {cover_name}", 2000, "success")
                return True

        # Also check for any image file in the folder
        for ext in ['.jpg', '.jpeg', '.png', '.gif']:
            for file in path.glob(f"*{ext}"):
                # Skip if it's a track file (unlikely but possible)
                if file.stem.lower() not in ['cover', 'folder', 'front', 'album', 'artwork']:
                    self.cover_path_var.set(str(file))
                    logger.info(f"Auto-detected cover art: {file.name}")
                    self.show_toast(f"Auto-detected cover: {file.name}", 2000, "success")
                    return True

        return False

    def get_current_track_paths(self, album_path=None):
        """Return track paths from the visible album/manual context."""
        paths = []
        if hasattr(self, 'track_table'):
            for row in self.get_track_table_rows():
                if len(row) > 12 and row[12]:
                    path = Path(row[12])
                    if path.exists():
                        paths.append(path)

        if paths:
            return paths

        if self.manual_tracks:
            return [Path(path) for path in self.manual_tracks if Path(path).exists()]

        if album_path and Path(album_path).is_dir():
            folder = Path(album_path)
            for ext in ('*.wav', '*.flac', '*.aiff', '*.mp3', '*.ogg', '*.opus', '*.m4a', '*.aac', '*.mod', '*.xm'):
                paths.extend(folder.glob(ext))
                paths.extend(folder.glob(ext.upper()))

        return paths

    def extract_first_embedded_cover_to_temp(self, tracks):
        """Extract the first embedded track cover art to a temporary file."""
        import tempfile
        import mutagen
        from mutagen.flac import FLAC
        from mutagen.mp4 import MP4, MP4Cover
        from mutagen.oggvorbis import OggVorbis
        from mutagen.oggopus import OggOpus
        from PIL import Image

        for track_path in tracks:
            try:
                file_data = mutagen.File(track_path)
                if file_data is None:
                    continue

                cover_data = None
                mime_type = None

                if isinstance(file_data, (FLAC, OggVorbis, OggOpus)) and file_data.pictures:
                    cover_data = file_data.pictures[0].data
                    mime_type = file_data.pictures[0].mime
                elif getattr(file_data, 'tags', None) is not None:
                    tags = file_data.tags
                    if hasattr(tags, 'getall'):
                        pictures = tags.getall("APIC")
                        if pictures:
                            cover_data = pictures[0].data
                            mime_type = pictures[0].mime
                    if cover_data is None and 'covr' in tags:
                        cover = tags['covr'][0]
                        cover_data = bytes(cover)
                        mime_type = 'image/png' if getattr(cover, 'imageformat', None) == MP4Cover.FORMAT_PNG else 'image/jpeg'

                if not cover_data:
                    continue

                suffix = '.png' if mime_type and 'png' in mime_type.lower() else '.jpg'
                temp_dir = Path(tempfile.gettempdir()) / "bandcamp_auto_uploader_covers"
                temp_dir.mkdir(parents=True, exist_ok=True)
                safe_name = re.sub(r'[^A-Za-z0-9._-]+', '_', track_path.stem).strip('._-') or 'track'
                cover_path = temp_dir / f"{safe_name}_embedded_cover{suffix}"
                cover_path.write_bytes(cover_data)

                with Image.open(cover_path) as img:
                    img.verify()

                logger.info(f"Auto-extracted embedded cover art from {track_path.name}")
                return cover_path
            except Exception as e:
                logger.debug(f"Failed to auto-extract embedded cover from {track_path}: {e}")

        return None

    def auto_extract_cover_art_if_missing(self, album_path=None):
        """Use embedded track artwork when no cover image was found."""
        if self.cover_path_var.get() or not getattr(self.config, 'extract_track_cover_if_missing', True):
            return False

        cover_path = self.extract_first_embedded_cover_to_temp(self.get_current_track_paths(album_path))
        if not cover_path:
            return False

        self.cover_path_var.set(str(cover_path))
        self.add_to_cover_library(str(cover_path))
        self.show_toast("Extracted cover art from track metadata", 2200, "success", trigger="cover_load")
        return True

    def apply_album_load_preferences(self, album_path):
        """Apply metadata, fallback, and order preferences after an album folder loads."""
        path = Path(album_path)

        if self.config.auto_load_metadata:
            self.auto_fill_album_details_from_metadata(path)

        if (
            getattr(self.config, 'use_folder_name_when_album_missing', True)
            and not self.album_name_var.get()
        ):
            self.album_name_var.set(path.name)

        if getattr(self.config, 'smart_randomize_on_album_load', False):
            self.smart_randomize_tracks(show_feedback=False)

        if getattr(self.config, 'auto_guess_case_on_album_load', False):
            self.apply_guess_case_to_track_titles(preview=False, show_feedback=False)

    def on_album_selection_changed(self):
        """Reset album-change UI state controlled by Preferences."""
        if getattr(self.config, 'clear_progress_on_album_change', True):
            self.clear_upload_progress("No upload in progress")

    def clear_album_load_fields(self):
        """Clear album-specific fields before loading metadata from another album."""
        self.album_name_var.set("")
        self.album_artist_var.set("")
        self.album_tags_var.set("")
        if hasattr(self, 'tag_entry'):
            self.tag_entry.delete(0, tk.END)

        self.set_album_description_text("")
        self.album_credits_var.set("")
        if hasattr(self, 'credits_text'):
            self.credits_text.delete("1.0", tk.END)

        self.cover_path_var.set("")
        self.album_publish_date_var.set("")
        self.album_record_label_var.set("")
        self.album_catalog_number_var.set("")
        self.album_upc_var.set("")
        self.album_download_desc_var.set("")
        self.album_release_message_var.set("")
        self.album_license_var.set("All Rights Reserved")

    def get_album_description_text(self):
        """Return current album description text from the widget when available."""
        if hasattr(self, 'desc_text'):
            return self.desc_text.get("1.0", "end-1c").strip()
        return self.album_description_var.get().strip()

    def set_album_description_text(self, text):
        """Set album description text and backing variable together."""
        self.album_description_var.set(text)
        if hasattr(self, 'desc_text'):
            original_state = str(self.desc_text.cget("state"))
            if original_state == tk.DISABLED:
                self.desc_text.configure(state=tk.NORMAL)
            self.desc_text.delete("1.0", tk.END)
            self.desc_text.insert("1.0", text)
            if original_state == tk.DISABLED:
                self.desc_text.configure(state=tk.DISABLED)

    def setup_album_session_autosave(self):
        """Track album-detail changes for the per-folder session file."""
        if getattr(self, '_album_session_autosave_ready', False):
            return

        vars_to_watch = (
            self.album_name_var,
            self.album_artist_var,
            self.album_tags_var,
            self.album_description_var,
            self.album_credits_var,
            self.album_license_var,
            self.album_publish_date_var,
            self.album_upc_var,
            self.album_catalog_number_var,
            self.album_record_label_var,
            self.album_download_desc_var,
            self.album_release_message_var,
        )
        for var in vars_to_watch:
            var.trace_add('write', lambda *args: self.queue_album_session_save())

        self._album_session_autosave_ready = True

    def get_album_session_file_path(self, album_path=None):
        """Return the sidecar file path for the current album folder."""
        album_path = album_path or self.album_path_var.get()
        if not album_path:
            return None

        path = Path(album_path)
        if not path.is_dir():
            return None

        return path / "session.txt"

    def get_legacy_album_session_file_path(self, album_path=None):
        """Return the previous sidecar name for one-time migration/cleanup."""
        album_path = album_path or self.album_path_var.get()
        if not album_path:
            return None

        path = Path(album_path)
        if not path.is_dir():
            return None

        return path / "bandcamp_auto_uploader_album.txt"

    def get_album_session_details(self):
        """Return album-detail fields that should survive reloads."""
        credits = self.credits_text.get("1.0", "end-1c") if hasattr(self, 'credits_text') else self.album_credits_var.get()
        return {
            "album_name": self.album_name_var.get(),
            "artist": self.album_artist_var.get(),
            "release_date": self.album_publish_date_var.get(),
            "tags": self.album_tags_var.get(),
            "description": self.get_album_description_text(),
            "credits": credits,
            "license": self.album_license_var.get(),
            "download_description": self.album_download_desc_var.get(),
            "release_message": self.album_release_message_var.get(),
            "record_label": self.album_record_label_var.get(),
            "catalog_number": self.album_catalog_number_var.get(),
            "upc": self.album_upc_var.get(),
            "cover_art": self.cover_path_var.get() if hasattr(self, 'cover_path_var') else "",
        }

    def get_album_session_payload(self):
        """Build a serializable album session snapshot."""
        columns = list(self.track_table["columns"]) if hasattr(self, 'track_table') else []
        rows = []
        if hasattr(self, 'track_table'):
            for item in self.track_table.get_children():
                values = list(self.track_table.item(item).get("values", ()))
                row = {}
                for index, column in enumerate(columns):
                    row[column] = str(values[index]) if index < len(values) else ""
                rows.append(row)

        return {
            "version": 1,
            "saved_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "album_path": self.album_path_var.get(),
            "album_details": self.get_album_session_details(),
            "locked_track_keys": sorted(getattr(self, 'locked_track_keys', set())),
            "track_columns": columns,
            "tracks": rows,
        }

    def render_album_session_text(self, payload):
        """Render a human-readable session file with a machine-readable block."""
        details = payload.get("album_details", {})
        lines = [
            "[Album Details]",
            f"Saved At: {payload.get('saved_at', '')}",
            f"Album Folder: {payload.get('album_path', '')}",
            f"Album Name: {details.get('album_name', '')}",
            f"Artist: {details.get('artist', '')}",
            f"Release Date: {details.get('release_date', '')}",
            f"Tags: {details.get('tags', '')}",
            f"License: {details.get('license', '')}",
            f"Record Label: {details.get('record_label', '')}",
            f"Catalog Number: {details.get('catalog_number', '')}",
            f"UPC/EAN: {details.get('upc', '')}",
            f"Cover Art: {details.get('cover_art', '')}",
            "",
            "[Description]",
            details.get("description", ""),
            "",
            "[Credits]",
            details.get("credits", ""),
            "",
            "[Download Description]",
            details.get("download_description", ""),
            "",
            "[Release Message]",
            details.get("release_message", ""),
            "",
            "[Tracks]",
        ]

        for row in payload.get("tracks", []):
            number = row.get("track_no", "")
            artist = row.get("artist", "")
            title = row.get("track_name", "")
            comment = row.get("comment", "")
            file_path = row.get("file_path", "")
            lines.append(f"{number}. {artist} - {title}".strip())
            if comment:
                lines.append(f"   Comment: {comment}")
            lines.append(f"   File: {file_path}")

        lines.extend([
            "",
            "--- BEGIN BAU SESSION JSON ---",
            json.dumps(payload, indent=2, ensure_ascii=False),
            "--- END BAU SESSION JSON ---",
            "",
        ])
        return "\n".join(lines)

    def save_album_session_file(self):
        """Write the current album session into the album folder."""
        self._album_session_save_job = None
        if not getattr(self.config, 'create_album_session_files', True):
            return
        if getattr(self, '_album_session_loading', False):
            return

        session_path = self.get_album_session_file_path()
        if not session_path:
            return

        try:
            payload = self.get_album_session_payload()
            session_path.write_text(self.render_album_session_text(payload), encoding="utf-8")
            logger.debug(f"Saved album session file: {session_path}")
            if getattr(self.config, 'notify_on_album_save', False):
                self.show_toast("Album session saved", 1800, "success", trigger="album_save")
        except Exception as e:
            logger.warning(f"Failed to save album session file: {e}")

    def queue_album_session_save(self, delay_ms=700):
        """Debounce album session writes while the user edits fields."""
        if not getattr(self.config, 'create_album_session_files', True):
            return
        if getattr(self, '_album_session_loading', False):
            return
        if not self.get_album_session_file_path():
            return
        if self._album_session_save_job is not None:
            try:
                self.root.after_cancel(self._album_session_save_job)
            except tk.TclError:
                pass
        self._album_session_save_job = self.root.after(delay_ms, self.save_album_session_file)

    def read_album_session_payload(self, session_path):
        """Read the JSON block from a human-readable album session file."""
        text = session_path.read_text(encoding="utf-8")
        begin = "--- BEGIN BAU SESSION JSON ---"
        end = "--- END BAU SESSION JSON ---"
        if begin not in text or end not in text:
            return None

        json_text = text.split(begin, 1)[1].split(end, 1)[0].strip()
        return json.loads(json_text)

    def apply_album_session_details(self, details):
        """Restore album-detail fields from the session file."""
        self.album_name_var.set(details.get("album_name", ""))
        self.album_artist_var.set(details.get("artist", ""))
        self.album_publish_date_var.set(details.get("release_date", ""))
        self.album_tags_var.set(details.get("tags", ""))
        if hasattr(self, 'tag_entry'):
            self.tag_entry.delete(0, tk.END)
            self.tag_entry.insert(0, details.get("tags", ""))
            self.validate_tag_limit()

        self.set_album_description_text(details.get("description", ""))
        self.album_credits_var.set(details.get("credits", ""))
        if hasattr(self, 'credits_text'):
            self.credits_text.delete("1.0", tk.END)
            self.credits_text.insert("1.0", details.get("credits", ""))

        self.album_license_var.set(details.get("license", "All Rights Reserved"))
        self.album_download_desc_var.set(details.get("download_description", ""))
        self.album_release_message_var.set(details.get("release_message", ""))
        self.album_record_label_var.set(details.get("record_label", ""))
        self.album_catalog_number_var.set(details.get("catalog_number", ""))
        self.album_upc_var.set(details.get("upc", ""))

        self.cover_path_var.set(details.get("cover_art", ""))

    def apply_album_session_tracks(self, payload):
        """Restore saved track order and editable table fields."""
        if not hasattr(self, 'track_table'):
            return

        saved_rows = payload.get("tracks", [])
        if not saved_rows:
            return

        columns = list(self.track_table["columns"])
        current_rows = []
        for item in self.track_table.get_children():
            values = list(self.track_table.item(item).get("values", ()))
            while len(values) < len(columns):
                values.append("")
            current_rows.append(values)

        current_by_path = {
            str(values[12]): values
            for values in current_rows
            if len(values) > 12 and str(values[12]).strip()
        }
        used_paths = set()
        restored_rows = []

        for saved_row in saved_rows:
            file_path = str(saved_row.get("file_path", "")).strip()
            if file_path and file_path not in current_by_path:
                continue

            values = list(current_by_path.get(file_path, [""] * len(columns)))
            for index, column in enumerate(columns):
                if column in saved_row:
                    values[index] = saved_row.get(column, "")
            restored_rows.append(values)
            if file_path:
                used_paths.add(file_path)

        for values in current_rows:
            file_path = str(values[12]).strip() if len(values) > 12 else ""
            if file_path and file_path not in used_paths:
                restored_rows.append(values)

        if not restored_rows:
            return

        for item in self.track_table.get_children():
            self.track_table.delete(item)
        for values in restored_rows:
            self.insert_track_row(values)

        self.renumber_tracks()
        self.maybe_auto_fit_track_columns()

    def load_or_create_album_session_file(self, album_path):
        """Load an album session sidecar if it exists, otherwise create one."""
        if not getattr(self.config, 'create_album_session_files', True):
            return

        session_path = self.get_album_session_file_path(album_path)
        if not session_path:
            return

        legacy_session_path = self.get_legacy_album_session_file_path(album_path)
        if (
            legacy_session_path
            and legacy_session_path.exists()
            and not session_path.exists()
        ):
            try:
                legacy_session_path.replace(session_path)
                logger.info(f"Migrated album session file to: {session_path}")
            except Exception as e:
                logger.warning(f"Failed to migrate legacy album session file: {e}")

        if not session_path.exists():
            self.save_album_session_file()
            self.show_toast("Album session file created", 1800, "success", trigger="file_add")
            return

        try:
            payload = self.read_album_session_payload(session_path)
            if not payload:
                self.show_toast("Album session file has no loadable data", 2200, "warning")
                return

            self._album_session_loading = True
            self.apply_album_session_details(payload.get("album_details", {}))
            self.locked_track_keys = set(payload.get("locked_track_keys", []))
            self.apply_album_session_tracks(payload)
            self.sync_track_table_to_current_album()
            self.show_toast("Album session restored", 1800, "success", trigger="file_add")
        except Exception as e:
            logger.warning(f"Failed to load album session file: {e}")
            self.show_toast("Could not load album session file", 2200, "warning")
        finally:
            self._album_session_loading = False

    def build_album_upload_credits(self, credits):
        """Append the uploader footer to album credits without replacing user text."""
        footer = (
            "This album was uploaded by Bandcamp Auto Uploader\n"
            "https://github.com/Nai64/BandcampAutoUploader"
        )
        credits = credits.strip()
        if footer in credits:
            return credits
        if credits:
            return f"{credits}\n\n{footer}"
        return footer

    def get_track_table_rows(self):
        """Return visible track rows from the preview table."""
        rows = []
        if not hasattr(self, 'track_table'):
            return rows

        for item in self.track_table.get_children():
            values = list(self.track_table.item(item)['values'])
            while len(values) < 13:
                values.append("")
            rows.append(values)
        return rows

    def get_current_album_directory(self, fallback_track_path=None):
        """Return the best folder for album-side exports."""
        album_path = self.album_path_var.get()
        if album_path and Path(album_path).is_dir():
            return Path(album_path)

        if fallback_track_path:
            track_path = Path(fallback_track_path)
            if track_path.exists():
                return track_path.parent

        for row in self.get_track_table_rows():
            if len(row) > 12 and row[12]:
                track_path = Path(row[12])
                if track_path.exists():
                    return track_path.parent

        return Path.cwd()

    def get_track_table_state_snapshot(self, label="Edit"):
        """Capture the editable album/table state for undo and redo."""
        return {
            "label": label,
            "rows": [tuple(row) for row in self.get_track_table_rows()],
            "locked_track_keys": sorted(getattr(self, 'locked_track_keys', set())),
            "album_details": self.get_album_session_details(),
        }

    def restore_track_table_state_snapshot(self, snapshot):
        """Restore a captured album/table state."""
        self._album_session_loading = True
        try:
            self.locked_track_keys = set(snapshot.get("locked_track_keys", []))
            self.apply_album_session_details(snapshot.get("album_details", {}))

            if hasattr(self, 'track_table'):
                for item in self.track_table.get_children():
                    self.track_table.delete(item)
                for row in snapshot.get("rows", []):
                    self.insert_track_row(row)

            self.sync_track_table_to_current_album()
            self.maybe_auto_fit_track_columns()
        finally:
            self._album_session_loading = False
        self.queue_album_session_save()

    def push_undo_state(self, label="Edit"):
        """Store the current table state before a mutating action."""
        if not hasattr(self, 'track_table'):
            return
        self.undo_buffer.append(self.get_track_table_state_snapshot(label))
        self.undo_buffer = self.undo_buffer[-50:]
        self.redo_buffer.clear()

    def undo_track_table_action(self):
        """Undo the latest captured track-table action."""
        if not self.undo_buffer:
            self.show_toast("Nothing to undo", 1500, "info")
            return
        current = self.get_track_table_state_snapshot("Redo state")
        snapshot = self.undo_buffer.pop()
        self.redo_buffer.append(current)
        self.restore_track_table_state_snapshot(snapshot)
        self.show_toast(f"Undid: {snapshot.get('label', 'Edit')}", 1700, "success")

    def redo_track_table_action(self):
        """Redo the latest undone track-table action."""
        if not self.redo_buffer:
            self.show_toast("Nothing to redo", 1500, "info")
            return
        current = self.get_track_table_state_snapshot("Undo state")
        snapshot = self.redo_buffer.pop()
        self.undo_buffer.append(current)
        self.restore_track_table_state_snapshot(snapshot)
        self.show_toast("Redo applied", 1700, "success")

    def get_visible_track_columns(self):
        """Return the currently displayed preview table columns."""
        if not hasattr(self, 'track_table'):
            return []

        display_columns = self.track_table.cget("displaycolumns")
        all_columns = list(self.track_table["columns"])

        if not display_columns or display_columns == "#all":
            return [col for col in all_columns if col != "file_path"]

        if isinstance(display_columns, str):
            columns = self.root.tk.splitlist(display_columns)
        else:
            columns = list(display_columns)

        return [col for col in columns if col in all_columns and col != "file_path"]

    def auto_fit_track_columns(self):
        """Resize visible preview columns to fit their content inside the table."""
        self._auto_fit_columns_job = None
        if self.is_upload_in_progress():
            return
        if not hasattr(self, 'track_table'):
            return

        import tkinter.font as tkfont

        self.root.update_idletasks()

        columns = self.get_visible_track_columns()
        if not columns:
            return

        all_columns = list(self.track_table["columns"])
        default_min_widths = {
            "track_no": 48,
            "artist": 56,
            "track_name": 84,
            "comment": 64,
            "length": 52,
            "extension": 42,
            "price": 42,
            "nyp": 36,
            "year": 44,
            "genre": 54,
            "bitrate": 58,
            "file_size": 62,
            "sample_rate": 66,
            "channels": 52,
            "bit_depth": 56,
            "album_metadata": 68,
            "album_artist_metadata": 78,
            "composer": 66,
            "isrc": 62,
        }
        max_widths = {
            "artist": 180,
            "track_name": 260,
            "comment": 240,
            "genre": 140,
            "album_metadata": 180,
            "album_artist_metadata": 180,
            "composer": 160,
            "isrc": 150,
        }

        style = ttk.Style()
        tree_font_value = style.lookup("Treeview", "font") or "TkDefaultFont"
        heading_font_value = style.lookup("Treeview.Heading", "font") or tree_font_value

        def resolve_font(font_value):
            if isinstance(font_value, str):
                try:
                    return tkfont.nametofont(font_value)
                except tk.TclError:
                    pass
            return tkfont.Font(font=font_value)

        tree_font = resolve_font(tree_font_value)
        heading_font = resolve_font(heading_font_value)

        measured_widths = {}
        for col_id in columns:
            header = self.track_table.heading(col_id, "text") or col_id
            min_width = default_min_widths.get(col_id, 50)
            desired_width = max(min_width, heading_font.measure(str(header)) + 18)

            try:
                value_index = all_columns.index(col_id)
            except ValueError:
                continue

            for item in self.track_table.get_children():
                values = self.track_table.item(item).get("values", ())
                if value_index >= len(values):
                    continue
                desired_width = max(desired_width, tree_font.measure(str(values[value_index])) + 18)

            measured_widths[col_id] = min(desired_width, max_widths.get(col_id, 120))

        available_width = self.track_table.winfo_width()
        if available_width <= 1 and self.track_table.master:
            available_width = self.track_table.master.winfo_width()
        if available_width <= 1:
            self.maybe_auto_fit_track_columns(delay=120)
            return
        available_width = max(available_width - 6, 1)

        total_width = sum(measured_widths.values())
        if total_width < available_width:
            flexible_columns = [
                col for col in columns
                if col in {
                    "artist", "track_name", "comment", "album_metadata",
                    "album_artist_metadata", "composer"
                }
            ]
            if not flexible_columns:
                flexible_columns = columns
            extra = available_width - total_width
            per_column_extra = extra // len(flexible_columns)
            remainder = extra % len(flexible_columns)
            for index, col_id in enumerate(flexible_columns):
                measured_widths[col_id] += per_column_extra + (1 if index < remainder else 0)
        elif total_width > available_width:
            shrinkable_columns = [
                col for col in columns
                if measured_widths[col] > default_min_widths.get(col, 50)
            ]
            overflow = total_width - available_width
            while overflow > 0 and shrinkable_columns:
                shrink_step = max(1, overflow // len(shrinkable_columns))
                next_shrinkable = []
                for col_id in shrinkable_columns:
                    min_width = default_min_widths.get(col_id, 50)
                    shrink_by = min(shrink_step, measured_widths[col_id] - min_width, overflow)
                    measured_widths[col_id] -= shrink_by
                    overflow -= shrink_by
                    if measured_widths[col_id] > min_width:
                        next_shrinkable.append(col_id)
                    if overflow <= 0:
                        break
                shrinkable_columns = next_shrinkable

        for col_id, width in measured_widths.items():
            self.track_table.column(col_id, width=max(1, int(width)), stretch=False)

        self.track_table.column("file_path", width=0, stretch=False)

    def maybe_auto_fit_track_columns(self, delay=60):
        """Auto-fit preview columns when the preference is enabled."""
        if not getattr(self.config, 'auto_fit_columns', True):
            return
        if not hasattr(self, 'root'):
            return
        if self._auto_fit_columns_job is not None:
            try:
                self.root.after_cancel(self._auto_fit_columns_job)
            except tk.TclError:
                pass
        self._auto_fit_columns_job = self.root.after(delay, self.auto_fit_track_columns)

    def on_track_table_configure(self, event=None):
        """Keep preview columns fitted when the table gets its real startup size."""
        self.maybe_auto_fit_track_columns()

    def build_tracklist_description(self, rows):
        """Build a numbered tracklist from the preview table."""
        lines = []
        for index, row in enumerate(rows, 1):
            artist = str(row[1]).strip()
            title = str(row[2]).strip()
            if not title:
                continue
            label = f"{artist} - {title}" if artist else title
            lines.append(f"{index}. {label}")
        return "\n".join(lines)

    def build_track_comments_description(self, rows):
        """Build a description from track comment metadata."""
        lines = []
        for index, row in enumerate(rows, 1):
            title = str(row[2]).strip()
            comment = str(row[3]).strip()
            if not comment:
                continue
            label = f"{index}. {title}" if title else f"Track {index}"
            lines.append(f"{label}: {comment}")
        return "\n".join(lines)

    def build_album_info_description(self, rows):
        """Build a compact album-info description from current fields and track rows."""
        lines = []
        album_name = self.album_name_var.get().strip()
        artist = self.album_artist_var.get().strip()
        release_date = self.album_publish_date_var.get().strip()
        tags = self.album_tags_var.get().strip()

        if album_name:
            lines.append(f"Album: {album_name}")
        if artist:
            lines.append(f"Artist: {artist}")
        if release_date:
            lines.append(f"Release Date: {release_date}")
        if rows:
            lines.append(f"Tracks: {len(rows)}")
        if tags:
            lines.append(f"Tags: {tags}")

        tracklist = self.build_tracklist_description(rows)
        if tracklist:
            if lines:
                lines.append("")
            lines.append("Tracklist:")
            lines.append(tracklist)

        return "\n".join(lines)

    def build_technical_details_description(self, rows):
        """Build a compact technical summary using visible audio metadata."""
        lines = []
        for index, row in enumerate(rows, 1):
            title = str(row[2]).strip() or f"Track {index}"
            fields = []
            for label, value in (
                ("length", row[4] if len(row) > 4 else ""),
                ("format", row[5] if len(row) > 5 else ""),
                ("bitrate", row[10] if len(row) > 10 else ""),
                ("size", row[11] if len(row) > 11 else ""),
            ):
                value = str(value).strip()
                if value:
                    fields.append(f"{label}: {value}")
            suffix = f" ({', '.join(fields)})" if fields else ""
            lines.append(f"{index}. {title}{suffix}")
        return "\n".join(lines)

    def get_album_description_rows(self, album):
        """Build description rows from the final album object used for upload."""
        rows = []
        for index, track in enumerate(getattr(album, 'tracks', []), 1):
            track_path = getattr(track, 'path', None)
            file_size = 0
            extension = ""
            if track_path and track_path.exists():
                file_size = track_path.stat().st_size / (1024 ** 2)
                extension = track_path.suffix

            track_data = getattr(track, 'track_data', None)
            artist = getattr(track_data, 'artist', '') if track_data else ''
            title = getattr(track_data, 'title', '') if track_data else ''
            comment = ""
            if track_data:
                comment = (
                    getattr(track_data, 'download_desc', '')
                    or getattr(track_data, 'about', '')
                    or ""
                )
            if not comment and track_path:
                comment = self.get_track_comment_metadata(track_path)

            length = self.get_audio_length(track_path) if track_path else ""
            year, genre, bitrate = self.get_track_metadata(track_path) if track_path else ("", "", "")
            if file_size > 1024:
                size_str = f"{file_size / 1024:.1f} GB"
            elif file_size:
                size_str = f"{file_size:.1f} MB"
            else:
                size_str = ""

            extra_metadata = self.get_extra_track_metadata_columns(track_path) if track_path else ("", "", "", "", "", "", "")
            rows.append([
                index,
                artist,
                title,
                comment,
                length,
                extension,
                f"${track_data.price}" if track_data and getattr(track_data, 'price', '') else "",
                "Yes" if track_data and getattr(track_data, 'nyp', 0) else "No",
                year,
                genre,
                bitrate,
                size_str,
                track_path or "",
                *extra_metadata,
            ])
        return rows

    DEFAULT_DESCRIPTION_TEMPLATES = DESCRIPTION_TEMPLATES

    def render_description_template(self, mode, rows):
        """Render a template string with track and album data."""
        templates = getattr(self.config, 'description_templates', {})
        template = templates.get(mode) or self.DEFAULT_DESCRIPTION_TEMPLATES.get(mode)
        if not template:
            return None

        if mode in ("Album Info", "Release Notes", "Bandcamp Classic", "Metadata Dump"):
            album_data = {
                "album": self.album_name_var.get().strip(),
                "artist": self.album_artist_var.get().strip(),
                "date": self.album_publish_date_var.get().strip(),
                "tags": self.album_tags_var.get().strip(),
                "tracks": str(len(rows)),
            }
            tracklist = self.build_tracklist_description(rows)
            album_data["tracklist"] = tracklist
            album_data["album_info"] = self.build_album_info_description(rows)
            album_data["track_comments"] = self.build_track_comments_description(rows)
            album_data["technical_details"] = self.build_technical_details_description(rows)
            result = template.format(**album_data)
            lines = [line for line in result.split("\n") if line.strip()]
            return "\n".join(lines)

        lines = []
        for index, row in enumerate(rows, 1):
            data = {
                "n": str(index),
                "artist": str(row[1]).strip(),
                "title": str(row[2]).strip(),
                "comment": str(row[3]).strip() if len(row) > 3 else "",
                "length": str(row[4]).strip() if len(row) > 4 else "",
                "format": str(row[5]).strip() if len(row) > 5 else "",
                "price": str(row[6]).strip() if len(row) > 6 else "",
                "year": str(row[8]).strip() if len(row) > 8 else "",
                "genre": str(row[9]).strip() if len(row) > 9 else "",
                "bitrate": str(row[10]).strip() if len(row) > 10 else "",
                "size": str(row[11]).strip() if len(row) > 11 else "",
            }
            lines.append(template.format(**data))
        return "\n".join(lines)

    def build_auto_description_from_mode(self, rows=None):
        """Build the configured automatic album description without touching widgets."""
        mode = getattr(self.config, 'description_auto_fill_mode', "Off")
        if mode == "Off":
            return ""

        if rows is None:
            rows = self.get_track_table_rows()

        return self.render_description_template(mode, rows) or ""

    def prepare_upload_description_from_template(self, rows=None, current_description=None, update_widget=True):
        """Apply the selected description template at Upload Album click time."""
        if rows is None:
            self.sync_track_table_to_current_album()
            rows = self.get_track_table_rows()

        upload_description = (
            current_description
            if current_description is not None
            else self.get_album_description_text()
        ).strip()
        if not getattr(self.config, 'description_auto_fill_on_upload', True):
            return upload_description

        generated_description = self.build_auto_description_from_mode(rows).strip()
        mode = getattr(self.config, 'description_auto_fill_mode', "Off")
        if not generated_description and mode == "Off":
            generated_description = self.build_tracklist_description(rows).strip()

        if generated_description:
            if upload_description and generated_description not in upload_description:
                upload_description = f"{upload_description}\n\n{generated_description}"
            else:
                upload_description = generated_description
            if update_widget:
                self.root.after(0, lambda text=upload_description: self.set_album_description_text(text))
            logger.info(f"Generated upload description from template '{mode}' ({len(upload_description)} characters)")
        else:
            logger.warning(f"Description template '{mode}' produced no upload description")

        return upload_description

    def browse_album(self):
        """Browse for album directory"""
        if self.is_upload_in_progress():
            self.show_toast("Upload in progress", 1600, "warning")
            return

        directory = filedialog.askdirectory(title="Select Album Folder")
        if directory:
            self.album_path_var.set(directory)
            self.upload_btn['state'] = tk.NORMAL if self.selected_artist_url else tk.DISABLED
            self.on_album_selection_changed()
            self.clear_album_load_fields()

            self.preview_album()

            # Auto-detect cover art
            self.auto_detect_cover_art(directory)
            self.auto_extract_cover_art_if_missing(directory)

            self.apply_album_load_preferences(directory)
            self.load_or_create_album_session_file(directory)

            # Add to recent albums
            self.add_to_recent_albums(directory)
            
            # Auto-start upload if enabled
            if self.config.auto_start_upload and self.selected_artist_url:
                self.root.after(500, self.start_upload)

    def reload_album(self):
        """Reload the currently selected album folder."""
        if self.is_upload_in_progress():
            self.show_toast("Upload in progress", 1600, "warning")
            return

        album_path = self.album_path_var.get()
        if not album_path:
            messagebox.showwarning("No Album Folder", "Please select an album folder first")
            return

        path = Path(album_path)
        if not path.is_dir():
            messagebox.showerror("Invalid Album Folder", f"Folder does not exist:\n{album_path}")
            return

        session_paths = [
            session_path
            for session_path in (
                self.get_album_session_file_path(path),
                self.get_legacy_album_session_file_path(path),
            )
            if session_path and session_path.exists()
        ]
        if session_paths:
            if not messagebox.askyesno(
                "Reload Fresh Album",
                "Reloading the album will delete the saved session.txt for this folder and rebuild the preview from the audio files.\n\nContinue?"
            ):
                return
            for session_path in session_paths:
                try:
                    session_path.unlink()
                    logger.info(f"Deleted album session file for fresh reload: {session_path}")
                except Exception as e:
                    messagebox.showerror("Reload Failed", f"Could not delete:\n{session_path}\n\n{e}")
                    return

        self.on_album_selection_changed()
        self.clear_album_load_fields()
        self.preview_album()
        self.auto_detect_cover_art(path)
        self.auto_extract_cover_art_if_missing(path)
        self.apply_album_load_preferences(path)
        self.load_or_create_album_session_file(path)
        self.add_to_recent_albums(str(path))
        self.upload_btn['state'] = tk.NORMAL if self.selected_artist_url else tk.DISABLED
        self.show_toast("Album reloaded", 1800, "success", trigger="file_add")
    
    def open_album_folder(self):
        """Open album folder in file explorer"""
        if self.is_upload_in_progress():
            self.show_toast("Upload in progress", 1600, "warning")
            return

        path = self.album_path_var.get()
        if not path:
            messagebox.showwarning("No Folder", "Please select an album folder first")
            return
        
        if not Path(path).exists():
            messagebox.showerror("Folder Not Found", f"Folder does not exist:\n{path}")
            return
        
        import os
        
        folder = Path(path).resolve()
        try:
            if os.name == 'nt':  # Windows
                os.startfile(str(folder))
            elif sys.platform == "darwin":
                subprocess.Popen(['open', str(folder)])
            else:
                subprocess.Popen(['xdg-open', str(folder)])
        except Exception as e:
            logger.exception(e)
            messagebox.showerror("Open Folder Failed", f"Could not open folder:\n{folder}\n\n{e}")
            return
        
        self.show_toast("Folder opened", 1500, "success", trigger="file_add")
    
    def copy_album_path(self):
        """Copy album path to clipboard"""
        path = self.album_path_var.get()
        if not path:
            messagebox.showwarning("No Path", "Please select an album folder first")
            return
        
        self.root.clipboard_clear()
        self.root.clipboard_append(path)
    
    def auto_fill_album_name(self):
        """Auto-fill album name from folder name"""
        path = self.album_path_var.get()
        if not path:
            messagebox.showwarning("No Folder", "Please select an album folder first")
            return

        folder_name = Path(path).name
        self.album_name_var.set(folder_name)
    
    def auto_fill_artist_name(self):
        """Auto-fill artist name from track metadata"""
        path = self.album_path_var.get()
        from pathlib import Path

        audio_files = []

        if path:
            album_path = Path(path)
            if not album_path.exists():
                messagebox.showwarning("Invalid Path", "The selected folder does not exist")
                return

            audio_extensions = ['.flac', '.mp3', '.wav', '.aiff', '.aif', '.ogg', '.opus', '.m4a', '.aac', '.mod', '.xm']
            for ext in audio_extensions:
                audio_files.extend(album_path.glob(f'*{ext}'))
                audio_files.extend(album_path.glob(f'*{ext.upper()}'))
        elif self.manual_tracks:
            audio_files = self.manual_tracks
        else:
            messagebox.showwarning("No Folder", "Please select an album folder or add tracks first")
            return

        if not audio_files:
            messagebox.showwarning("No Audio Files", "No audio files found")
            return

        try:
            from mutagen import File
            audio_file = File(audio_files[0])
            if audio_file:
                artist = None
                if getattr(self.config, 'use_album_artist_in_album_details', False):
                    if hasattr(audio_file, 'albumartist'):
                        artist = audio_file.albumartist
                    elif 'TPE2' in audio_file:
                        artist = audio_file['TPE2'][0]
                    elif 'ALBUMARTIST' in audio_file:
                        artist = audio_file['ALBUMARTIST'][0]
                    elif 'aART' in audio_file:
                        artist = audio_file['aART'][0]
                if not artist:
                    if hasattr(audio_file, 'artist'):
                        artist = audio_file.artist
                    elif 'TPE1' in audio_file:
                        artist = audio_file['TPE1'][0]
                    elif 'ARTIST' in audio_file:
                        artist = audio_file['ARTIST'][0]
                    elif '\xa9ART' in audio_file:
                        artist = audio_file['\xa9ART'][0]

                if artist:
                    self.album_artist_var.set(artist)
                else:
                    messagebox.showinfo("No Artist", "No artist tag found in the audio file")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to read metadata: {str(e)}")

    def show_release_date_calendar(self):
        """Show calendar dialog to select release date"""
        from datetime import datetime
        import calendar

        # Create a simple calendar dialog
        dialog = tk.Toplevel(self.root)
        dialog.title("Select Release Date")
        dialog.geometry("350x340")
        dialog.resizable(True, True)
        dialog.transient(self.root)
        dialog.grab_set()

        # Center dialog
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (350 // 2)
        y = (dialog.winfo_screenheight() // 2) - (340 // 2)
        dialog.geometry(f"+{x}+{y}")

        # Calendar frame
        cal_frame = ttk.Frame(dialog, padding=10)
        cal_frame.pack(fill=tk.BOTH, expand=True)

        # Month/Year selector
        month_year_frame = ttk.Frame(cal_frame)
        month_year_frame.pack(fill=tk.X, pady=(0, 8))

        current_date = datetime.now()
        self.cal_year = current_date.year
        self.cal_month = current_date.month

        # Year row
        year_frame = ttk.Frame(month_year_frame)
        year_frame.pack(fill=tk.X, pady=(0, 5))

        year_label = ttk.Label(year_frame, text="Year:", font=("Segoe UI", 9))
        year_label.pack(side=tk.LEFT, padx=(0, 3))

        years = list(range(1900, 2101))
        self.cal_year_combo = ttk.Combobox(year_frame, values=years, width=8, font=("Segoe UI", 9), state="readonly")
        self.cal_year_combo.set(str(self.cal_year))
        self.cal_year_combo.pack(side=tk.LEFT, padx=(0, 5))
        self.cal_year_combo.bind("<<ComboboxSelected>>", lambda e: self.on_year_selected())

        ttk.Button(year_frame, text="<", command=lambda: self.adjust_calendar(-1, 0), width=4).pack(side=tk.LEFT)
        ttk.Button(year_frame, text=">", command=lambda: self.adjust_calendar(1, 0), width=4).pack(side=tk.LEFT)

        # Month row
        month_frame = ttk.Frame(month_year_frame)
        month_frame.pack(fill=tk.X)

        month_label = ttk.Label(month_frame, text="Month:", font=("Segoe UI", 9))
        month_label.pack(side=tk.LEFT, padx=(0, 3))

        month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                       "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        self.cal_month_combo = ttk.Combobox(month_frame, values=month_names, width=6, font=("Segoe UI", 9), state="readonly")
        self.cal_month_combo.set(month_names[self.cal_month - 1])
        self.cal_month_combo.pack(side=tk.LEFT, padx=(0, 5))
        self.cal_month_combo.bind("<<ComboboxSelected>>", lambda e: self.on_month_selected())

        ttk.Button(month_frame, text="<", command=lambda: self.adjust_calendar(0, -1), width=4).pack(side=tk.LEFT)
        ttk.Button(month_frame, text=">", command=lambda: self.adjust_calendar(0, 1), width=4).pack(side=tk.LEFT)

        # Calendar grid
        self.cal_grid = ttk.Frame(cal_frame)
        self.cal_grid.pack(fill=tk.BOTH, expand=True)

        # Configure grid columns to expand equally
        for i in range(7):
            self.cal_grid.columnconfigure(i, weight=1)

        # Configure grid rows to expand equally
        for i in range(7):
            self.cal_grid.rowconfigure(i, weight=1)

        self.render_calendar()

        # Buttons
        button_frame = ttk.Frame(cal_frame)
        button_frame.pack(fill=tk.X, pady=(8, 0))

        ttk.Button(button_frame, text="Today", command=self.select_today, width=8).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(button_frame, text="Cancel", command=dialog.destroy, width=8).pack(side=tk.RIGHT)

        # Store dialog reference
        self.cal_dialog = dialog

    def on_year_selected(self):
        """Handle year selection from dropdown"""
        selected_year = int(self.cal_year_combo.get())
        self.cal_year = selected_year
        self.render_calendar()

    def on_month_selected(self):
        """Handle month selection from dropdown"""
        month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                       "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        selected_month_name = self.cal_month_combo.get()
        self.cal_month = month_names.index(selected_month_name) + 1
        self.render_calendar()

    def adjust_calendar(self, year_delta, month_delta):
        """Adjust calendar month/year"""
        self.cal_year += year_delta
        self.cal_month += month_delta

        # Handle month overflow
        if self.cal_month > 12:
            self.cal_month = 1
            self.cal_year += 1
        elif self.cal_month < 1:
            self.cal_month = 12
            self.cal_year -= 1

        self.render_calendar()

    def render_calendar(self):
        """Render calendar grid for current month/year"""
        # Clear existing widgets
        for widget in self.cal_grid.winfo_children():
            widget.destroy()

        import calendar

        # Get calendar data
        cal = calendar.monthcalendar(self.cal_year, self.cal_month)

        # Month names for dropdown
        month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                       "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

        # Update month dropdown
        if hasattr(self, 'cal_month_combo'):
            self.cal_month_combo.set(month_names[self.cal_month - 1])

        # Update year dropdown
        if hasattr(self, 'cal_year_combo'):
            self.cal_year_combo.set(str(self.cal_year))

        # Add day headers
        days = ["Su", "Mo", "Tu", "We", "Th", "Fr", "Sa"]
        for col, day in enumerate(days):
            ttk.Label(self.cal_grid, text=day, font=("Segoe UI", 8, "bold")).grid(row=0, column=col, sticky="nsew", padx=1, pady=1)

        # Add day buttons using grid layout (starting at row 1, after headers)
        for row, week in enumerate(cal):
            for col, day in enumerate(week):
                if day == 0:
                    blank = ttk.Label(self.cal_grid, text="")
                    blank.grid(row=row+1, column=col, sticky="nsew", padx=1, pady=1)
                else:
                    date_str = f"{self.cal_year:04d}-{self.cal_month:02d}-{day:02d}"
                    btn = ttk.Button(
                        self.cal_grid,
                        text=str(day),
                        command=lambda d=date_str: self.select_date(d)
                    )
                    btn.grid(row=row+1, column=col, sticky="nsew", padx=1, pady=1)

    def select_date(self, date_str):
        """Select a date from calendar"""
        self.album_publish_date_var.set(date_str)
        self.cal_dialog.destroy()

    def select_today(self):
        """Select today's date"""
        from datetime import datetime
        today = datetime.now().strftime("%Y-%m-%d")
        self.album_publish_date_var.set(today)
        self.cal_dialog.destroy()

    def clear_all_fields(self):
        """Clear all input fields with warning dialog"""
        result = messagebox.askyesno(
            "Clear All Fields",
            "Clear all input fields?\n\nThis will reset album details, tags, description, and other metadata."
        )
        
        if result:
            self.album_name_var.set("")
            self.album_artist_var.set("")
            self.album_tags_var.set("")
            if hasattr(self, 'tag_entry'):
                self.tag_entry.delete(0, tk.END)
            self.album_description_var.set("")
            self.album_credits_var.set("")
            self.desc_text.delete("1.0", "end")
            self.credits_text.delete("1.0", "end")
            self.cover_path_var.set("")
            self.album_publish_date_var.set("")
            self.album_record_label_var.set("")
            self.album_catalog_number_var.set("")
            self.album_upc_var.set("")
            self.album_download_desc_var.set("")
            self.album_release_message_var.set("")
            self.album_license_var.set("All Rights Reserved")
    
    def paste_album_path(self):
        """Paste path from clipboard"""
        if self.is_upload_in_progress():
            self.show_toast("Upload in progress", 1600, "warning")
            return

        try:
            path = self.root.clipboard_get()
            if path and Path(path).exists():
                self.album_path_var.set(path)
                self.on_album_selection_changed()
                self.clear_album_load_fields()
                self.preview_album()

                # Auto-detect cover art
                self.auto_detect_cover_art(path)
                self.auto_extract_cover_art_if_missing(path)
                self.apply_album_load_preferences(path)
                self.load_or_create_album_session_file(path)
            else:
                messagebox.showwarning("Invalid Path", "Clipboard does not contain a valid folder path")
        except:
            messagebox.showwarning("Paste Error", "Could not paste from clipboard")
    
    def show_album_context_menu(self, event):
        """Show context menu for album entry"""
        if self.is_upload_in_progress():
            return

        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(label="Browse...", command=self.browse_album)
        menu.add_command(label="Paste Path", command=self.paste_album_path)
        menu.add_separator()
        menu.add_command(label="Open Folder", command=self.open_album_folder)
        menu.add_command(label="Copy Path", command=self.copy_album_path)
        menu.add_separator()
        menu.add_command(label="Clear", command=lambda: self.album_path_var.set(""))
        menu.add_command(label="Clear All", command=self.clear_all_fields)
        
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
    
    def add_to_recent_albums(self, path):
        """Add album path to recent list"""
        if not hasattr(self.config, 'recent_albums'):
            self.config.recent_albums = []
        
        # Remove if already exists
        if path in self.config.recent_albums:
            self.config.recent_albums.remove(path)
        
        # Add to front
        self.config.recent_albums.insert(0, path)
        
        # Keep only 10 most recent
        self.config.recent_albums = self.config.recent_albums[:10]
        
        # Save config
        try:
            save_config(self.config)
        except:
            pass  # Non-critical if save fails

    def get_track_table_column_labels(self):
        """Return user-facing labels for track table columns."""
        return {
            "track_no": "Track No.",
            "artist": "Artist",
            "track_name": "Track Name",
            "comment": "Comment",
            "length": "Length",
            "extension": "Extension",
            "price": "Price",
            "nyp": "NYP",
            "year": "Year",
            "genre": "Genre",
            "bitrate": "Bitrate",
            "file_size": "File Size",
            "file_path": "File Path",
            "sample_rate": "Sample Rate",
            "channels": "Channels",
            "bit_depth": "Bit Depth",
            "album_metadata": "Album",
            "album_artist_metadata": "Album Artist",
            "composer": "Composer",
            "isrc": "ISRC",
        }

    def configure_track_table_tags(self):
        """Configure row tags for the track preview table."""
        if not hasattr(self, 'track_table'):
            return

        self.track_table.tag_configure("normal", font=("Consolas", 8))
        self.track_table.tag_configure("locked", background=getattr(self.config, 'locked_track_highlight_color', '#fff4ce'))
        self.track_table.tag_configure("drag_target", background="#e8f4fd")

    def apply_track_item_tags(self, item_id, *extra_tags):
        """Restore row tags while preserving locked-row highlighting."""
        if not self.track_table.exists(item_id):
            return
        tags = ["normal"]
        if self.is_track_item_locked(item_id):
            tags.append("locked")
        tags.extend(tag for tag in extra_tags if tag not in tags)
        self.track_table.item(item_id, tags=tuple(tags))

    def get_track_table_editable_columns(self):
        """Columns that can be edited one cell at a time or in bulk."""
        return {
            "artist",
            "track_name",
            "comment",
            "price",
            "nyp",
            "album_metadata",
            "album_artist_metadata",
            "composer",
            "isrc",
        }

    def get_track_table_column_index(self, column_id):
        """Return the value index for a track table column id."""
        try:
            return list(self.track_table["columns"]).index(column_id)
        except ValueError:
            return None

    def get_track_table_column_id_from_event_column(self, event_column):
        """Map a Treeview event column like #2 to the underlying column id."""
        if not event_column or not str(event_column).startswith("#"):
            return None

        try:
            display_index = int(str(event_column).replace("#", "")) - 1
        except ValueError:
            return None

        all_columns = list(self.track_table["columns"])
        display_columns = self.track_table.cget("displaycolumns")
        if not display_columns or display_columns == "#all":
            visible_columns = all_columns
        elif isinstance(display_columns, str):
            visible_columns = list(self.root.tk.splitlist(display_columns))
        else:
            visible_columns = list(display_columns)

        if 0 <= display_index < len(visible_columns):
            return visible_columns[display_index]
        return None

    def configure_track_table_heading_commands(self):
        """Let editable column headers batch-update that whole column."""
        labels = self.get_track_table_column_labels()
        editable_columns = self.get_track_table_editable_columns()
        for column_id in self.track_table["columns"]:
            if column_id in editable_columns:
                self.track_table.heading(
                    column_id,
                    text=labels.get(column_id, column_id),
                    command=lambda col=column_id: self.batch_edit_track_column(col)
                )

    def ask_text_value(self, title, prompt, initialvalue=""):
        """Ask for a text value using ttk controls instead of classic Tk buttons."""
        dialog = tk.Toplevel(self.root)
        dialog.title(title)
        dialog.transient(self.root)
        dialog.resizable(False, False)

        result = {"value": None}

        frame = ttk.Frame(dialog, padding=12)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text=prompt).pack(anchor=tk.W, pady=(0, 6))
        value_var = tk.StringVar(value=initialvalue)
        entry = ttk.Entry(frame, textvariable=value_var, width=42)
        entry.pack(fill=tk.X, pady=(0, 10))

        button_frame = ttk.Frame(frame)
        button_frame.pack(fill=tk.X)

        def accept(_event=None):
            result["value"] = value_var.get()
            dialog.destroy()

        def cancel(_event=None):
            dialog.destroy()

        ttk.Button(button_frame, text="OK", command=accept).pack(side=tk.RIGHT, padx=(6, 0))
        ttk.Button(button_frame, text="Cancel", command=cancel).pack(side=tk.RIGHT)

        dialog.bind("<Return>", accept)
        dialog.bind("<Escape>", cancel)
        dialog.protocol("WM_DELETE_WINDOW", cancel)

        dialog.update_idletasks()
        x = self.root.winfo_rootx() + (self.root.winfo_width() // 2) - (dialog.winfo_width() // 2)
        y = self.root.winfo_rooty() + (self.root.winfo_height() // 2) - (dialog.winfo_height() // 2)
        dialog.geometry(f"+{max(0, x)}+{max(0, y)}")

        entry.focus_set()
        entry.select_range(0, tk.END)
        dialog.grab_set()
        self.root.wait_window(dialog)
        return result["value"]

    def batch_edit_track_column(self, column_id):
        """Prompt for a value and apply it to every row in the chosen column."""
        if self.is_upload_in_progress():
            self.show_toast("Upload in progress", 1600, "warning")
            return

        if column_id not in self.get_track_table_editable_columns():
            return

        rows = self.track_table.get_children()
        if not rows:
            return

        column_index = self.get_track_table_column_index(column_id)
        if column_index is None:
            return

        label = self.get_track_table_column_labels().get(column_id, column_id)
        existing_values = []
        for row_id in rows:
            values = list(self.track_table.item(row_id).get("values", ()))
            existing_values.append(str(values[column_index]) if column_index < len(values) else "")
        first_value = existing_values[0] if existing_values and all(value == existing_values[0] for value in existing_values) else ""

        new_value = self.ask_text_value(
            f"Update {label}",
            f"Set {label} for all tracks:",
            initialvalue=first_value
        )
        if new_value is None:
            return

        self.push_undo_state(f"Update {label}")
        changed = 0
        for row_id in rows:
            if self.is_track_item_locked(row_id):
                continue
            values = list(self.track_table.item(row_id).get("values", ()))
            if column_index >= len(values):
                continue
            values[column_index] = new_value.strip()
            self.track_table.item(row_id, values=tuple(values))
            changed += 1

        self.maybe_auto_fit_track_columns()
        self.sync_track_table_to_current_album()
        self.show_toast(f"Updated {label} for {changed} track(s)", 1800, "success")

    def on_table_double_click(self, event):
        """Handle double-click on table cell to edit"""
        # Get the item and column that was clicked
        item = self.track_table.identify('item', event.x, event.y)
        column = self.track_table.identify('column', event.x, event.y)

        if not item or not column:
            return
        if self.is_track_item_locked(item):
            self.show_toast("Track is locked", 1600, "warning")
            return

        column_id = self.get_track_table_column_id_from_event_column(column)
        col_index = self.get_track_table_column_index(column_id)

        if column_id not in self.get_track_table_editable_columns() or col_index is None:
            return

        # Get current value
        current_values = self.track_table.item(item)['values']
        current_value = current_values[col_index]

        # Get cell coordinates
        x, y, width, height = self.track_table.bbox(item, column)

        # Create entry widget for editing
        edit_var = tk.StringVar(value=current_value)
        entry = ttk.Entry(self.track_table, textvariable=edit_var, font=("Consolas", 8))
        entry.place(x=x, y=y, width=width, height=height)
        entry.focus_set()
        entry.select_range(0, tk.END)

        # Store original value for cancel
        original_value = current_value

        def save_edit(event=None):
            new_value = edit_var.get().strip()
            if new_value != original_value:
                self.push_undo_state(f"Edit {self.get_track_table_column_labels().get(column_id, column_id)}")
                # Update the value in the table
                new_values = list(current_values)
                new_values[col_index] = new_value
                self.track_table.item(item, values=tuple(new_values))
                self.maybe_auto_fit_track_columns()
                self.sync_track_table_to_current_album()
            entry.destroy()

        def cancel_edit(event=None):
            entry.destroy()

        entry.bind('<Return>', save_edit)
        entry.bind('<Escape>', cancel_edit)
        entry.bind('<FocusOut>', lambda e: save_edit())

    def on_drag_start(self, event):
        """Start drag operation for track reordering"""
        item = self.track_table.identify('item', event.x, event.y)
        if item:
            if self.is_track_item_locked(item):
                self.drag_data = {"item": None, "y": 0, "x": 0, "started": False, "highlight": None}
                return
            self.drag_data = {"item": item, "y": event.y, "x": event.x, "started": False, "highlight": None}

    def on_drag_motion(self, event):
        """Handle drag motion - show visual feedback"""
        if self.drag_data["item"] and not self.drag_data["started"]:
            # Check if moved more than 5 pixels
            if abs(event.y - self.drag_data["y"]) > 5 or abs(event.x - self.drag_data["x"]) > 5:
                self.drag_data["started"] = True

        if self.drag_data["started"]:
            # Clear previous highlight
            if self.drag_data["highlight"]:
                self.apply_track_item_tags(self.drag_data["highlight"])
                self.drag_data["highlight"] = None

            # Find item under cursor
            target_item = self.track_table.identify('item', event.x, event.y)
            if target_item and target_item != self.drag_data["item"] and not self.is_track_item_locked(target_item):
                # Highlight the target row
                self.apply_track_item_tags(target_item, "drag_target")
                self.drag_data["highlight"] = target_item

    def on_drag_release(self, event):
        """Handle drag release - reorder tracks"""
        # Clear highlight
        if self.drag_data.get("highlight"):
            self.apply_track_item_tags(self.drag_data["highlight"])

        if not self.drag_data.get("item") or not self.drag_data.get("started"):
            self.drag_data = {"item": None, "y": 0, "x": 0, "started": False, "highlight": None}
            return

        source_item = self.drag_data["item"]
        target_item = self.track_table.identify('item', event.x, event.y)

        if target_item and source_item != target_item:
            if self.is_track_item_locked(target_item):
                self.show_toast("Cannot move onto a locked track", 1600, "warning")
                self.drag_data = {"item": None, "y": 0, "x": 0, "started": False, "highlight": None}
                return

            self.push_undo_state("Reorder Tracks")
            # Get all items
            all_items = self.track_table.get_children()
            source_idx = all_items.index(source_item)
            target_idx = all_items.index(target_item)

            # Get values
            source_values = self.track_table.item(source_item)['values']

            # Remove source
            self.track_table.delete(source_item)

            # Re-get all items after deletion (indices shift)
            all_items = self.track_table.get_children()

            # Insert at target position (adjust index if source was before target)
            if source_idx < target_idx:
                insert_idx = target_idx - 1  # Items shifted up
            else:
                insert_idx = target_idx

            # Insert at the correct position
            if insert_idx >= len(all_items):
                self.insert_track_row(source_values)
            else:
                target_parent = self.track_table.parent(all_items[insert_idx]) if all_items else ""
                self.insert_track_row(source_values, insert_idx)

            # Renumber tracks
            self.renumber_tracks()
            self.sync_track_table_to_current_album()

        # Reset drag data
        self.drag_data = {"item": None, "y": 0, "x": 0, "started": False, "highlight": None}

    def renumber_tracks(self):
        """Renumber tracks after reordering"""
        for idx, item in enumerate(self.track_table.get_children(), 1):
            values = list(self.track_table.item(item)['values'])
            values[0] = idx  # Update track number
            self.track_table.item(item, values=tuple(values))

    def guess_track_title_case(self, title: str) -> str:
        """Guess MusicBrainz-style title case for a track title."""
        import re

        small_words = {
            "a", "an", "and", "as", "at", "but", "by", "for", "from", "in",
            "into", "nor", "of", "on", "onto", "or", "over", "per", "so",
            "the", "to", "up", "via", "vs", "with", "yet"
        }
        preserve_upper = {
            "AI", "CD", "DJ", "EP", "LP", "MC", "TV", "UK", "US", "USA",
            "USB", "VIP", "VR", "III", "IV", "VI", "VII", "VIII", "IX", "XI",
            "XII", "XIII", "XIV", "XV", "XVI", "XVII", "XVIII", "XIX", "XX"
        }

        cleaned = re.sub(r"[_\s]+", " ", str(title).strip())
        if not cleaned:
            return ""

        word_indexes = [i for i, token in enumerate(re.findall(r"[A-Za-z0-9]+(?:'[A-Za-z0-9]+)?|[^A-Za-z0-9]+", cleaned)) if re.match(r"[A-Za-z0-9]", token)]
        if not word_indexes:
            return cleaned
        first_word = word_indexes[0]
        last_word = word_indexes[-1]
        tokens = re.findall(r"[A-Za-z0-9]+(?:'[A-Za-z0-9]+)?|[^A-Za-z0-9]+", cleaned)

        def format_word(word, token_index):
            upper_word = word.upper()
            lower_word = word.lower()

            if upper_word in preserve_upper:
                return upper_word
            if token_index not in (first_word, last_word) and lower_word in small_words:
                return lower_word

            parts = lower_word.split("'")
            cased = "'".join(part[:1].upper() + part[1:] if part else part for part in parts)
            cased = re.sub(r"'(M|S|T|Re|Ve|Ll|D)\b", lambda m: "'" + m.group(1).lower(), cased)
            cased = re.sub(r"\bMc([a-z])", lambda m: "Mc" + m.group(1).upper(), cased)
            return cased

        result = []
        force_cap_next = True
        for index, token in enumerate(tokens):
            if re.match(r"[A-Za-z0-9]", token):
                if force_cap_next:
                    result.append(format_word(token, first_word if token.lower() in small_words else index))
                else:
                    result.append(format_word(token, index))
                force_cap_next = False
            else:
                result.append(token)
                if any(mark in token for mark in (":", "?", "!", ".", "-", "(", "[", "{", "/", "\\")):
                    force_cap_next = True

        return "".join(result)

    def preview_guess_case_track_titles(self, event=None):
        """Temporarily preview guessed title casing in the track table."""
        if self.is_upload_in_progress():
            return
        if self.guess_case_preview_values is not None:
            return

        items = list(self.track_table.get_children())
        if not items:
            return

        self.guess_case_preview_values = {
            item: tuple(self.track_table.item(item)['values'])
            for item in items
        }
        self.apply_guess_case_to_track_titles(preview=True)

    def restore_guess_case_track_titles(self, event=None):
        """Restore track titles after hover preview."""
        if self.guess_case_preview_values is None:
            return

        for item, values in self.guess_case_preview_values.items():
            if self.track_table.exists(item):
                self.track_table.item(item, values=values)
        self.guess_case_preview_values = None

    def apply_guess_case_to_track_titles(self, preview=False, show_feedback=True):
        """Apply guessed title casing to all visible track titles."""
        if self.is_upload_in_progress():
            return
        items = list(self.track_table.get_children())
        if not items:
            if show_feedback:
                self.show_toast("No tracks to update", 2000, "warning")
            return

        preview_values = self.guess_case_preview_values
        changed = 0
        for item in items:
            values = list(self.track_table.item(item)['values'])
            if len(values) < 3:
                continue

            old_title = str(values[2])
            new_title = self.guess_track_title_case(old_title)
            if new_title and new_title != old_title:
                values[2] = new_title
                self.track_table.item(item, values=tuple(values))
                changed += 1

        if not preview:
            if preview_values:
                changed = sum(
                    1
                    for item, original_values in preview_values.items()
                    if self.track_table.exists(item)
                    and len(original_values) > 2
                    and len(self.track_table.item(item)['values']) > 2
                    and self.track_table.item(item)['values'][2] != original_values[2]
                )
            self.guess_case_preview_values = None
            self.sync_track_table_to_current_album()
            if changed and show_feedback:
                self.show_toast(f"Guess Case applied to {changed} track title(s)", 2000, "success")
            elif show_feedback:
                self.show_toast("Track titles already look good", 2000, "info")

    FILENAME_PATTERNS = [
        (r"^(\d+)\s*[.\-)_\s]+\s*(.+?)\s*-\s*(.+)", 1, 2, 3),
        (r"^Track\s*(\d+)\s*[.\-)_\s]+\s*(.+?)\s*-\s*(.+)", 1, 2, 3),
        (r"^(\d+)\s*[.\-)_\s]+\s*(.+)", 1, None, 2),
        (r"^Track\s*(\d+)\s*[.\-)_\s]+\s*(.+)", 1, None, 2),
        (r"^(\d+)\s*(.+)", 1, None, 2),
        (r"^(.+?)\s*-\s*(.+)", None, 1, 2),
    ]

    def get_filename_patterns(self):
        patterns = []
        custom = getattr(self.config, 'filename_track_patterns', [])
        for entry in custom:
            if isinstance(entry, str):
                patterns.append((entry, None, None, 1))
            elif isinstance(entry, (list, tuple)) and len(entry) >= 4:
                patterns.append(tuple(entry[:4]))
            elif isinstance(entry, (list, tuple)) and len(entry) == 3:
                patterns.append(tuple(entry) + (None,))
        patterns.extend(self.FILENAME_PATTERNS)
        return patterns

    def preview_extract_from_filename(self, event=None):
        if self.is_upload_in_progress():
            return
        if self.extract_filename_preview_values is not None:
            return
        items = list(self.track_table.get_children())
        if not items:
            return
        self.extract_filename_preview_values = {
            item: tuple(self.track_table.item(item)['values'])
            for item in items
        }
        self.apply_extract_from_filename(preview=True)

    def restore_extract_from_filename(self, event=None):
        if self.extract_filename_preview_values is None:
            return
        for item, values in self.extract_filename_preview_values.items():
            if self.track_table.exists(item):
                self.track_table.item(item, values=values)
        self.extract_filename_preview_values = None

    def apply_extract_from_filename(self, preview=False, show_feedback=True):
        if self.is_upload_in_progress():
            return
        items = list(self.track_table.get_children())
        if not items:
            if show_feedback:
                self.show_toast("No tracks to update", 2000, "warning")
            return

        preview_values = self.extract_filename_preview_values
        changed = 0
        track_no_idx = self.get_track_table_column_index("track_no")
        artist_idx = self.get_track_table_column_index("artist")
        track_name_idx = self.get_track_table_column_index("track_name")
        file_path_idx = self.get_track_table_column_index("file_path")

        for item in items:
            values = list(self.track_table.item(item)['values'])
            if len(values) <= max(track_no_idx, track_name_idx, artist_idx, file_path_idx):
                continue

            if not str(values[file_path_idx]).strip():
                continue

            old_no = str(values[track_no_idx])
            old_artist = str(values[artist_idx])
            old_title = str(values[track_name_idx])
            stem = Path(str(values[file_path_idx])).stem

            parsed_no, parsed_artist, parsed_title = self.parse_track_from_filename(stem)
            if parsed_no is not None:
                values[track_no_idx] = str(parsed_no)
            if parsed_artist:
                values[artist_idx] = parsed_artist
            if parsed_title:
                values[track_name_idx] = parsed_title
            was_no = old_no != str(values[track_no_idx])
            was_artist = old_artist != str(values[artist_idx])
            was_title = old_title != str(values[track_name_idx])
            if was_no or was_artist or was_title:
                changed += 1

            self.track_table.item(item, values=tuple(values))

        if not preview:
            self.extract_filename_preview_values = None
            self.sync_track_table_to_current_album()
            if changed and show_feedback:
                self.show_toast(f"Extracted from {changed} filename(s)", 2000, "success")
            elif show_feedback:
                self.show_toast("No changes needed", 2000, "info")

    def parse_track_from_filename(self, stem):
        import re
        for entry in self.get_filename_patterns():
            pattern, track_group, artist_group, title_group = entry[0], entry[1], entry[2], entry[3]
            m = re.match(pattern, stem, re.IGNORECASE)
            if not m:
                continue
            track_no = None
            if track_group is not None:
                try:
                    track_no = int(m.group(track_group))
                except (ValueError, IndexError):
                    pass
            artist = None
            if artist_group is not None:
                try:
                    artist = m.group(artist_group)
                    if artist:
                        artist = re.sub(r"[_\s]+", " ", artist).strip()
                except (ValueError, IndexError):
                    pass
            title = None
            if title_group is not None:
                try:
                    title = m.group(title_group)
                    if title:
                        title = re.sub(r"[_\s]+", " ", title).strip()
                except (ValueError, IndexError):
                    pass
            return track_no, artist, title
        return None, None, None

    def sync_track_table_to_current_album(self):
        """Push visible track-table order and editable metadata into current_album."""
        if getattr(self, 'manual_tracks', None):
            paths_by_string = {str(path): path for path in self.manual_tracks}
            reordered_manual_tracks = []
            for item in self.track_table.get_children():
                values = self.track_table.item(item)['values']
                file_path = str(values[12]) if len(values) > 12 else ""
                track_path = paths_by_string.get(file_path)
                if track_path is not None:
                    reordered_manual_tracks.append(track_path)
            if len(reordered_manual_tracks) == len(self.manual_tracks):
                self.manual_tracks = reordered_manual_tracks

        if not hasattr(self, 'current_album') or not self.current_album:
            self.queue_album_session_save()
            return

        items = list(self.track_table.get_children())
        tracks_by_path = {
            str(track.path): track
            for track in self.current_album.tracks
            if getattr(track, 'path', None) is not None
        }
        reordered_tracks = []

        for index, item in enumerate(items, 1):
            values = self.track_table.item(item)['values']
            file_path = str(values[12]) if len(values) > 12 else ""
            track = tracks_by_path.get(file_path)
            if track is None:
                continue

            track.track_data.track_number = index
            if len(values) > 1:
                track.track_data.artist = values[1]
            if len(values) > 2:
                track.track_data.title = values[2]
            if len(values) > 3:
                track.track_data.download_desc = values[3]
            reordered_tracks.append(track)

        if reordered_tracks and len(reordered_tracks) == len(self.current_album.tracks):
            self.current_album.tracks = reordered_tracks
        self.queue_album_session_save()

    def get_track_table_values(self, track_path=None, index=None):
        """Return visible table values by file path or row index."""
        items = list(self.track_table.get_children())
        track_path_str = str(track_path) if track_path is not None else ""

        for item in items:
            values = self.track_table.item(item)['values']
            if len(values) > 12 and track_path_str and str(values[12]) == track_path_str:
                return values

        if index is not None and 0 <= index < len(items):
            return self.track_table.item(items[index])['values']

        return ()

    def browse_cover(self):
        """Browse for cover art image"""
        if self.is_upload_in_progress():
            self.show_toast("Upload in progress", 1600, "warning")
            return

        filename = filedialog.askopenfilename(
            title="Select Cover Art",
            filetypes=[
                ("Image files", "*.jpg *.jpeg *.png *.gif"),
                ("JPEG", "*.jpg *.jpeg"),
                ("PNG", "*.png"),
                ("GIF", "*.gif"),
                ("All files", "*.*")
            ]
        )
        if filename:
            self.cover_path_var.set(filename)
            self.add_to_cover_library(filename)

    def view_cover_art(self):
        """View cover art in a resizable 1:1 dialog"""
        if self.is_upload_in_progress():
            self.show_toast("Upload in progress", 1600, "warning")
            return

        cover_path = self.cover_path_var.get()
        if not cover_path or not Path(cover_path).exists():
            messagebox.showinfo("No Cover Art", "No cover art selected.")
            return

        try:
            from PIL import Image, ImageTk

            # Load image
            img = Image.open(cover_path)
            width, height = img.size

            # Create dialog
            dialog = tk.Toplevel(self.root)
            dialog.title(f"Cover Art ({width}x{height})")
            dialog.transient(self.root)
            dialog.grab_set()

            # Calculate initial size (max 800x800, maintain 1:1)
            max_size = 800
            if width > max_size or height > max_size:
                scale = max_size / max(width, height)
                display_width = int(width * scale)
                display_height = int(height * scale)
            else:
                display_width = width
                display_height = height

            # Set initial geometry
            dialog.geometry(f"{display_width}x{display_height}")

            # Center on parent
            dialog.update_idletasks()
            x = self.root.winfo_x() + (self.root.winfo_width() - display_width) // 2
            y = self.root.winfo_y() + (self.root.winfo_height() - display_height) // 2
            dialog.geometry(f"+{x}+{y}")

            # Main frame
            main_frame = ttk.Frame(dialog)
            main_frame.pack(fill=tk.BOTH, expand=True)

            # Canvas for image
            canvas = tk.Canvas(main_frame, bg="black")
            canvas.pack(fill=tk.BOTH, expand=True)

            # Display image
            photo = ImageTk.PhotoImage(img)
            canvas.create_image(display_width // 2, display_height // 2, image=photo, anchor=tk.CENTER)

            # Keep reference to prevent garbage collection
            dialog.photo = photo

            # Handle resize to maintain 1:1 aspect ratio
            def on_resize(event):
                # Get current canvas size
                canvas_width = event.width
                canvas_height = event.height

                # Calculate scale to fit while maintaining aspect ratio
                scale = min(canvas_width / width, canvas_height / height)
                new_width = int(width * scale)
                new_height = int(height * scale)

                # Resize image
                resized_img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                new_photo = ImageTk.PhotoImage(resized_img)

                # Update canvas
                canvas.delete("all")
                canvas.create_image(canvas_width // 2, canvas_height // 2, image=new_photo, anchor=tk.CENTER)
                dialog.photo = new_photo

            canvas.bind('<Configure>', on_resize)

            # Close on Escape
            dialog.bind('<Escape>', lambda e: dialog.destroy())

        except Exception as e:
            messagebox.showerror("Error", f"Failed to view cover art:\n{e}")
            logger.exception(e)

    def show_cover_context_menu(self, event):
        """Show context menu for cover art"""
        if self.is_upload_in_progress():
            return

        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(label="Clear Cover Art", command=lambda: self.cover_path_var.set(""))
        menu.add_command(label="View Cover Art", command=self.view_cover_art)

        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def detect_cover_from_tracks(self):
        """Detect and extract cover art from tracks in current album"""
        if self.is_upload_in_progress():
            self.show_toast("Upload in progress", 1600, "warning")
            return

        import mutagen
        from mutagen.flac import FLAC
        from mutagen.mp3 import MP3
        from mutagen.mp4 import MP4Cover
        from mutagen.oggvorbis import OggVorbis
        from mutagen.oggopus import OggOpus
        from mutagen.wave import WAVE
        from mutagen.aiff import AIFF
        from PIL import Image, ImageTk
        import tempfile

        # Get tracks from either album folder or manual tracks
        tracks = []
        album_path = self.album_path_var.get()

        if album_path and Path(album_path).exists():
            # Get tracks from album folder
            path = Path(album_path)
            for ext in ['*.wav', '*.flac', '*.aiff', '*.mp3', '*.ogg', '*.opus', '*.m4a', '*.aac', '*.mod', '*.xm']:
                tracks.extend(path.glob(ext))
                tracks.extend(path.glob(ext.upper()))
        elif self.manual_tracks:
            # Get manually added tracks
            tracks = self.manual_tracks

        if not tracks:
            messagebox.showinfo("No Tracks", "No tracks found to detect cover art from.")
            return

        # Extract cover art from tracks
        cover_images = []
        for track_path in tracks:
            try:
                file_data = mutagen.File(track_path)
                if file_data is None:
                    continue

                cover_data = None
                mime_type = None

                # Extract from FLAC/OGG/Opus (pictures)
                if isinstance(file_data, (FLAC, OggVorbis, OggOpus)) and len(file_data.pictures) > 0:
                    cover_data = file_data.pictures[0].data
                    mime_type = file_data.pictures[0].mime
                # Extract from MP3/WAV/AIFF (ID3 APIC)
                elif hasattr(file_data, 'tags') and file_data.tags is not None:
                    pictures = file_data.tags.getall("APIC")
                    if len(pictures) > 0:
                        cover_data = pictures[0].data
                        mime_type = pictures[0].mime
                    # Extract from MP4/M4A (covr)
                    if cover_data is None and 'covr' in file_data.tags:
                        cover = file_data.tags['covr'][0]
                        cover_data = bytes(cover)
                        mime_type = 'image/png' if getattr(cover, 'imageformat', None) == MP4Cover.FORMAT_PNG else 'image/jpeg'

                if cover_data:
                    # Save to temp file
                    ext = '.jpg' if 'jpeg' in mime_type else '.png' if 'png' in mime_type else '.jpg'
                    temp_fd, temp_path = tempfile.mkstemp(suffix=ext)
                    try:
                        with os.fdopen(temp_fd, 'wb') as f:
                            f.write(cover_data)

                        # Load image to get dimensions
                        img = Image.open(temp_path)
                        cover_images.append({
                            'path': temp_path,
                            'track': track_path.name,
                            'size': f"{img.width}x{img.height}",
                            'image': img
                        })
                    except Exception as e:
                        logger.error(f"Failed to process cover from {track_path.name}: {e}")
                        try:
                            os.unlink(temp_path)
                        except:
                            pass

            except Exception as e:
                logger.error(f"Failed to extract cover from {track_path.name}: {e}")
                continue

        if not cover_images:
            messagebox.showinfo("No Cover Art Found", "No embedded cover art found in any tracks.")
            return

        # Show dialog with cover arts
        self.show_cover_selection_dialog(cover_images)

    def show_cover_selection_dialog(self, cover_images):
        """Show dialog to select cover art from extracted images"""
        from PIL import Image, ImageTk

        dialog = tk.Toplevel(self.root)
        dialog.title("Detect Cover Art")
        dialog.geometry("820x650")
        dialog.transient(self.root)

        # Center dialog
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (820 // 2)
        y = (dialog.winfo_screenheight() // 2) - (650 // 2)
        dialog.geometry(f"+{x}+{y}")

        main_frame = ttk.Frame(dialog)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Content
        lib_frame = ttk.Frame(main_frame, padding=10)
        lib_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Grid of thumbnails with responsive layout
        lib_canvas = tk.Canvas(lib_frame, bg="#f0f0f0")
        lib_scrollbar = ttk.Scrollbar(lib_frame, orient="vertical", command=lib_canvas.yview)
        thumb_frame = ttk.Frame(lib_canvas)

        lib_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        lib_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        lib_canvas.create_window((0, 0), window=thumb_frame, anchor="nw")
        lib_canvas.configure(yscrollcommand=lib_scrollbar.set)

        def on_mousewheel(event):
            try:
                if not lib_canvas.winfo_exists():
                    return "break"
                if getattr(event, "num", None) == 4:
                    delta = -1
                elif getattr(event, "num", None) == 5:
                    delta = 1
                else:
                    event_delta = getattr(event, "delta", 0)
                    delta = -1 * int(event_delta / 120) if event_delta else 0
                if delta:
                    lib_canvas.yview_scroll(delta, "units")
            except tk.TclError:
                return "break"
            return "break"

        def bind_cover_scroll(*widgets):
            for widget in widgets:
                widget.bind("<MouseWheel>", on_mousewheel, add="+")
                widget.bind("<Button-4>", on_mousewheel, add="+")
                widget.bind("<Button-5>", on_mousewheel, add="+")

        bind_cover_scroll(lib_canvas, thumb_frame)

        def recalculate_grid():
            try:
                if not dialog.winfo_exists() or not lib_canvas.winfo_exists():
                    return
                canvas_width = lib_canvas.winfo_width()
                if canvas_width < 150:
                    dialog.after(100, recalculate_grid)
                    return
                scrollbar_width = lib_scrollbar.winfo_width()
                available_width = canvas_width - scrollbar_width - 10
                thumb_size = 140
                cols = max(1, available_width // thumb_size)
                for widget in thumb_frame.winfo_children():
                    widget.grid_forget()
                row, col = 0, 0
                for widget in thumb_frame.winfo_children():
                    widget.grid(row=row, column=col, padx=8, pady=8)
                    col += 1
                    if col >= cols:
                        col = 0
                        row += 1
                thumb_frame.update_idletasks()
                lib_canvas.configure(scrollregion=lib_canvas.bbox("all"))
            except tk.TclError:
                return

        # Display thumbnails
        for cover_info in cover_images:
            if not Path(cover_info['path']).exists():
                continue

            try:
                img = Image.open(cover_info['path'])
                img.thumbnail((120, 120), Image.Resampling.LANCZOS)
                photo = ImageTk.PhotoImage(img)

                thumb_container = ttk.Frame(thumb_frame)

                btn = ttk.Button(
                    thumb_container,
                    image=photo,
                    command=lambda c=cover_info: self.select_detected_cover(c, dialog)
                )
                btn.image = photo
                btn.pack()

                track_name = cover_info['track']
                marquee_text = track_name + "   "
                marquee_label = ttk.Label(thumb_container, text=marquee_text, font=("Segoe UI", 7), width=16)
                marquee_label.pack(pady=(2, 0))

                def scroll_marquee(label=marquee_label, text=marquee_text):
                    try:
                        if not dialog.winfo_exists() or not label.winfo_exists():
                            return
                        current = label.cget("text")
                        if current:
                            scrolled = current[1:] + current[0]
                            label.config(text=scrolled)
                            dialog.after(200, lambda: scroll_marquee(label, text))
                    except tk.TclError:
                        return

                dialog.after(100, lambda: scroll_marquee(marquee_label, marquee_text))
                bind_cover_scroll(thumb_container, btn, marquee_label)

            except Exception as e:
                logger.error(f"Failed to display cover from {cover_info['track']}: {e}")
                continue

        dialog.update_idletasks()
        recalculate_grid()
        lib_canvas.bind('<Configure>', lambda e: recalculate_grid())

    def select_detected_cover(self, cover_info, dialog):
        """Use selected cover from detection dialog"""
        self.cover_path_var.set(cover_info['path'])
        self.add_to_cover_library(cover_info['path'])
        dialog.destroy()
        self.show_toast("Cover art selected from track", 2000, "success", trigger="cover_load")

        # Handle window close - clean up temp files
        def on_close():
            for cover in cover_images:
                try:
                    if os.path.exists(cover['path']):
                        os.unlink(cover['path'])
                except:
                    pass
            dialog.destroy()

        dialog.protocol("WM_DELETE_WINDOW", on_close)
    
    def manual_load_cookies(self):
        """Manually load cookies from file"""
        filename = filedialog.askopenfilename(
            title="Select Cookies File",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )
        if not filename:
            return

        try:
            cj = http.cookiejar.MozillaCookieJar(filename)
            cj.load()
            self.config.cookies_file = filename
            save_config(self.config)
            logger.info(f"Manually loaded cookies from: {filename}")

            # Reload artists with new cookies
            self.load_artists()
        except Exception as e:
            logger.error(f"Failed to load cookies: {e}")
            messagebox.showerror("Load Error", f"Failed to load cookies:\n{e}")
    
    def preview_album(self):
        """Preview album information"""
        album_path = self.album_path_var.get()
        
        # If no album path but have manual tracks, show those
        if not album_path and self.manual_tracks:
            self.update_manual_tracks_preview()
            return
        
        if not album_path:
            return
        
        try:
            path = Path(album_path)
            if not path.is_dir():
                messagebox.showerror("Invalid Path", "Please select a valid directory")
                return
            
            # Create album object to preview
            album = Album.from_directory(path, self.config)
            self.current_album = album  # Store for checkbox refresh
            
            # Calculate total size
            total_size = 0
            
            for track in album.tracks:
                track_path = track.path
                if track_path.exists():
                    total_size += track_path.stat().st_size
            
            # Format size
            if total_size > 1024**3:
                size_str = f"{total_size / (1024**3):.2f} GB"
            elif total_size > 1024**2:
                size_str = f"{total_size / (1024**2):.2f} MB"
            else:
                size_str = f"{total_size / 1024:.2f} KB"

            # Clear existing table
            for item in self.track_table.get_children():
                self.track_table.delete(item)

            # Populate table with tracks
            for i, track in enumerate(album.tracks, 1):
                track_path = track.path
                file_size = track_path.stat().st_size / (1024**2) if track_path.exists() else 0
                extension = track_path.suffix if track_path.exists() else ""

                # Get track metadata
                artist = track.track_data.artist if track.track_data.artist and not self.ignore_artist_var.get() else ""
                title = track.track_data.title
                comment = track.track_data.download_desc or getattr(track.track_data, 'about', '') or self.get_track_comment_metadata(track_path)
                price = f"${track.track_data.price}" if track.track_data.price else ""
                nyp = "Yes" if track.track_data.nyp else "No"

                # Get audio length
                length = self.get_audio_length(track_path)
                
                # Get additional metadata
                year, genre, bitrate = self.get_track_metadata(track_path)
                
                # Format file size
                if file_size > 1024:
                    size_str = f"{file_size / 1024:.1f} GB"
                else:
                    size_str = f"{file_size:.1f} MB"

                extra_metadata = self.get_extra_track_metadata_columns(track_path)
                self.track_table.insert("", tk.END, values=(
                    i, artist, title, comment, length, extension, price, nyp,
                    year, genre, bitrate, size_str, track_path, *extra_metadata
                ), tags=("normal",))

            self.maybe_auto_fit_track_columns()

        except Exception as e:
            messagebox.showerror("Preview Error", f"Failed to preview album:\n{e}")
            logger.exception(e)
    
    def get_audio_length(self, file_path):
        """Get audio file length in MM:SS format"""
        try:
            import mutagen
            from mutagen.flac import FLAC
            from mutagen.mp3 import MP3
            from mutagen.mp4 import MP4
            from mutagen.oggvorbis import OggVorbis
            from mutagen.oggopus import OggOpus
            from mutagen.wave import WAVE
            from mutagen.aiff import AIFF
            
            if not file_path.exists():
                return ""
            
            # Get file extension
            ext = file_path.suffix.lower()
            
            # Load appropriate file type
            if ext == '.flac':
                audio = FLAC(file_path)
            elif ext == '.mp3':
                audio = MP3(file_path)
            elif ext == '.ogg':
                audio = OggVorbis(file_path)
            elif ext == '.opus':
                audio = OggOpus(file_path)
            elif ext in ('.m4a', '.aac'):
                audio = MP4(file_path)
            elif ext == '.wav':
                audio = WAVE(file_path)
            elif ext in ['.aiff', '.aif']:
                audio = AIFF(file_path)
            elif ext in ('.mod', '.xm'):
                return ""
            else:
                return ""

            # Get length in seconds
            length_seconds = audio.info.length
            if length_seconds:
                minutes = int(length_seconds // 60)
                seconds = int(length_seconds % 60)
                return f"{minutes}:{seconds:02d}"
            else:
                return ""
        except Exception as e:
            logger.warning(f"Failed to get audio length for {file_path}: {e}")
            return ""
    
    def get_track_metadata(self, file_path):
        """Get year, genre, and bitrate from audio file"""
        try:
            import mutagen
            from mutagen.flac import FLAC
            from mutagen.mp3 import MP3
            from mutagen.mp4 import MP4
            from mutagen.oggvorbis import OggVorbis
            from mutagen.oggopus import OggOpus
            from mutagen.wave import WAVE
            from mutagen.aiff import AIFF
            
            if not file_path.exists():
                return "", "", ""
            
            ext = file_path.suffix.lower()
            
            # Load appropriate file type
            if ext == '.flac':
                audio = FLAC(file_path)
            elif ext == '.mp3':
                audio = MP3(file_path)
            elif ext == '.ogg':
                audio = OggVorbis(file_path)
            elif ext == '.opus':
                audio = OggOpus(file_path)
            elif ext in ('.m4a', '.aac'):
                audio = MP4(file_path)
            elif ext == '.wav':
                audio = WAVE(file_path)
            elif ext in ['.aiff', '.aif']:
                audio = AIFF(file_path)
            elif ext in ('.mod', '.xm'):
                return "", "", ""
            else:
                return "", "", ""
            
            # Extract year
            year = ""
            if 'date' in audio:
                year = audio['date'][0]
            elif 'TDRC' in audio:
                year = str(audio['TDRC'])
            elif 'TYER' in audio:
                year = audio['TYER'][0]
            elif '\xa9day' in audio:
                year = audio['\xa9day'][0]
            
            # Extract genre
            genre = ""
            if 'genre' in audio:
                genre = audio['genre'][0]
            elif 'TCON' in audio:
                genre = audio['TCON'][0]
            elif '\xa9gen' in audio:
                genre = str(audio['\xa9gen'][0])
            
            # Extract bitrate
            bitrate = ""
            if hasattr(audio.info, 'bitrate'):
                bitrate = f"{audio.info.bitrate // 1000} kbps"
            elif hasattr(audio.info, 'sample_rate'):
                # For lossless formats, show sample rate instead
                bitrate = f"{audio.info.sample_rate // 1000} kHz"
            
            return year, genre, bitrate
            
        except Exception as e:
            logger.warning(f"Failed to get metadata for {file_path}: {e}")
            return "", "", ""

    def get_track_comment_metadata(self, file_path):
        """Extract track comment metadata for description auto-fill."""
        try:
            from mutagen.flac import FLAC
            from mutagen.mp3 import MP3
            from mutagen.mp4 import MP4
            from mutagen.oggvorbis import OggVorbis
            from mutagen.oggopus import OggOpus
            from mutagen.wave import WAVE
            from mutagen.aiff import AIFF

            if not file_path or not Path(file_path).exists():
                return ""

            path = Path(file_path)
            ext = path.suffix.lower()
            if ext == '.flac':
                audio = FLAC(path)
                return self.get_audio_metadata_value(audio, ('comment', 'description', '\xa9cmt'))
            if ext == '.mp3':
                audio = MP3(path)
            elif ext in ('.ogg', '.opus'):
                audio = (OggVorbis if ext == '.ogg' else OggOpus)(path)
                return self.get_audio_metadata_value(audio, ('comment', 'description'))
            elif ext in ('.m4a', '.aac'):
                audio = MP4(path)
                return self.get_audio_metadata_value(audio, ('\xa9cmt', 'comment', 'description'))
            elif ext in ('.wav', '.wave'):
                audio = WAVE(path)
            elif ext in ('.aiff', '.aif'):
                audio = AIFF(path)
            elif ext in ('.mod', '.xm'):
                return ""
            else:
                return ""

            if getattr(audio, 'tags', None) is not None:
                comments = audio.tags.getall("COMM")
                if comments and getattr(comments[0], 'text', None):
                    return str(comments[0].text[0]).strip()
            return self.get_audio_metadata_value(audio, ('COMM', 'comment', 'description', '\xa9cmt'))
        except Exception as e:
            logger.debug(f"Failed to get track comment metadata for {file_path}: {e}")
            return ""

    def get_track_artist_metadata(self, file_path):
        """Extract artist metadata for restoring the preview artist column only."""
        try:
            from mutagen.flac import FLAC
            from mutagen.mp3 import MP3
            from mutagen.mp4 import MP4
            from mutagen.oggvorbis import OggVorbis
            from mutagen.oggopus import OggOpus
            from mutagen.wave import WAVE
            from mutagen.aiff import AIFF

            if not file_path or not Path(file_path).exists():
                return ""

            path = Path(file_path)
            ext = path.suffix.lower()
            if ext == '.flac':
                audio = FLAC(path)
            elif ext == '.mp3':
                audio = MP3(path)
            elif ext == '.ogg':
                audio = OggVorbis(path)
            elif ext == '.opus':
                audio = OggOpus(path)
            elif ext in ('.m4a', '.aac'):
                audio = MP4(path)
            elif ext in ('.wav', '.wave'):
                audio = WAVE(path)
            elif ext in ('.aiff', '.aif'):
                audio = AIFF(path)
            elif ext in ('.mod', '.xm'):
                return ""
            else:
                return ""

            return self.get_audio_metadata_value(audio, ('artist', 'TPE1', '\xa9ART'))
        except Exception as e:
            logger.debug(f"Failed to get track artist metadata for {file_path}: {e}")
            return ""

    def get_extra_track_metadata_columns(self, file_path):
        """Return optional metadata columns for the preview table."""
        empty_values = ("", "", "", "", "", "", "")
        try:
            from mutagen.flac import FLAC
            from mutagen.mp3 import MP3
            from mutagen.mp4 import MP4
            from mutagen.oggvorbis import OggVorbis
            from mutagen.oggopus import OggOpus
            from mutagen.wave import WAVE
            from mutagen.aiff import AIFF

            if not file_path or not Path(file_path).exists():
                return empty_values

            path = Path(file_path)
            ext = path.suffix.lower()
            if ext == '.flac':
                audio = FLAC(path)
            elif ext == '.mp3':
                audio = MP3(path)
            elif ext == '.ogg':
                audio = OggVorbis(path)
            elif ext == '.opus':
                audio = OggOpus(path)
            elif ext in ('.m4a', '.aac'):
                audio = MP4(path)
            elif ext in ('.wav', '.wave'):
                audio = WAVE(path)
            elif ext in ('.aiff', '.aif'):
                audio = AIFF(path)
            elif ext in ('.mod', '.xm'):
                return empty_values
            else:
                return empty_values

            info = getattr(audio, 'info', None)
            sample_rate = f"{info.sample_rate} Hz" if info and getattr(info, 'sample_rate', None) else ""
            channels = str(info.channels) if info and getattr(info, 'channels', None) else ""
            bit_depth_value = (
                getattr(info, 'bits_per_sample', None)
                or getattr(info, 'bit_depth', None)
            )
            bit_depth = f"{bit_depth_value}-bit" if bit_depth_value else ""

            album = self.get_audio_metadata_value(audio, ('album', 'TALB', '\xa9alb'))
            album_artist = self.get_audio_metadata_value(audio, ('albumartist', 'album artist', 'TPE2', 'aART'))
            composer = self.get_audio_metadata_value(audio, ('composer', 'TCOM', '\xa9wrt'))
            isrc = self.get_audio_metadata_value(audio, ('isrc', 'TSRC'))

            return sample_rate, channels, bit_depth, album, album_artist, composer, isrc
        except Exception as e:
            logger.debug(f"Failed to get extra metadata columns for {file_path}: {e}")
            return empty_values

    def get_audio_metadata_value(self, audio, keys):
        """Return the first readable metadata value for any of the given keys."""
        for key in keys:
            if key not in audio:
                continue

            raw_value = audio[key]
            try:
                if hasattr(raw_value, "text") and raw_value.text:
                    value = raw_value.text[0]
                elif isinstance(raw_value, (list, tuple)) and raw_value:
                    value = raw_value[0]
                else:
                    value = raw_value

                value = str(value).strip()
                if value:
                    return value
            except Exception:
                continue

        return ""

    def normalize_metadata_release_date(self, value):
        """Normalize common track date metadata formats for the release date field."""
        if not value:
            return ""

        import re

        text = str(value).strip()
        if not text:
            return ""

        match = re.search(r"\b(\d{1,2})[-./](\d{1,2})[-./](\d{4})\b", text)
        if match:
            first = int(match.group(1))
            second = int(match.group(2))
            year = int(match.group(3))
            if 1900 <= year <= 2100 and 1 <= first <= 31 and 1 <= second <= 12:
                return f"{year:04d}-{second:02d}-{first:02d}"
            if 1900 <= year <= 2100 and 1 <= first <= 12 and 1 <= second <= 31:
                return f"{year:04d}-{first:02d}-{second:02d}"

        match = re.search(r"\b(\d{4})(?:[-./](\d{1,2})(?:[-./](\d{1,2}))?)?\b", text)
        if match:
            year = int(match.group(1))
            month = int(match.group(2) or 1)
            day = int(match.group(3) or 1)
            if 1900 <= year <= 2100 and 1 <= month <= 12 and 1 <= day <= 31:
                return f"{year:04d}-{month:02d}-{day:02d}"

        return ""

    def choose_common_metadata_value(self, values):
        """Choose the most common non-empty metadata value, preserving first-seen order for ties."""
        from collections import Counter

        cleaned_values = [str(value).strip() for value in values if str(value).strip()]
        if not cleaned_values:
            return ""

        counts = Counter(value.lower() for value in cleaned_values)
        best_key = max(counts, key=lambda key: counts[key])
        for value in cleaned_values:
            if value.lower() == best_key:
                return value

        return cleaned_values[0]
    
    def auto_fill_album_details_from_metadata(self, directory):
        """Auto-fill album details from track metadata"""
        try:
            import mutagen
            from mutagen.flac import FLAC
            from mutagen.mp3 import MP3
            from mutagen.mp4 import MP4
            from mutagen.oggvorbis import OggVorbis
            from mutagen.oggopus import OggOpus
            from mutagen.wave import WAVE
            from mutagen.aiff import AIFF
            from pathlib import Path
            
            album_path = Path(directory)
            if not album_path.exists():
                return
            
            # Find audio files in the directory
            audio_extensions = ['.flac', '.mp3', '.wav', '.aiff', '.aif', '.ogg', '.opus', '.m4a', '.aac', '.mod', '.xm']
            audio_files = []
            for ext in audio_extensions:
                audio_files.extend(album_path.glob(f'*{ext}'))
                audio_files.extend(album_path.glob(f'*{ext.upper()}'))
            
            if not audio_files:
                return

            album_values = []
            release_date_values = []
            for audio_file in audio_files:
                try:
                    track_ext = audio_file.suffix.lower()
                    if track_ext == '.flac':
                        track_audio = FLAC(audio_file)
                    elif track_ext == '.mp3':
                        track_audio = MP3(audio_file)
                    elif track_ext == '.ogg':
                        track_audio = OggVorbis(audio_file)
                    elif track_ext == '.opus':
                        track_audio = OggOpus(audio_file)
                    elif track_ext in ('.m4a', '.aac'):
                        track_audio = MP4(audio_file)
                    elif track_ext == '.wav':
                        track_audio = WAVE(audio_file)
                    elif track_ext in ['.aiff', '.aif']:
                        track_audio = AIFF(audio_file)
                    else:
                        continue

                    album_value = self.get_audio_metadata_value(track_audio, ('album', 'TALB', '\xa9alb'))
                    if album_value:
                        album_values.append(album_value)

                    release_date_value = self.get_audio_metadata_value(
                        track_audio,
                        ('date', 'originaldate', 'releasedate', 'TDRC', 'TDOR', 'TYER', '\xa9day')
                    )
                    normalized_release_date = self.normalize_metadata_release_date(release_date_value)
                    if normalized_release_date:
                        release_date_values.append(normalized_release_date)
                except Exception as e:
                    logger.debug(f"Failed to scan album metadata from {audio_file}: {e}")

            guessed_album = self.choose_common_metadata_value(album_values)
            guessed_release_date = self.choose_common_metadata_value(release_date_values)
            
            # Use the first audio file to extract metadata
            first_file = audio_files[0]
            ext = first_file.suffix.lower()
            
            # Load appropriate file type
            if ext == '.flac':
                audio = FLAC(first_file)
            elif ext == '.mp3':
                audio = MP3(first_file)
            elif ext == '.ogg':
                audio = OggVorbis(first_file)
            elif ext == '.opus':
                audio = OggOpus(first_file)
            elif ext in ('.m4a', '.aac'):
                audio = MP4(first_file)
            elif ext == '.wav':
                audio = WAVE(first_file)
            elif ext in ['.aiff', '.aif']:
                audio = AIFF(first_file)
            elif ext in ('.mod', '.xm'):
                audio = None
            else:
                return

            if audio is None:
                return
            
            # Extract metadata
            metadata = {}
            
            # Album name
            album_metadata = self.get_audio_metadata_value(audio, ('album', 'TALB', '\xa9alb'))
            if album_metadata:
                metadata['album'] = album_metadata
            elif guessed_album:
                metadata['album'] = guessed_album
            
            # Artist
            if 'artist' in audio:
                metadata['artist'] = audio['artist'][0]
            elif 'TPE1' in audio:  # MP3 tag
                metadata['artist'] = audio['TPE1'][0]
            elif '\xa9ART' in audio:  # MP4 tag
                metadata['artist'] = audio['\xa9ART'][0]
            
            # Year
            if 'date' in audio:
                metadata['year'] = audio['date'][0]
            elif 'TDRC' in audio:  # MP3 tag
                metadata['year'] = str(audio['TDRC'])
            elif 'TYER' in audio:  # Old MP3 tag
                metadata['year'] = audio['TYER'][0]
            
            # Genre
            if 'genre' in audio:
                metadata['genre'] = audio['genre'][0]
            elif 'TCON' in audio:  # MP3 tag
                metadata['genre'] = audio['TCON'][0]
            elif '\xa9gen' in audio:  # MP4 tag
                metadata['genre'] = str(audio['\xa9gen'][0])
            
            # Comment
            if 'comment' in audio:
                metadata['comment'] = audio['comment'][0]
            elif 'COMM' in audio:  # MP3/ID3 tag
                metadata['comment'] = audio['COMM'][0]
            elif '\xa9cmt' in audio:  # MP4 tag
                metadata['comment'] = audio['\xa9cmt'][0]
            
            # Track Title
            if 'title' in audio:
                metadata['title'] = audio['title'][0]
            elif 'TIT2' in audio:  # MP3 tag
                metadata['title'] = audio['TIT2'][0]
            elif '\xa9nam' in audio:  # MP4 tag
                metadata['title'] = audio['\xa9nam'][0]
            
            # Album Artist
            if 'albumartist' in audio:
                metadata['albumartist'] = audio['albumartist'][0]
            elif 'TPE2' in audio:  # MP3 tag
                metadata['albumartist'] = audio['TPE2'][0]
            elif 'aART' in audio:  # MP4 tag
                metadata['albumartist'] = audio['aART'][0]
            
            # Composer
            if 'composer' in audio:
                metadata['composer'] = audio['composer'][0]
            elif 'TCOM' in audio:  # MP3 tag
                metadata['composer'] = audio['TCOM'][0]
            elif '\xa9wrt' in audio:  # MP4 tag
                metadata['composer'] = audio['\xa9wrt'][0]
            
            # Track Number
            if 'tracknumber' in audio:
                metadata['tracknumber'] = str(audio['tracknumber'][0])
            elif 'TRCK' in audio:  # MP3 tag
                metadata['tracknumber'] = audio['TRCK'][0]
            elif 'trkn' in audio and audio['trkn']:  # MP4 tag
                metadata['tracknumber'] = str(audio['trkn'][0][0])
            
            # Duration
            if hasattr(audio, 'info') and hasattr(audio.info, 'length'):
                duration_seconds = int(audio.info.length)
                minutes = duration_seconds // 60
                seconds = duration_seconds % 60
                metadata['duration'] = f"{minutes}:{seconds:02d}"
            
            # Bitrate
            if hasattr(audio, 'info') and hasattr(audio.info, 'bitrate'):
                bitrate_kbps = audio.info.bitrate // 1000
                metadata['bitrate'] = f"{bitrate_kbps}kbps"
            
            # Apply metadata to form fields (only if empty)
            if (
                getattr(self.config, 'guess_album_title_from_track_metadata', True)
                and guessed_album
                and not self.album_name_var.get()
            ):
                self.album_name_var.set(guessed_album)
            elif (
                getattr(self.config, 'guess_album_title_from_track_metadata', True)
                and 'album' in metadata
                and not self.album_name_var.get()
            ):
                self.album_name_var.set(metadata['album'])

            if (
                getattr(self.config, 'guess_release_date_from_track_metadata', True)
                and guessed_release_date
                and not self.album_publish_date_var.get()
            ):
                self.album_publish_date_var.set(guessed_release_date)
                metadata['release_date'] = guessed_release_date

            if (
                getattr(self.config, 'use_folder_name_when_album_missing', True)
                and not guessed_album
                and not self.album_name_var.get()
            ):
                self.album_name_var.set(album_path.name)
            
            if getattr(self.config, 'use_album_artist_in_album_details', False):
                if 'albumartist' in metadata and not self.album_artist_var.get():
                    self.album_artist_var.set(metadata['albumartist'])
                elif 'artist' in metadata and not self.album_artist_var.get():
                    self.album_artist_var.set(metadata['artist'])
            elif 'artist' in metadata and not self.album_artist_var.get():
                self.album_artist_var.set(metadata['artist'])
            
            # Detect release type based on track count
            track_count = len(audio_files)
            if track_count <= 3:
                release_type = "Single"
            elif track_count <= 6:
                release_type = "EP"
            else:
                release_type = "Album"
            
            # Auto-tag metadata to tags field based on settings
            tag_mappings = [
                ('year', self.config.auto_tag_year),
                ('genre', self.config.auto_tag_genre),
                ('artist', self.config.auto_tag_artist),
                ('album', self.config.auto_tag_album),
                ('comment', self.config.auto_tag_comment),
                ('title', self.config.auto_tag_track_title),
                ('albumartist', self.config.auto_tag_album_artist),
                ('composer', self.config.auto_tag_composer),
                ('tracknumber', self.config.auto_tag_track_number),
                ('duration', self.config.auto_tag_duration),
                ('bitrate', self.config.auto_tag_bitrate),
                ('release_type', self.config.auto_tag_release_type)
            ]
            
            # Add release type to metadata for auto-tagging
            metadata['release_type'] = release_type
            
            # Get existing tags from the entry
            existing_tags_text = self.album_tags_var.get()
            existing_tags = [tag.strip() for tag in existing_tags_text.split(',') if tag.strip()]
            
            tags_added = 0
            for tag_key, setting_enabled in tag_mappings:
                if tag_key in metadata and setting_enabled:
                    tag_value = metadata[tag_key]
                    if tag_value and tag_value not in existing_tags:
                        existing_tags.append(tag_value)
                        tags_added += 1
            
            # Update the tag entry and variable (validation will handle limit)
            new_tags_text = ', '.join(existing_tags)
            self.album_tags_var.set(new_tags_text)
            if hasattr(self, 'tag_entry'):
                self.tag_entry.delete(0, tk.END)
                self.tag_entry.insert(0, new_tags_text)
                # Trigger validation to enforce 10 tag limit
                self.validate_tag_limit()
            
            logger.info(f"Auto-filled album details from metadata: {metadata}")
            self.show_toast(f"Auto-filled album details from metadata ({tags_added} tags added)", 2000, "success", trigger="metadata_load")
            
        except Exception as e:
            logger.warning(f"Failed to auto-fill album details from metadata: {e}")
    
    def create_tag_input(self, parent):
        """Create a simple text entry for tags"""
        # Container frame for tag input
        self.tag_container = ttk.Frame(parent)
        self.tag_container.pack(fill=tk.X, pady=(0, 6))

        # EDIT button for tags
        self.edit_tags_btn = ttk.Button(self.tag_container, text="Edit", width=5, command=self.open_tag_edit_dialog)
        self.edit_tags_btn.pack(side=tk.RIGHT, padx=(5, 0))

        # Simple text entry for tags
        self.tag_entry = ttk.Entry(self.tag_container, font=("Segoe UI", 8))
        self.tag_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Bind to validate tag limit
        self.tag_entry.bind('<KeyRelease>', self.validate_tag_limit)
        self.tag_entry.bind('<FocusOut>', self.validate_tag_limit)

        # Initialize with existing tags
        existing_tags = self.album_tags_var.get()
        if existing_tags:
            self.tag_entry.insert(0, existing_tags)
    
    def validate_tag_limit(self, event=None):
        """Validate and limit tags to 10"""
        if not hasattr(self, 'tag_entry'):
            return
            
        tag_text = self.tag_entry.get()
        tags = [tag.strip() for tag in tag_text.split(',') if tag.strip()]
        
        if len(tags) > 10:
            # Trim to 10 tags
            tags = tags[:10]
            new_text = ', '.join(tags)
            self.tag_entry.delete(0, tk.END)
            self.tag_entry.insert(0, new_text)
            self.album_tags_var.set(new_text)
            self.show_toast("Maximum 10 tags allowed (Bandcamp limit)", 2000, "warning")
        else:
            self.album_tags_var.set(tag_text)
    
    def open_tag_edit_dialog(self):
        """Open a dialog to edit tags as wrapped text"""
        dialog = tk.Toplevel(self.root)
        dialog.title("Edit Tags")
        dialog.geometry("400x300")
        dialog.transient(self.root)
        dialog.grab_set()
        
        # Text area for editing tags
        text_frame = ttk.Frame(dialog)
        text_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        text_area = tk.Text(text_frame, font=("Segoe UI", 10), wrap=tk.WORD)
        text_area.pack(fill=tk.BOTH, expand=True)
        
        # Load current tags (one per line for wrapping)
        current_tags = self.album_tags_var.get()
        tags_list = [tag.strip() for tag in current_tags.split(',') if tag.strip()]
        text_area.insert("1.0", '\n'.join(tags_list))
        
        # Buttons
        button_frame = ttk.Frame(dialog)
        button_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
        
        def save_tags():
            tag_text = text_area.get("1.0", "end-1c").strip()
            # Split by newlines and commas, filter empty
            new_tags = [tag.strip() for tag in tag_text.replace(',', '\n').split('\n') if tag.strip()]
            
            # Update the entry and variable (validation will handle limit)
            new_tags_text = ', '.join(new_tags)
            self.tag_entry.delete(0, tk.END)
            self.tag_entry.insert(0, new_tags_text)
            self.album_tags_var.set(new_tags_text)
            # Trigger validation to enforce 10 tag limit
            self.validate_tag_limit()
            dialog.destroy()
        
        def cancel():
            dialog.destroy()
        
        ttk.Button(button_frame, text="Save", command=save_tags).pack(side=tk.RIGHT, padx=(5, 0))
        ttk.Button(button_frame, text="Cancel", command=cancel).pack(side=tk.RIGHT)
    
    def shuffle_tracks(self):
        """Shuffle the track order in the current album"""
        items = list(self.track_table.get_children())
        if not items:
            self.show_toast("No tracks to shuffle", 2000, "warning")
            return

        try:
            import random

            locked_positions = {
                index: tuple(self.track_table.item(item)['values'])
                for index, item in enumerate(items)
                if self.is_track_item_locked(item)
            }
            values = [
                self.track_table.item(item)['values']
                for item in items
                if not self.is_track_item_locked(item)
            ]
            random.shuffle(values)

            for item in items:
                self.track_table.delete(item)

            unlocked_index = 0
            for i in range(1, len(items) + 1):
                vals = locked_positions.get(i - 1)
                if vals is None:
                    vals = values[unlocked_index]
                    unlocked_index += 1
                vals = list(vals)
                vals[0] = i
                if len(vals) < 13:
                    vals.append("")
                self.insert_track_row(vals)
            self.sync_track_table_to_current_album()
            self.show_toast("Tracks randomized", 2000, "success")
            logger.info("Track order shuffled")
        except Exception as e:
            messagebox.showerror("Shuffle Error", f"Failed to shuffle tracks:\n{e}")
            logger.exception(e)

    def smart_randomize_tracks(self, show_feedback=True):
        """Shuffle tracks while trying to avoid same-position and same-artist clustering."""
        items = list(self.track_table.get_children())
        if len(items) < 2:
            if show_feedback:
                self.show_toast("Need at least two tracks to randomize", 2000, "warning")
            return

        try:
            import random

            locked_positions = {
                index: tuple(self.track_table.item(item)['values'])
                for index, item in enumerate(items)
                if self.is_track_item_locked(item)
            }
            original_values = [
                tuple(self.track_table.item(item)['values'])
                for item in items
                if not self.is_track_item_locked(item)
            ]
            if len(original_values) < 2:
                if show_feedback:
                    self.show_toast("Need at least two unlocked tracks to randomize", 2000, "warning")
                return

            def score_order(order):
                same_position = sum(1 for i, vals in enumerate(order) if vals == original_values[i])
                adjacent_same_artist = 0
                for left, right in zip(order, order[1:]):
                    left_artist = str(left[1]).strip().lower() if len(left) > 1 else ""
                    right_artist = str(right[1]).strip().lower() if len(right) > 1 else ""
                    if left_artist and left_artist == right_artist:
                        adjacent_same_artist += 1
                return same_position + (adjacent_same_artist * 3)

            best_order = original_values[:]
            best_score = score_order(best_order)
            for _ in range(200):
                candidate = original_values[:]
                random.shuffle(candidate)
                candidate_score = score_order(candidate)
                if candidate_score < best_score:
                    best_order = candidate
                    best_score = candidate_score
                    if best_score == 0:
                        break

            for item in items:
                self.track_table.delete(item)

            unlocked_index = 0
            for i in range(1, len(items) + 1):
                vals = locked_positions.get(i - 1)
                if vals is None:
                    vals = best_order[unlocked_index]
                    unlocked_index += 1
                vals = list(vals)
                vals[0] = i
                if len(vals) < 13:
                    vals.append("")
                self.insert_track_row(vals)

            self.sync_track_table_to_current_album()
            if show_feedback:
                self.show_toast("Smart randomize applied", 2000, "success")
            logger.info("Smart randomized track order")
        except Exception as e:
            messagebox.showerror("Smart Randomize Error", f"Failed to smart-randomize tracks:\n{e}")
            logger.exception(e)

    def parse_duration_seconds(self, value):
        """Parse a duration string like MM:SS or HH:MM:SS for sorting."""
        parts = [part.strip() for part in str(value).split(":") if part.strip()]
        if not parts:
            return None
        try:
            numbers = [int(part) for part in parts]
        except ValueError:
            return None
        seconds = 0
        for number in numbers:
            seconds = seconds * 60 + number
        return seconds

    def parse_numeric_prefix(self, value):
        """Return the first numeric value in a string, or None."""
        match = re.search(r"-?\d+(?:\.\d+)?", str(value))
        return float(match.group(0)) if match else None

    def parse_file_size_mb(self, value, file_path=""):
        """Parse table file size text or read the real file size for sorting."""
        try:
            if file_path and Path(file_path).exists():
                return Path(file_path).stat().st_size / (1024 ** 2)
        except OSError:
            pass

        text = str(value).strip().lower()
        number = self.parse_numeric_prefix(text)
        if number is None:
            return None
        if "gb" in text:
            return number * 1024
        if "kb" in text:
            return number / 1024
        return number

    def get_track_sort_value(self, values, criterion):
        """Return a stable sort key for a track-table row."""
        values = list(values)
        while len(values) < 20:
            values.append("")

        text_columns = {
            "title": 2,
            "artist": 1,
            "extension": 5,
            "genre": 9,
            "album": 16,
            "album_artist": 17,
            "composer": 18,
            "isrc": 19,
        }
        numeric_columns = {
            "track_no": 0,
            "price": 6,
            "year": 8,
            "bitrate": 10,
            "sample_rate": 13,
            "channels": 14,
            "bit_depth": 15,
        }

        if criterion == "file_size":
            value = self.parse_file_size_mb(values[11], values[12])
            return (value is None, value or 0)
        if criterion == "length":
            value = self.parse_duration_seconds(values[4])
            return (value is None, value or 0)
        if criterion == "metadata_track_no":
            file_path = Path(values[12]) if values[12] else None
            value = get_metadata_track_number(file_path) if file_path else None
            return (value is None, value or 0)
        if criterion in numeric_columns:
            value = self.parse_numeric_prefix(values[numeric_columns[criterion]])
            return (value is None, value or 0)
        if criterion in text_columns:
            value = str(values[text_columns[criterion]]).strip().casefold()
            return (not value, value)

        value = str(values[2]).strip().casefold()
        return (not value, value)

    def sort_tracks_by(self, criterion, label):
        """Sort the preview table by a criterion and toggle next sort direction."""
        items = list(self.track_table.get_children())
        if not items:
            self.show_toast("No tracks to sort", 2000, "warning")
            return

        ascending = self.context_sort_directions.get(criterion, True)
        locked_positions = {
            index: tuple(self.track_table.item(item)['values'])
            for index, item in enumerate(items)
            if self.is_track_item_locked(item)
        }
        rows = [
            (
                self.get_track_sort_value(self.track_table.item(item)['values'], criterion),
                tuple(self.track_table.item(item)['values'])
            )
            for item in items
            if not self.is_track_item_locked(item)
        ]
        rows.sort(key=lambda row: row[0], reverse=not ascending)
        sorted_values = [values for _, values in rows]

        for item in items:
            self.track_table.delete(item)

        unlocked_index = 0
        for index in range(len(items)):
            if index in locked_positions:
                self.insert_track_row(locked_positions[index])
            else:
                self.insert_track_row(sorted_values[unlocked_index])
                unlocked_index += 1

        self.renumber_tracks()
        self.sync_track_table_to_current_album()
        self.maybe_auto_fit_track_columns()
        self.context_sort_directions[criterion] = not ascending
        direction = "ascending" if ascending else "descending"
        self.show_toast(f"Sorted by {label} ({direction})", 1600, "success")

    def close_track_context_menu(self):
        """Dismiss any active track context menu and clear menu references."""
        for attr_name in ("_active_track_sort_menu", "_active_track_context_menu"):
            menu = getattr(self, attr_name, None)
            if menu is None:
                continue
            try:
                if menu.winfo_exists():
                    menu.unpost()
                    menu.grab_release()
            except tk.TclError:
                pass
            setattr(self, attr_name, None)

    def get_track_lock_key_from_values(self, values):
        """Return a stable lock key for a track row."""
        values = list(values)
        file_path = str(values[12]).strip() if len(values) > 12 else ""
        if file_path:
            return file_path
        title = str(values[2]).strip() if len(values) > 2 else ""
        track_no = str(values[0]).strip() if values else ""
        return f"row:{track_no}:{title}"

    def get_track_lock_key(self, item_id):
        """Return the lock key for a tree item."""
        return self.get_track_lock_key_from_values(self.track_table.item(item_id).get("values", ()))

    def is_track_item_locked(self, item_id):
        """Return True when the track row is locked."""
        return self.get_track_lock_key(item_id) in getattr(self, 'locked_track_keys', set())

    def insert_track_row(self, values, index=tk.END):
        """Insert a track row while preserving lock tags."""
        key = self.get_track_lock_key_from_values(values)
        tags = ("normal", "locked") if key in getattr(self, 'locked_track_keys', set()) else ("normal",)
        return self.track_table.insert("", index, values=tuple(values), tags=tags)

    def toggle_track_lock(self, item_id):
        """Lock or unlock a track row from context menu actions."""
        key = self.get_track_lock_key(item_id)
        if key in self.locked_track_keys:
            self.locked_track_keys.remove(key)
            self.apply_track_item_tags(item_id)
            self.queue_album_session_save()
            self.show_toast("Track unlocked", 1500, "success")
        else:
            self.locked_track_keys.add(key)
            self.apply_track_item_tags(item_id)
            self.queue_album_session_save()
            self.show_toast("Track locked", 1500, "success")
    
    def show_track_context_menu(self, event):
        """Show context menu for track table"""
        self.close_track_context_menu()

        # Get selected item
        item_id = self.track_table.identify_row(event.y)
        
        # Create context menu
        context_menu = tk.Menu(self.root, tearoff=0)
        self._active_track_sort_menu = None
        has_items = False

        def close_then_run(command, undo_label=None):
            def wrapped():
                self.close_track_context_menu()
                if undo_label:
                    self.push_undo_state(undo_label)
                command()
            return wrapped

        def add_separator_if_needed():
            if has_items and not getattr(self.config, 'context_menu_remove_dividers', False):
                context_menu.add_separator()

        def add_menu_command(label, command, icon_label=None, state=tk.NORMAL, undo_label=None):
            nonlocal has_items
            icon = None
            if self.config.show_context_menu_icons and icon_label:
                icon = self.icon_images.get(icon_label)
            if icon:
                context_menu.add_command(label=label, command=close_then_run(command, undo_label), image=icon, compound=tk.LEFT, state=state)
            else:
                context_menu.add_command(label=label, command=close_then_run(command, undo_label), state=state)
            has_items = True

        def add_sort_submenu():
            nonlocal has_items
            sort_options = [
                ("file_size", "file size", "Sort File Size", "sort_by_file_size"),
                ("length", "length", "Sort Length", "sort_by_length"),
                ("title", "alphabetically", "Sort Alphabetically", "sort_by_alphabetically"),
                ("artist", "artist name", "Sort Artist", "sort_by_artist"),
                ("track_no", "track number", "Sort Track Number", "sort_by_track_number"),
                ("metadata_track_no", "metadata track #", "Sort Metadata Track Number", "sort_by_metadata_track_number"),
                ("extension", "extension", "Sort Extension", "sort_by_extension"),
                ("price", "price", "Sort Price", "sort_by_price"),
                ("year", "year", "Sort Year", "sort_by_year"),
                ("genre", "genre", "Sort Genre", "sort_by_genre"),
                ("bitrate", "bitrate", "Sort Bitrate", "sort_by_bitrate"),
                ("sample_rate", "sample rate", "Sort Sample Rate", "sort_by_sample_rate"),
                ("channels", "channels", "Sort Channels", "sort_by_channels"),
                ("bit_depth", "bit depth", "Sort Bit Depth", "sort_by_bit_depth"),
                ("album", "album metadata", "Sort Album", "sort_by_album"),
                ("album_artist", "album artist metadata", "Sort Album Artist", "sort_by_album_artist"),
                ("composer", "composer", "Sort Composer", "sort_by_composer"),
                ("isrc", "ISRC", "Sort ISRC", "sort_by_isrc"),
            ]
            sort_options = [
                option for option in sort_options
                if getattr(self.config, option[3], True)
            ]
            if not sort_options:
                return
            sort_menu = tk.Menu(context_menu, tearoff=0)
            self._active_track_sort_menu = sort_menu
            for criterion, label, icon_label, _config_key in sort_options:
                ascending = self.context_sort_directions.get(criterion, True)
                direction_marker = "Asc" if ascending else "Desc"
                command = close_then_run(lambda c=criterion, l=label: self.sort_tracks_by(c, l), f"Sort by {label}")
                sort_menu.add_command(
                    label=f"Sort by {label} ({direction_marker})",
                    command=command
                )

            icon = None
            if self.config.show_context_menu_icons:
                icon = self.icon_images.get("Sort By")
            if icon:
                context_menu.add_cascade(label="Sort By...", menu=sort_menu, image=icon, compound=tk.LEFT)
            else:
                context_menu.add_cascade(label="Sort By...", menu=sort_menu)
            has_items = True
        
        # Add track-specific options only if an item is selected
        if item_id:
            # Select the item
            self.track_table.selection_set(item_id)
            
            if self.config.context_menu_play:
                add_menu_command("Play", lambda: self.play_track(item_id), "Play")

            if getattr(self.config, 'context_menu_lock_unlock', True):
                lock_label = "Unlock Track" if self.is_track_item_locked(item_id) else "Lock Track"
                add_separator_if_needed()
                add_menu_command(lock_label, lambda: self.toggle_track_lock(item_id), lock_label, undo_label=lock_label)
            
            if self.config.context_menu_remove_track:
                add_separator_if_needed()
                add_menu_command("Remove Track", lambda: self.remove_track(item_id), "Remove Track", undo_label="Remove Track")

            move_options = [
                (self.config.context_menu_move_up, "Move Up", lambda: self.move_track_up(item_id), "Move Up"),
                (self.config.context_menu_move_down, "Move Down", lambda: self.move_track_down(item_id), "Move Down"),
                (getattr(self.config, 'context_menu_move_to_top', True), "Move to Top", lambda: self.move_track_to_top(item_id), "Move to Top"),
                (getattr(self.config, 'context_menu_move_to_bottom', True), "Move to Bottom", lambda: self.move_track_to_bottom(item_id), "Move to Bottom"),
            ]
            enabled_move_options = [option for option in move_options if option[0]]
            if enabled_move_options:
                add_separator_if_needed()
                for _, label, command, icon_label in enabled_move_options:
                    add_menu_command(label, command, icon_label, undo_label=label)

            file_options = [
                (self.config.context_menu_open_file, "Open File Location", lambda: self.open_file_location(item_id), "Open File Location"),
                (self.config.context_menu_replace_file, "Replace File", lambda: self.replace_track_file(item_id), "Replace File", "Replace File"),
                (getattr(self.config, 'context_menu_extract_cover_art', True), "Extract Cover Art", lambda: self.extract_cover_art_from_track(item_id), "Extract Cover Art", "Extract Cover Art"),
                (getattr(self.config, 'context_menu_set_track_cover_as_album_cover', True), "Set Track Cover as Album Cover", lambda: self.set_track_cover_as_album_cover(item_id), "Set Track Cover as Album Cover", "Set Track Cover"),
                (getattr(self.config, 'context_menu_extract_track_info', True), "Extract Track Information", lambda: self.extract_track_information(item_id), "Extract Track Information", None),
            ]
            enabled_file_options = [option for option in file_options if option[0]]
            if enabled_file_options:
                add_separator_if_needed()
                for option in enabled_file_options:
                    _enabled, label, command, icon_label, *undo_label = option
                    add_menu_command(label, command, icon_label, undo_label=undo_label[0] if undo_label else None)

            metadata_options = [
                (self.config.context_menu_copy_metadata, "Copy Metadata", lambda: self.copy_track_metadata(item_id), "Copy Metadata"),
                (self.config.context_menu_paste_metadata, "Paste Metadata", lambda: self.paste_track_metadata(item_id), "Paste Metadata", "Paste Metadata"),
                (getattr(self.config, 'context_menu_revert_to_original', True), "Revert to Original", lambda: self.revert_track_to_original(item_id), "Revert to Original", "Revert to Original"),
                (getattr(self.config, 'context_menu_clear_metadata', True), "Clear Metadata", lambda: self.clear_track_metadata(item_id), "Clear Metadata", "Clear Metadata"),
            ]
            enabled_metadata_options = [option for option in metadata_options if option[0]]
            if enabled_metadata_options:
                add_separator_if_needed()
                for option in enabled_metadata_options:
                    _enabled, label, command, icon_label, *undo_label = option
                    add_menu_command(label, command, icon_label, undo_label=undo_label[0] if undo_label else None)

        session_options = [
            (getattr(self.config, 'context_menu_extract_tracklist', True), "Extract Tracklist", self.extract_tracklist, "Extract Tracklist", None),
            (getattr(self.config, 'context_menu_open_session', True), "Open session.txt", self.open_album_session_file, "Open session.txt", None),
            (getattr(self.config, 'context_menu_undo', True), "Undo", self.undo_track_table_action, "Undo", tk.NORMAL if self.undo_buffer else tk.DISABLED),
            (getattr(self.config, 'context_menu_redo', True), "Redo", self.redo_track_table_action, "Redo", tk.NORMAL if self.redo_buffer else tk.DISABLED),
        ]
        enabled_session_options = [option for option in session_options if option[0]]
        if enabled_session_options:
            add_separator_if_needed()
            for _, label, command, icon_label, state in enabled_session_options:
                add_menu_command(label, command, icon_label, state=state)
            
        global_order_options = [
            (self.config.context_menu_randomize, "Randomize", self.shuffle_tracks, "Randomize"),
            (getattr(self.config, 'context_menu_smart_randomize', True), "Smart Randomize", self.smart_randomize_tracks, "Smart Randomize"),
        ]
        enabled_global_order_options = [option for option in global_order_options if option[0]]
        if enabled_global_order_options:
            add_separator_if_needed()
            for _, label, command, icon_label in enabled_global_order_options:
                add_menu_command(label, command, icon_label, undo_label=label)

        sort_method_keys = [
            "sort_by_file_size", "sort_by_length", "sort_by_alphabetically",
            "sort_by_artist", "sort_by_track_number", "sort_by_extension",
            "sort_by_metadata_track_number",
            "sort_by_price", "sort_by_year", "sort_by_genre", "sort_by_bitrate",
            "sort_by_sample_rate", "sort_by_channels", "sort_by_bit_depth",
            "sort_by_album", "sort_by_album_artist", "sort_by_composer",
            "sort_by_isrc",
        ]
        if (
            getattr(self.config, 'context_menu_sort_by', True)
            and self.track_table.get_children()
            and any(getattr(self.config, key, True) for key in sort_method_keys)
        ):
            add_separator_if_needed()
            add_sort_submenu()

        global_clear_options = [
            (getattr(self.config, 'context_menu_clear_all_metadata', True), "Clear All Metadata", self.clear_all_track_metadata, "Clear All Metadata"),
            (self.config.context_menu_clear_all, "Clear All Tracks", self.clear_manual_tracks, "Clear All Tracks"),
        ]
        enabled_global_clear_options = [option for option in global_clear_options if option[0]]
        if enabled_global_clear_options:
            add_separator_if_needed()
            for _, label, command, icon_label in enabled_global_clear_options:
                add_menu_command(label, command, icon_label, undo_label=label)

        if not has_items:
            return
        
        # Show menu at cursor position
        self._active_track_context_menu = context_menu
        x = getattr(event, "x_root", 0) or self.root.winfo_pointerx()
        y = getattr(event, "y_root", 0) or self.root.winfo_pointery()
        try:
            context_menu.tk_popup(x, y)
        finally:
            try:
                context_menu.grab_release()
            except tk.TclError:
                pass
    
    def play_track(self, item_id):
        """Play the selected track"""
        # Get file path from the table
        track_values = self.track_table.item(item_id)['values']
        file_path = track_values[12] if len(track_values) > 12 else ""
        
        if not file_path:
            self.show_toast("No file path available", 2000, "warning")
            return
        
        try:
            import platform
            if platform.system() == "Windows":
                subprocess.Popen(['start', '', file_path], shell=True)
            elif platform.system() == "Darwin":  # macOS
                subprocess.Popen(['open', file_path])
            else:  # Linux
                subprocess.Popen(['xdg-open', file_path])
        except Exception as e:
            logger.exception(e)
    
    def remove_track(self, item_id):
        """Remove a track from the table"""
        if self.is_track_item_locked(item_id):
            self.show_toast("Track is locked", 1600, "warning")
            return
        self.track_table.delete(item_id)
        self.sync_track_table_to_current_album()
        self.show_toast("Track removed", 2000, "success", trigger="track_remove")
    
    def move_track_up(self, item_id):
        """Move a track up in the order"""
        if self.is_track_item_locked(item_id):
            self.show_toast("Track is locked", 1600, "warning")
            return
        items = list(self.track_table.get_children())
        current_index = items.index(item_id)
        
        if current_index > 0:
            # Get current values
            current_values = list(self.track_table.item(item_id)['values'])
            previous_item = items[current_index - 1]
            if self.is_track_item_locked(previous_item):
                self.show_toast("Cannot move past a locked track", 1600, "warning")
                return
            previous_values = list(self.track_table.item(previous_item)['values'])
            
            # Ensure both have file_path (add empty string if missing)
            if len(current_values) < 13:
                current_values.append("")
            if len(previous_values) < 13:
                previous_values.append("")
            
            # Swap values
            self.track_table.item(item_id, values=tuple(previous_values))
            self.track_table.item(previous_item, values=tuple(current_values))
            self.sync_track_table_to_current_album()
    
    def move_track_down(self, item_id):
        """Move a track down in the order"""
        if self.is_track_item_locked(item_id):
            self.show_toast("Track is locked", 1600, "warning")
            return
        items = list(self.track_table.get_children())
        current_index = items.index(item_id)
        
        if current_index < len(items) - 1:
            # Get current values
            current_values = list(self.track_table.item(item_id)['values'])
            next_item = items[current_index + 1]
            if self.is_track_item_locked(next_item):
                self.show_toast("Cannot move past a locked track", 1600, "warning")
                return
            next_values = list(self.track_table.item(next_item)['values'])
            
            # Ensure both have file_path (add empty string if missing)
            if len(current_values) < 13:
                current_values.append("")
            if len(next_values) < 13:
                next_values.append("")
            
            # Swap values
            self.track_table.item(item_id, values=tuple(next_values))
            self.track_table.item(next_item, values=tuple(current_values))
            self.sync_track_table_to_current_album()

    def move_track_to_top(self, item_id):
        """Move a track to the top of the order."""
        if self.is_track_item_locked(item_id):
            self.show_toast("Track is locked", 1600, "warning")
            return
        items = list(self.track_table.get_children())
        if not items or item_id == items[0]:
            return

        values = list(self.track_table.item(item_id)['values'])
        if len(values) < 13:
            values.append("")

        self.track_table.delete(item_id)
        self.insert_track_row(values, 0)
        self.renumber_tracks()
        self.sync_track_table_to_current_album()
        self.show_toast("Track moved to top", 1500, "success")

    def move_track_to_bottom(self, item_id):
        """Move a track to the bottom of the order."""
        if self.is_track_item_locked(item_id):
            self.show_toast("Track is locked", 1600, "warning")
            return
        items = list(self.track_table.get_children())
        if not items or item_id == items[-1]:
            return

        values = list(self.track_table.item(item_id)['values'])
        if len(values) < 13:
            values.append("")

        self.track_table.delete(item_id)
        self.insert_track_row(values)
        self.renumber_tracks()
        self.sync_track_table_to_current_album()
        self.show_toast("Track moved to bottom", 1500, "success")
    
    def open_file_location(self, item_id):
        """Open the file location in file explorer"""
        # Get file path from the table
        track_values = self.track_table.item(item_id)['values']
        file_path = track_values[12] if len(track_values) > 12 else ""
        
        if not file_path:
            self.show_toast("No file path available", 2000, "warning")
            return
        
        try:
            import platform

            # Get directory
            directory = os.path.dirname(file_path)
            
            if platform.system() == "Windows":
                subprocess.Popen(['explorer', '/select,', file_path])
            elif platform.system() == "Darwin":  # macOS
                subprocess.Popen(['open', directory])
            else:  # Linux
                subprocess.Popen(['xdg-open', directory])
        except Exception as e:
            logger.exception(e)
    
    def replace_track_file(self, item_id):
        """Replace the audio file for a track"""
        if self.is_track_item_locked(item_id):
            self.show_toast("Track is locked", 1600, "warning")
            return
        from tkinter import filedialog
        
        # Open file dialog to select new file
        file_path = filedialog.askopenfilename(
            title="Select Audio File",
            filetypes=[
                ("Audio Files", "*.mp3 *.flac *.wav *.ogg *.opus *.m4a *.aac *.mod *.xm"),
                ("All Files", "*.*")
            ]
        )
        
        if not file_path:
            return
        
        try:
            # Get file info
            file_size = os.path.getsize(file_path) / (1024 * 1024)  # MB
            extension = os.path.splitext(file_path)[1].replace('.', '').upper()
            
            # Get audio length
            length = self.get_audio_length(file_path)
            
            # Get metadata
            year, genre, bitrate = self.get_track_metadata(file_path)
            
            # Format file size
            if file_size > 1024:
                size_str = f"{file_size / 1024:.1f} GB"
            else:
                size_str = f"{file_size:.1f} MB"
            
            # Get current values
            current_values = list(self.track_table.item(item_id)['values'])
            while len(current_values) < 20:
                current_values.append("")
            
            # Update with new file info (preserve artist, title, comment, price, nyp)
            current_values[4] = length  # length
            current_values[5] = extension  # extension
            current_values[8] = year  # year
            current_values[9] = genre  # genre
            current_values[10] = bitrate  # bitrate
            current_values[11] = size_str  # file size
            current_values[12] = file_path  # file path
            extra_metadata = self.get_extra_track_metadata_columns(file_path)
            current_values[13:20] = list(extra_metadata)
            
            # Update the table
            self.track_table.item(item_id, values=tuple(current_values))
            self.sync_track_table_to_current_album()
        except Exception as e:
            logger.exception(e)

    def extract_cover_art_from_track(self, item_id):
        """Extract embedded cover art from the selected track and use it as album cover."""
        track_values = self.track_table.item(item_id)['values']
        file_path = track_values[12] if len(track_values) > 12 else ""

        if not file_path or not Path(file_path).exists():
            self.show_toast("No valid track file path available", 2000, "warning")
            return

        try:
            import datetime
            import re
            import mutagen
            from mutagen.flac import FLAC
            from mutagen.mp4 import MP4Cover
            from PIL import Image

            file_data = mutagen.File(file_path)
            if file_data is None:
                messagebox.showinfo("No Cover Art Found", "Could not read metadata from this track.")
                return

            cover_data = None
            mime_type = None

            if isinstance(file_data, FLAC) and file_data.pictures:
                cover_data = file_data.pictures[0].data
                mime_type = file_data.pictures[0].mime
            elif getattr(file_data, 'tags', None) is not None:
                tags = file_data.tags
                if hasattr(tags, 'getall'):
                    pictures = tags.getall("APIC")
                    if pictures:
                        cover_data = pictures[0].data
                        mime_type = pictures[0].mime
                if cover_data is None and 'covr' in tags:
                    cover = tags['covr'][0]
                    cover_data = bytes(cover)
                    if getattr(cover, 'imageformat', None) == MP4Cover.FORMAT_PNG:
                        mime_type = 'image/png'
                    else:
                        mime_type = 'image/jpeg'

            if not cover_data:
                messagebox.showinfo("No Cover Art Found", "No embedded cover art was found in this track.")
                return

            suffix = '.png' if mime_type and 'png' in mime_type.lower() else '.jpg'
            filetype_label = "PNG Image" if suffix == '.png' else "JPEG Image"
            safe_stem = re.sub(r'[^A-Za-z0-9._-]+', '_', Path(file_path).stem).strip('._-') or 'track'
            initial_dir = self.album_path_var.get()
            if not initial_dir or not Path(initial_dir).exists():
                initial_dir = str(Path(file_path).parent)
            initial_name = f"{safe_stem}_cover{suffix}"

            cover_path = filedialog.asksaveasfilename(
                title="Save Extracted Cover Art",
                initialdir=initial_dir,
                initialfile=initial_name,
                defaultextension=suffix,
                filetypes=[
                    (filetype_label, f"*{suffix}"),
                    ("PNG Image", "*.png"),
                    ("JPEG Image", "*.jpg *.jpeg"),
                    ("All Files", "*.*"),
                ],
            )

            if not cover_path:
                return

            cover_path = Path(cover_path)

            with open(cover_path, 'wb') as f:
                f.write(cover_data)

            with Image.open(cover_path) as img:
                img.verify()

            self.cover_path_var.set(str(cover_path))
            self.add_to_cover_library(str(cover_path))
            self.show_toast("Cover art extracted from track", 2000, "success")
            logger.info(f"Extracted cover art from {file_path} to {cover_path}")

        except Exception as e:
            logger.exception(e)
            messagebox.showerror("Extract Cover Art Failed", f"Failed to extract cover art:\n{e}")

    def set_track_cover_as_album_cover(self, item_id):
        """Use the selected track's embedded artwork as the album cover."""
        track_values = self.track_table.item(item_id)['values']
        file_path = track_values[12] if len(track_values) > 12 else ""
        if not file_path or not Path(file_path).exists():
            self.show_toast("No valid track file path available", 2000, "warning")
            return

        cover_path = self.extract_first_embedded_cover_to_temp([Path(file_path)])
        if not cover_path:
            messagebox.showinfo("No Cover Art Found", "No embedded cover art was found in this track.")
            return

        self.cover_path_var.set(str(cover_path))
        self.add_to_cover_library(str(cover_path))
        self.show_toast("Track cover set as album cover", 2000, "success", trigger="cover_load")

    def extract_tracklist(self):
        """Save the current preview tracklist into the album folder."""
        rows = self.get_track_table_rows()
        if not rows:
            self.show_toast("No tracks to export", 1800, "warning")
            return

        output_dir = self.get_current_album_directory()
        output_path = output_dir / "tracklist.txt"
        album_name = self.album_name_var.get().strip() or output_dir.name
        artist = self.album_artist_var.get().strip()

        lines = [album_name]
        if artist:
            lines.append(artist)
        lines.append("")

        for index, row in enumerate(rows, 1):
            track_no = str(row[0]).strip() if len(row) > 0 and str(row[0]).strip() else str(index)
            title = str(row[2]).strip() if len(row) > 2 else ""
            track_artist = str(row[1]).strip() if len(row) > 1 else ""
            length = str(row[4]).strip() if len(row) > 4 else ""
            line = f"{track_no}. "
            if track_artist:
                line += f"{track_artist} - "
            line += title or "Untitled Track"
            if length:
                line += f" [{length}]"
            lines.append(line)

        try:
            output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            self.show_toast(f"Tracklist saved: {output_path.name}", 2000, "success", trigger="file_add")
            logger.info(f"Extracted tracklist to {output_path}")
        except Exception as e:
            logger.exception(e)
            messagebox.showerror("Extract Tracklist Failed", f"Failed to save tracklist:\n{e}")

    def open_album_session_file(self):
        """Open the current album's session.txt file."""
        session_path = self.get_album_session_file_path()
        if not session_path or not session_path.exists():
            self.show_toast("session.txt not found", 2000, "warning")
            return

        try:
            if os.name == "nt":
                os.startfile(str(session_path))
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(session_path)])
            else:
                subprocess.Popen(["xdg-open", str(session_path)])
        except Exception as e:
            logger.exception(e)
            messagebox.showerror("Open session.txt Failed", f"Could not open:\n{session_path}\n\n{e}")

    def format_track_info_value(self, value):
        """Return a readable, bounded metadata value for exported diagnostics."""
        if isinstance(value, bytes):
            return f"<bytes: {len(value)}>"
        if hasattr(value, "data") and isinstance(getattr(value, "data", None), bytes):
            mime = getattr(value, "mime", "")
            desc = getattr(value, "desc", "")
            return f"<embedded picture: {mime}, {len(value.data)} bytes, desc={desc!r}>"
        if isinstance(value, (list, tuple)):
            return ", ".join(self.format_track_info_value(item) for item in value)

        text = str(value)
        if len(text) > 1000:
            return text[:1000] + "... <truncated>"
        return text

    def extract_track_information(self, item_id):
        """Save detailed technical and metadata information for a selected track."""
        values = list(self.track_table.item(item_id).get("values", ()))
        while len(values) < 20:
            values.append("")

        file_path = Path(values[12]) if values[12] else None
        if file_path is None or not file_path.exists():
            self.show_toast("No valid track file path available", 2000, "warning")
            return

        try:
            import datetime
            import mutagen

            output_dir = self.get_current_album_directory(file_path)
            safe_stem = re.sub(r'[^A-Za-z0-9._-]+', '_', file_path.stem).strip('._-') or "track"
            output_path = output_dir / f"{safe_stem}_track_information.txt"
            stat = file_path.stat()
            file_data = mutagen.File(file_path)

            lines = [
                "Track Information",
                "",
                "[File]",
                f"Path: {file_path}",
                f"Name: {file_path.name}",
                f"Extension: {file_path.suffix}",
                f"Size: {stat.st_size} bytes ({stat.st_size / (1024 ** 2):.2f} MB)",
                f"Modified: {datetime.datetime.fromtimestamp(stat.st_mtime).isoformat(sep=' ', timespec='seconds')}",
                "",
                "[Preview Row]",
            ]

            column_labels = self.get_track_table_column_labels()
            for column_id, value in zip(list(self.track_table["columns"]), values):
                lines.append(f"{column_labels.get(column_id, column_id)}: {value}")

            lines.extend(["", "[Audio Info]"])
            if file_data is None:
                lines.append("Could not read audio metadata.")
            else:
                info = getattr(file_data, "info", None)
                lines.append(f"Container: {type(file_data).__name__}")
                lines.append(f"Info Type: {type(info).__name__ if info else ''}")
                for attr in (
                    "length", "sample_rate", "bits_per_sample", "bitrate", "channels",
                    "mode", "codec", "encoder_info", "encoder_settings",
                ):
                    if info is not None and hasattr(info, attr):
                        lines.append(f"{attr}: {getattr(info, attr)}")

                lines.extend(["", "[Metadata Tags]"])
                tags = getattr(file_data, "tags", None)
                if not tags:
                    lines.append("No tags found.")
                else:
                    tag_items = tags.items() if hasattr(tags, "items") else []
                    for key, value in sorted(tag_items, key=lambda item: str(item[0]).casefold()):
                        lines.append(f"{key}: {self.format_track_info_value(value)}")

                if hasattr(file_data, "pictures"):
                    lines.extend(["", "[Pictures]"])
                    if file_data.pictures:
                        for index, picture in enumerate(file_data.pictures, 1):
                            lines.append(
                                f"{index}. mime={picture.mime}, type={picture.type}, "
                                f"size={len(picture.data)} bytes, desc={picture.desc!r}"
                            )
                    else:
                        lines.append("No FLAC pictures found.")

            output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            self.show_toast(f"Track info saved: {output_path.name}", 2200, "success", trigger="file_add")
            logger.info(f"Extracted track information to {output_path}")
        except Exception as e:
            logger.exception(e)
            messagebox.showerror("Extract Track Information Failed", f"Failed to save track information:\n{e}")
    
    def copy_track_metadata(self, item_id):
        """Copy track metadata to clipboard"""
        # Get track values from the table
        track_values = self.track_table.item(item_id)['values']
        # Store as a dictionary for easier access
        self.copied_track_metadata = {
            'artist': track_values[1],
            'track_name': track_values[2],
            'comment': track_values[3],
            'price': track_values[6],
            'nyp': track_values[7]
        }
    
    def paste_track_metadata(self, item_id):
        """Paste copied metadata to this track"""
        if self.is_track_item_locked(item_id):
            self.show_toast("Track is locked", 1600, "warning")
            return
        if not self.copied_track_metadata:
            return
        
        # Get current values
        current_values = list(self.track_table.item(item_id)['values'])
        
        # Update with copied metadata
        current_values[1] = self.copied_track_metadata['artist']
        current_values[2] = self.copied_track_metadata['track_name']
        current_values[3] = self.copied_track_metadata['comment']
        current_values[6] = self.copied_track_metadata['price']
        current_values[7] = self.copied_track_metadata['nyp']
        
        # Update the table
        self.track_table.item(item_id, values=tuple(current_values))

    def clear_track_metadata(self, item_id):
        """Clear metadata fields for the selected track without removing its title."""
        if self.is_track_item_locked(item_id):
            self.show_toast("Track is locked", 1600, "warning")
            return
        values = list(self.track_table.item(item_id)['values'])
        while len(values) < 13:
            values.append("")

        for index in (1, 3, 8, 9, 10):
            values[index] = ""

        self.track_table.item(item_id, values=tuple(values))
        self.sync_track_table_metadata_to_current_album()
        self.show_toast("Track metadata cleared", 1500, "success")

    def revert_track_to_original(self, item_id):
        """Restore a track row from the source file metadata."""
        if self.is_track_item_locked(item_id):
            self.show_toast("Track is locked", 1600, "warning")
            return
        values = list(self.track_table.item(item_id)['values'])
        while len(values) < 20:
            values.append("")

        file_path = Path(values[12]) if values[12] else None
        if file_path is None or not file_path.exists():
            self.show_toast("No original file path available", 2000, "warning")
            return

        try:
            original_config = dataclasses.replace(
                self.config,
                ignore_all_metadata=False,
                ignore_artist_name=False,
                use_filename_as_title=False,
            )
            track = Track.from_file(file_path, original_config)
            if track is None:
                self.show_toast("Could not read original metadata", 2000, "warning")
                return

            file_size = file_path.stat().st_size / (1024 ** 2)
            size_str = f"{file_size / 1024:.1f} GB" if file_size > 1024 else f"{file_size:.1f} MB"
            year, genre, bitrate = self.get_track_metadata(file_path)
            extra_metadata = self.get_extra_track_metadata_columns(file_path)

            values[1] = track.track_data.artist
            values[2] = track.track_data.title
            values[3] = track.track_data.download_desc or getattr(track.track_data, 'about', '') or self.get_track_comment_metadata(file_path)
            values[4] = self.get_audio_length(file_path)
            values[5] = file_path.suffix
            values[6] = f"${track.track_data.price}" if track.track_data.price else ""
            values[7] = "Yes" if track.track_data.nyp else "No"
            values[8] = year
            values[9] = genre
            values[10] = bitrate
            values[11] = size_str
            values[12] = file_path
            values[13:20] = list(extra_metadata)

            self.track_table.item(item_id, values=tuple(values))
            self.sync_track_table_to_current_album()
            self.show_toast("Track reverted to original metadata", 1800, "success")
        except Exception as e:
            logger.exception(e)
            messagebox.showerror("Revert Failed", f"Failed to revert track metadata:\n{e}")

    def clear_all_track_metadata(self):
        """Clear metadata fields for every visible track without removing titles."""
        items = list(self.track_table.get_children())
        if not items:
            self.show_toast("No tracks to update", 2000, "warning")
            return

        for item in items:
            if self.is_track_item_locked(item):
                continue
            values = list(self.track_table.item(item)['values'])
            while len(values) < 13:
                values.append("")
            for index in (1, 3, 8, 9, 10):
                values[index] = ""
            self.track_table.item(item, values=tuple(values))

        self.sync_track_table_metadata_to_current_album()
        self.show_toast("All track metadata cleared", 2000, "success")

    def sync_track_table_metadata_to_current_album(self):
        """Push editable table metadata into current_album when it is available."""
        self.sync_track_table_to_current_album()
    
    def on_filename_as_title_changed(self):
        """Handle changes to the 'Use filename as title' checkbox"""
        if self.is_upload_in_progress():
            return

        try:
            self.config.use_filename_as_title = self.filename_as_title_var.get()
            save_config(self.config)
            self.sync_track_table_to_current_album()
            if getattr(self.config, 'notify_on_settings_save', False):
                self.show_toast("Setting applied", 1500, "success", trigger="settings_save")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to update setting:\n{e}")
            logger.exception(e)

    def on_ignore_metadata_changed(self):
        """Handle changes to the 'Ignore metadata' checkbox"""
        if self.is_upload_in_progress():
            return

        try:
            self.config.ignore_all_metadata = self.ignore_metadata_var.get()
            save_config(self.config)
            self.update_preview_artist_visibility()
            if getattr(self.config, 'notify_on_settings_save', False):
                self.show_toast("Setting applied", 1500, "success", trigger="settings_save")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to update setting:\n{e}")
            logger.exception(e)

    def on_ignore_artist_changed(self):
        """Handle changes to the 'Ignore artist' checkbox"""
        if self.is_upload_in_progress():
            return

        try:
            self.config.ignore_artist_name = self.ignore_artist_var.get()
            save_config(self.config)
            self.update_preview_artist_visibility()
            if getattr(self.config, 'notify_on_settings_save', False):
                self.show_toast("Setting applied", 1500, "success", trigger="settings_save")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to update setting:\n{e}")
            logger.exception(e)

    def update_preview_artist_visibility(self):
        """Apply artist visibility settings without rebuilding track titles or metadata."""
        if not hasattr(self, 'track_table'):
            return

        hide_artist = self.ignore_artist_var.get() or self.ignore_metadata_var.get()
        for item in self.track_table.get_children():
            values = list(self.track_table.item(item)['values'])
            while len(values) < 13:
                values.append("")

            if hide_artist:
                values[1] = ""
            elif not str(values[1]).strip():
                values[1] = self.get_track_artist_metadata(values[12])

            self.track_table.item(item, values=tuple(values))

        self.sync_track_table_to_current_album()
    
    def start_upload(self):
        """Start album upload in background thread"""
        if self.upload_thread and self.upload_thread.is_alive():
            messagebox.showwarning("Upload Running", "An upload is already in progress.")
            return

        if not self.session or not self.selected_artist_url:
            messagebox.showerror("Error", "Please select an artist first")
            return
        
        album_path = self.album_path_var.get()
        if not album_path and not self.manual_tracks:
            messagebox.showerror("Error", "Please select an album folder or add tracks")
            return

        self.sync_track_table_to_current_album()
        upload_description_text = self.get_album_description_text()

        # Confirm upload if setting is enabled
        if self.config.confirm_before_upload:
            if not messagebox.askyesno(
                "Confirm Upload",
                f"Upload album to {self.selected_artist_url}?\n\nThis will create a new album on Bandcamp."
            ):
                return

        upload_credits = self.credits_text.get("1.0", "end-1c")
        self.prepare_upload_progress_from_table()
        self.upload_cancel_event = threading.Event()
        
        # Disable all controls except cancel button
        self.disable_ui_during_upload()
        self.set_cancel_buttons_state(tk.NORMAL)
        self.update_status("Starting upload...", 0)

        if getattr(self.config, 'open_logs_on_upload', False):
            for tab_id in self.notebook.tabs():
                if self.notebook.tab(tab_id, "text") == "Logs":
                    self.notebook.select(tab_id)
                    break

        def upload():
            try:
                logger.info("Starting upload process")
                
                # Apply ignore artist name setting from checkbox to config
                self.config.ignore_artist_name = self.ignore_artist_var.get()
                if self.config.ignore_artist_name:
                    logger.info("Ignoring artist name from metadata")
                
                self.update_status("Processing album...", 10)
                
                # Build album from manual tracks if available, otherwise from directory
                if self.manual_tracks:
                    logger.info(f"Building album from {len(self.manual_tracks)} manually added tracks")
                    from bandcamp_auto_uploader.upload import Track, BandcampAlbumData
                    
                    # Get album name
                    album_name = self.album_name_var.get().strip()
                    if not album_name:
                        album_name = "Untitled Album"
                    
                    album_data = BandcampAlbumData(
                        title=album_name,
                        price=str(self.config.album_price),
                        nyp=int(self.config.name_your_price),
                    )
                    
                    # Create tracks from manual files
                    tracks = []
                    for i, track_path in enumerate(self.manual_tracks, 1):
                        track = Track.from_file(track_path, self.config)
                        if track:
                            # Set track number based on order
                            track.track_data.track_number = i
                            table_values = self.get_track_table_values(track_path, i - 1)
                            if len(table_values) > 1:
                                track.track_data.artist = table_values[1]
                            if len(table_values) > 2 and table_values[2]:
                                track.track_data.title = table_values[2]
                            if len(table_values) > 3:
                                track.track_data.download_desc = table_values[3]
                            tracks.append(track)
                            logger.info(f"  {i}. {track.track_data.title}")
                    
                    # Auto-detect cover if available
                    cover_art = None
                    if album_path:
                        path = Path(album_path)
                        for ext in (".jpg", ".png", ".jpeg", ".gif"):
                            cover_file = path / ("cover" + ext)
                            if cover_file.exists():
                                from bandcamp_auto_uploader.upload import CoverArt
                                cover_art = CoverArt(path=cover_file)
                                logger.info(f"Auto-detected cover art: {cover_file}")
                                break
                    
                    album = Album(album_data, tracks, cover_art)
                else:
                    path = Path(album_path)
                    has_current_album_for_path = (
                        hasattr(self, 'current_album')
                        and self.current_album is not None
                        and getattr(self.current_album, 'tracks', None)
                        and all(track.path.parent == path for track in self.current_album.tracks)
                    )
                    if has_current_album_for_path:
                        album = self.current_album
                        logger.info("Using current album track order from preview/reorder")
                    else:
                        album = Album.from_directory(path, self.config)
                
                # Update album name if provided
                album_name = self.album_name_var.get().strip()
                if album_name:
                    album.album_data.title = album_name
                    logger.info(f"Using custom album name: {album_name}")
                
                # Update artist if provided
                album_artist = self.album_artist_var.get().strip()
                if album_artist:
                    logger.info(f"Using custom artist: {album_artist}")
                    # Set album artist
                    album.album_data.artist = album_artist
                
                # Update tags if provided
                tags = self.album_tags_var.get().strip()
                if tags:
                    album.album_data.tags = tags
                    logger.info(f"Using tags: {tags}")

                # Update publishing details
                publish_date = self.album_publish_date_var.get().strip()
                if publish_date:
                    album.album_data.release_date = publish_date
                    logger.info(f"Using release date: {publish_date}")

                record_label = self.album_record_label_var.get().strip()
                if record_label:
                    album.album_data.label_name = record_label
                    logger.info(f"Using record label: {record_label}")

                catalog_number = self.album_catalog_number_var.get().strip()
                if catalog_number:
                    album.album_data.cat_number = catalog_number
                    logger.info(f"Using catalog number: {catalog_number}")

                upc = self.album_upc_var.get().strip()
                if upc:
                    album.album_data.upc = upc
                    logger.info(f"Using UPC/EAN: {upc}")

                download_desc = self.album_download_desc_var.get().strip()
                if download_desc:
                    album.album_data.download_desc = download_desc
                    logger.info(f"Using download description: {download_desc}")

                release_message = self.album_release_message_var.get().strip()
                if release_message:
                    album.album_data.tralbum_release_message = release_message
                    logger.info(f"Using release message: {release_message}")

                # Set album description and credits after the final album object is ready.
                upload_description = self.prepare_upload_description_from_template(
                    rows=self.get_album_description_rows(album),
                    current_description=upload_description_text,
                    update_widget=True,
                )
                album.album_data.about = upload_description
                logger.info(f"Using album description ({len(upload_description)} characters)")

                album.album_data.credits = self.build_album_upload_credits(upload_credits)
                logger.info("Using album credits with uploader footer")

                # Set license type for all tracks
                license = self.album_license_var.get().strip()
                if license:
                    # Map license names to Bandcamp license type IDs
                    license_map = {
                        "All Rights Reserved": "1",
                        "CC Attribution": "2",
                        "CC Attribution-ShareAlike": "3",
                        "CC Attribution-NoDerivatives": "4",
                        "CC Attribution-NonCommercial": "5",
                        "CC Attribution-NonCommercial-ShareAlike": "6",
                        "CC Attribution-NonCommercial-NoDerivatives": "7",
                        "Public Domain": "8"
                    }
                    license_id = license_map.get(license, "1")
                    for track in album.tracks:
                        track.track_data.license_type = license_id
                    logger.info(f"Using license - {license} (type={license_id})")

                self.root.after(0, lambda tracks=list(album.tracks): self.prepare_upload_progress_tracks(tracks))
                self.update_status("Processing cover art...", 20)
                
                # Handle custom cover art
                cover_path = self.cover_path_var.get()
                if cover_path:
                    logger.info(f"Using custom cover art: {cover_path}")
                    cover_file = Path(cover_path)
                    
                    # Scale cover art if requested
                    if self.scale_cover_var.get():
                        size_str = self.scale_size_var.get()
                        target_size = int(size_str.split('x')[0])
                        logger.info(f"Scaling cover art to {size_str}...")
                        
                        import io

                        img = self.normalize_cover_image(cover_file, "#ffffff")
                        img = self.crop_cover_to_square(img)
                        img = self.apply_custom_scaling(img, target_size)
                        
                        # Save to bytes
                        img_bytes = io.BytesIO()
                        img.save(img_bytes, format='JPEG', quality=95)
                        img_bytes.seek(0)
                        
                        from bandcamp_auto_uploader.upload import CoverArt
                        album.cover_art = CoverArt(data=img_bytes.read(), file_name="cover.jpg")
                        logger.info(f"Cover art scaled to {size_str}")
                    else:
                        from bandcamp_auto_uploader.upload import CoverArt
                        album.cover_art = CoverArt(path=cover_file)
                
                self.update_status("Uploading to Bandcamp...", 60)

                def progress_callback(event, payload):
                    self.root.after(0, lambda e=event, p=dict(payload): self.handle_upload_progress_event(e, p))

                upload_result = album.upload(
                    self.session, 
                    self.selected_artist_url,
                    timeout=self.config.upload_timeout,
                    retry_delay=self.config.retry_delay,
                    retry_failed=self.config.retry_failed_uploads,
                    retry_attempts=self.config.retry_attempts,
                    progress_callback=progress_callback,
                    cancel_event=self.upload_cancel_event
                )
                album_url = upload_result.get("album_url") if isinstance(upload_result, dict) else None
                
                logger.info("Upload completed successfully!")
                if album_url:
                    logger.info(f"Uploaded album URL: {album_url}")
                
                self.update_status("Upload complete!", 100)
                
                # Add to upload history
                self.root.after(0, lambda: self.add_upload_to_history(
                    album.album_data.title,
                    self.artist_var.get()
                ))
                
                self.root.after(0, lambda: messagebox.showinfo(
                    "Upload Complete",
                    f"Album '{album.album_data.title}' uploaded successfully!"
                ))

                if getattr(self.config, 'copy_album_url_after_upload', False) and album_url:
                    self.root.after(0, lambda url=album_url: self.copy_uploaded_album_url(url))

                if getattr(self.config, 'open_album_page_after_upload', True) and album_url:
                    self.root.after(0, lambda url=album_url: self.open_uploaded_album_page(url))
                
                # Clear manual tracks after successful upload
                if self.manual_tracks:
                    self.root.after(0, lambda: self.manual_tracks.clear())
                    self.root.after(0, lambda: self.update_manual_tracks_preview())
                    logger.info("Cleared manually added tracks after successful upload")
                
                self.root.after(100, lambda: self.show_toast("Album uploaded successfully!", 3000, "success", trigger="upload_success"))
            except UploadCancelled:
                logger.warning("Upload stopped after user cancellation")
                self.update_status("Upload cancelled", None)
                self.root.after(
                    100,
                    lambda: self.show_toast("Upload cancelled", 2500, "warning")
                )
            except Exception as e:
                exc_info = sys.exc_info()
                error_message = str(e)
                logger.exception(e)
                self.update_status("Upload failed", None)
                self.root.after(
                    0,
                    lambda msg=error_message, info=exc_info: self.show_bug_log_prompt(
                        "Upload Failed",
                        f"Upload failed:\n\n{msg}",
                        error_text=msg,
                        exc_info=info,
                    )
                )
                self.root.after(100, lambda: self.show_toast("Upload failed - check logs", 3000, "error", trigger="upload_error"))
            finally:
                self.root.after(0, self.upload_finished)
                self.root.after(1000, lambda: self.update_status("Ready", None))
        
        self.upload_thread = threading.Thread(target=upload, daemon=True)
        self.upload_thread.start()

    def open_uploaded_album_page(self, album_url):
        """Open the uploaded Bandcamp album page in the default browser."""
        if not album_url:
            return

        try:
            webbrowser.open(album_url)
            self.show_toast("Opened uploaded album page", 2200, "success", trigger="upload_success")
        except Exception as e:
            logger.warning(f"Failed to open uploaded album page {album_url}: {e}")

    def copy_uploaded_album_url(self, album_url):
        """Copy the uploaded Bandcamp album URL to the clipboard."""
        if not album_url:
            return

        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(album_url)
            logger.info(f"Copied uploaded album URL to clipboard: {album_url}")
        except Exception as e:
            logger.warning(f"Failed to copy uploaded album URL {album_url}: {e}")
    
    def cancel_upload(self):
        """Cancel ongoing upload"""
        if not self.upload_thread or not self.upload_thread.is_alive():
            self.set_cancel_buttons_state(tk.DISABLED)
            return

        if messagebox.askyesno("Cancel Upload", "Are you sure you want to cancel?\n\nThis may leave the upload in an incomplete state."):
            logger.warning("Upload cancellation requested by user")
            self.upload_cancel_event.set()
            self.set_cancel_buttons_state(tk.DISABLED)
            self.handle_upload_progress_event("album_cancelled", {"message": "Cancelling after current step..."})
            self.update_status("Cancelling upload...", None)

    def set_cancel_buttons_state(self, state):
        """Keep upload cancel buttons in sync across tabs."""
        if hasattr(self, 'cancel_btn'):
            self.cancel_btn['state'] = state
        if hasattr(self, 'log_cancel_btn'):
            self.log_cancel_btn['state'] = state

    def is_upload_in_progress(self):
        """Return True while the background upload worker is active."""
        return bool(self.upload_thread and self.upload_thread.is_alive())

    def set_widget_state_if_exists(self, attr_name, state):
        """Set a Tk widget state when the widget has been created."""
        widget = getattr(self, attr_name, None)
        if widget is None:
            return
        try:
            widget.configure(state=state)
        except tk.TclError:
            pass

    def set_upload_interaction_state(self, state):
        """Enable or disable controls that must not mutate the album during upload."""
        widget_states = {
            "refresh_btn": state,
            "album_browse_btn": state,
            "open_folder_btn": state,
            "reload_album_btn": state,
            "album_path_entry": state,
            "ignore_artist_check": state,
            "filename_as_title_check": state,
            "ignore_metadata_check": state,
            "guess_case_btn": state,
            "extract_filename_btn": state,
            "add_track_btn": state,
            "cover_entry": state,
            "browse_cover_btn": state,
            "view_cover_btn": state,
            "library_cover_btn": state,
            "detect_cover_btn": state,
            "scale_cover_check": state,
        }
        for attr_name, widget_state in widget_states.items():
            self.set_widget_state_if_exists(attr_name, widget_state)

        combo_state = "readonly" if state == tk.NORMAL else tk.DISABLED
        self.set_widget_state_if_exists("scale_size_combo", combo_state)
    
    def disable_ui_during_upload(self):
        """Disable all UI controls during upload except cancel button"""
        # Disable all buttons in the upload tab
        if hasattr(self, 'upload_btn'):
            self.upload_btn['state'] = tk.DISABLED

        if hasattr(self, 'load_cookies_btn'):
            self.load_cookies_btn['state'] = tk.DISABLED

        self.set_upload_interaction_state(tk.DISABLED)

        # Disable artist dropdown
        if hasattr(self, 'artist_dropdown'):
            self.artist_dropdown['state'] = tk.DISABLED

        # Disable all album detail fields
        self.disable_album_details()

        # Track table doesn't support state option, so we skip it
        # The context menu and other interactions will be disabled by disabling the parent frame

    def enable_ui_after_upload(self):
        """Re-enable all UI controls after upload completes"""
        # Switch back to Upload tab
        for tab_id in self.notebook.tabs():
            if self.notebook.tab(tab_id, "text") == "Upload":
                self.notebook.select(tab_id)
                break

        # Enable buttons
        if hasattr(self, 'upload_btn'):
            self.upload_btn['state'] = tk.NORMAL

        if hasattr(self, 'load_cookies_btn'):
            self.load_cookies_btn['state'] = tk.NORMAL

        self.set_upload_interaction_state(tk.NORMAL)

        # Enable artist dropdown
        if hasattr(self, 'artist_dropdown'):
            self.artist_dropdown['state'] = "readonly"

        # Enable album details
        self.enable_album_details()

        # Track table doesn't support state option, so we skip it

    def disable_album_details(self):
        """Disable all album detail input fields"""
        # Disable album name
        if hasattr(self, 'album_name_entry'):
            self.album_name_entry['state'] = tk.DISABLED
        if hasattr(self, 'album_name_auto_btn'):
            self.album_name_auto_btn['state'] = tk.DISABLED

        # Disable artist
        if hasattr(self, 'album_artist_entry'):
            self.album_artist_entry['state'] = tk.DISABLED
        if hasattr(self, 'album_artist_auto_btn'):
            self.album_artist_auto_btn['state'] = tk.DISABLED

        # Disable release date
        if hasattr(self, 'album_release_date_entry'):
            self.album_release_date_entry['state'] = tk.DISABLED
        if hasattr(self, 'album_release_date_btn'):
            self.album_release_date_btn['state'] = tk.DISABLED

        # Disable tags
        if hasattr(self, 'tag_entry'):
            self.tag_entry['state'] = tk.DISABLED
        if hasattr(self, 'edit_tags_btn'):
            self.edit_tags_btn['state'] = tk.DISABLED

        # Disable description
        if hasattr(self, 'desc_text'):
            self.desc_text['state'] = tk.DISABLED

        # Disable credits
        if hasattr(self, 'credits_text'):
            self.credits_text['state'] = tk.DISABLED

        # Disable license
        if hasattr(self, 'album_license_combo'):
            self.album_license_combo['state'] = tk.DISABLED

        # Disable download description
        if hasattr(self, 'album_download_desc_entry'):
            self.album_download_desc_entry['state'] = tk.DISABLED

        # Disable release message
        if hasattr(self, 'album_release_message_entry'):
            self.album_release_message_entry['state'] = tk.DISABLED

        # Disable record label
        if hasattr(self, 'album_record_label_entry'):
            self.album_record_label_entry['state'] = tk.DISABLED

        # Disable catalog number
        if hasattr(self, 'album_catalog_number_entry'):
            self.album_catalog_number_entry['state'] = tk.DISABLED

        # Disable UPC
        if hasattr(self, 'album_upc_entry'):
            self.album_upc_entry['state'] = tk.DISABLED

        # Disable album path entry
        if hasattr(self, 'album_path_entry'):
            self.album_path_entry['state'] = tk.DISABLED

    def enable_album_details(self):
        """Enable all album detail input fields"""
        # Enable album name
        if hasattr(self, 'album_name_entry'):
            self.album_name_entry['state'] = tk.NORMAL
        if hasattr(self, 'album_name_auto_btn'):
            self.album_name_auto_btn['state'] = tk.NORMAL

        # Enable artist
        if hasattr(self, 'album_artist_entry'):
            self.album_artist_entry['state'] = tk.NORMAL
        if hasattr(self, 'album_artist_auto_btn'):
            self.album_artist_auto_btn['state'] = tk.NORMAL

        # Enable release date
        if hasattr(self, 'album_release_date_entry'):
            self.album_release_date_entry['state'] = tk.NORMAL
        if hasattr(self, 'album_release_date_btn'):
            self.album_release_date_btn['state'] = tk.NORMAL

        # Enable tags
        if hasattr(self, 'tag_entry'):
            self.tag_entry['state'] = tk.NORMAL
        if hasattr(self, 'edit_tags_btn'):
            self.edit_tags_btn['state'] = tk.NORMAL

        # Enable description
        if hasattr(self, 'desc_text'):
            self.desc_text['state'] = tk.NORMAL

        # Enable credits
        if hasattr(self, 'credits_text'):
            self.credits_text['state'] = tk.NORMAL

        # Enable license
        if hasattr(self, 'album_license_combo'):
            self.album_license_combo['state'] = "readonly"

        # Enable download description
        if hasattr(self, 'album_download_desc_entry'):
            self.album_download_desc_entry['state'] = tk.NORMAL

        # Enable release message
        if hasattr(self, 'album_release_message_entry'):
            self.album_release_message_entry['state'] = tk.NORMAL

        # Enable record label
        if hasattr(self, 'album_record_label_entry'):
            self.album_record_label_entry['state'] = tk.NORMAL

        # Enable catalog number
        if hasattr(self, 'album_catalog_number_entry'):
            self.album_catalog_number_entry['state'] = tk.NORMAL

        # Enable UPC
        if hasattr(self, 'album_upc_entry'):
            self.album_upc_entry['state'] = tk.NORMAL

        # Enable album path entry
        if hasattr(self, 'album_path_entry'):
            self.album_path_entry['state'] = tk.NORMAL

    def upload_finished(self):
        """Reset UI after upload completes or is cancelled"""
        self.enable_ui_after_upload()
        self.set_cancel_buttons_state(tk.DISABLED)
    
    def add_track_to_album(self):
        """Add individual track files to the current album"""
        if self.is_upload_in_progress():
            self.show_toast("Upload in progress", 1600, "warning")
            return

        track_files = filedialog.askopenfilenames(
            title="Select Track Files",
            filetypes=[
                ("Audio files", "*.wav *.flac *.aiff *.mp3 *.ogg *.opus *.m4a *.aac *.mod *.xm"),
                ("WAV", "*.wav"),
                ("FLAC", "*.flac"),
                ("AIFF", "*.aiff"),
                ("MP3", "*.mp3"),
                ("OGG", "*.ogg"),
                ("Opus", "*.opus"),
                ("M4A/AAC", "*.m4a *.aac"),
                ("Tracker Modules", "*.mod *.xm"),
                ("All files", "*.*")
            ]
        )

        if not track_files:
            return

        for track_file in track_files:
            track_path = Path(track_file)
            if track_path not in self.manual_tracks:
                self.manual_tracks.append(track_path)
                logger.info(f"Added track: {track_path.name}")

        self.sort_manual_tracks_by_metadata_numbers()
        self.show_toast(f"Added {len(track_files)} track(s)", 2000, "success", trigger="track_add")

        # Treat as new album - clear album folder path since we're building from tracks
        self.album_path_var.set("")
        self.current_album = None

        # Update preview to show tracks
        self.update_manual_tracks_preview()

        # Enable upload button if we have tracks
        if self.manual_tracks:
            self.upload_btn['state'] = tk.NORMAL

    def sort_manual_tracks_by_metadata_numbers(self):
        """Prioritize embedded track-number metadata while preserving manual order as fallback."""
        indexed_tracks = list(enumerate(self.manual_tracks))
        indexed_tracks.sort(
            key=lambda item: (
                get_metadata_track_number(item[1]) is None,
                get_metadata_track_number(item[1]) or 0,
                item[0],
                item[1].name.casefold(),
            )
        )
        self.manual_tracks = [track_path for _index, track_path in indexed_tracks]
    
    def clear_manual_tracks(self):
        """Clear all manually added tracks"""
        if not self.manual_tracks:
            # Also clear the table if no manual tracks
            for item in self.track_table.get_children():
                self.track_table.delete(item)
            self.locked_track_keys.clear()
            return

        if messagebox.askyesno("Clear Tracks", f"Clear all {len(self.manual_tracks)} added tracks?"):
            self.manual_tracks.clear()
            self.locked_track_keys.clear()
            logger.info("Cleared all manually added tracks")
            self.show_toast("All tracks cleared", 2000, "info")

            # Update preview
            self.update_manual_tracks_preview()

            # Disable upload button if no album path either
            if not self.album_path_var.get():
                self.upload_btn['state'] = tk.DISABLED
    
    def update_manual_tracks_preview(self):
        """Update preview to show manually added tracks"""
        # Clear existing table
        for item in self.track_table.get_children():
            self.track_table.delete(item)

        if not self.manual_tracks:
            return

        # Detect release type based on track count
        track_count = len(self.manual_tracks)
        if track_count <= 3:
            release_type = "Single"
        elif track_count <= 6:
            release_type = "EP"
        else:
            release_type = "Album"
        
        # Extract metadata from first track for auto-tagging
        metadata = {}
        if self.manual_tracks:
            first_track = self.manual_tracks[0]
            try:
                ext = first_track.suffix.lower()
                if ext == '.mp3':
                    audio = MP3(first_track)
                elif ext == '.flac':
                    audio = FLAC(first_track)
                elif ext == '.ogg':
                    audio = OggVorbis(first_track)
                elif ext == '.opus':
                    audio = OggOpus(first_track)
                elif ext in ('.m4a', '.aac'):
                    audio = MP4(first_track)
                elif ext in ('.wav', '.wave'):
                    audio = WAVE(first_track)
                elif ext in ('.aiff', '.aif'):
                    audio = AIFF(first_track)
                else:
                    audio = None
                
                if audio:
                    # Extract metadata
                    if 'album' in audio:
                        metadata['album'] = audio['album'][0]
                    elif 'TALB' in audio:
                        metadata['album'] = audio['TALB'][0]
                    elif '\xa9alb' in audio:
                        metadata['album'] = audio['\xa9alb'][0]
                    
                    if 'artist' in audio:
                        metadata['artist'] = audio['artist'][0]
                    elif 'TPE1' in audio:
                        metadata['artist'] = audio['TPE1'][0]
                    elif '\xa9ART' in audio:
                        metadata['artist'] = audio['\xa9ART'][0]
                    
                    if 'date' in audio:
                        metadata['year'] = audio['date'][0]
                    elif 'TDRC' in audio:
                        metadata['year'] = str(audio['TDRC'])
                    elif 'TYER' in audio:
                        metadata['year'] = audio['TYER'][0]
                    elif '\xa9day' in audio:
                        metadata['year'] = audio['\xa9day'][0]
                    
                    if 'genre' in audio:
                        metadata['genre'] = audio['genre'][0]
                    elif 'TCON' in audio:
                        metadata['genre'] = audio['TCON'][0]
                    elif '\xa9gen' in audio:
                        metadata['genre'] = str(audio['\xa9gen'][0])
                    
                    if 'comment' in audio:
                        metadata['comment'] = audio['comment'][0]
                    elif 'COMM' in audio:
                        metadata['comment'] = audio['COMM'][0]
                    elif '\xa9cmt' in audio:
                        metadata['comment'] = audio['\xa9cmt'][0]
                    
                    if 'title' in audio:
                        metadata['title'] = audio['title'][0]
                    elif 'TIT2' in audio:
                        metadata['title'] = audio['TIT2'][0]
                    elif '\xa9nam' in audio:
                        metadata['title'] = audio['\xa9nam'][0]
                    
                    if 'albumartist' in audio:
                        metadata['albumartist'] = audio['albumartist'][0]
                    elif 'TPE2' in audio:
                        metadata['albumartist'] = audio['TPE2'][0]
                    elif 'aART' in audio:
                        metadata['albumartist'] = audio['aART'][0]
                    
                    if 'composer' in audio:
                        metadata['composer'] = audio['composer'][0]
                    elif 'TCOM' in audio:
                        metadata['composer'] = audio['TCOM'][0]
                    elif '\xa9wrt' in audio:
                        metadata['composer'] = audio['\xa9wrt'][0]
                    
                    if 'tracknumber' in audio:
                        metadata['tracknumber'] = str(audio['tracknumber'][0])
                    elif 'TRCK' in audio:
                        metadata['tracknumber'] = audio['TRCK'][0]
                    elif 'trkn' in audio and audio['trkn']:
                        metadata['tracknumber'] = str(audio['trkn'][0][0])
                    
                    if hasattr(audio, 'info') and hasattr(audio.info, 'length'):
                        duration_seconds = int(audio.info.length)
                        minutes = duration_seconds // 60
                        seconds = duration_seconds % 60
                        metadata['duration'] = f"{minutes}:{seconds:02d}"
                    
                    if hasattr(audio, 'info') and hasattr(audio.info, 'bitrate'):
                        bitrate_kbps = audio.info.bitrate // 1000
                        metadata['bitrate'] = f"{bitrate_kbps}kbps"
            except Exception as e:
                logger.debug(f"Failed to extract metadata from first track: {e}")

        album_values = []
        release_date_values = []
        for track_path in self.manual_tracks:
            try:
                track_ext = track_path.suffix.lower()
                if track_ext == '.mp3':
                    track_audio = MP3(track_path)
                elif track_ext == '.flac':
                    track_audio = FLAC(track_path)
                elif track_ext == '.ogg':
                    track_audio = OggVorbis(track_path)
                elif track_ext == '.opus':
                    track_audio = OggOpus(track_path)
                elif track_ext in ('.m4a', '.aac'):
                    track_audio = MP4(track_path)
                elif track_ext in ('.wav', '.wave'):
                    track_audio = WAVE(track_path)
                elif track_ext in ('.aiff', '.aif'):
                    track_audio = AIFF(track_path)
                else:
                    continue

                album_value = self.get_audio_metadata_value(track_audio, ('album', 'TALB', '\xa9alb'))
                if album_value:
                    album_values.append(album_value)

                release_date_value = self.get_audio_metadata_value(
                    track_audio,
                    ('date', 'originaldate', 'releasedate', 'TDRC', 'TDOR', 'TYER', '\xa9day')
                )
                normalized_release_date = self.normalize_metadata_release_date(release_date_value)
                if normalized_release_date:
                    release_date_values.append(normalized_release_date)
            except Exception as e:
                logger.debug(f"Failed to scan manual track album metadata from {track_path}: {e}")

        guessed_album = self.choose_common_metadata_value(album_values)
        guessed_release_date = self.choose_common_metadata_value(release_date_values)

        if self.config.auto_load_metadata:
            if (
                getattr(self.config, 'guess_album_title_from_track_metadata', True)
                and guessed_album
                and not self.album_name_var.get()
            ):
                self.album_name_var.set(guessed_album)

            if (
                getattr(self.config, 'guess_release_date_from_track_metadata', True)
                and guessed_release_date
                and not self.album_publish_date_var.get()
            ):
                self.album_publish_date_var.set(guessed_release_date)

            # Auto-fill artist from first track's metadata
            if not self.album_artist_var.get() and self.manual_tracks:
                first_track = self.manual_tracks[0]
                try:
                    ext = first_track.suffix.lower()
                    if ext == '.flac':
                        track_audio = FLAC(first_track)
                    elif ext == '.mp3':
                        track_audio = MP3(first_track)
                    elif ext == '.ogg':
                        track_audio = OggVorbis(first_track)
                    elif ext == '.opus':
                        track_audio = OggOpus(first_track)
                    elif ext in ('.m4a', '.aac'):
                        track_audio = MP4(first_track)
                    elif ext in ('.wav', '.wave'):
                        track_audio = WAVE(first_track)
                    elif ext in ('.aiff', '.aif'):
                        track_audio = AIFF(first_track)
                    else:
                        track_audio = None

                    if track_audio:
                        if getattr(self.config, 'use_album_artist_in_album_details', False):
                            artist_value = self.get_audio_metadata_value(track_audio, ('albumartist', 'TPE2', 'aART'))
                        else:
                            artist_value = self.get_audio_metadata_value(track_audio, ('artist', 'TPE1', '\xa9ART'))
                        if artist_value:
                            self.album_artist_var.set(artist_value)
                except Exception as e:
                    logger.debug(f"Failed to get artist from first manual track: {e}")

            if (
                getattr(self.config, 'use_folder_name_when_album_missing', True)
                and not guessed_album
                and self.manual_tracks
                and not self.album_name_var.get()
            ):
                first_parent = self.manual_tracks[0].parent
                if all(track.parent == first_parent for track in self.manual_tracks):
                    self.album_name_var.set(first_parent.name)

        if guessed_album and 'album' not in metadata:
            metadata['album'] = guessed_album
        
        # Add release type to metadata for auto-tagging
        metadata['release_type'] = release_type
        
        # Auto-tag metadata to tags field based on settings
        tag_mappings = [
            ('year', self.config.auto_tag_year),
            ('genre', self.config.auto_tag_genre),
            ('artist', self.config.auto_tag_artist),
            ('album', self.config.auto_tag_album),
            ('comment', self.config.auto_tag_comment),
            ('title', self.config.auto_tag_track_title),
            ('albumartist', self.config.auto_tag_album_artist),
            ('composer', self.config.auto_tag_composer),
            ('tracknumber', self.config.auto_tag_track_number),
            ('duration', self.config.auto_tag_duration),
            ('bitrate', self.config.auto_tag_bitrate),
            ('release_type', self.config.auto_tag_release_type)
        ]
        
        # Get existing tags from the entry
        existing_tags_text = self.album_tags_var.get()
        existing_tags = [tag.strip() for tag in existing_tags_text.split(',') if tag.strip()]
        
        tags_added = 0
        for tag_key, setting_enabled in tag_mappings:
            if tag_key in metadata and setting_enabled:
                tag_value = metadata[tag_key]
                if tag_value and tag_value not in existing_tags:
                    existing_tags.append(tag_value)
                    tags_added += 1
        
        # Update the tag entry and variable (validation will handle limit)
        new_tags_text = ', '.join(existing_tags)
        self.album_tags_var.set(new_tags_text)
        if hasattr(self, 'tag_entry'):
            self.tag_entry.delete(0, tk.END)
            self.tag_entry.insert(0, new_tags_text)
            # Trigger validation to enforce 10 tag limit
            self.validate_tag_limit()
        
        if tags_added > 0:
            logger.info(f"Auto-tagged {tags_added} metadata fields from manual tracks")

        # Populate table with manual tracks
        for i, track_path in enumerate(self.manual_tracks, 1):
            file_size = track_path.stat().st_size / (1024**2) if track_path.exists() else 0
            extension = track_path.suffix if track_path.exists() else ""

            # Use filename as title if checkbox is checked
            if self.filename_as_title_var.get():
                title = track_path.stem
            else:
                title = track_path.stem  # Default to stem for now

            # Get metadata from file
            year, genre, bitrate = self.get_track_metadata(track_path)
            length = self.get_audio_length(track_path)
            
            # Format file size
            if file_size > 1024:
                size_str = f"{file_size / 1024:.1f} GB"
            else:
                size_str = f"{file_size:.1f} MB"

            # Placeholder values for manual tracks
            artist = ""
            comment = self.get_track_comment_metadata(track_path)
            price = ""
            nyp = ""

            extra_metadata = self.get_extra_track_metadata_columns(track_path)
            self.track_table.insert("", tk.END, values=(
                i, artist, title, comment, length, extension, price, nyp,
                year, genre, bitrate, size_str, track_path, *extra_metadata
            ), tags=("normal",))

        self.maybe_auto_fit_track_columns()
    



    def bind_keyboard_shortcuts(self):
        """Bind keyboard shortcuts for common actions"""
        # Ctrl+S: Save (if in album editor)
        self.root.bind('<Control-s>', lambda e: self.save_shortcut())
        # Ctrl+Z: Undo
        self.root.bind('<Control-z>', lambda e: self.undo_action())
        # Ctrl+Y: Redo
        self.root.bind('<Control-y>', lambda e: self.redo_action())
        # F5: Refresh current tab
        self.root.bind('<F5>', lambda e: self.refresh_current_tab())

    def update_status(self, message: str, progress: Optional[int] = None):
        """No-op - status bar removed"""
        pass
    
    def show_toast(self, message: str, duration: int = 3000, toast_type: str = "info", trigger: str = None):
        """Show a non-blocking toast notification
        
        Args:
            message: The message to display
            duration: Duration in milliseconds
            toast_type: Type of toast (info, success, warning, error)
            trigger: Optional trigger name to check if notification should be shown
        """
        # Check if toasts are enabled
        if getattr(self.config, 'enable_toasts', True) == False:
            return
            
        # Check if trigger is enabled (if provided)
        if trigger:
            trigger_config = f"notify_on_{trigger}"
            if not getattr(self.config, trigger_config, False):
                return

        # Use Windows native notifications if enabled and available
        # Note: windows-toasts library allows custom app names and is more modern than win10toast
        if getattr(self.config, 'windows_notifications', False) and self.windows_toasts_available:
            try:
                from windows_toasts import Toast, WindowsToaster
                toaster = WindowsToaster('Bandcamp Auto Uploader')
                
                # Create toast with custom app name
                newToast = Toast()
                newToast.text_fields = [message]
                
                # Show toast
                toaster.show_toast(newToast)
                return
            except Exception as e:
                # Fallback to custom toasts on error
                logger.warning(f"Windows notifications failed: {e}, falling back to custom toasts")
        
        # Use configured duration if available
        if hasattr(self.config, 'toast_duration'):
            duration = self.config.toast_duration * 1000  # Convert to milliseconds
        
        self.toast_queue.put((message, duration, toast_type))
    
    def monitor_toasts(self):
        """Monitor toast queue and display notifications"""
        try:
            message, duration, toast_type = self.toast_queue.get_nowait()
            self.display_toast(message, duration, toast_type)
        except queue.Empty:
            pass
        finally:
            self.root.after(self.toast_poll_interval_ms, self.monitor_toasts)
    
    def display_toast(self, message: str, duration: int, toast_type: str):
        """Display a modern floating toast notification inside the app window."""
        import time
        import tkinter.font as tkfont
        from PIL import Image, ImageDraw, ImageTk

        toast = tk.Toplevel(self.root)
        toast.withdraw()
        toast.overrideredirect(True)
        toast.attributes('-topmost', True)

        transparent_color = "#010203"
        toast.configure(bg=transparent_color)
        try:
            toast.attributes('-transparentcolor', transparent_color)
        except tk.TclError:
            transparent_color = getattr(self.config, 'toast_bg_color', '#1f2933')
            toast.configure(bg=transparent_color)

        accent_map = {
            'info': getattr(self.config, 'toast_info_color', '#38bdf8'),
            'success': getattr(self.config, 'toast_success_color', '#22c55e'),
            'warning': getattr(self.config, 'toast_warning_color', '#f59e0b'),
            'error': getattr(self.config, 'toast_error_color', '#ef4444')
        }
        icon_map = {
            'info': 'i',
            'success': '✓',
            'warning': '!',
            'error': '×'
        }

        accent_color = accent_map.get(toast_type, accent_map['info'])
        surface_color = getattr(self.config, 'toast_bg_color', '#1f2933')
        border_color = getattr(self.config, 'toast_border_color', '#334155')
        text_color = getattr(self.config, 'toast_text_color', '#f8fafc')
        close_color = "#94a3b8"
        close_hover_color = "#e2e8f0"

        font_family = getattr(self.config, 'toast_font_family', 'Segoe UI')
        try:
            font_size = int(getattr(self.config, 'toast_font_size', 10))
        except (TypeError, ValueError):
            font_size = 10
        font_weight = 'bold' if getattr(self.config, 'toast_font_bold', False) else 'normal'
        message_font = (font_family, font_size, font_weight)
        icon_font = ("Segoe UI Symbol", max(11, font_size + 2), "bold")
        close_font = ("Segoe UI", max(11, font_size + 1), "normal")

        measure_font = tkfont.Font(font=message_font)
        min_width = 300
        max_width = 440
        text_width = min(max(measure_font.measure(message) + 118, min_width), max_width)
        wrap_length = max(text_width - 116, 160)

        canvas = tk.Canvas(
            toast,
            width=text_width,
            height=90,
            bg=transparent_color,
            highlightthickness=0,
            bd=0
        )
        canvas.pack(fill=tk.BOTH, expand=True)

        text_item = canvas.create_text(
            76, 22,
            text=message,
            fill=text_color,
            font=message_font,
            anchor=tk.NW,
            width=wrap_length
        )
        canvas.update_idletasks()
        text_bbox = canvas.bbox(text_item) or (76, 22, text_width - 44, 42)
        toast_height = max(70, (text_bbox[3] - text_bbox[1]) + 42)
        canvas.configure(height=toast_height)
        canvas.delete(text_item)

        def render_toast_background(width, height):
            """Render anti-aliased toast chrome with PIL supersampling."""
            scale = 3
            image = Image.new("RGBA", (width * scale, height * scale), (0, 0, 0, 0))
            draw = ImageDraw.Draw(image)

            def scaled_box(x1, y1, x2, y2):
                return [x1 * scale, y1 * scale, x2 * scale, y2 * scale]

            draw.rounded_rectangle(
                scaled_box(2, 2, width - 3, height - 3),
                radius=12 * scale,
                fill=border_color
            )
            draw.rounded_rectangle(
                scaled_box(3, 3, width - 4, height - 4),
                radius=11 * scale,
                fill=surface_color
            )
            draw.ellipse(
                scaled_box(24, 20, 48, 44),
                fill=accent_color
            )

            resampling = getattr(getattr(Image, "Resampling", Image), "LANCZOS")
            return image.resize((width, height), resampling)

        toast_background = ImageTk.PhotoImage(render_toast_background(text_width, toast_height), master=toast)
        canvas.create_image(0, 0, image=toast_background, anchor=tk.NW)
        canvas.toast_background = toast_background

        canvas.create_text(
            36, 32,
            text=icon_map.get(toast_type, icon_map['info']),
            fill="#ffffff",
            font=icon_font
        )
        canvas.create_text(
            76, 20,
            text=message,
            fill=text_color,
            font=message_font,
            anchor=tk.NW,
            width=wrap_length
        )

        close_tag = "toast_close"
        close_text_tag = "toast_close_text"
        close_x = text_width - 30
        canvas.create_text(
            close_x, 27,
            text="×",
            fill=close_color,
            font=close_font,
            tags=(close_tag, close_text_tag)
        )
        canvas.create_rectangle(
            close_x - 12, 15, close_x + 12, 39,
            fill="",
            outline="",
            tags=(close_tag,)
        )
        progress_bg = canvas.create_line(
            18, toast_height - 17, text_width - 26, toast_height - 17,
            fill="#475569",
            width=2,
            capstyle=tk.ROUND
        )
        progress_fg = canvas.create_line(
            18, toast_height - 17, text_width - 26, toast_height - 17,
            fill=accent_color,
            width=2,
            capstyle=tk.ROUND
        )
        canvas.tag_lower(progress_bg, progress_fg)

        toast.update_idletasks()
        position = getattr(self.config, 'toast_position', 'top-right')

        if position == 'top-right':
            x = self.root.winfo_x() + self.root.winfo_width() - toast.winfo_width() - 20
            y = self.root.winfo_y() + 60
        elif position == 'top-left':
            x = self.root.winfo_x() + 20
            y = self.root.winfo_y() + 60
        elif position == 'bottom-right':
            x = self.root.winfo_x() + self.root.winfo_width() - toast.winfo_width() - 20
            y = self.root.winfo_y() + self.root.winfo_height() - toast.winfo_height() - 20
        elif position == 'bottom-left':
            x = self.root.winfo_x() + 20
            y = self.root.winfo_y() + self.root.winfo_height() - toast.winfo_height() - 20
        else:
            # Default to top-right
            x = self.root.winfo_x() + self.root.winfo_width() - toast.winfo_width() - 20
            y = self.root.winfo_y() + 60

        toast.geometry(f"+{x}+{y}")
        toast.deiconify()

        closed = False
        start_time = time.monotonic()

        def destroy_toast():
            nonlocal closed
            if closed:
                return
            closed = True
            try:
                toast.destroy()
            except tk.TclError:
                pass

        def fade_out(alpha=0.96):
            if closed:
                return
            if alpha <= 0.08:
                destroy_toast()
                return
            try:
                toast.attributes('-alpha', alpha)
            except tk.TclError:
                destroy_toast()
                return
            toast.after(24, lambda: fade_out(alpha - 0.08))

        def begin_close():
            if getattr(self.config, 'toast_fade_out', True):
                fade_out()
            else:
                destroy_toast()

        def update_progress():
            if closed:
                return
            elapsed_ms = (time.monotonic() - start_time) * 1000
            remaining = max(0, 1 - (elapsed_ms / max(duration, 1)))
            line_end = 18 + (text_width - 44) * remaining
            canvas.coords(progress_fg, 18, toast_height - 17, line_end, toast_height - 17)
            if remaining > 0:
                toast.after(40, update_progress)

        def on_close_enter(_event=None):
            canvas.itemconfigure(close_text_tag, fill=close_hover_color)
            canvas.configure(cursor="hand2")

        def on_close_leave(_event=None):
            canvas.itemconfigure(close_text_tag, fill=close_color)
            canvas.configure(cursor="")

        canvas.tag_bind(close_tag, "<Button-1>", lambda _event: destroy_toast())
        canvas.tag_bind(close_tag, "<Enter>", on_close_enter)
        canvas.tag_bind(close_tag, "<Leave>", on_close_leave)

        update_progress()
        toast.after(duration, begin_close)
    
    
    def save_shortcut(self):
        """Handle Ctrl+S shortcut (context-aware)"""
        # Check if we're in a context where save makes sense
        focused = self.root.focus_get()
        if focused:
            self.show_toast("Save shortcut triggered", 1500, "info")
    
    def undo_action(self):
        """Handle Ctrl+Z undo"""
        self.undo_track_table_action()

    def redo_action(self):
        """Handle Ctrl+Y redo."""
        self.redo_track_table_action()
    
    def refresh_current_tab(self):
        """Handle F5 shortcut - refresh current tab"""
        if self.is_upload_in_progress():
            self.show_toast("Upload in progress", 1600, "warning")
            return

        current_tab = self.get_selected_tab_text()
        if current_tab == "Upload":
            self.load_artists()
            self.show_toast("Refreshed artists", 2000, "success")

    def get_selected_tab_text(self):
        """Return the selected notebook tab label, or an empty string if unavailable."""
        try:
            return self.notebook.tab(self.notebook.select(), "text")
        except Exception:
            return ""
    
    
    def on_closing(self):
        """Handle window close event - save window geometry"""
        try:
            # Save current window geometry
            geometry = self.root.geometry()
            self.config.window_geometry = geometry
            save_config(self.config)
            if self._album_session_save_job is not None:
                try:
                    self.root.after_cancel(self._album_session_save_job)
                except tk.TclError:
                    pass
                self._album_session_save_job = None
            self.save_album_session_file()
        except Exception as e:
            logger.error(f"Failed to save window geometry: {e}")
        finally:
            self.root.destroy()
    
    def on_drop_folder(self, event):
        """Handle drag & drop of folder onto album path field"""
        if self.is_upload_in_progress():
            self.show_toast("Upload in progress", 1600, "warning")
            return

        try:
            # TkinterDnD provides data as a string
            path = event.data
            # Clean up the path (remove braces if present)
            path = path.strip('{}').strip()

            if Path(path).is_dir():
                self.album_path_var.set(path)
                self.upload_btn['state'] = tk.NORMAL if self.selected_artist_url else tk.DISABLED
                self.on_album_selection_changed()
                self.clear_album_load_fields()
    
                self.preview_album()

                # Auto-detect cover art
                self.auto_detect_cover_art(path)
                self.auto_extract_cover_art_if_missing(path)
                self.apply_album_load_preferences(path)
                self.load_or_create_album_session_file(path)
                self.show_toast("Album folder loaded", 2000, "success", trigger="file_add")
            else:
                self.show_toast("Please drop a folder, not a file", 2000, "warning")


        except Exception as e:
            logger.error(f"Drag & drop folder failed: {e}")
    
    def on_drop_image(self, event):
        """Handle drag & drop of image onto cover art field"""
        if self.is_upload_in_progress():
            self.show_toast("Upload in progress", 1600, "warning")
            return

        try:
            path = event.data
            path = path.strip('{}').strip()
            
            # Check if it's an image file
            if Path(path).suffix.lower() in ['.jpg', '.jpeg', '.png', '.gif']:
                self.cover_path_var.set(path)
                self.show_toast("Cover art loaded", 2000, "success", trigger="cover_load")
            else:
                self.show_toast("Please drop an image file (JPG, PNG, GIF)", 2000, "warning")
        except Exception as e:
            logger.error(f"Drag & drop image failed: {e}")

    def on_drop_track_files(self, event):
        """Handle drag & drop of audio files or album folder onto the track table"""
        if self.is_upload_in_progress():
            self.show_toast("Upload in progress", 1600, "warning")
            return

        try:
            items = self.root.tk.splitlist(event.data)
            folder = None
            audio_extensions = {'.wav', '.flac', '.aiff', '.aif', '.mp3', '.ogg', '.opus', '.m4a', '.aac', '.mod', '.xm'}
            audio_files = []

            for item in items:
                path = Path(item.strip())
                if path.is_dir():
                    folder = path
                    break
                elif path.suffix.lower() in audio_extensions:
                    audio_files.append(path)

            if folder is not None:
                self.album_path_var.set(str(folder))
                self.upload_btn['state'] = tk.NORMAL if self.selected_artist_url else tk.DISABLED
                self.on_album_selection_changed()
                self.clear_album_load_fields()
                self.preview_album()
                self.auto_detect_cover_art(str(folder))
                self.auto_extract_cover_art_if_missing(str(folder))
                self.apply_album_load_preferences(str(folder))
                self.load_or_create_album_session_file(str(folder))
                self.add_to_recent_albums(str(folder))
                self.show_toast("Album folder loaded", 2000, "success", trigger="file_add")
                if self.config.auto_start_upload and self.selected_artist_url:
                    self.root.after(500, self.start_upload)
            elif audio_files:
                added = 0
                for path in audio_files:
                    if path not in self.manual_tracks:
                        self.manual_tracks.append(path)
                        logger.info(f"Added track: {path.name}")
                        added += 1
                if added > 0:
                    self.sort_manual_tracks_by_metadata_numbers()
                    self.album_path_var.set("")
                    self.current_album = None
                    self.update_manual_tracks_preview()
                    if self.manual_tracks:
                        self.upload_btn['state'] = tk.NORMAL
                    self.show_toast(f"Added {added} track(s)", 2000, "success", trigger="track_add")
            else:
                self.show_toast("No supported audio files or folders found", 2000, "warning")
        except Exception as e:
            logger.error(f"Drag & drop tracks failed: {e}")

    def add_upload_to_history(self, album_name, artist_name):
        """Add successful upload to history"""
        import datetime
        
        if not hasattr(self.config, 'upload_history'):
            self.config.upload_history = []
        
        history_entry = {
            "album": album_name,
            "artist": artist_name,
            "timestamp": datetime.datetime.now().isoformat(),
            "date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        }
        
        self.config.upload_history.insert(0, history_entry)
        self.config.upload_history = self.config.upload_history[:10]  # Keep last 10
        
        try:
            save_config(self.config)
        except Exception as e:
            logger.error(f"Failed to save upload history: {e}")
    
    def manage_cover_art_library(self):
        """Manage recently used cover art."""
        if self.is_upload_in_progress():
            self.show_toast("Upload in progress", 1600, "warning")
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("Library")
        dialog.geometry("820x650")
        dialog.transient(self.root)

        # Center dialog
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (820 // 2)
        y = (dialog.winfo_screenheight() // 2) - (650 // 2)
        dialog.geometry(f"+{x}+{y}")

        main_frame = ttk.Frame(dialog)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Library content
        lib_frame = ttk.Frame(main_frame, padding=10)
        lib_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Grid of thumbnails with responsive layout
        lib_canvas = tk.Canvas(lib_frame, bg="#f0f0f0")
        lib_scrollbar = ttk.Scrollbar(lib_frame, orient="vertical", command=lib_canvas.yview)
        thumb_frame = ttk.Frame(lib_canvas)

        lib_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        lib_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        lib_canvas.create_window((0, 0), window=thumb_frame, anchor="nw")
        lib_canvas.configure(yscrollcommand=lib_scrollbar.set)

        # Mouse wheel scrolling is scoped to the cover library dialog. Using
        # bind_all here leaves a dead canvas callback behind after close.
        def on_mousewheel(event):
            try:
                if not lib_canvas.winfo_exists():
                    return "break"

                if getattr(event, "num", None) == 4:
                    delta = -1
                elif getattr(event, "num", None) == 5:
                    delta = 1
                else:
                    event_delta = getattr(event, "delta", 0)
                    delta = -1 * int(event_delta / 120) if event_delta else 0

                if delta:
                    lib_canvas.yview_scroll(delta, "units")
            except tk.TclError:
                return "break"
            return "break"

        def bind_cover_scroll(*widgets):
            for widget in widgets:
                widget.bind("<MouseWheel>", on_mousewheel, add="+")  # Windows
                widget.bind("<Button-4>", on_mousewheel, add="+")  # Linux scroll up
                widget.bind("<Button-5>", on_mousewheel, add="+")  # Linux scroll down

        bind_cover_scroll(lib_canvas, thumb_frame)

        cover_library = getattr(self.config, 'cover_art_library', [])

        # Function to recalculate grid layout based on canvas width
        def recalculate_grid():
            try:
                if not dialog.winfo_exists() or not lib_canvas.winfo_exists():
                    return

                canvas_width = lib_canvas.winfo_width()
                if canvas_width < 150:  # Too small, wait
                    dialog.after(100, recalculate_grid)
                    return

                # Subtract scrollbar width from available space
                scrollbar_width = lib_scrollbar.winfo_width()
                available_width = canvas_width - scrollbar_width - 10  # Extra padding

                thumb_size = 140  # 120 + 20 (for marquee label)
                cols = max(1, available_width // thumb_size)

                # Re-grid all buttons
                for widget in thumb_frame.winfo_children():
                    widget.grid_forget()

                row, col = 0, 0
                for widget in thumb_frame.winfo_children():
                    widget.grid(row=row, column=col, padx=8, pady=8)
                    col += 1
                    if col >= cols:
                        col = 0
                        row += 1

                thumb_frame.update_idletasks()
                lib_canvas.configure(scrollregion=lib_canvas.bbox("all"))
            except tk.TclError:
                return

        # Display thumbnails
        if not cover_library:
            empty_label = ttk.Label(thumb_frame, text="")
            empty_label.grid(row=0, column=0, pady=50)
            bind_cover_scroll(empty_label)
        else:
            for cover_path in cover_library:
                if not Path(cover_path).exists():
                    continue

                try:
                    from PIL import Image, ImageTk
                    img = Image.open(cover_path)
                    img.thumbnail((120, 120), Image.Resampling.LANCZOS)
                    photo = ImageTk.PhotoImage(img)

                    # Frame for thumbnail + marquee
                    thumb_container = ttk.Frame(thumb_frame)

                    btn = ttk.Button(
                        thumb_container,
                        image=photo,
                        command=lambda p=cover_path: self.use_cover_from_library(p, dialog)
                    )
                    btn.image = photo
                    btn.pack()

                    # Marquee label for filename
                    filename = Path(cover_path).name
                    marquee_text = filename + "   "
                    marquee_label = ttk.Label(thumb_container, text=marquee_text, font=("Segoe UI", 7), width=16)
                    marquee_label.pack(pady=(2, 0))

                    # Marquee animation for this label
                    def scroll_marquee(label=marquee_label, text=marquee_text):
                        try:
                            if not dialog.winfo_exists() or not label.winfo_exists():
                                return
                            current = label.cget("text")
                            if current:
                                scrolled = current[1:] + current[0]
                                label.config(text=scrolled)
                                dialog.after(200, lambda: scroll_marquee(label, text))
                        except tk.TclError:
                            return

                    dialog.after(100, lambda: scroll_marquee(marquee_label, marquee_text))
                    bind_cover_scroll(thumb_container, btn, marquee_label)

                    # Don't place yet, will be placed by recalculate_grid
                except:
                    continue

            # Initial grid calculation
            dialog.update_idletasks()
            recalculate_grid()

            # Recalculate on window resize
            lib_canvas.bind('<Configure>', lambda e: recalculate_grid())
    
    def use_cover_from_library(self, cover_path, dialog):
        """Use selected cover from library"""
        self.cover_path_var.set(cover_path)
        self.show_toast("Cover art loaded from library", 2000, "success", trigger="cover_load")
        dialog.destroy()
    

    def add_to_cover_library(self, cover_path):
        """Add cover art to library"""
        if not cover_path or not Path(cover_path).exists():
            return
        
        if not hasattr(self.config, 'cover_art_library'):
            self.config.cover_art_library = []
        
        if cover_path not in self.config.cover_art_library:
            self.config.cover_art_library.insert(0, cover_path)
            self.config.cover_art_library = self.config.cover_art_library[:20]  # Keep last 20
            try:
                save_config(self.config)
            except:
                pass
    


def main():
    """Main entry point for GUI"""
    set_windows_app_user_model_id()
    if DRAG_DROP_AVAILABLE:
        root = TkinterDnD.Tk()
    else:
        root = tk.Tk()
    app = BandcampUploaderGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
