"""Log tab and log formatting mixin for the Tkinter GUI."""

import dataclasses
import json
import logging
import os
import platform
import queue
import subprocess
import sys
import tkinter as tk
import traceback
import webbrowser
from datetime import datetime
from pathlib import Path
from tkinter import ttk, scrolledtext, messagebox

from bandcamp_auto_uploader.config import get_app_data_dir, get_config_file_path
from bandcamp_auto_uploader.gui.common import sanitize_log_text


ISSUE_URL = "https://github.com/Nai64/BandcampAutoUploader/issues/new"
SUPPORT_LOG_TAB_LINES = 200


class LogsMixin:
    def get_app_log_dir(self):
        """Return the persistent diagnostic log folder."""
        return get_app_data_dir() / "Logs"

    def get_app_log_file_path(self):
        """Return the main persistent diagnostic log file."""
        if not hasattr(self, "_app_log_file_path"):
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            self._app_log_file_path = self.get_app_log_dir() / f"bau_{timestamp}.log"
        return self._app_log_file_path

    def create_log_tab(self, parent):
        """Create log viewer"""
        # Get font settings from config
        font_family = getattr(self.config, 'log_font_family', 'Segoe UI')
        font_size = getattr(self.config, 'log_font_size', 9)
        font_weight = "bold" if getattr(self.config, 'log_font_bold', False) else "normal"

        # Get color settings from config
        text_color = getattr(self.config, 'log_text_color', '#ffffff')
        bg_color = getattr(self.config, 'log_bg_color', '#1e1e1e')

        # Get display settings from config
        word_wrap = getattr(self.config, 'log_word_wrap', True)
        wrap_mode = tk.WORD if word_wrap else tk.NONE

        # Log display
        self.log_text = scrolledtext.ScrolledText(
            parent,
            wrap=wrap_mode,
            font=(font_family, font_size, font_weight),
            bg=bg_color,
            fg=text_color
        )
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Control buttons
        button_frame = ttk.Frame(parent)
        button_frame.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Button(
            button_frame,
            text="Clear Logs",
            command=lambda: self.log_text.delete(1.0, tk.END)
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            button_frame,
            text="Copy Logs",
            command=self.copy_logs
        ).pack(side=tk.LEFT, padx=5)

        ttk.Button(
            button_frame,
            text="Open Log Folder",
            command=self.open_log_folder
        ).pack(side=tk.LEFT, padx=5)

        ttk.Button(
            button_frame,
            text="Export Log",
            command=self.export_bug_report
        ).pack(side=tk.LEFT, padx=5)

        self.log_cancel_btn = ttk.Button(
            button_frame,
            text="Cancel Upload",
            command=self.cancel_upload,
            state=tk.DISABLED
        )
        self.log_cancel_btn.pack(side=tk.LEFT, padx=5)

    def open_log_folder(self):
        """Open the folder containing persistent logs."""
        log_dir = self.get_app_log_dir()
        log_dir.mkdir(parents=True, exist_ok=True)
        try:
            if os.name == "nt":
                os.startfile(str(log_dir))
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(log_dir)])
            else:
                subprocess.Popen(["xdg-open", str(log_dir)])
        except Exception as e:
            messagebox.showerror("Open Log Folder Failed", f"Could not open:\n{log_dir}\n\n{e}")

    def get_safe_config_snapshot(self):
        """Return config values with private fields omitted for support bundles."""
        config_data = dataclasses.asdict(self.config)
        sensitive_markers = ("cookie", "token", "password", "secret", "api_key", "key")
        private_config_keys = {
            "cover_art_library",
            "last_selected_artist",
            "recent_albums",
            "recent_artists",
            "upload_history",
        }
        for key in list(config_data):
            if key in private_config_keys or any(marker in key.lower() for marker in sensitive_markers):
                config_data.pop(key)
        config_data["_privacy_note"] = "Sensitive config values are omitted from this support export."
        return config_data

    def get_support_track_details(self):
        """Return current track-table details without local folder paths."""
        if not hasattr(self, "track_table"):
            return []

        columns = list(self.track_table["columns"])
        labels = {}
        if hasattr(self, "get_track_table_column_labels"):
            labels = self.get_track_table_column_labels()

        tracks = []
        for item_id in self.track_table.get_children():
            values = list(self.track_table.item(item_id).get("values", ()))
            row = {}
            for index, column_id in enumerate(columns):
                if index >= len(values):
                    continue
                value = values[index]
                if column_id == "file_path":
                    value = Path(str(value)).name if value else ""
                    column_name = "File Name"
                else:
                    column_name = labels.get(column_id, column_id)
                if isinstance(value, str):
                    value = sanitize_log_text(value)
                row[column_name] = value
            tracks.append(row)
        return tracks

    def get_support_system_info(self):
        """Return diagnostic system/app details for support bundles."""
        info = {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "python": sys.version,
            "platform": platform.platform(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "cwd": str(Path.cwd()),
            "config_file": str(get_config_file_path()),
            "log_file": str(self.get_app_log_file_path()),
            "frozen": bool(getattr(sys, "frozen", False)),
        }
        return {
            key: sanitize_log_text(value) if isinstance(value, str) else value
            for key, value in info.items()
        }

    def write_support_snapshot(self, reason="Manual export", error_text=None, exc_info=None):
        """Append diagnostic context to the single BAU log file."""
        log_dir = self.get_app_log_dir()
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = self.get_app_log_file_path()

        logging.getLogger("bandcamp-auto-uploader").info("Writing support snapshot to log file")
        for handler in logging.getLogger("bandcamp-auto-uploader").handlers:
            try:
                handler.flush()
            except Exception:
                pass

        info = self.get_support_system_info()
        config = self.get_safe_config_snapshot()
        tracks = self.get_support_track_details()
        gui_logs = self.log_text.get("1.0", "end-1c") if hasattr(self, "log_text") else ""
        gui_log_lines = gui_logs.splitlines()
        if len(gui_log_lines) > SUPPORT_LOG_TAB_LINES:
            gui_logs = "\n".join(gui_log_lines[-SUPPORT_LOG_TAB_LINES:])
            gui_logs = (
                f"Showing last {SUPPORT_LOG_TAB_LINES} visible Log tab lines.\n"
                f"{gui_logs}"
            )
        error_section = ""
        if error_text or exc_info:
            traceback_text = ""
            if exc_info:
                traceback_text = "".join(traceback.format_exception(*exc_info))
            error_section = (
                "[error.txt]\n"
                f"Reason: {sanitize_log_text(reason)}\n"
                f"Message: {sanitize_log_text(error_text or '')}\n"
                f"{sanitize_log_text(traceback_text)}\n\n"
            )

        snapshot = (
            "\n\n"
            "==============================\n"
            "BAU SUPPORT SNAPSHOT\n"
            "==============================\n\n"
            f"{error_section}"
            "[systeminfo.json]\n"
            f"{json.dumps(info, indent=2)}\n\n"
            "[config.json]\n"
            f"{json.dumps(config, indent=2)}\n\n"
            "[tracks.json]\n"
            f"{json.dumps(tracks, indent=2)}\n\n"
            "[log_tab.txt]\n"
            f"{sanitize_log_text(gui_logs)}\n"
            "==============================\n"
            "END BAU SUPPORT SNAPSHOT\n"
            "==============================\n"
        )

        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as log_file:
            log_file.write(snapshot)

        logging.getLogger("bandcamp-auto-uploader").info(f"Support snapshot written: {log_path}")
        return log_path

    def show_log_created_dialog(self, title, message, log_path, is_error=False):
        """Show a log-created dialog with OK and Open Issue actions."""
        dialog = tk.Toplevel(self.root)
        dialog.title(title)
        dialog.transient(self.root)
        dialog.resizable(False, False)

        frame = ttk.Frame(dialog, padding=14)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(
            frame,
            text=message,
            justify=tk.LEFT,
            wraplength=520
        ).pack(fill=tk.X, pady=(0, 10))

        path_text = tk.Text(frame, height=3, width=72, wrap=tk.WORD)
        path_text.insert("1.0", str(log_path))
        path_text.configure(state=tk.DISABLED)
        path_text.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(
            frame,
            text=f"Create an issue here:\n{ISSUE_URL}\n\nplease paste your log file here",
            justify=tk.LEFT,
            wraplength=520
        ).pack(fill=tk.X, pady=(0, 12))

        button_frame = ttk.Frame(frame)
        button_frame.pack(fill=tk.X)

        def open_issue():
            webbrowser.open(ISSUE_URL)

        ttk.Button(button_frame, text="OK", command=dialog.destroy).pack(side=tk.RIGHT, padx=(6, 0))
        ttk.Button(button_frame, text="Open Issue", command=open_issue).pack(side=tk.RIGHT)

        dialog.update_idletasks()
        x = self.root.winfo_rootx() + (self.root.winfo_width() // 2) - (dialog.winfo_width() // 2)
        y = self.root.winfo_rooty() + (self.root.winfo_height() // 2) - (dialog.winfo_height() // 2)
        dialog.geometry(f"+{max(0, x)}+{max(0, y)}")

        if is_error:
            dialog.grab_set()

    def show_bug_log_prompt(self, title, message, error_text=None, exc_info=None):
        """Create a support log and tell the user where to report it."""
        try:
            log_path = self.write_support_snapshot(title, error_text=error_text, exc_info=exc_info)

            self.root.clipboard_clear()
            self.root.clipboard_append(str(log_path))
            self.show_log_created_dialog(
                title,
                f"{message}\n\n"
                "A log was created and its path was copied to your clipboard.",
                log_path,
                is_error=True
            )
        except Exception as e:
            messagebox.showerror(title, f"{message}\n\nCould not write log:\n{e}")

    def export_bug_report(self):
        """Append diagnostic context to the single BAU log file."""
        try:
            log_path = self.write_support_snapshot("Manual export")
            self.root.clipboard_clear()
            self.root.clipboard_append(str(log_path))
            self.show_log_created_dialog(
                "Log Ready",
                "Log path copied to your clipboard.",
                log_path
            )
        except Exception as e:
            messagebox.showerror("Export Log Failed", f"Could not write log:\n{e}")

    def copy_logs(self):
        """Copy logs to clipboard"""
        logs = self.log_text.get(1.0, tk.END)
        self.root.clipboard_clear()
        self.root.clipboard_append(logs)
        messagebox.showinfo("Copied", "Logs copied to clipboard")

    def monitor_logs(self):
        """Monitor log queue and update log display"""
        try:
            while True:
                item = self.log_queue.get_nowait()

                # Handle both old format (string) and new format (tuple)
                if isinstance(item, tuple):
                    message, levelno = item
                else:
                    message = item
                    levelno = logging.INFO  # Default to INFO for old messages

                # Get color from config based on log level
                if levelno >= logging.CRITICAL:
                    color = getattr(self.config, 'log_error_color', '#ff0000')  # Use ERROR color for CRITICAL
                elif levelno >= logging.ERROR:
                    color = self.config.log_error_color
                elif levelno >= logging.WARNING:
                    color = self.config.log_warning_color
                elif levelno >= logging.INFO:
                    color = self.config.log_info_color
                else:  # DEBUG
                    color = self.config.log_debug_color

                # Format message based on display settings
                formatted_message = sanitize_log_text(self.format_log_message(message, levelno))

                # Insert message with color tag
                self.log_text.insert(tk.END, formatted_message + "\n", (f"level_{levelno}",))
                self.log_text.tag_config(f"level_{levelno}", foreground=color)

                # Trim to max lines if set
                if self.config.log_max_lines > 0:
                    line_count = int(self.log_text.index('end-1c').split('.')[0])
                    if line_count > self.config.log_max_lines:
                        # Remove excess lines from the top
                        excess_lines = line_count - self.config.log_max_lines
                        self.log_text.delete(1.0, f"{excess_lines + 1}.0")

                # Auto-scroll if enabled
                if self.config.log_auto_scroll:
                    self.log_text.see(tk.END)
        except queue.Empty:
            pass

        # Schedule next check
        self.root.after(self.log_poll_interval_ms, self.monitor_logs)

    def format_log_message(self, message, levelno):
        """Format log message based on display settings"""
        formatted = message

        # Remove existing timestamp if present (to reformat based on settings)
        if not self.config.log_show_timestamps:
            # Remove timestamp from message if it exists
            timestamp_pattern = r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} - |^\d{2}:\d{2}:\d{2} - '
            formatted = re.sub(timestamp_pattern, '', formatted)

        # Add log level if enabled
        if self.config.log_show_levels:
            level_name = logging.getLevelName(levelno)
            if not formatted.startswith(level_name):
                formatted = f"[{level_name}] {formatted}"

        return formatted

