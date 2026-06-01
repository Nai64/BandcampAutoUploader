"""Settings and preferences mixin for the Tkinter GUI."""

import sys
import tkinter as tk
from tkinter import ttk, messagebox, colorchooser

from bandcamp_auto_uploader.config import Config, save_config
from bandcamp_auto_uploader.gui.common import DESCRIPTION_AUTO_FILL_MODES, ToolTip
from bandcamp_auto_uploader import __version__


SORT_METHOD_SETTINGS = [
    ("File Size", "sort_by_file_size"),
    ("Length", "sort_by_length"),
    ("Alphabetically", "sort_by_alphabetically"),
    ("Artist Name", "sort_by_artist"),
    ("Track Number", "sort_by_track_number"),
    ("Metadata Track #", "sort_by_metadata_track_number"),
    ("Extension", "sort_by_extension"),
    ("Price", "sort_by_price"),
    ("Year", "sort_by_year"),
    ("Genre", "sort_by_genre"),
    ("Bitrate", "sort_by_bitrate"),
    ("Sample Rate", "sort_by_sample_rate"),
    ("Channels", "sort_by_channels"),
    ("Bit Depth", "sort_by_bit_depth"),
    ("Album Metadata", "sort_by_album"),
    ("Album Artist Metadata", "sort_by_album_artist"),
    ("Composer", "sort_by_composer"),
    ("ISRC", "sort_by_isrc"),
]


SCALING_METHOD_OPTIONS = [
    "Nearest", "Box", "Bilinear", "Hamming", "Bicubic", "Lanczos",
    "Area", "Mitchell", "Catmull-Rom", "Sinc", "Gaussian", "Pixelate",
    "Hermite", "Blackman", "Kaiser", "Welch", "Parzen", "Bartlett",
    "Cubic", "Quadratic", "Average", "Max", "Min", "Median", "Sharpen",
    "Edge-Enhanced", "B-Spline", "Rational"
]


class SettingsMixin:
    def create_settings_tab(self, parent):
        """Create settings interface with sidebar navigation"""
        
        # Main container
        main_frame = ttk.Frame(parent)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Sidebar navigation with default Windows styling
        sidebar = ttk.Frame(main_frame, width=150)
        sidebar.pack(side=tk.LEFT, fill=tk.BOTH, padx=(15, 10), pady=15)
        self.settings_sidebar = sidebar

        search_frame = ttk.Frame(sidebar)
        search_frame.pack(fill=tk.X, pady=(0, 8))
        self.settings_search_frame = search_frame
        self.settings_search_var = tk.StringVar()
        self.settings_search_entry = ttk.Entry(search_frame, textvariable=self.settings_search_var)
        self.settings_search_entry.pack(fill=tk.X)
        self.settings_search_var.trace_add('write', lambda *_args: self.update_settings_search_results())

        self.settings_search_results = ttk.Treeview(
            sidebar,
            selectmode='browse',
            show='tree',
            height=7
        )
        self.settings_search_results.bind('<<TreeviewSelect>>', self.on_settings_search_result_select)
        self.settings_search_results.place_forget()
        self.settings_search_result_items = {}
        self.settings_search_index = []
        
        # Sidebar treeview for hierarchical navigation (expands to fill height)
        self.settings_tree = ttk.Treeview(
            sidebar,
            selectmode='browse',
            show='tree'
        )
        self.settings_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Sidebar scrollbar (hidden but functional)
        sidebar_scrollbar = ttk.Scrollbar(sidebar, orient="vertical", command=self.settings_tree.yview)
        sidebar_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        sidebar_scrollbar.pack_forget()  # Hide scrollbar but keep functionality
        self.settings_tree.configure(yscrollcommand=sidebar_scrollbar.set)
        
        # Hide treeview headings
        self.settings_tree.heading('#0', text='')
        
        # Populate tree with sections and sub-items
        general_id = self.settings_tree.insert('', 'end', 'General', text='General')
        self.settings_tree.insert(general_id, 'end', 'general_settings', text='General Settings')
        self.settings_tree.insert(general_id, 'end', 'context_menu', text='Context Menu')
        self.settings_tree.insert(general_id, 'end', 'sort_methods', text='Sort Methods')
        self.settings_tree.insert(general_id, 'end', 'auto_tagging', text='Auto Tagging')
        
        notifications_id = self.settings_tree.insert('', 'end', 'Notifications', text='Notifications')
        self.settings_tree.insert(notifications_id, 'end', 'toasts', text='Toast Notifications')
        self.settings_tree.insert(notifications_id, 'end', 'windows_notifications', text='Windows Notifications')
        self.settings_tree.insert(notifications_id, 'end', 'notification_triggers', text='Notification Triggers')
        
        upload_id = self.settings_tree.insert('', 'end', 'Upload', text='Upload')
        self.settings_tree.insert(upload_id, 'end', 'upload_settings', text='Upload Settings')
        
        # Interface with sub-items
        interface_id = self.settings_tree.insert('', 'end', 'Interface', text='Interface')
        self.settings_tree.insert(interface_id, 'end', 'columns', text='Track Table Columns')
        self.settings_tree.insert(interface_id, 'end', 'logs', text='Logs')
        
        self.settings_tree.insert('', 'end', 'Advanced', text='Advanced')
        self.settings_tree.insert('', 'end', 'About', text='About')
        
        # Bind selection event
        self.settings_tree.bind('<<TreeviewSelect>>', self.on_settings_tree_select)
        
        # Bind mouse wheel for sidebar
        def on_sidebar_mouse_wheel(event):
            self.settings_tree.yview_scroll(int(-1*(event.delta/120)), "units")
        
        self.settings_tree.bind('<MouseWheel>', on_sidebar_mouse_wheel)
        
        # Content area with scrollbars
        content_container = ttk.Frame(main_frame)
        content_container.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(10, 15), pady=15)
        
        # Canvas for content scrolling
        content_canvas = tk.Canvas(content_container, highlightthickness=0)
        content_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Content scrollbars
        v_scrollbar = ttk.Scrollbar(content_container, orient="vertical", command=content_canvas.yview)
        v_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        content_canvas.configure(yscrollcommand=v_scrollbar.set)
        
        # Content frame inside canvas
        content_frame = ttk.Frame(content_canvas)
        self.content_canvas_window = content_canvas.create_window((0, 0), window=content_frame, anchor="nw", width=1, height=1)
        self.content_canvas = content_canvas  # Store as instance variable
        
        # Configure canvas scroll region
        def configure_content_canvas(event):
            self.content_canvas.configure(scrollregion=self.content_canvas.bbox("all"))
            self.content_canvas.itemconfig(self.content_canvas_window, width=event.width, height=event.height)
        
        self.content_canvas.bind('<Configure>', configure_content_canvas)
        
        # Bind mouse wheel for content canvas
        def on_content_mouse_wheel(event):
            self.content_canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        
        self.content_canvas.bind('<MouseWheel>', on_content_mouse_wheel)
        
        # Create all settings frames
        self.settings_frames = {}

        # Track Table Columns frame
        columns_frame = ttk.Frame(content_frame)
        self.create_column_settings(columns_frame)
        self.settings_frames["columns"] = columns_frame

        # Auto Tagging frame
        auto_tagging_frame = ttk.Frame(content_frame)
        self.create_auto_tagging_settings(auto_tagging_frame)
        self.settings_frames["auto_tagging"] = auto_tagging_frame

        # Upload Settings frame
        upload_settings_frame = ttk.Frame(content_frame)
        self.create_upload_settings(upload_settings_frame)
        self.settings_frames["upload_settings"] = upload_settings_frame
        
        # Advanced frame with Reset All button
        advanced_frame = ttk.Frame(content_frame)
        self.create_advanced_settings(advanced_frame)
        self.settings_frames["Advanced"] = advanced_frame

        # Interface sub-item frames
        logs_frame = ttk.Frame(content_frame)
        self.create_logs_settings(logs_frame)
        self.settings_frames["logs"] = logs_frame
        
        # About frame
        about_frame = ttk.Frame(content_frame)
        self.create_about_settings(about_frame)
        self.settings_frames["About"] = about_frame
        
        # General Settings frame
        general_settings_frame = ttk.Frame(content_frame)
        self.create_general_settings(general_settings_frame)
        self.settings_frames["general_settings"] = general_settings_frame
        
        # Context Menu frame
        context_menu_frame = ttk.Frame(content_frame)
        self.create_context_menu_settings(context_menu_frame)
        self.settings_frames["context_menu"] = context_menu_frame

        # Sort Methods frame
        sort_methods_frame = ttk.Frame(content_frame)
        self.create_sort_method_settings(sort_methods_frame)
        self.settings_frames["sort_methods"] = sort_methods_frame
        
        # Combined General frame (includes all sub-sections)
        general_combined_frame = ttk.Frame(content_frame)
        self.create_general_combined_settings(general_combined_frame)
        self.settings_frames["General"] = general_combined_frame
        
        # Notifications sub-item frames
        toasts_frame = ttk.Frame(content_frame)
        self.create_toast_settings(toasts_frame)
        self.settings_frames["toasts"] = toasts_frame
        
        windows_notifications_frame = ttk.Frame(content_frame)
        self.create_windows_notifications_settings(windows_notifications_frame)
        self.settings_frames["windows_notifications"] = windows_notifications_frame
        
        notification_triggers_frame = ttk.Frame(content_frame)
        self.create_notification_triggers_settings(notification_triggers_frame)
        self.settings_frames["notification_triggers"] = notification_triggers_frame
        
        # Combined Notifications frame (includes all sub-sections)
        notifications_combined_frame = ttk.Frame(content_frame)
        self.create_notifications_combined_settings(notifications_combined_frame)
        self.settings_frames["Notifications"] = notifications_combined_frame
        
        # Combined Interface frame (includes all sub-sections)
        interface_combined_frame = ttk.Frame(content_frame)
        self.create_interface_combined_settings(interface_combined_frame)
        self.settings_frames["Interface"] = interface_combined_frame
        
        # Show General Settings by default (sub-item of General)
        self.settings_tree.selection_set('general_settings')
        self.switch_settings_tab("general_settings")
        
        # Expand all parent sections so sub-options are visible immediately.
        for section_id in self.settings_tree.get_children(''):
            if self.settings_tree.get_children(section_id):
                self.settings_tree.item(section_id, open=True)

        self.build_settings_search_index()

    def build_settings_search_index(self):
        """Index preference rows so search can jump to the real setting."""
        section_trees = [
            ("General Settings", "general_settings", "general_tree"),
            ("Context Menu", "context_menu", "context_menu_tree"),
            ("Sort Methods", "sort_methods", "sort_method_tree"),
            ("Auto Tagging", "auto_tagging", "auto_tagging_tree"),
            ("Toast Notifications", "toasts", "toast_tree"),
            ("Windows Notifications", "windows_notifications", "windows_notifications_tree"),
            ("Notification Triggers", "notification_triggers", "notification_triggers_tree"),
            ("Upload Settings", "upload_settings", "upload_tree"),
            ("Track Table Columns", "columns", "column_tree"),
            ("Logs", "logs", "logs_tree"),
            ("Advanced", "Advanced", "advanced_tree"),
        ]

        self.settings_search_index = []
        for section_label, section_id, tree_attr in section_trees:
            tree = getattr(self, tree_attr, None)
            if tree is None:
                continue

            for item_id in tree.get_children(''):
                values = tree.item(item_id).get('values', ())
                setting_name = str(values[0]).strip() if values else tree.item(item_id).get('text', '')
                setting_value = str(values[1]).strip() if len(values) > 1 else ''
                if not setting_name:
                    continue

                self.settings_search_index.append({
                    "display": f"{setting_name}  [{section_label}]",
                    "needle": f"{setting_name} {setting_value} {section_label}".casefold(),
                    "section_id": section_id,
                    "tree_attr": tree_attr,
                    "item_id": item_id,
                })

    def update_settings_search_results(self):
        """Refresh preference search results."""
        if not hasattr(self, 'settings_search_results'):
            return

        query = self.settings_search_var.get().strip().casefold()
        for item in self.settings_search_results.get_children(''):
            self.settings_search_results.delete(item)
        self.settings_search_result_items = {}

        if not query:
            self.settings_search_results.place_forget()
            return

        words = [word for word in query.split() if word]
        matches = [
            entry for entry in self.settings_search_index
            if all(word in entry["needle"] for word in words)
        ][:30]

        if not matches:
            item_id = self.settings_search_results.insert('', 'end', text='No settings found')
            self.settings_search_result_items[item_id] = None
            self.place_settings_search_results()
            return

        for entry in matches:
            item_id = self.settings_search_results.insert('', 'end', text=entry["display"])
            self.settings_search_result_items[item_id] = entry

        self.place_settings_search_results()

    def place_settings_search_results(self):
        """Float search results over the sidebar tree without changing layout."""
        if not hasattr(self, 'settings_search_results'):
            return

        self.settings_sidebar.update_idletasks()
        self.settings_search_frame.update_idletasks()
        self.settings_search_entry.update_idletasks()
        width = max(120, self.settings_sidebar.winfo_width() - 2)
        y = (
            self.settings_search_entry.winfo_rooty()
            - self.settings_sidebar.winfo_rooty()
            + self.settings_search_entry.winfo_height()
            + 3
        )
        result_count = max(1, len(self.settings_search_results.get_children('')))
        row_height = 22
        height = min(220, max(48, result_count * row_height + 6))
        self.settings_search_results.place(x=0, y=y, width=width, height=height)
        self.settings_search_results.lift()

    def on_settings_search_result_select(self, _event=None):
        """Jump from a search result to its setting row."""
        selection = self.settings_search_results.selection()
        if not selection:
            return

        entry = self.settings_search_result_items.get(selection[0])
        if not entry:
            return

        section_id = entry["section_id"]
        tree_attr = entry["tree_attr"]
        item_id = entry["item_id"]
        self.settings_tree.selection_set(section_id)
        self.settings_tree.focus(section_id)
        self.settings_tree.see(section_id)
        self.switch_settings_tab(section_id)
        self.settings_search_results.place_forget()

        def select_setting_row():
            tree = getattr(self, tree_attr, None)
            if tree is None or not tree.exists(item_id):
                return
            tree.selection_set(item_id)
            tree.focus(item_id)
            tree.see(item_id)

        self.root.after_idle(select_setting_row)
    
    def on_settings_tree_select(self, event):
        """Handle treeview selection event"""
        selection = self.settings_tree.selection()
        if selection:
            item_id = selection[0]
            self.switch_settings_tab(item_id)
    
    def switch_settings_tab(self, item_id):
        """Switch between settings sections"""
        # Hide all frames
        for frame in self.settings_frames.values():
            frame.pack_forget()
        
        # If parent item is selected, show first child instead
        if item_id not in self.settings_frames:
            children = self.settings_tree.get_children(item_id)
            if children:
                item_id = children[0]
        
        # Show selected frame
        if item_id in self.settings_frames:
            self.settings_frames[item_id].pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
            # Update scroll region after a short delay to let the frame render
            self.root.after(50, lambda: self.update_settings_scroll_region())
    
    def update_settings_scroll_region(self):
        """Update the settings content scroll region"""
        if hasattr(self, 'content_canvas'):
            # Update scroll region to include the full content
            self.content_canvas.configure(scrollregion=self.content_canvas.bbox("all"))
            # Ensure the content window fills the available width and height
            canvas_width = self.content_canvas.winfo_width()
            canvas_height = self.content_canvas.winfo_height()
            self.content_canvas.itemconfig(self.content_canvas_window, width=canvas_width, height=canvas_height)
    
    def create_general_settings(self, parent):
        """Create General settings section using Treeview"""
        # General settings treeview
        settings = [
            ("Apply settings immediately", "apply_settings_immediately", "bool"),
            ("Maximize app on open", "maximize_on_open", "bool"),
            ("Disable tooltips", "disable_tooltips", "bool"),
            ("Auto load metadata for album details", "auto_load_metadata", "bool"),
            ("Use Album Artist metadata for Artist in Album details", "use_album_artist_in_album_details", "bool"),
            ("Create session.txt files (Recommended)", "create_album_session_files", "bool"),
            ("Guess album title from track metadata", "guess_album_title_from_track_metadata", "bool"),
            ("Guess release date from track metadata", "guess_release_date_from_track_metadata", "bool"),
            ("Folder name if album tag missing", "use_folder_name_when_album_missing", "bool"),
            ("Smart-randomize on album load", "smart_randomize_on_album_load", "bool"),
            ("Auto guess case tracks on album load", "auto_guess_case_on_album_load", "bool"),
            ("Always auto-scale cover art", "always_auto_scale_cover", "bool"),
            ("Cover scaling method", "cover_scaling_method", "str"),
            ("Description auto-fill", "description_auto_fill_mode", "str"),
            ("Preview Description", "preview_description", "action"),
            ("Create description on upload", "description_auto_fill_on_upload", "bool"),
            ("Extract track cover if cover missing", "extract_track_cover_if_missing", "bool"),
            ("Clear progress on album change", "clear_progress_on_album_change", "bool"),
            ("Auto load cookies on startup", "auto_load_cookies", "bool"),
            ("Check for updates on startup", "check_for_updates", "bool"),
            ("Check for updates now", "check_updates_now", "action"),
        ]
        
        # Create treeview for general settings (no headings)
        self.general_tree = ttk.Treeview(
            parent,
            columns=('setting', 'value'),
            show='tree',
            selectmode='browse'
        )
        self.general_tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Hide the tree column
        self.general_tree.column('#0', width=0, stretch=False)
        
        # Configure columns
        self.general_tree.column('setting', width=250, anchor=tk.W)
        self.general_tree.column('value', width=150, anchor=tk.W)
        
        # Populate treeview with settings
        self.general_vars = {}
        self.general_item_mapping = {}
        
        for setting_name, config_key, setting_type in settings:
            if setting_type == "bool":
                var = tk.BooleanVar(value=getattr(self.config, config_key, True))
                display_value = "☑" if var.get() else "☐"
            elif setting_type == "str":
                var = tk.StringVar(value=getattr(self.config, config_key, "Off"))
                display_value = var.get()
            elif setting_type == "action":
                var = None
                display_value = "Preview..."
            
            if var is not None:
                self.general_vars[config_key] = var
            self.general_vars[f"{config_key}_type"] = setting_type
            
            # Add item to treeview
            item_id = self.general_tree.insert('', 'end', values=(setting_name, display_value))
            self.general_item_mapping[item_id] = config_key
        
        # Bind double-click to edit
        self.general_tree.bind('<Button-1>', self.on_general_tree_click)
        self.general_tree.bind('<Double-Button-1>', self.on_general_tree_double_click)
    
    def create_context_menu_settings(self, parent):
        """Create Context Menu settings section using Treeview"""
        # Context menu settings treeview
        settings = [
            ("Show Context Menu Icons", "show_context_menu_icons", "bool"),
            ("Remove Dividers", "context_menu_remove_dividers", "bool"),
            ("Play", "context_menu_play", "bool"),
            ("Remove Track", "context_menu_remove_track", "bool"),
            ("Move Up", "context_menu_move_up", "bool"),
            ("Move Down", "context_menu_move_down", "bool"),
            ("Move to Top", "context_menu_move_to_top", "bool"),
            ("Move to Bottom", "context_menu_move_to_bottom", "bool"),
            ("Open File Location", "context_menu_open_file", "bool"),
            ("Replace File", "context_menu_replace_file", "bool"),
            ("Extract Cover Art", "context_menu_extract_cover_art", "bool"),
            ("Extract Tracklist", "context_menu_extract_tracklist", "bool"),
            ("Open session.txt", "context_menu_open_session", "bool"),
            ("Set Track Cover as Album Cover", "context_menu_set_track_cover_as_album_cover", "bool"),
            ("Undo", "context_menu_undo", "bool"),
            ("Redo", "context_menu_redo", "bool"),
            ("Extract Track Information", "context_menu_extract_track_info", "bool"),
            ("Copy Metadata", "context_menu_copy_metadata", "bool"),
            ("Paste Metadata", "context_menu_paste_metadata", "bool"),
            ("Revert to Original", "context_menu_revert_to_original", "bool"),
            ("Lock/Unlock", "context_menu_lock_unlock", "bool"),
            ("Randomize", "context_menu_randomize", "bool"),
            ("Smart Randomize", "context_menu_smart_randomize", "bool"),
            ("Sort By", "context_menu_sort_by", "bool"),
            ("Clear Metadata", "context_menu_clear_metadata", "bool"),
            ("Clear All Metadata", "context_menu_clear_all_metadata", "bool"),
            ("Clear All Tracks", "context_menu_clear_all", "bool")
        ]
        
        # Create treeview for context menu settings (no headings)
        self.context_menu_tree = ttk.Treeview(
            parent,
            columns=('setting', 'value'),
            show='tree',
            selectmode='browse'
        )
        self.context_menu_tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Hide the tree column
        self.context_menu_tree.column('#0', width=0, stretch=False)
        
        # Configure columns
        self.context_menu_tree.column('setting', width=250, anchor=tk.W)
        self.context_menu_tree.column('value', width=150, anchor=tk.W)
        
        # Populate treeview with settings
        self.context_menu_vars = {}
        self.context_menu_item_mapping = {}
        
        for setting_name, config_key, setting_type in settings:
            if setting_type == "bool":
                var = tk.BooleanVar(value=getattr(self.config, config_key, True))
                display_value = "☑" if var.get() else "☐"
            
            self.context_menu_vars[config_key] = var
            self.context_menu_vars[f"{config_key}_type"] = setting_type
            
            # Add item to treeview
            item_id = self.context_menu_tree.insert('', 'end', values=(setting_name, display_value))
            self.context_menu_item_mapping[item_id] = config_key
        
        # Bind double-click to edit
        self.context_menu_tree.bind('<Double-Button-1>', self.on_context_menu_tree_double_click)
    
    def on_context_menu_tree_double_click(self, event):
        """Handle double-click on context menu treeview to toggle settings"""
        # Get clicked item and column
        item_id = self.context_menu_tree.identify('item', event.x, event.y)
        column = self.context_menu_tree.identify('column', event.x, event.y)
        
        if not item_id or column != '#2':  # Only edit value column
            return
        
        # Get config_key from mapping
        config_key = self.context_menu_item_mapping.get(item_id)
        if not config_key:
            return
        
        # Toggle boolean
        current_value = self.context_menu_vars[config_key].get()
        new_value = not current_value
        self.context_menu_vars[config_key].set(new_value)
        self.context_menu_tree.set(item_id, 'value', '☑' if new_value else '☐')
        self.apply_context_menu_settings()
    
    def apply_context_menu_settings(self):
        """Apply context menu settings immediately"""
        context_menu_configs = [
            "show_context_menu_icons", "context_menu_remove_dividers",
            "context_menu_play", "context_menu_remove_track", "context_menu_move_up",
            "context_menu_move_down", "context_menu_move_to_top", "context_menu_move_to_bottom",
            "context_menu_open_file", "context_menu_replace_file", "context_menu_extract_cover_art",
            "context_menu_extract_tracklist", "context_menu_open_session",
            "context_menu_set_track_cover_as_album_cover", "context_menu_undo",
            "context_menu_redo", "context_menu_extract_track_info",
            "context_menu_copy_metadata", "context_menu_paste_metadata",
            "context_menu_revert_to_original", "context_menu_lock_unlock",
            "context_menu_randomize", "context_menu_smart_randomize",
            "context_menu_sort_by", "context_menu_clear_metadata", "context_menu_clear_all_metadata",
            "context_menu_clear_all"
        ]
        
        for config_key in context_menu_configs:
            if config_key in self.context_menu_vars:
                setattr(self.config, config_key, self.context_menu_vars[config_key].get())
        
        save_config(self.config)
        self.refresh_context_menu_icons()

    def create_sort_method_settings(self, parent):
        """Create Sort By submenu method visibility settings."""
        self.sort_method_tree = ttk.Treeview(
            parent,
            columns=('setting', 'value'),
            show='tree',
            selectmode='browse'
        )
        self.sort_method_tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.sort_method_tree.column('#0', width=0, stretch=False)
        self.sort_method_tree.column('setting', width=250, anchor=tk.W)
        self.sort_method_tree.column('value', width=150, anchor=tk.W)

        self.sort_method_vars = {}
        self.sort_method_item_mapping = {}

        for setting_name, config_key in SORT_METHOD_SETTINGS:
            var = tk.BooleanVar(value=getattr(self.config, config_key, True))
            display_value = "☑" if var.get() else "☐"

            self.sort_method_vars[config_key] = var
            item_id = self.sort_method_tree.insert('', 'end', values=(setting_name, display_value))
            self.sort_method_item_mapping[item_id] = config_key

        self.sort_method_tree.bind('<Double-Button-1>', self.on_sort_method_tree_double_click)

    def on_sort_method_tree_double_click(self, event):
        """Handle double-click on sort method settings."""
        item_id = self.sort_method_tree.identify('item', event.x, event.y)
        column = self.sort_method_tree.identify('column', event.x, event.y)

        if not item_id or column != '#2':
            return

        config_key = self.sort_method_item_mapping.get(item_id)
        if not config_key:
            return

        current_value = self.sort_method_vars[config_key].get()
        new_value = not current_value
        self.sort_method_vars[config_key].set(new_value)
        self.sort_method_tree.set(item_id, 'value', '☑' if new_value else '☐')
        self.apply_sort_method_settings()

    def apply_sort_method_settings(self):
        """Apply Sort By submenu method settings immediately."""
        for _setting_name, config_key in SORT_METHOD_SETTINGS:
            if config_key in self.sort_method_vars:
                setattr(self.config, config_key, self.sort_method_vars[config_key].get())

        save_config(self.config)
    
    def create_toast_settings(self, parent):
        """Create Toast Notifications settings section using Treeview"""
        # Toast settings treeview
        settings = [
            ("Enable Toast Notifications", "enable_toasts", "bool"),
            ("Toast Duration (s)", "toast_duration", "int"),
            ("Toast Position", "toast_position", "str"),
            ("Test Toast Notification", "test_toast_notification", "action"),
            ("Enable Fade Out Effect", "toast_fade_out", "bool"),
            ("Font Family", "toast_font_family", "str"),
            ("Font Size", "toast_font_size", "int"),
            ("Font Bold", "toast_font_bold", "bool"),
            ("Text Color", "toast_text_color", "color"),
            ("Background Color", "toast_bg_color", "color"),
            ("Border Color", "toast_border_color", "color"),
            ("Success Color", "toast_success_color", "color"),
            ("Error Color", "toast_error_color", "color"),
            ("Warning Color", "toast_warning_color", "color"),
            ("Info Color", "toast_info_color", "color")
        ]
        
        # Create treeview for toast settings (no headings)
        self.toast_tree = ttk.Treeview(
            parent,
            columns=('setting', 'value'),
            show='tree',
            selectmode='browse'
        )
        self.toast_tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Hide the tree column
        self.toast_tree.column('#0', width=0, stretch=False)
        
        # Configure columns
        self.toast_tree.column('setting', width=250, anchor=tk.W)
        self.toast_tree.column('value', width=150, anchor=tk.W)
        
        # Populate treeview with settings
        self.toast_vars = {}
        self.toast_item_mapping = {}
        
        for setting_name, config_key, setting_type in settings:
            if setting_type == "bool":
                var = tk.BooleanVar(value=getattr(self.config, config_key, True))
                display_value = "☑" if var.get() else "☐"
            elif setting_type == "int":
                var = tk.StringVar(value=str(getattr(self.config, config_key, 3)))
                display_value = var.get()
            elif setting_type == "str":
                var = tk.StringVar(value=getattr(self.config, config_key, 'Segoe UI'))
                display_value = var.get()
            elif setting_type == "color":
                var = tk.StringVar(value=getattr(self.config, config_key, '#ffffff'))
                display_value = var.get()
            elif setting_type == "action":
                var = tk.StringVar(value="Test")
                display_value = "Test"
            
            self.toast_vars[config_key] = var
            self.toast_vars[f"{config_key}_type"] = setting_type
            
            # Add item to treeview
            item_id = self.toast_tree.insert('', 'end', values=(setting_name, display_value))
            self.toast_item_mapping[item_id] = config_key
        
        # Bind double-click to edit
        self.toast_tree.bind('<Double-Button-1>', self.on_toast_tree_double_click)
    
    def on_toast_tree_double_click(self, event):
        """Handle double-click on toast treeview to edit settings inline"""
        # Get clicked item and column
        item_id = self.toast_tree.identify('item', event.x, event.y)
        column = self.toast_tree.identify('column', event.x, event.y)
        
        if not item_id or column != '#2':  # Only edit value column
            return
        
        # Get config_key from mapping
        config_key = self.toast_item_mapping.get(item_id)
        if not config_key:
            return
        
        setting_type = self.toast_vars.get(f"{config_key}_type")
        
        if setting_type == "bool":
            # Toggle boolean
            current_value = self.toast_vars[config_key].get()
            new_value = not current_value
            self.toast_vars[config_key].set(new_value)
            self.toast_tree.set(item_id, 'value', '☑' if new_value else '☐')
            self.apply_toast_settings()
        elif setting_type == "int":
            # Inline editing with Entry
            self.edit_treeview_cell(self.toast_tree, item_id, 'value', 
                                   self.toast_vars[config_key].get(), 
                                   lambda v: self.apply_toast_int_setting(config_key, v))
        elif setting_type == "str":
            # Inline dropdown for position and font family
            if config_key == "toast_position":
                positions = ['top-right', 'top-left', 'bottom-right', 'bottom-left']
                self.edit_treeview_cell_dropdown(self.toast_tree, item_id, 'value',
                                                positions, self.toast_vars[config_key].get(),
                                                lambda v: self.apply_toast_str_setting(config_key, v))
            elif config_key == "toast_font_family":
                fonts = ['Segoe UI', 'Arial', 'Helvetica', 'Times New Roman', 'Courier New', 'Verdana', 'Georgia', 'Tahoma']
                self.edit_treeview_cell_dropdown(self.toast_tree, item_id, 'value',
                                                fonts, self.toast_vars[config_key].get(),
                                                lambda v: self.apply_toast_str_setting(config_key, v))
            else:
                self.edit_treeview_cell(self.toast_tree, item_id, 'value', 
                                       self.toast_vars[config_key].get(), 
                                       lambda v: self.apply_toast_str_setting(config_key, v))
        elif setting_type == "color":
            # Color picker
            color = colorchooser.askcolor(title=f"Choose {config_key} color",
                                        initialcolor=self.toast_vars[config_key].get())
            if color[1]:
                self.toast_vars[config_key].set(color[1])
                self.toast_tree.set(item_id, 'value', color[1])
                self.apply_toast_settings()
        elif setting_type == "action":
            # Execute action
            if config_key == "test_toast_notification":
                self.test_toast_notification()
    
    def apply_toast_settings(self):
        """Apply toast settings immediately"""
        self.config.enable_toasts = self.toast_vars['enable_toasts'].get()
        self.config.toast_duration = int(self.toast_vars['toast_duration'].get())
        self.config.toast_position = self.toast_vars['toast_position'].get()
        self.config.toast_fade_out = self.toast_vars['toast_fade_out'].get()
        self.config.toast_font_family = self.toast_vars['toast_font_family'].get()
        self.config.toast_font_size = int(self.toast_vars['toast_font_size'].get())
        self.config.toast_font_bold = self.toast_vars['toast_font_bold'].get()
        self.config.toast_text_color = self.toast_vars['toast_text_color'].get()
        self.config.toast_bg_color = self.toast_vars['toast_bg_color'].get()
        self.config.toast_border_color = self.toast_vars['toast_border_color'].get()
        self.config.toast_success_color = self.toast_vars['toast_success_color'].get()
        self.config.toast_error_color = self.toast_vars['toast_error_color'].get()
        self.config.toast_warning_color = self.toast_vars['toast_warning_color'].get()
        self.config.toast_info_color = self.toast_vars['toast_info_color'].get()
        save_config(self.config)
    
    def apply_toast_int_setting(self, config_key, new_value):
        """Apply integer setting and update treeview"""
        try:
            int_value = int(new_value)
            self.toast_vars[config_key].set(str(int_value))
            self.apply_toast_settings()
            return True
        except ValueError:
            return False
    
    def apply_toast_str_setting(self, config_key, new_value):
        """Apply string setting and update treeview"""
        self.toast_vars[config_key].set(new_value)
        self.apply_toast_settings()
        return True
    
    def create_windows_notifications_settings(self, parent):
        """Create Windows Notifications settings section using Treeview"""
        # Windows notifications settings treeview
        settings = [
            ("Enable Windows Notifications", "windows_notifications", "bool"),
            ("Test Notification", "test_notification", "action")
        ]
        
        # Create treeview for windows notifications settings (no headings)
        self.windows_notifications_tree = ttk.Treeview(
            parent,
            columns=('setting', 'value'),
            show='tree',
            selectmode='browse'
        )
        self.windows_notifications_tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Hide the tree column
        self.windows_notifications_tree.column('#0', width=0, stretch=False)
        
        # Configure columns
        self.windows_notifications_tree.column('setting', width=250, anchor=tk.W)
        self.windows_notifications_tree.column('value', width=150, anchor=tk.W)
        
        # Populate treeview with settings
        self.windows_notifications_vars = {}
        self.windows_notifications_item_mapping = {}
        
        for setting_name, config_key, setting_type in settings:
            if setting_type == "bool":
                var = tk.BooleanVar(value=getattr(self.config, config_key, False))
                display_value = "☑" if var.get() else "☐"
            elif setting_type == "action":
                var = tk.StringVar(value="Test")
                display_value = "Test"
            
            self.windows_notifications_vars[config_key] = var
            self.windows_notifications_vars[f"{config_key}_type"] = setting_type
            
            # Add item to treeview
            item_id = self.windows_notifications_tree.insert('', 'end', values=(setting_name, display_value))
            self.windows_notifications_item_mapping[item_id] = config_key
        
        # Bind double-click to edit
        self.windows_notifications_tree.bind('<Double-Button-1>', self.on_windows_notifications_tree_double_click)
    
    def on_windows_notifications_tree_double_click(self, event):
        """Handle double-click on windows notifications treeview to toggle settings"""
        # Get clicked item and column
        item_id = self.windows_notifications_tree.identify('item', event.x, event.y)
        column = self.windows_notifications_tree.identify('column', event.x, event.y)
        
        if not item_id or column != '#2':  # Only edit value column
            return
        
        # Get config_key from mapping
        config_key = self.windows_notifications_item_mapping.get(item_id)
        if not config_key:
            return
        
        setting_type = self.windows_notifications_vars.get(f"{config_key}_type")
        
        if setting_type == "bool":
            # Toggle boolean
            current_value = self.windows_notifications_vars[config_key].get()
            new_value = not current_value
            self.windows_notifications_vars[config_key].set(new_value)
            self.windows_notifications_tree.set(item_id, 'value', '☑' if new_value else '☐')
            self.apply_windows_notifications_settings()
        elif setting_type == "action":
            # Execute action
            if config_key == "test_notification":
                self.test_windows_notification()
    
    def apply_windows_notifications_settings(self):
        """Apply windows notifications settings immediately"""
        new_value = self.windows_notifications_vars['windows_notifications'].get()
        
        # Prevent enabling if library is not available
        if new_value and not self.windows_toasts_available:
            self.windows_notifications_vars['windows_notifications'].set(False)
            messagebox.showerror("Error", "windows-toasts package is not installed. Please install it with: pip install windows-toasts")
            return
        
        self.config.windows_notifications = new_value
        save_config(self.config)
    
    def test_windows_notification(self):
        """Test Windows notification by sending a test notification"""
        if sys.platform != "win32":
            messagebox.showinfo("Test Notification", "Windows notifications are only available on Windows.")
            return

        if not self.windows_toasts_available:
            messagebox.showerror("Test Failed", "windows-toasts package is not installed. Please install it with: pip install windows-toasts")
            return
        
        try:
            from windows_toasts import Toast, WindowsToaster
            toaster = WindowsToaster('Bandcamp Auto Uploader')
            
            newToast = Toast()
            newToast.text_fields = ["This is a test notification to verify Windows notifications are working correctly."]
            
            toaster.show_toast(newToast)
            self.show_toast("Test notification sent", 2000, "success")
        except Exception as e:
            messagebox.showerror("Test Failed", f"Failed to send test notification:\n{e}")
    
    def test_toast_notification(self):
        """Test toast notification by sending a test notification"""
        # Force show the test notification regardless of trigger settings
        self.toast_queue.put(("This is a test toast notification", 3000, "info"))
    
    def create_notification_triggers_settings(self, parent):
        """Create Notification Triggers settings section using Treeview"""
        # Notification trigger settings treeview
        settings = [
            ("Notify on Upload Success", "notify_on_upload_success", "bool"),
            ("Notify on Upload Error", "notify_on_upload_error", "bool"),
            ("Notify on Track Error", "notify_on_track_error", "bool"),
            ("Notify on Conversion Complete", "notify_on_conversion_complete", "bool"),
            ("Notify on Metadata Load", "notify_on_metadata_load", "bool"),
            ("Notify on File Add", "notify_on_file_add", "bool"),
            ("Notify on Track Add", "notify_on_track_add", "bool"),
            ("Notify on Track Remove", "notify_on_track_remove", "bool"),
            ("Notify on Cover Load", "notify_on_cover_load", "bool"),
            ("Notify on Album Save", "notify_on_album_save", "bool"),
            ("Notify on Settings Save", "notify_on_settings_save", "bool"),
            ("Notify on Artists Load", "notify_on_artists_load", "bool"),
            ("Notify on Template Save", "notify_on_template_save", "bool")
        ]
        
        # Create treeview for notification trigger settings (no headings)
        self.notification_triggers_tree = ttk.Treeview(
            parent,
            columns=('setting', 'value'),
            show='tree',
            selectmode='browse'
        )
        self.notification_triggers_tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Hide the tree column
        self.notification_triggers_tree.column('#0', width=0, stretch=False)
        
        # Configure columns
        self.notification_triggers_tree.column('setting', width=250, anchor=tk.W)
        self.notification_triggers_tree.column('value', width=150, anchor=tk.W)
        
        # Populate treeview with settings
        self.notification_triggers_vars = {}
        self.notification_triggers_item_mapping = {}
        
        for setting_name, config_key, setting_type in settings:
            if setting_type == "bool":
                var = tk.BooleanVar(value=getattr(self.config, config_key, True))
                display_value = "☑" if var.get() else "☐"
            
            self.notification_triggers_vars[config_key] = var
            self.notification_triggers_vars[f"{config_key}_type"] = setting_type
            
            # Add item to treeview
            item_id = self.notification_triggers_tree.insert('', 'end', values=(setting_name, display_value))
            self.notification_triggers_item_mapping[item_id] = config_key
        
        # Bind double-click to edit
        self.notification_triggers_tree.bind('<Double-Button-1>', self.on_notification_triggers_tree_double_click)
    
    def on_notification_triggers_tree_double_click(self, event):
        """Handle double-click on notification triggers treeview to toggle settings"""
        # Get clicked item and column
        item_id = self.notification_triggers_tree.identify('item', event.x, event.y)
        column = self.notification_triggers_tree.identify('column', event.x, event.y)
        
        if not item_id or column != '#2':  # Only edit value column
            return
        
        # Get config_key from mapping
        config_key = self.notification_triggers_item_mapping.get(item_id)
        if not config_key:
            return
        
        # Toggle boolean
        current_value = self.notification_triggers_vars[config_key].get()
        new_value = not current_value
        self.notification_triggers_vars[config_key].set(new_value)
        self.notification_triggers_tree.set(item_id, 'value', '☑' if new_value else '☐')
        self.apply_notification_triggers_settings()
    
    def apply_notification_triggers_settings(self):
        """Apply notification trigger settings immediately"""
        trigger_configs = [
            "notify_on_upload_success", "notify_on_upload_error", "notify_on_track_error",
            "notify_on_conversion_complete", "notify_on_metadata_load", "notify_on_file_add",
            "notify_on_track_add", "notify_on_track_remove", "notify_on_cover_load",
            "notify_on_album_save", "notify_on_settings_save", "notify_on_artists_load", "notify_on_template_save"
        ]
        
        for config_key in trigger_configs:
            if config_key in self.notification_triggers_vars:
                setattr(self.config, config_key, self.notification_triggers_vars[config_key].get())
        
        save_config(self.config)
    
    def create_notifications_combined_settings(self, parent):
        """Create combined Notifications settings section that includes all sub-sections"""
        # Combined settings from all notification sub-sections
        settings = [
            # Toast Notifications settings
            ("Toast: Enable Toast Notifications", "enable_toasts", "bool"),
            ("Toast: Toast Duration (s)", "toast_duration", "int"),
            ("Toast: Toast Position", "toast_position", "str"),
            ("Toast: Test Toast Notification", "test_toast_notification", "action"),
            ("Toast: Enable Fade Out Effect", "toast_fade_out", "bool"),
            ("Toast: Font Family", "toast_font_family", "str"),
            ("Toast: Font Size", "toast_font_size", "int"),
            ("Toast: Font Bold", "toast_font_bold", "bool"),
            ("Toast: Text Color", "toast_text_color", "color"),
            ("Toast: Background Color", "toast_bg_color", "color"),
            ("Toast: Border Color", "toast_border_color", "color"),
            ("Toast: Success Color", "toast_success_color", "color"),
            ("Toast: Error Color", "toast_error_color", "color"),
            ("Toast: Warning Color", "toast_warning_color", "color"),
            ("Toast: Info Color", "toast_info_color", "color"),
            # Windows Notifications settings
            ("Windows: Enable Windows Notifications", "windows_notifications", "bool"),
            ("Windows: Test Notification", "test_notification", "action"),
            # Notification Triggers settings
            ("Trigger: Notify on Upload Success", "notify_on_upload_success", "bool"),
            ("Trigger: Notify on Upload Error", "notify_on_upload_error", "bool"),
            ("Trigger: Notify on Track Error", "notify_on_track_error", "bool"),
            ("Trigger: Notify on Conversion Complete", "notify_on_conversion_complete", "bool"),
            ("Trigger: Notify on Metadata Load", "notify_on_metadata_load", "bool"),
            ("Trigger: Notify on File Add", "notify_on_file_add", "bool"),
            ("Trigger: Notify on Track Add", "notify_on_track_add", "bool"),
            ("Trigger: Notify on Track Remove", "notify_on_track_remove", "bool"),
            ("Trigger: Notify on Cover Load", "notify_on_cover_load", "bool"),
            ("Trigger: Notify on Album Save", "notify_on_album_save", "bool"),
            ("Trigger: Notify on Settings Save", "notify_on_settings_save", "bool"),
            ("Trigger: Notify on Artists Load", "notify_on_artists_load", "bool"),
            ("Trigger: Notify on Template Save", "notify_on_template_save", "bool")
        ]
        
        # Create treeview for combined notifications settings (no headings)
        self.notifications_combined_tree = ttk.Treeview(
            parent,
            columns=('setting', 'value'),
            show='tree',
            selectmode='browse'
        )
        self.notifications_combined_tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Hide the tree column
        self.notifications_combined_tree.column('#0', width=0, stretch=False)
        
        # Configure columns
        self.notifications_combined_tree.column('setting', width=250, anchor=tk.W)
        self.notifications_combined_tree.column('value', width=150, anchor=tk.W)
        
        # Populate treeview with settings
        self.notifications_combined_vars = {}
        self.notifications_combined_item_mapping = {}
        
        for setting_name, config_key, setting_type in settings:
            if setting_type == "bool":
                var = tk.BooleanVar(value=getattr(self.config, config_key, True))
                display_value = "☑" if var.get() else "☐"
            elif setting_type == "int":
                var = tk.StringVar(value=str(getattr(self.config, config_key, 3)))
                display_value = var.get()
            elif setting_type == "str":
                var = tk.StringVar(value=getattr(self.config, config_key, 'Segoe UI'))
                display_value = var.get()
            elif setting_type == "color":
                var = tk.StringVar(value=getattr(self.config, config_key, '#ffffff'))
                display_value = var.get()
            elif setting_type == "action":
                var = tk.StringVar(value="Test")
                display_value = "Test"
            
            self.notifications_combined_vars[config_key] = var
            self.notifications_combined_vars[f"{config_key}_type"] = setting_type
            
            # Add item to treeview
            item_id = self.notifications_combined_tree.insert('', 'end', values=(setting_name, display_value))
            self.notifications_combined_item_mapping[item_id] = config_key
        
        # Bind double-click to edit
        self.notifications_combined_tree.bind('<Double-Button-1>', self.on_notifications_combined_tree_double_click)
    
    def on_notifications_combined_tree_double_click(self, event):
        """Handle double-click on combined notifications treeview to toggle settings"""
        # Get clicked item and column
        item_id = self.notifications_combined_tree.identify('item', event.x, event.y)
        column = self.notifications_combined_tree.identify('column', event.x, event.y)
        
        if not item_id or column != '#2':  # Only edit value column
            return
        
        # Get config_key from mapping
        config_key = self.notifications_combined_item_mapping.get(item_id)
        if not config_key:
            return
        
        setting_type = self.notifications_combined_vars.get(f"{config_key}_type")
        
        if setting_type == "bool":
            # Toggle boolean
            current_value = self.notifications_combined_vars[config_key].get()
            new_value = not current_value
            self.notifications_combined_vars[config_key].set(new_value)
            self.notifications_combined_tree.set(item_id, 'value', '☑' if new_value else '☐')
            self.apply_notifications_combined_settings()
        elif setting_type == "action":
            # Execute action
            if config_key == "test_toast_notification":
                self.test_toast_notification()
            elif config_key == "test_notification":
                self.test_windows_notification()
    
    def apply_notifications_combined_settings(self):
        """Apply combined notifications settings immediately"""
        # Apply toast settings
        self.config.enable_toasts = self.notifications_combined_vars['enable_toasts'].get()
        self.config.toast_duration = int(self.notifications_combined_vars['toast_duration'].get())
        self.config.toast_position = self.notifications_combined_vars['toast_position'].get()
        self.config.toast_fade_out = self.notifications_combined_vars['toast_fade_out'].get()
        self.config.toast_font_family = self.notifications_combined_vars['toast_font_family'].get()
        self.config.toast_font_size = int(self.notifications_combined_vars['toast_font_size'].get())
        self.config.toast_font_bold = self.notifications_combined_vars['toast_font_bold'].get()
        self.config.toast_text_color = self.notifications_combined_vars['toast_text_color'].get()
        self.config.toast_bg_color = self.notifications_combined_vars['toast_bg_color'].get()
        self.config.toast_border_color = self.notifications_combined_vars['toast_border_color'].get()
        self.config.toast_success_color = self.notifications_combined_vars['toast_success_color'].get()
        self.config.toast_error_color = self.notifications_combined_vars['toast_error_color'].get()
        self.config.toast_warning_color = self.notifications_combined_vars['toast_warning_color'].get()
        self.config.toast_info_color = self.notifications_combined_vars['toast_info_color'].get()
        
        # Apply windows notifications settings
        new_value = self.notifications_combined_vars['windows_notifications'].get()
        
        # Prevent enabling if library is not available
        if new_value and not self.windows_toasts_available:
            self.notifications_combined_vars['windows_notifications'].set(False)
            messagebox.showerror("Error", "windows-toasts package is not installed. Please install it with: pip install windows-toasts")
            return
        
        self.config.windows_notifications = new_value
        
        # Apply notification trigger settings
        trigger_configs = [
            "notify_on_upload_success", "notify_on_upload_error", "notify_on_track_error",
            "notify_on_conversion_complete", "notify_on_metadata_load", "notify_on_file_add",
            "notify_on_track_add", "notify_on_track_remove", "notify_on_cover_load",
            "notify_on_album_save", "notify_on_settings_save", "notify_on_artists_load", "notify_on_template_save"
        ]
        
        for config_key in trigger_configs:
            if config_key in self.notifications_combined_vars:
                setattr(self.config, config_key, self.notifications_combined_vars[config_key].get())
        
        save_config(self.config)
    
    def test_windows_notification(self):
        """Test Windows notification by sending a test notification"""
        if sys.platform != "win32":
            messagebox.showinfo("Test Notification", "Windows notifications are only available on Windows.")
            return

        if not self.windows_toasts_available:
            messagebox.showerror("Test Failed", "windows-toasts package is not installed. Please install it with: pip install windows-toasts")
            return
        
        try:
            from windows_toasts import Toast, WindowsToaster
            toaster = WindowsToaster('Bandcamp Auto Uploader')
            
            newToast = Toast()
            newToast.text_fields = ["This is a test notification to verify Windows notifications are working correctly."]
            
            toaster.show_toast(newToast)
            self.show_toast("Test notification sent", 2000, "success")
        except Exception as e:
            messagebox.showerror("Test Failed", f"Failed to send test notification:\n{e}")
    
    def on_general_tree_double_click(self, event):
        """Handle double-click on general treeview to edit settings"""
        # Get clicked item
        item_id = self.general_tree.identify('item', event.x, event.y)
        if not item_id:
            return
        
        # Get config_key from mapping
        config_key = self.general_item_mapping.get(item_id)
        if not config_key:
            return
        
        setting_type = self.general_vars.get(f"{config_key}_type")

        if setting_type == "action":
            if config_key == "preview_description":
                self.open_description_preview_dialog()
            elif config_key == "check_updates_now":
                self.check_for_updates_now()
            return
        
        if setting_type == "bool":
            # Toggle boolean
            current_value = self.general_vars[config_key].get()
            new_value = not current_value
            self.general_vars[config_key].set(new_value)
            self.general_tree.set(item_id, 'value', '☑' if new_value else '☐')
            
            # Apply the appropriate setting
            if config_key == "apply_settings_immediately":
                self.apply_immediate_setting()
            elif config_key == "maximize_on_open":
                self.apply_maximize_setting()
            elif config_key == "disable_tooltips":
                self.apply_tooltip_setting()
            elif config_key == "auto_load_metadata":
                self.apply_auto_load_metadata_setting()
            elif config_key in (
                "create_album_session_files",
                "guess_album_title_from_track_metadata",
                "guess_release_date_from_track_metadata",
                "use_folder_name_when_album_missing",
                "use_album_artist_in_album_details",
                "smart_randomize_on_album_load",
                "auto_guess_case_on_album_load",
                "always_auto_scale_cover",
                "description_auto_fill_on_upload",
                "extract_track_cover_if_missing",
                "clear_progress_on_album_change",
            ):
                self.apply_metadata_guess_setting()
            elif config_key == "auto_load_cookies":
                self.apply_auto_load_cookies_setting()
            elif config_key == "check_for_updates":
                self.config.check_for_updates = self.general_vars['check_for_updates'].get()
                save_config(self.config)
        elif setting_type == "str":
            if config_key == "description_auto_fill_mode":
                self.edit_treeview_cell_dropdown(
                    self.general_tree,
                    item_id,
                    'value',
                    DESCRIPTION_AUTO_FILL_MODES,
                    self.general_vars[config_key].get(),
                    lambda v: self.apply_general_str_setting(config_key, v),
                )
            elif config_key == "cover_scaling_method":
                self.edit_treeview_cell_dropdown(
                    self.general_tree,
                    item_id,
                    'value',
                    SCALING_METHOD_OPTIONS,
                    self.general_vars[config_key].get(),
                    lambda v: self.apply_general_str_setting(config_key, v),
                )

    def on_general_tree_click(self, event):
        """Handle single-click actions in the General settings tree."""
        item_id = self.general_tree.identify('item', event.x, event.y)
        column = self.general_tree.identify('column', event.x, event.y)
        if not item_id or column != '#2':
            return

        config_key = self.general_item_mapping.get(item_id)
        if config_key == "preview_description":
            self.root.after_idle(self.open_description_preview_dialog)
            return "break"
        if config_key == "check_updates_now":
            self.root.after_idle(self.check_for_updates_now)
            return "break"

    def center_dialog(self, dialog, width=None, height=None, parent=None):
        """Center a dialog over its parent window, falling back to the screen."""
        dialog.update_idletasks()
        width = width or dialog.winfo_width()
        height = height or dialog.winfo_height()
        parent = parent if parent is not None and parent.winfo_exists() else self.root

        parent.update_idletasks()
        parent_x = parent.winfo_rootx()
        parent_y = parent.winfo_rooty()
        parent_width = parent.winfo_width()
        parent_height = parent.winfo_height()

        if parent_width <= 1 or parent_height <= 1:
            x = (dialog.winfo_screenwidth() // 2) - (width // 2)
            y = (dialog.winfo_screenheight() // 2) - (height // 2)
        else:
            x = parent_x + (parent_width // 2) - (width // 2)
            y = parent_y + (parent_height // 2) - (height // 2)

        dialog.geometry(f"{width}x{height}+{max(0, x)}+{max(0, y)}")

    def get_preferences_dialog_parent(self):
        """Return the active Preferences dialog when it exists."""
        dialog = getattr(self, 'preferences_dialog', None)
        if dialog is not None and dialog.winfo_exists():
            return dialog
        return self.root

    def open_description_preview_dialog(self):
        """Preview the description generated by the selected template."""
        generated_description = self.build_auto_description_from_mode().strip()
        description = generated_description
        mode = getattr(self.config, 'description_auto_fill_mode', "Off")
        if not description:
            if mode == "Off":
                description = "Description auto-fill is Off."
            else:
                description = "No description could be generated from the current album preview."

        parent = self.get_preferences_dialog_parent()
        dialog = tk.Toplevel(parent)
        dialog.title("Preview Description")
        dialog.transient(parent)
        dialog.resizable(True, True)
        self.center_dialog(dialog, 640, 460, parent)

        def close_preview():
            try:
                dialog.grab_release()
            except tk.TclError:
                pass
            if parent is not self.root and parent.winfo_exists():
                try:
                    parent.grab_set()
                except tk.TclError:
                    pass
            dialog.destroy()

        dialog.protocol("WM_DELETE_WINDOW", close_preview)
        dialog.grab_set()

        frame = ttk.Frame(dialog, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)

        text_frame = ttk.Frame(frame)
        text_frame.pack(fill=tk.BOTH, expand=True)

        preview_text = tk.Text(text_frame, wrap=tk.WORD, font=("Consolas", 9), height=16)
        scrollbar = ttk.Scrollbar(text_frame, orient=tk.VERTICAL, command=preview_text.yview)
        preview_text.configure(yscrollcommand=scrollbar.set)
        preview_text.insert("1.0", description)
        preview_text.config(state=tk.DISABLED)
        preview_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        button_frame = ttk.Frame(frame)
        button_frame.pack(fill=tk.X, pady=(10, 0))

        def use_description():
            self.set_album_description_text(generated_description)
            self.show_toast("Description applied", 1800, "success")
            close_preview()

        ttk.Button(
            button_frame,
            text="Use Description",
            command=use_description,
            state=tk.NORMAL if generated_description else tk.DISABLED
        ).pack(side=tk.RIGHT, padx=(5, 0))
        ttk.Button(button_frame, text="Close", command=close_preview).pack(side=tk.RIGHT)
    
    def apply_general_str_setting(self, config_key, new_value):
        """Apply a General string/dropdown setting and update config."""
        if config_key == "description_auto_fill_mode" and new_value not in DESCRIPTION_AUTO_FILL_MODES:
            return False
        if config_key == "cover_scaling_method" and new_value not in SCALING_METHOD_OPTIONS:
            return False

        self.general_vars[config_key].set(new_value)
        setattr(self.config, config_key, new_value)
        if config_key == "cover_scaling_method" and hasattr(self, 'scaling_method_var'):
            self.scaling_method_var.set(new_value)
        save_config(self.config)
        if config_key == "description_auto_fill_mode" and getattr(self.config, 'notify_on_template_save', False):
            self.show_toast(f"Description template set to: {new_value}", 1800, "success", trigger="template_save")
        return True
    
    def apply_immediate_setting(self):
        """Apply the 'apply settings immediately' setting"""
        self.config.apply_settings_immediately = self.general_vars['apply_settings_immediately'].get()
        save_config(self.config)
    
    def apply_maximize_setting(self):
        """Apply the 'maximize on open' setting"""
        self.config.maximize_on_open = self.general_vars['maximize_on_open'].get()
        save_config(self.config)

    def apply_tooltip_setting(self):
        """Apply the tooltip visibility setting."""
        self.config.disable_tooltips = self.general_vars['disable_tooltips'].get()
        ToolTip.disabled = self.config.disable_tooltips
        save_config(self.config)
    
    def apply_auto_load_metadata_setting(self):
        """Apply the 'auto load metadata' setting"""
        self.config.auto_load_metadata = self.general_vars['auto_load_metadata'].get()
        save_config(self.config)

    def apply_metadata_guess_setting(self):
        """Apply metadata guessing and album-load settings."""
        self.config.guess_album_title_from_track_metadata = self.general_vars['guess_album_title_from_track_metadata'].get()
        self.config.guess_release_date_from_track_metadata = self.general_vars['guess_release_date_from_track_metadata'].get()
        self.config.create_album_session_files = self.general_vars['create_album_session_files'].get()
        self.config.use_folder_name_when_album_missing = self.general_vars['use_folder_name_when_album_missing'].get()
        self.config.use_album_artist_in_album_details = self.general_vars['use_album_artist_in_album_details'].get()
        self.config.smart_randomize_on_album_load = self.general_vars['smart_randomize_on_album_load'].get()
        self.config.auto_guess_case_on_album_load = self.general_vars['auto_guess_case_on_album_load'].get()
        self.config.always_auto_scale_cover = self.general_vars['always_auto_scale_cover'].get()
        self.config.description_auto_fill_on_upload = self.general_vars['description_auto_fill_on_upload'].get()
        self.config.extract_track_cover_if_missing = self.general_vars['extract_track_cover_if_missing'].get()
        self.config.clear_progress_on_album_change = self.general_vars['clear_progress_on_album_change'].get()
        if hasattr(self, 'scale_cover_var'):
            self.scale_cover_var.set(self.config.always_auto_scale_cover)
        save_config(self.config)

    def apply_auto_load_cookies_setting(self):
        """Apply the 'auto load cookies' setting"""
        self.config.auto_load_cookies = self.general_vars['auto_load_cookies'].get()
        save_config(self.config)

    def on_scale_cover_changed(self):
        """Persist the preferred cover auto-scale checkbox state."""
        try:
            self.config.always_auto_scale_cover = self.scale_cover_var.get()
            save_config(self.config)
        except Exception as e:
            logger.debug(f"Failed to save cover scaling preference: {e}")

    def create_about_settings(self, parent):
        """Create About section"""
        import webbrowser
        import sys

        container = ttk.Frame(parent)
        container.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        ttk.Label(container, text="Bandcamp Auto Uploader",
                  font=("Segoe UI", 16, "bold")).pack()

        ttk.Label(container, text=f"Version {__version__}",
                  font=("Segoe UI", 10)).pack(pady=(5, 15))

        info = f"Python {sys.version.split()[0]}  |  {sys.platform}  |  {'EXE' if getattr(sys, 'frozen', False) else 'Source'}"
        ttk.Label(container, text=info, font=("Segoe UI", 8), foreground="gray").pack()

        ttk.Separator(container, orient='horizontal').pack(fill=tk.X, pady=15)

        ttk.Label(container, text="Links", font=("Segoe UI", 10, "bold")).pack()
        ttk.Button(container, text="GitHub Repository",
                   command=lambda: webbrowser.open("https://github.com/Nai64/BandcampAutoUploader"),
                   width=25).pack(pady=3)
        ttk.Button(container, text="Original Project (7x11x13)",
                   command=lambda: webbrowser.open("https://github.com/7x11x13/bandcamp-auto-uploader"),
                   width=25).pack(pady=3)

        ttk.Separator(container, orient='horizontal').pack(fill=tk.X, pady=15)

        ttk.Label(container, text="Credits", font=("Segoe UI", 10, "bold")).pack()
        credits = ("Based on bandcamp-auto-uploader by 7x11x13\n"
                   "GUI fork and enhancements by Nai64\n"
                   "Some icons by Yusuke Kamiyamane (CC BY 3.0)")
        ttk.Label(container, text=credits, font=("Segoe UI", 8), justify=tk.CENTER,
                  foreground="gray").pack(pady=(5, 15))

        ttk.Label(container, text="MIT License — See GitHub for full text",
                  font=("Segoe UI", 8), foreground="gray").pack()
    
    def edit_treeview_cell(self, tree, item_id, column, current_value, callback):
        """Edit treeview cell inline with Entry widget"""
        # Get cell coordinates
        x, y, width, height = tree.bbox(item_id, column)
        
        # Create entry widget
        entry = ttk.Entry(tree, font=("Segoe UI", 9))
        entry.place(x=x, y=y, width=width, height=height)
        entry.insert(0, current_value)
        entry.select_range(0, tk.END)
        entry.focus_set()
        
        def save_edit(event=None):
            new_value = entry.get().strip()
            if new_value and callback(new_value):
                tree.set(item_id, column, new_value)
            entry.destroy()
        
        def cancel_edit(event=None):
            entry.destroy()
        
        entry.bind('<Return>', save_edit)
        entry.bind('<Escape>', cancel_edit)
        entry.bind('<FocusOut>', lambda e: save_edit())
    
    def edit_treeview_cell_dropdown(self, tree, item_id, column, options, current_value, callback):
        """Edit treeview cell inline with dropdown"""
        # Get cell coordinates
        x, y, width, height = tree.bbox(item_id, column)
        
        # Create combobox
        combo = ttk.Combobox(tree, values=options, state="readonly", font=("Segoe UI", 9))
        combo.place(x=x, y=y, width=width, height=height)
        combo.set(current_value)
        combo.focus_set()
        
        # Open dropdown after a small delay to ensure widget is rendered
        def open_dropdown():
            try:
                combo.event_generate('<Button-1>')
            except:
                pass
        
        combo.after(50, open_dropdown)
        
        def save_edit(event=None):
            new_value = combo.get()
            if callback(new_value):
                tree.set(item_id, column, new_value)
            combo.destroy()
        
        def cancel_edit(event=None):
            combo.destroy()
        
        combo.bind('<<ComboboxSelected>>', save_edit)
        combo.bind('<Escape>', cancel_edit)
    
    def create_column_settings(self, parent):
        """Create Track Table Columns settings section using Treeview"""
        # Column visibility settings
        columns = [
            ("Always Auto Fit Columns", "auto_fit_columns", "bool"),
            ("Locked Track Highlight", "locked_track_highlight_color", "color"),
            ("Track No.", "show_track_no", "bool"),
            ("Artist", "show_artist", "bool"),
            ("Track Name", "show_track_name", "bool"),
            ("Comment", "show_comment", "bool"),
            ("Length", "show_length", "bool"),
            ("Extension", "show_extension", "bool"),
            ("Price", "show_price", "bool"),
            ("NYP", "show_nyp", "bool"),
            ("Year", "show_year", "bool"),
            ("Genre", "show_genre", "bool"),
            ("Bitrate", "show_bitrate", "bool"),
            ("File Size", "show_file_size", "bool"),
            ("Sample Rate", "show_sample_rate", "bool"),
            ("Channels", "show_channels", "bool"),
            ("Bit Depth", "show_bit_depth", "bool"),
            ("Album Metadata", "show_album_metadata", "bool"),
            ("Album Artist Metadata", "show_album_artist_metadata", "bool"),
            ("Composer", "show_composer", "bool"),
            ("ISRC", "show_isrc", "bool")
        ]
        
        # Create treeview for column settings (no headings)
        self.column_tree = ttk.Treeview(
            parent,
            columns=('setting', 'value'),
            show='tree',
            selectmode='browse'
        )
        self.column_tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Hide the tree column
        self.column_tree.column('#0', width=0, stretch=False)
        
        # Configure columns
        self.column_tree.column('setting', width=250, anchor=tk.W)
        self.column_tree.column('value', width=150, anchor=tk.W)
        
        # Populate treeview with settings
        self.column_vars = {}
        self.column_item_mapping = {}
        
        for col_name, config_key, setting_type in columns:
            if setting_type == "color":
                var = tk.StringVar(value=getattr(self.config, config_key, "#fff4ce"))
                display_value = var.get()
            else:
                var = tk.BooleanVar(value=getattr(self.config, config_key, True))
                display_value = "☑" if var.get() else "☐"
            
            self.column_vars[config_key] = var
            self.column_vars[f"{config_key}_type"] = setting_type
            
            # Add item to treeview
            item_id = self.column_tree.insert('', 'end', values=(col_name, display_value))
            self.column_item_mapping[item_id] = config_key
        
        # Bind double-click to edit
        self.column_tree.bind('<Double-Button-1>', self.on_column_tree_double_click)

    def create_logs_settings(self, parent):
        """Create Logs visual customization settings section using Treeview"""
        # Logs settings treeview
        settings = [
            # Font Settings
            ("Font Family", "log_font_family", "choice", ["Segoe UI", "Consolas", "Courier New", "monospace", "Arial", "Tahoma"]),
            ("Font Size", "log_font_size", "int", 8, 16),
            ("Font Bold", "log_font_bold", "bool"),
            # Color Settings
            ("Text Color", "log_text_color", "color"),
            ("Background Color", "log_bg_color", "color"),
            ("INFO Color", "log_info_color", "color"),
            ("WARNING Color", "log_warning_color", "color"),
            ("ERROR Color", "log_error_color", "color"),
            ("DEBUG Color", "log_debug_color", "color"),
            # Display Settings
            ("Show Timestamps", "log_show_timestamps", "bool"),
            ("Timestamp Format", "log_timestamp_format", "choice", ["HH:MM:SS", "YYYY-MM-DD HH:MM:SS", "MM/DD/YYYY HH:MM:SS", "None"]),
            ("Show Log Levels", "log_show_levels", "bool"),
            ("Word Wrap", "log_word_wrap", "bool"),
            ("Line Spacing", "log_line_spacing", "int", 1, 3),
            # Behavior Settings
            ("Auto-scroll to Bottom", "log_auto_scroll", "bool"),
            ("Max Lines (0 = unlimited)", "log_max_lines", "int", 0, 10000),
            ("Save Diagnostic Log File", "log_to_file", "bool"),
            ("Diagnostic Log Level", "log_file_level", "choice", ["DEBUG", "INFO", "WARNING", "ERROR"])
        ]
        
        # Create treeview for logs settings (no headings)
        self.logs_tree = ttk.Treeview(
            parent,
            columns=('setting', 'value'),
            show='tree',
            selectmode='browse'
        )
        self.logs_tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Hide the tree column
        self.logs_tree.column('#0', width=0, stretch=False)
        
        # Configure columns
        self.logs_tree.column('setting', width=250, anchor=tk.W)
        self.logs_tree.column('value', width=150, anchor=tk.W)
        
        # Populate treeview with settings
        self.logs_vars = {}
        self.logs_item_mapping = {}
        
        for setting_data in settings:
            setting_name = setting_data[0]
            config_key = setting_data[1]
            setting_type = setting_data[2]
            
            if setting_type == "bool":
                var = tk.BooleanVar(value=getattr(self.config, config_key, False))
                display_value = "☑" if var.get() else "☐"
            elif setting_type == "int":
                min_val = setting_data[3]
                max_val = setting_data[4]
                var = tk.IntVar(value=getattr(self.config, config_key, min_val))
                display_value = str(var.get())
            elif setting_type == "choice":
                choices = setting_data[3]
                var = tk.StringVar(value=getattr(self.config, config_key, choices[0]))
                display_value = var.get()
            elif setting_type == "color":
                var = tk.StringVar(value=getattr(self.config, config_key, '#ffffff'))
                display_value = var.get()
            
            self.logs_vars[config_key] = var
            self.logs_vars[f"{config_key}_type"] = setting_type
            if setting_type == "int":
                self.logs_vars[f"{config_key}_min"] = min_val
                self.logs_vars[f"{config_key}_max"] = max_val
            elif setting_type == "choice":
                self.logs_vars[f"{config_key}_choices"] = choices
            
            # Add item to treeview
            item_id = self.logs_tree.insert('', 'end', values=(setting_name, display_value))
            self.logs_item_mapping[item_id] = config_key
        
        # Bind double-click to edit
        self.logs_tree.bind('<Double-Button-1>', self.on_logs_tree_double_click)

    def on_logs_tree_double_click(self, event):
        """Handle double-click on logs treeview to edit settings"""
        # Get clicked item and column
        item_id = self.logs_tree.identify('item', event.x, event.y)
        column = self.logs_tree.identify('column', event.x, event.y)
        
        if not item_id or column != '#2':  # Only edit value column
            return
        
        # Get config_key from mapping
        config_key = self.logs_item_mapping.get(item_id)
        if not config_key:
            return
        
        setting_type = self.logs_vars.get(f"{config_key}_type")
        
        if setting_type == "bool":
            # Toggle boolean
            current_value = self.logs_vars[config_key].get()
            new_value = not current_value
            self.logs_vars[config_key].set(new_value)
            self.logs_tree.set(item_id, 'value', '☑' if new_value else '☐')
            
            # Apply the setting
            setattr(self.config, config_key, new_value)
            save_config(self.config)
            self.apply_log_visual_settings()
            if config_key in ("log_to_file", "log_file_level") and hasattr(self, "setup_logging"):
                self.setup_logging()
            
        elif setting_type == "int":
            # Edit integer inline
            min_val = self.logs_vars.get(f"{config_key}_min", 0)
            max_val = self.logs_vars.get(f"{config_key}_max", 10000)
            current_value = str(self.logs_vars[config_key].get())
            
            def validate_and_save(new_value):
                try:
                    int_val = int(new_value)
                    if min_val <= int_val <= max_val:
                        self.logs_vars[config_key].set(int_val)
                        setattr(self.config, config_key, int_val)
                        save_config(self.config)
                        self.apply_log_visual_settings()
                        if config_key in ("log_to_file", "log_file_level") and hasattr(self, "setup_logging"):
                            self.setup_logging()
                        return True
                except ValueError:
                    pass
                return False
            
            self.edit_treeview_cell(self.logs_tree, item_id, 'value', current_value, validate_and_save)
            
        elif setting_type == "choice":
            # Edit choice inline with dropdown
            choices = self.logs_vars.get(f"{config_key}_choices", [])
            current_value = self.logs_vars[config_key].get()
            
            def validate_and_save(new_value):
                self.logs_vars[config_key].set(new_value)
                setattr(self.config, config_key, new_value)
                save_config(self.config)
                self.apply_log_visual_settings()
                if config_key in ("log_to_file", "log_file_level") and hasattr(self, "setup_logging"):
                    self.setup_logging()
                return True
            
            self.edit_treeview_cell_dropdown(self.logs_tree, item_id, 'value', choices, current_value, validate_and_save)
            
        elif setting_type == "color":
            # Edit color with color picker (only one that needs a dialog)
            current_color = self.logs_vars[config_key].get()
            new_color = colorchooser.askcolor(color=current_color)[1]
            if new_color:
                self.logs_vars[config_key].set(new_color)
                self.logs_tree.set(item_id, 'value', new_color)
                setattr(self.config, config_key, new_color)
                save_config(self.config)
                self.apply_log_visual_settings()



    def apply_log_visual_settings(self):
        """Apply all log visual settings to the log widget"""
        if not hasattr(self, 'log_text'):
            return

        # Apply font settings
        font_family = self.config.log_font_family
        font_size = self.config.log_font_size
        font_weight = "bold" if self.config.log_font_bold else "normal"
        self.log_text.configure(font=(font_family, font_size, font_weight))

        # Apply color settings
        self.log_text.configure(fg=self.config.log_text_color, bg=self.config.log_bg_color)

        # Apply word wrap
        wrap_mode = tk.WORD if self.config.log_word_wrap else tk.NONE
        self.log_text.configure(wrap=wrap_mode)

        # Note: Line spacing and timestamp formats require log message format changes
        # These will be applied in the log formatting logic
    
    def create_interface_combined_settings(self, parent):
        """Create combined Interface settings section that includes all sub-sections"""
        # Combined settings from all interface sub-sections
        settings = [
            # Track Table Columns settings
            ("Columns: Always Auto Fit Columns", "auto_fit_columns", "bool"),
            ("Columns: Locked Track Highlight", "locked_track_highlight_color", "color"),
            ("Columns: Track No.", "show_track_no", "bool"),
            ("Columns: Artist", "show_artist", "bool"),
            ("Columns: Track Name", "show_track_name", "bool"),
            ("Columns: Comment", "show_comment", "bool"),
            ("Columns: Length", "show_length", "bool"),
            ("Columns: Extension", "show_extension", "bool"),
            ("Columns: Price", "show_price", "bool"),
            ("Columns: NYP", "show_nyp", "bool"),
            ("Columns: Year", "show_year", "bool"),
            ("Columns: Genre", "show_genre", "bool"),
            ("Columns: Bitrate", "show_bitrate", "bool"),
            ("Columns: File Size", "show_file_size", "bool"),
            ("Columns: Sample Rate", "show_sample_rate", "bool"),
            ("Columns: Channels", "show_channels", "bool"),
            ("Columns: Bit Depth", "show_bit_depth", "bool"),
            ("Columns: Album Metadata", "show_album_metadata", "bool"),
            ("Columns: Album Artist Metadata", "show_album_artist_metadata", "bool"),
            ("Columns: Composer", "show_composer", "bool"),
            ("Columns: ISRC", "show_isrc", "bool"),
            # Logs Font Settings
            ("Logs: Font Family", "log_font_family", "choice", ["Segoe UI", "Consolas", "Courier New", "monospace", "Arial", "Tahoma"]),
            ("Logs: Font Size", "log_font_size", "int", 8, 16),
            ("Logs: Font Bold", "log_font_bold", "bool"),
            # Logs Color Settings
            ("Logs: Text Color", "log_text_color", "color"),
            ("Logs: Background Color", "log_bg_color", "color"),
            ("Logs: INFO Color", "log_info_color", "color"),
            ("Logs: WARNING Color", "log_warning_color", "color"),
            ("Logs: ERROR Color", "log_error_color", "color"),
            ("Logs: DEBUG Color", "log_debug_color", "color"),
            # Logs Display Settings
            ("Logs: Show Timestamps", "log_show_timestamps", "bool"),
            ("Logs: Timestamp Format", "log_timestamp_format", "choice", ["HH:MM:SS", "YYYY-MM-DD HH:MM:SS", "MM/DD/YYYY HH:MM:SS", "None"]),
            ("Logs: Show Log Levels", "log_show_levels", "bool"),
            ("Logs: Word Wrap", "log_word_wrap", "bool"),
            ("Logs: Line Spacing", "log_line_spacing", "int", 1, 3),
            # Logs Behavior Settings
            ("Logs: Auto-scroll to Bottom", "log_auto_scroll", "bool"),
            ("Logs: Max Lines (0 = unlimited)", "log_max_lines", "int", 0, 10000),
            ("Logs: Save Diagnostic Log File", "log_to_file", "bool"),
            ("Logs: Diagnostic Log Level", "log_file_level", "choice", ["DEBUG", "INFO", "WARNING", "ERROR"])
        ]
        
        # Create treeview for combined interface settings (no headings)
        self.interface_combined_tree = ttk.Treeview(
            parent,
            columns=('setting', 'value'),
            show='tree',
            selectmode='browse'
        )
        self.interface_combined_tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Hide the tree column
        self.interface_combined_tree.column('#0', width=0, stretch=False)
        
        # Configure columns
        self.interface_combined_tree.column('setting', width=250, anchor=tk.W)
        self.interface_combined_tree.column('value', width=150, anchor=tk.W)
        
        # Populate treeview with settings
        self.interface_combined_vars = {}
        self.interface_combined_item_mapping = {}
        
        for setting_data in settings:
            setting_name = setting_data[0]
            config_key = setting_data[1]
            setting_type = setting_data[2]
            
            if setting_type == "bool":
                var = tk.BooleanVar(value=getattr(self.config, config_key, True))
                display_value = "☑" if var.get() else "☐"
            elif setting_type == "int":
                min_val = setting_data[3]
                max_val = setting_data[4]
                var = tk.IntVar(value=getattr(self.config, config_key, min_val))
                display_value = str(var.get())
            elif setting_type == "choice":
                choices = setting_data[3]
                var = tk.StringVar(value=getattr(self.config, config_key, choices[0]))
                display_value = var.get()
            elif setting_type == "color":
                var = tk.StringVar(value=getattr(self.config, config_key, '#ffffff'))
                display_value = var.get()
            
            self.interface_combined_vars[config_key] = var
            self.interface_combined_vars[f"{config_key}_type"] = setting_type
            if setting_type == "int":
                self.interface_combined_vars[f"{config_key}_min"] = min_val
                self.interface_combined_vars[f"{config_key}_max"] = max_val
            elif setting_type == "choice":
                self.interface_combined_vars[f"{config_key}_choices"] = choices
            
            # Add item to treeview
            item_id = self.interface_combined_tree.insert('', 'end', values=(setting_name, display_value))
            self.interface_combined_item_mapping[item_id] = config_key
        
        # Bind double-click to edit
        self.interface_combined_tree.bind('<Double-Button-1>', self.on_interface_combined_tree_double_click)
    
    def on_interface_combined_tree_double_click(self, event):
        """Handle double-click on combined interface treeview to edit settings"""
        # Get clicked item and column
        item_id = self.interface_combined_tree.identify('item', event.x, event.y)
        column = self.interface_combined_tree.identify('column', event.x, event.y)
        
        if not item_id or column != '#2':  # Only edit value column
            return
        
        # Get config_key from mapping
        config_key = self.interface_combined_item_mapping.get(item_id)
        if not config_key:
            return
        
        setting_type = self.interface_combined_vars.get(f"{config_key}_type")
        
        if setting_type == "bool":
            # Toggle boolean
            current_value = self.interface_combined_vars[config_key].get()
            new_value = not current_value
            self.interface_combined_vars[config_key].set(new_value)
            self.interface_combined_tree.set(item_id, 'value', '☑' if new_value else '☐')
            self.apply_interface_combined_settings()
            
        elif setting_type == "int":
            # Edit integer inline
            min_val = self.interface_combined_vars.get(f"{config_key}_min", 0)
            max_val = self.interface_combined_vars.get(f"{config_key}_max", 10000)
            current_value = str(self.interface_combined_vars[config_key].get())
            
            def validate_and_save(new_value):
                try:
                    int_val = int(new_value)
                    if min_val <= int_val <= max_val:
                        self.interface_combined_vars[config_key].set(int_val)
                        self.apply_interface_combined_settings()
                        return True
                except ValueError:
                    pass
                return False
            
            self.edit_treeview_cell(self.interface_combined_tree, item_id, 'value', current_value, validate_and_save)
            
        elif setting_type == "choice":
            # Edit choice inline with dropdown
            choices = self.interface_combined_vars.get(f"{config_key}_choices", [])
            current_value = self.interface_combined_vars[config_key].get()
            
            def validate_and_save(new_value):
                self.interface_combined_vars[config_key].set(new_value)
                self.apply_interface_combined_settings()
                return True
            
            self.edit_treeview_cell_dropdown(self.interface_combined_tree, item_id, 'value', choices, current_value, validate_and_save)
            
        elif setting_type == "color":
            # Edit color with color picker
            current_color = self.interface_combined_vars[config_key].get()
            new_color = colorchooser.askcolor(color=current_color)[1]
            if new_color:
                self.interface_combined_vars[config_key].set(new_color)
                self.interface_combined_tree.set(item_id, 'value', new_color)
                self.apply_interface_combined_settings()
    
    def apply_interface_combined_settings(self):
        """Apply combined interface settings immediately"""
        # Apply column visibility settings
        column_configs = [
            "auto_fit_columns",
            "show_track_no", "show_artist", "show_track_name", "show_comment",
            "show_length", "show_extension", "show_price", "show_nyp",
            "show_year", "show_genre", "show_bitrate", "show_file_size",
            "show_sample_rate", "show_channels", "show_bit_depth",
            "show_album_metadata", "show_album_artist_metadata",
            "show_composer", "show_isrc", "locked_track_highlight_color"
        ]
        
        for config_key in column_configs:
            if config_key in self.interface_combined_vars:
                setattr(self.config, config_key, self.interface_combined_vars[config_key].get())
        
        # Apply logs settings
        self.config.log_font_family = self.interface_combined_vars['log_font_family'].get()
        self.config.log_font_size = self.interface_combined_vars['log_font_size'].get()
        self.config.log_font_bold = self.interface_combined_vars['log_font_bold'].get()
        self.config.log_text_color = self.interface_combined_vars['log_text_color'].get()
        self.config.log_bg_color = self.interface_combined_vars['log_bg_color'].get()
        self.config.log_info_color = self.interface_combined_vars['log_info_color'].get()
        self.config.log_warning_color = self.interface_combined_vars['log_warning_color'].get()
        self.config.log_error_color = self.interface_combined_vars['log_error_color'].get()
        self.config.log_debug_color = self.interface_combined_vars['log_debug_color'].get()
        self.config.log_show_timestamps = self.interface_combined_vars['log_show_timestamps'].get()
        self.config.log_timestamp_format = self.interface_combined_vars['log_timestamp_format'].get()
        self.config.log_show_levels = self.interface_combined_vars['log_show_levels'].get()
        self.config.log_word_wrap = self.interface_combined_vars['log_word_wrap'].get()
        self.config.log_line_spacing = self.interface_combined_vars['log_line_spacing'].get()
        self.config.log_auto_scroll = self.interface_combined_vars['log_auto_scroll'].get()
        self.config.log_max_lines = self.interface_combined_vars['log_max_lines'].get()
        self.config.log_to_file = self.interface_combined_vars['log_to_file'].get()
        self.config.log_file_level = self.interface_combined_vars['log_file_level'].get()
        
        save_config(self.config)
        
        # Apply visual changes
        self.apply_log_visual_settings()
        if hasattr(self, "setup_logging"):
            self.setup_logging()
        if hasattr(self, 'configure_track_table_tags'):
            self.configure_track_table_tags()
        self.apply_column_visibility()
    
    def on_column_tree_double_click(self, event):
        """Handle double-click on column treeview to toggle visibility"""
        # Get clicked item and column
        item_id = self.column_tree.identify('item', event.x, event.y)
        column = self.column_tree.identify('column', event.x, event.y)
        
        if not item_id or column != '#2':  # Only edit value column
            return
        
        # Get config_key from mapping
        config_key = self.column_item_mapping.get(item_id)
        if not config_key:
            return
        
        setting_type = self.column_vars.get(f"{config_key}_type", "bool")
        if setting_type == "color":
            current_color = self.column_vars[config_key].get()
            new_color = colorchooser.askcolor(color=current_color)[1]
            if new_color:
                self.column_vars[config_key].set(new_color)
                self.column_tree.set(item_id, 'value', new_color)
                self.apply_column_settings()
            return

        # Toggle boolean
        current_value = self.column_vars[config_key].get()
        new_value = not current_value
        self.column_vars[config_key].set(new_value)
        self.column_tree.set(item_id, 'value', '☑' if new_value else '☐')
        self.apply_column_settings()
    
    def apply_column_settings(self):
        """Apply column visibility settings immediately"""
        column_configs = [
            "auto_fit_columns",
            "show_track_no", "show_artist", "show_track_name", "show_comment",
            "show_length", "show_extension", "show_price", "show_nyp",
            "show_year", "show_genre", "show_bitrate", "show_file_size",
            "show_sample_rate", "show_channels", "show_bit_depth",
            "show_album_metadata", "show_album_artist_metadata",
            "show_composer", "show_isrc"
        ]
        
        for config_key in column_configs:
            if config_key in self.column_vars:
                setattr(self.config, config_key, self.column_vars[config_key].get())
        if "locked_track_highlight_color" in self.column_vars:
            self.config.locked_track_highlight_color = self.column_vars["locked_track_highlight_color"].get()
        
        save_config(self.config)
        if hasattr(self, 'configure_track_table_tags'):
            self.configure_track_table_tags()
        self.apply_column_visibility()
    
    def create_auto_tagging_settings(self, parent):
        """Create Auto Tagging settings section using Treeview"""
        # Auto tagging settings
        settings = [
            ("Year", "auto_tag_year", "bool"),
            ("Genre", "auto_tag_genre", "bool"),
            ("Artist", "auto_tag_artist", "bool"),
            ("Album", "auto_tag_album", "bool"),
            ("Comment", "auto_tag_comment", "bool"),
            ("Track Title", "auto_tag_track_title", "bool"),
            ("Album Artist", "auto_tag_album_artist", "bool"),
            ("Composer", "auto_tag_composer", "bool"),
            ("Track Number", "auto_tag_track_number", "bool"),
            ("Duration", "auto_tag_duration", "bool"),
            ("Bitrate", "auto_tag_bitrate", "bool"),
            ("Release Type", "auto_tag_release_type", "bool")
        ]
        
        # Create treeview for auto tagging settings (no headings)
        self.auto_tagging_tree = ttk.Treeview(
            parent,
            columns=('setting', 'value'),
            show='tree',
            selectmode='browse'
        )
        self.auto_tagging_tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Hide the tree column
        self.auto_tagging_tree.column('#0', width=0, stretch=False)
        
        # Configure columns
        self.auto_tagging_tree.column('setting', width=250, anchor=tk.W)
        self.auto_tagging_tree.column('value', width=150, anchor=tk.W)
        
        # Populate treeview with settings
        self.auto_tagging_vars = {}
        self.auto_tagging_item_mapping = {}
        
        for setting_name, config_key, setting_type in settings:
            if setting_type == "bool":
                var = tk.BooleanVar(value=getattr(self.config, config_key, False))
                display_value = "☑" if var.get() else "☐"
            
            self.auto_tagging_vars[config_key] = var
            self.auto_tagging_vars[f"{config_key}_type"] = setting_type
            
            # Add item to treeview
            item_id = self.auto_tagging_tree.insert('', 'end', values=(setting_name, display_value))
            self.auto_tagging_item_mapping[item_id] = config_key
        
        # Bind double-click to edit
        self.auto_tagging_tree.bind('<Double-Button-1>', self.on_auto_tagging_tree_double_click)
    
    def on_auto_tagging_tree_double_click(self, event):
        """Handle double-click on auto tagging treeview to toggle settings"""
        # Get clicked item and column
        item_id = self.auto_tagging_tree.identify('item', event.x, event.y)
        column = self.auto_tagging_tree.identify('column', event.x, event.y)
        
        if not item_id or column != '#2':  # Only edit value column
            return
        
        # Get config_key from mapping
        config_key = self.auto_tagging_item_mapping.get(item_id)
        if not config_key:
            return
        
        # Toggle boolean
        current_value = self.auto_tagging_vars[config_key].get()
        new_value = not current_value
        
        # Check limit when trying to enable (not disable)
        if new_value:
            # Count currently enabled auto-tagging options
            enabled_count = sum(1 for key, var in self.auto_tagging_vars.items() 
                             if not key.endswith('_type') and var.get())
            if enabled_count >= 10:
                self.show_toast("Maximum 10 auto-tagging options allowed", 2000, "warning")
                return
        
        self.auto_tagging_vars[config_key].set(new_value)
        self.auto_tagging_tree.set(item_id, 'value', '☑' if new_value else '☐')
        self.apply_auto_tagging_settings()
    
    def apply_auto_tagging_settings(self):
        """Apply auto tagging settings immediately"""
        self.config.auto_tag_year = self.auto_tagging_vars['auto_tag_year'].get()
        self.config.auto_tag_genre = self.auto_tagging_vars['auto_tag_genre'].get()
        self.config.auto_tag_artist = self.auto_tagging_vars['auto_tag_artist'].get()
        self.config.auto_tag_album = self.auto_tagging_vars['auto_tag_album'].get()
        self.config.auto_tag_comment = self.auto_tagging_vars['auto_tag_comment'].get()
        self.config.auto_tag_track_title = self.auto_tagging_vars['auto_tag_track_title'].get()
        self.config.auto_tag_album_artist = self.auto_tagging_vars['auto_tag_album_artist'].get()
        self.config.auto_tag_composer = self.auto_tagging_vars['auto_tag_composer'].get()
        self.config.auto_tag_track_number = self.auto_tagging_vars['auto_tag_track_number'].get()
        self.config.auto_tag_duration = self.auto_tagging_vars['auto_tag_duration'].get()
        self.config.auto_tag_bitrate = self.auto_tagging_vars['auto_tag_bitrate'].get()
        self.config.auto_tag_release_type = self.auto_tagging_vars['auto_tag_release_type'].get()
        save_config(self.config)
    
    def create_upload_settings(self, parent):
        """Create Upload settings section using Treeview"""
        # Upload settings treeview
        settings = [
            ("Auto-start upload after adding files", "auto_start_upload", "bool"),
            ("Confirm before starting upload", "confirm_before_upload", "bool"),
            ("Open logs on album upload", "open_logs_on_upload", "bool"),
            ("Open album page after upload", "open_album_page_after_upload", "bool"),
            ("Copy album URL to clipboard after upload", "copy_album_url_after_upload", "bool"),
            ("Use embedded cover art from tracks", "extract_embedded_cover_art", "bool"),
            ("Detailed track information in progress", "detailed_progress_track_info", "bool"),
            ("Show progress timing details", "show_progress_timing_details", "bool"),
            ("Max concurrent uploads", "max_concurrent_uploads", "int", 1, 5),
            ("Upload timeout (seconds)", "upload_timeout", "int", 30, 600),
            ("Retry failed uploads", "retry_failed_uploads", "bool"),
            ("Retry attempts", "retry_attempts", "int", 1, 10),
            ("Retry delay (seconds)", "retry_delay", "int", 1, 60)
        ]
        
        # Create treeview for upload settings (no headings)
        self.upload_tree = ttk.Treeview(
            parent,
            columns=('setting', 'value'),
            show='tree',
            selectmode='browse'
        )
        self.upload_tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Hide the tree column
        self.upload_tree.column('#0', width=0, stretch=False)
        
        # Configure columns
        self.upload_tree.column('setting', width=250, anchor=tk.W)
        self.upload_tree.column('value', width=150, anchor=tk.W)
        
        # Populate treeview with settings
        self.upload_vars = {}
        self.upload_item_mapping = {}
        
        for setting_data in settings:
            setting_name = setting_data[0]
            config_key = setting_data[1]
            setting_type = setting_data[2]
            
            if setting_type == "bool":
                var = tk.BooleanVar(value=getattr(self.config, config_key, False))
                display_value = "☑" if var.get() else "☐"
            elif setting_type == "int":
                min_val = setting_data[3]
                max_val = setting_data[4]
                var = tk.IntVar(value=getattr(self.config, config_key, min_val))
                display_value = str(var.get())
            
            self.upload_vars[config_key] = var
            self.upload_vars[f"{config_key}_type"] = setting_type
            if setting_type == "int":
                self.upload_vars[f"{config_key}_min"] = min_val
                self.upload_vars[f"{config_key}_max"] = max_val
            
            # Add item to treeview
            item_id = self.upload_tree.insert('', 'end', values=(setting_name, display_value))
            self.upload_item_mapping[item_id] = config_key
        
        # Bind double-click to edit
        self.upload_tree.bind('<Double-Button-1>', self.on_upload_tree_double_click)
    
    def on_upload_tree_double_click(self, event):
        """Handle double-click on upload treeview to edit settings"""
        # Get clicked item and column
        item_id = self.upload_tree.identify('item', event.x, event.y)
        column = self.upload_tree.identify('column', event.x, event.y)
        
        if not item_id or column != '#2':  # Only edit value column
            return
        
        # Get config_key from mapping
        config_key = self.upload_item_mapping.get(item_id)
        if not config_key:
            return
        
        setting_type = self.upload_vars.get(f"{config_key}_type")
        
        if setting_type == "bool":
            # Toggle boolean
            current_value = self.upload_vars[config_key].get()
            new_value = not current_value
            self.upload_vars[config_key].set(new_value)
            self.upload_tree.set(item_id, 'value', '☑' if new_value else '☐')
            self.apply_upload_settings()
            
        elif setting_type == "int":
            # Edit integer inline
            min_val = self.upload_vars.get(f"{config_key}_min", 0)
            max_val = self.upload_vars.get(f"{config_key}_max", 10000)
            current_value = str(self.upload_vars[config_key].get())
            
            def validate_and_save(new_value):
                try:
                    int_val = int(new_value)
                    if min_val <= int_val <= max_val:
                        self.upload_vars[config_key].set(int_val)
                        self.apply_upload_settings()
                        return True
                except ValueError:
                    pass
                return False
            
            self.edit_treeview_cell(self.upload_tree, item_id, 'value', current_value, validate_and_save)
    
    def apply_upload_settings(self):
        """Apply upload settings immediately"""
        self.config.auto_start_upload = self.upload_vars['auto_start_upload'].get()
        self.config.confirm_before_upload = self.upload_vars['confirm_before_upload'].get()
        self.config.open_logs_on_upload = self.upload_vars['open_logs_on_upload'].get()
        self.config.open_album_page_after_upload = self.upload_vars['open_album_page_after_upload'].get()
        self.config.copy_album_url_after_upload = self.upload_vars['copy_album_url_after_upload'].get()
        self.config.extract_embedded_cover_art = self.upload_vars['extract_embedded_cover_art'].get()
        self.config.detailed_progress_track_info = self.upload_vars['detailed_progress_track_info'].get()
        self.config.show_progress_timing_details = self.upload_vars['show_progress_timing_details'].get()
        self.config.max_concurrent_uploads = self.upload_vars['max_concurrent_uploads'].get()
        self.config.upload_timeout = self.upload_vars['upload_timeout'].get()
        self.config.retry_failed_uploads = self.upload_vars['retry_failed_uploads'].get()
        self.config.retry_attempts = self.upload_vars['retry_attempts'].get()
        self.config.retry_delay = self.upload_vars['retry_delay'].get()
        save_config(self.config)
    
    def create_general_combined_settings(self, parent):
        """Create combined General settings section that includes all sub-sections"""
        # Combined settings from all general sub-sections
        settings = [
            # General Settings
            ("General: Apply settings immediately", "apply_settings_immediately", "bool"),
            ("General: Maximize app on open", "maximize_on_open", "bool"),
            ("General: Disable tooltips", "disable_tooltips", "bool"),
            ("General: Auto load metadata for album details", "auto_load_metadata", "bool"),
            ("General: Use Album Artist metadata for Artist in Album details", "use_album_artist_in_album_details", "bool"),
            ("General: Create session.txt files (Recommended)", "create_album_session_files", "bool"),
            ("General: Guess album title from track metadata", "guess_album_title_from_track_metadata", "bool"),
            ("General: Guess release date from track metadata", "guess_release_date_from_track_metadata", "bool"),
            ("General: Folder name if album tag missing", "use_folder_name_when_album_missing", "bool"),
            ("General: Smart-randomize on album load", "smart_randomize_on_album_load", "bool"),
            ("General: Auto guess case tracks on album load", "auto_guess_case_on_album_load", "bool"),
            ("General: Always auto-scale cover art", "always_auto_scale_cover", "bool"),
            ("General: Cover scaling method", "cover_scaling_method", "str"),
            ("General: Description auto-fill", "description_auto_fill_mode", "str"),
            ("General: Preview Description", "preview_description", "action"),
            ("General: Create description on upload", "description_auto_fill_on_upload", "bool"),
            ("General: Extract track cover if cover missing", "extract_track_cover_if_missing", "bool"),
            ("General: Clear progress on album change", "clear_progress_on_album_change", "bool"),
            ("General: Auto load cookies on startup", "auto_load_cookies", "bool"),
            ("General: Check for updates on startup", "check_for_updates", "bool"),
            # Context Menu settings
            ("Context: Remove Dividers", "context_menu_remove_dividers", "bool"),
            ("Context: Play", "context_menu_play", "bool"),
            ("Context: Remove Track", "context_menu_remove_track", "bool"),
            ("Context: Move Up", "context_menu_move_up", "bool"),
            ("Context: Move Down", "context_menu_move_down", "bool"),
            ("Context: Move to Top", "context_menu_move_to_top", "bool"),
            ("Context: Move to Bottom", "context_menu_move_to_bottom", "bool"),
            ("Context: Open File", "context_menu_open_file", "bool"),
            ("Context: Replace File", "context_menu_replace_file", "bool"),
            ("Context: Extract Cover Art", "context_menu_extract_cover_art", "bool"),
            ("Context: Extract Tracklist", "context_menu_extract_tracklist", "bool"),
            ("Context: Open session.txt", "context_menu_open_session", "bool"),
            ("Context: Set Track Cover as Album Cover", "context_menu_set_track_cover_as_album_cover", "bool"),
            ("Context: Undo", "context_menu_undo", "bool"),
            ("Context: Redo", "context_menu_redo", "bool"),
            ("Context: Extract Track Information", "context_menu_extract_track_info", "bool"),
            ("Context: Copy Metadata", "context_menu_copy_metadata", "bool"),
            ("Context: Paste Metadata", "context_menu_paste_metadata", "bool"),
            ("Context: Revert to Original", "context_menu_revert_to_original", "bool"),
            ("Context: Lock/Unlock", "context_menu_lock_unlock", "bool"),
            ("Context: Randomize", "context_menu_randomize", "bool"),
            ("Context: Smart Randomize", "context_menu_smart_randomize", "bool"),
            ("Context: Sort By", "context_menu_sort_by", "bool"),
            ("Context: Clear Metadata", "context_menu_clear_metadata", "bool"),
            ("Context: Clear All Metadata", "context_menu_clear_all_metadata", "bool"),
            ("Context: Clear All", "context_menu_clear_all", "bool"),
            # Sort method settings
            *[(f"Sort: {setting_name}", config_key, "bool") for setting_name, config_key in SORT_METHOD_SETTINGS],
            # Auto Tagging settings
            ("Auto Tag: Year", "auto_tag_year", "bool"),
            ("Auto Tag: Genre", "auto_tag_genre", "bool"),
            ("Auto Tag: Artist", "auto_tag_artist", "bool"),
            ("Auto Tag: Album", "auto_tag_album", "bool"),
            ("Auto Tag: Comment", "auto_tag_comment", "bool"),
            ("Auto Tag: Track Title", "auto_tag_track_title", "bool"),
            ("Auto Tag: Album Artist", "auto_tag_album_artist", "bool"),
            ("Auto Tag: Composer", "auto_tag_composer", "bool"),
            ("Auto Tag: Track Number", "auto_tag_track_number", "bool"),
            ("Auto Tag: Duration", "auto_tag_duration", "bool"),
            ("Auto Tag: Bitrate", "auto_tag_bitrate", "bool"),
            ("Auto Tag: Release Type", "auto_tag_release_type", "bool")
        ]
        
        # Create treeview for combined general settings (no headings)
        self.general_combined_tree = ttk.Treeview(
            parent,
            columns=('setting', 'value'),
            show='tree',
            selectmode='browse'
        )
        self.general_combined_tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Hide the tree column
        self.general_combined_tree.column('#0', width=0, stretch=False)
        
        # Configure columns
        self.general_combined_tree.column('setting', width=250, anchor=tk.W)
        self.general_combined_tree.column('value', width=150, anchor=tk.W)
        
        # Populate treeview with settings
        self.general_combined_vars = {}
        self.general_combined_item_mapping = {}
        
        for setting_name, config_key, setting_type in settings:
            if setting_type == "bool":
                # Use appropriate default based on config
                if config_key.startswith("auto_tag_"):
                    var = tk.BooleanVar(value=getattr(self.config, config_key, False))
                else:
                    var = tk.BooleanVar(value=getattr(self.config, config_key, True))
                display_value = "☑" if var.get() else "☐"
            elif setting_type == "str":
                var = tk.StringVar(value=getattr(self.config, config_key, "Off"))
                display_value = var.get()
            elif setting_type == "action":
                var = None
                display_value = "Preview..."
            
            if var is not None:
                self.general_combined_vars[config_key] = var
            self.general_combined_vars[f"{config_key}_type"] = setting_type
            
            # Add item to treeview
            item_id = self.general_combined_tree.insert('', 'end', values=(setting_name, display_value))
            self.general_combined_item_mapping[item_id] = config_key
        
        # Bind double-click to edit
        self.general_combined_tree.bind('<Button-1>', self.on_general_combined_tree_click)
        self.general_combined_tree.bind('<Double-Button-1>', self.on_general_combined_tree_double_click)

    def on_general_combined_tree_click(self, event):
        """Handle single-click actions in the combined General settings tree."""
        item_id = self.general_combined_tree.identify('item', event.x, event.y)
        column = self.general_combined_tree.identify('column', event.x, event.y)
        if not item_id or column != '#2':
            return

        config_key = self.general_combined_item_mapping.get(item_id)
        if config_key == "preview_description":
            self.root.after_idle(self.open_description_preview_dialog)
            return "break"
        if config_key == "check_updates_now":
            self.root.after_idle(self.check_for_updates_now)
            return "break"
    
    def on_general_combined_tree_double_click(self, event):
        """Handle double-click on combined general treeview to toggle settings"""
        # Get clicked item and column
        item_id = self.general_combined_tree.identify('item', event.x, event.y)
        column = self.general_combined_tree.identify('column', event.x, event.y)
        
        if not item_id or column != '#2':  # Only edit value column
            return
        
        # Get config_key from mapping
        config_key = self.general_combined_item_mapping.get(item_id)
        if not config_key:
            return
        
        setting_type = self.general_combined_vars.get(f"{config_key}_type")

        if setting_type == "action":
            if config_key == "preview_description":
                self.open_description_preview_dialog()
            elif config_key == "check_updates_now":
                self.check_for_updates_now()
            return
        
        if setting_type == "bool":
            # Toggle boolean
            current_value = self.general_combined_vars[config_key].get()
            new_value = not current_value
            
            # Check limit for auto-tagging options
            if new_value and config_key.startswith("auto_tag_"):
                # Count currently enabled auto-tagging options
                enabled_count = sum(1 for key, var in self.general_combined_vars.items() 
                                 if not key.endswith('_type') and key.startswith("auto_tag_") and var.get())
                if enabled_count >= 10:
                    self.show_toast("Maximum 10 auto-tagging options allowed", 2000, "warning")
                    return
            
            self.general_combined_vars[config_key].set(new_value)
            self.general_combined_tree.set(item_id, 'value', '☑' if new_value else '☐')
            self.apply_general_combined_settings()
        elif setting_type == "str":
            if config_key == "description_auto_fill_mode":
                self.edit_treeview_cell_dropdown(
                    self.general_combined_tree,
                    item_id,
                    'value',
                    DESCRIPTION_AUTO_FILL_MODES,
                    self.general_combined_vars[config_key].get(),
                    lambda v: self.apply_general_combined_str_setting(config_key, v),
                )
            elif config_key == "cover_scaling_method":
                self.edit_treeview_cell_dropdown(
                    self.general_combined_tree,
                    item_id,
                    'value',
                    SCALING_METHOD_OPTIONS,
                    self.general_combined_vars[config_key].get(),
                    lambda v: self.apply_general_combined_str_setting(config_key, v),
                )
    
    def apply_general_combined_settings(self):
        """Apply combined general settings immediately"""
        # Apply general settings
        self.config.apply_settings_immediately = self.general_combined_vars['apply_settings_immediately'].get()
        self.config.maximize_on_open = self.general_combined_vars['maximize_on_open'].get()
        self.config.disable_tooltips = self.general_combined_vars['disable_tooltips'].get()
        self.config.auto_load_metadata = self.general_combined_vars['auto_load_metadata'].get()
        self.config.use_album_artist_in_album_details = self.general_combined_vars['use_album_artist_in_album_details'].get()
        self.config.create_album_session_files = self.general_combined_vars['create_album_session_files'].get()
        self.config.guess_album_title_from_track_metadata = self.general_combined_vars['guess_album_title_from_track_metadata'].get()
        self.config.guess_release_date_from_track_metadata = self.general_combined_vars['guess_release_date_from_track_metadata'].get()
        self.config.use_folder_name_when_album_missing = self.general_combined_vars['use_folder_name_when_album_missing'].get()
        self.config.smart_randomize_on_album_load = self.general_combined_vars['smart_randomize_on_album_load'].get()
        self.config.auto_guess_case_on_album_load = self.general_combined_vars['auto_guess_case_on_album_load'].get()
        self.config.always_auto_scale_cover = self.general_combined_vars['always_auto_scale_cover'].get()
        self.config.cover_scaling_method = self.general_combined_vars['cover_scaling_method'].get()
        self.config.description_auto_fill_mode = self.general_combined_vars['description_auto_fill_mode'].get()
        self.config.description_auto_fill_on_upload = self.general_combined_vars['description_auto_fill_on_upload'].get()
        self.config.extract_track_cover_if_missing = self.general_combined_vars['extract_track_cover_if_missing'].get()
        self.config.clear_progress_on_album_change = self.general_combined_vars['clear_progress_on_album_change'].get()
        self.config.auto_load_cookies = self.general_combined_vars['auto_load_cookies'].get()
        self.config.check_for_updates = self.general_combined_vars['check_for_updates'].get()
        ToolTip.disabled = self.config.disable_tooltips
        if hasattr(self, 'scale_cover_var'):
            self.scale_cover_var.set(self.config.always_auto_scale_cover)
        if hasattr(self, 'scaling_method_var'):
            self.scaling_method_var.set(self.config.cover_scaling_method)
        
        # Apply context menu settings
        self.config.context_menu_remove_dividers = self.general_combined_vars['context_menu_remove_dividers'].get()
        self.config.context_menu_play = self.general_combined_vars['context_menu_play'].get()
        self.config.context_menu_remove_track = self.general_combined_vars['context_menu_remove_track'].get()
        self.config.context_menu_move_up = self.general_combined_vars['context_menu_move_up'].get()
        self.config.context_menu_move_down = self.general_combined_vars['context_menu_move_down'].get()
        self.config.context_menu_move_to_top = self.general_combined_vars['context_menu_move_to_top'].get()
        self.config.context_menu_move_to_bottom = self.general_combined_vars['context_menu_move_to_bottom'].get()
        self.config.context_menu_open_file = self.general_combined_vars['context_menu_open_file'].get()
        self.config.context_menu_replace_file = self.general_combined_vars['context_menu_replace_file'].get()
        self.config.context_menu_extract_cover_art = self.general_combined_vars['context_menu_extract_cover_art'].get()
        self.config.context_menu_extract_tracklist = self.general_combined_vars['context_menu_extract_tracklist'].get()
        self.config.context_menu_open_session = self.general_combined_vars['context_menu_open_session'].get()
        self.config.context_menu_set_track_cover_as_album_cover = self.general_combined_vars['context_menu_set_track_cover_as_album_cover'].get()
        self.config.context_menu_undo = self.general_combined_vars['context_menu_undo'].get()
        self.config.context_menu_redo = self.general_combined_vars['context_menu_redo'].get()
        self.config.context_menu_extract_track_info = self.general_combined_vars['context_menu_extract_track_info'].get()
        self.config.context_menu_copy_metadata = self.general_combined_vars['context_menu_copy_metadata'].get()
        self.config.context_menu_paste_metadata = self.general_combined_vars['context_menu_paste_metadata'].get()
        self.config.context_menu_revert_to_original = self.general_combined_vars['context_menu_revert_to_original'].get()
        self.config.context_menu_lock_unlock = self.general_combined_vars['context_menu_lock_unlock'].get()
        self.config.context_menu_randomize = self.general_combined_vars['context_menu_randomize'].get()
        self.config.context_menu_smart_randomize = self.general_combined_vars['context_menu_smart_randomize'].get()
        self.config.context_menu_sort_by = self.general_combined_vars['context_menu_sort_by'].get()
        self.config.context_menu_clear_metadata = self.general_combined_vars['context_menu_clear_metadata'].get()
        self.config.context_menu_clear_all_metadata = self.general_combined_vars['context_menu_clear_all_metadata'].get()
        self.config.context_menu_clear_all = self.general_combined_vars['context_menu_clear_all'].get()

        # Apply sort method settings
        for _setting_name, config_key in SORT_METHOD_SETTINGS:
            if config_key in self.general_combined_vars:
                setattr(self.config, config_key, self.general_combined_vars[config_key].get())
        
        # Apply auto tagging settings
        self.config.auto_tag_year = self.general_combined_vars['auto_tag_year'].get()
        self.config.auto_tag_genre = self.general_combined_vars['auto_tag_genre'].get()
        self.config.auto_tag_artist = self.general_combined_vars['auto_tag_artist'].get()
        self.config.auto_tag_album = self.general_combined_vars['auto_tag_album'].get()
        self.config.auto_tag_comment = self.general_combined_vars['auto_tag_comment'].get()
        self.config.auto_tag_track_title = self.general_combined_vars['auto_tag_track_title'].get()
        self.config.auto_tag_album_artist = self.general_combined_vars['auto_tag_album_artist'].get()
        self.config.auto_tag_composer = self.general_combined_vars['auto_tag_composer'].get()
        self.config.auto_tag_track_number = self.general_combined_vars['auto_tag_track_number'].get()
        self.config.auto_tag_duration = self.general_combined_vars['auto_tag_duration'].get()
        self.config.auto_tag_bitrate = self.general_combined_vars['auto_tag_bitrate'].get()
        self.config.auto_tag_release_type = self.general_combined_vars['auto_tag_release_type'].get()
        
        save_config(self.config)
        self.refresh_context_menu_icons()

    def apply_general_combined_str_setting(self, config_key, new_value):
        """Apply a combined General string/dropdown setting."""
        if config_key == "description_auto_fill_mode" and new_value not in DESCRIPTION_AUTO_FILL_MODES:
            return False
        if config_key == "cover_scaling_method" and new_value not in SCALING_METHOD_OPTIONS:
            return False

        self.general_combined_vars[config_key].set(new_value)
        setattr(self.config, config_key, new_value)
        if config_key == "cover_scaling_method" and hasattr(self, 'scaling_method_var'):
            self.scaling_method_var.set(new_value)
        save_config(self.config)
        return True
    
    def apply_column_visibility(self):
        """Apply column visibility settings to track table"""
        if not hasattr(self, 'track_table'):
            return
        
        column_mapping = {
            "show_track_no": "track_no",
            "show_artist": "artist",
            "show_track_name": "track_name",
            "show_comment": "comment",
            "show_length": "length",
            "show_extension": "extension",
            "show_price": "price",
            "show_nyp": "nyp",
            "show_year": "year",
            "show_genre": "genre",
            "show_bitrate": "bitrate",
            "show_file_size": "file_size",
            "show_sample_rate": "sample_rate",
            "show_channels": "channels",
            "show_bit_depth": "bit_depth",
            "show_album_metadata": "album_metadata",
            "show_album_artist_metadata": "album_artist_metadata",
            "show_composer": "composer",
            "show_isrc": "isrc"
        }
        
        # Calculate total width of all columns
        total_width = sum(self.column_widths.values())
        
        # Build list of visible columns and calculate their total width
        visible_columns = []
        visible_width = 0
        
        for config_key, col_id in column_mapping.items():
            should_show = getattr(self.config, config_key, True)
            if should_show:
                visible_columns.append(col_id)
                visible_width += self.column_widths.get(col_id, 50)
        
        # Update displaycolumns to show only visible columns
        if visible_columns:
            self.track_table.configure(displaycolumns=visible_columns)
        else:
            # If no columns selected, show all by default
            self.track_table.configure(displaycolumns=list(column_mapping.values()))
            visible_columns = list(column_mapping.values())
            visible_width = total_width
        
        # Set column widths to maintain fixed total width
        if getattr(self.config, 'auto_fit_columns', True):
            if hasattr(self, 'maybe_auto_fit_track_columns'):
                self.maybe_auto_fit_track_columns()
            return

        if visible_columns and visible_width > 0:
            # Scale widths proportionally to maintain total width
            scale_factor = total_width / visible_width
            for col_id in visible_columns:
                original_width = self.column_widths.get(col_id, 50)
                scaled_width = int(original_width * scale_factor)
                self.track_table.column(col_id, width=scaled_width)
        else:
            # If no visible columns, set all to 0
            for col_id in column_mapping.values():
                self.track_table.column(col_id, width=0)
    
    def create_advanced_settings(self, parent):
        """Create Advanced settings using the standard Setting / Value layout."""
        self.advanced_tree = ttk.Treeview(
            parent,
            columns=('setting', 'value'),
            show='tree',
            selectmode='browse'
        )
        self.advanced_tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.advanced_tree.column('#0', width=0, stretch=False)
        self.advanced_tree.column('setting', width=250, anchor=tk.W)
        self.advanced_tree.column('value', width=150, anchor=tk.W)

        self.advanced_item_mapping = {}
        item_id = self.advanced_tree.insert('', 'end', values=("Reset all settings", "Reset..."))
        self.advanced_item_mapping[item_id] = "reset_all_settings"
        item_id = self.advanced_tree.insert('', 'end', values=("Custom Filename Patterns", "Manage..."))
        self.advanced_item_mapping[item_id] = "custom_filename_patterns"

        self.advanced_tree.bind('<Button-1>', self.on_advanced_tree_click)

    def on_advanced_tree_click(self, event):
        """Handle single-click actions in the Advanced settings tree."""
        item_id = self.advanced_tree.identify('item', event.x, event.y)
        column = self.advanced_tree.identify('column', event.x, event.y)
        if not item_id or column != '#2':
            return

        if self.advanced_item_mapping.get(item_id) == "reset_all_settings":
            self.root.after_idle(self.reset_all_settings)
            return "break"
        if self.advanced_item_mapping.get(item_id) == "custom_filename_patterns":
            self.root.after_idle(self.open_custom_filename_patterns_dialog)
            return "break"

    def reset_all_settings(self):
        """Reset all settings to defaults with 3 confirmation dialogs"""
        # First confirmation dialog
        confirm1 = messagebox.askyesno(
            "Reset All Settings - Confirmation 1/3",
            "Are you sure you want to reset ALL settings to defaults?\n\n"
            "This will reset:\n"
            "- All preferences and configurations\n"
            "- UI customizations (colors and fonts)\n"
            "- Column visibility settings\n"
            "- Context menu settings\n"
            "- Upload settings\n"
            "- Notification settings\n"
            "- And all other configurable options\n\n"
            "This action cannot be undone.",
            icon='warning'
        )
        
        if not confirm1:
            return
        
        # Second confirmation dialog
        confirm2 = messagebox.askyesno(
            "Reset All Settings - Confirmation 2/3",
            "This is your second warning.\n\n"
            "All your carefully customized settings will be lost.\n"
            "You will need to reconfigure everything from scratch.\n\n"
            "Are you absolutely sure you want to proceed?",
            icon='warning'
        )
        
        if not confirm2:
            return
        
        # Third confirmation dialog
        confirm3 = messagebox.askyesno(
            "Reset All Settings - Final Confirmation",
            "FINAL WARNING: This is your last chance to cancel.\n\n"
            "Once you click Yes, all settings will be immediately reset\n"
            "to their default values and the application will restart.\n\n"
            "Click Yes to reset everything or No to cancel.",
            icon='warning'
        )
        
        if not confirm3:
            return
        
        # Perform the reset
        try:
            default_config = Config()
            
            # Save the default config
            save_config(default_config)
            
            # Show success message
            messagebox.showinfo(
                "Settings Reset Complete",
                "All settings have been reset to defaults.\n\n"
                "The application will now restart to apply the changes."
            )
            
            # Restart the application
            self.restart_application()
            
        except Exception as e:
            messagebox.showerror(
                "Reset Failed",
                f"Failed to reset settings:\n{str(e)}"
            )

    def open_custom_filename_patterns_dialog(self):
        """Open dialog to manage custom filename regex patterns."""
        dialog = tk.Toplevel(self.root)
        dialog.title("Custom Filename Patterns")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.resizable(True, True)
        self.center_dialog(dialog, 600, 400, self.root)

        patterns = list(getattr(self.config, 'filename_track_patterns', []))

        frame = ttk.Frame(dialog, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text="Custom Regex Patterns",
                  font=("Segoe UI", 11, "bold")).pack(anchor=tk.W, pady=(0, 10))

        list_frame = ttk.Frame(frame)
        list_frame.pack(fill=tk.BOTH, expand=True)

        listbox = tk.Listbox(list_frame, font=("Consolas", 10))
        scroll = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=listbox.yview)
        listbox.configure(yscrollcommand=scroll.set)
        listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        def refresh_listbox():
            listbox.delete(0, tk.END)
            for p in patterns:
                if isinstance(p, str):
                    listbox.insert(tk.END, p)
                elif isinstance(p, (list, tuple)):
                    parts = [str(x) if x is not None else "" for x in p]
                    listbox.insert(tk.END, " | ".join(parts))

        refresh_listbox()

        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X, pady=(10, 0))

        def add_pattern():
            add_dialog = tk.Toplevel(dialog)
            add_dialog.title("Add Pattern")
            add_dialog.transient(dialog)
            add_dialog.grab_set()
            self.center_dialog(add_dialog, 500, 200, dialog)

            f = ttk.Frame(add_dialog, padding=10)
            f.pack(fill=tk.BOTH, expand=True)

            ttk.Label(f, text="Regex:").grid(row=0, column=0, sticky=tk.W, pady=3)
            regex_entry = ttk.Entry(f, width=50)
            regex_entry.grid(row=0, column=1, padx=(5, 0), pady=3)

            ttk.Label(f, text="Track # group:").grid(row=1, column=0, sticky=tk.W, pady=3)
            track_entry = ttk.Entry(f, width=10)
            track_entry.grid(row=1, column=1, sticky=tk.W, padx=(5, 0), pady=3)

            ttk.Label(f, text="Artist group:").grid(row=2, column=0, sticky=tk.W, pady=3)
            artist_entry = ttk.Entry(f, width=10)
            artist_entry.grid(row=2, column=1, sticky=tk.W, padx=(5, 0), pady=3)

            ttk.Label(f, text="Title group:").grid(row=3, column=0, sticky=tk.W, pady=3)
            title_entry = ttk.Entry(f, width=10)
            title_entry.grid(row=3, column=1, sticky=tk.W, padx=(5, 0), pady=3)

            def save_pattern():
                regex = regex_entry.get().strip()
                if not regex:
                    return
                track = track_entry.get().strip()
                artist = artist_entry.get().strip()
                title = title_entry.get().strip()
                entry = (
                    regex,
                    int(track) if track else None,
                    int(artist) if artist else None,
                    int(title) if title else None,
                )
                patterns.append(entry)
                refresh_listbox()
                add_dialog.destroy()

            btn_f = ttk.Frame(f)
            btn_f.grid(row=4, column=0, columnspan=2, pady=(15, 0))
            ttk.Button(btn_f, text="Add", command=save_pattern, width=12).pack(side=tk.LEFT, padx=5)
            ttk.Button(btn_f, text="Cancel", command=add_dialog.destroy, width=12).pack(side=tk.LEFT)

        def remove_selected():
            sel = listbox.curselection()
            if not sel:
                return
            idx = sel[0]
            if 0 <= idx < len(patterns):
                patterns.pop(idx)
                refresh_listbox()

        ttk.Button(btn_frame, text="Add", command=add_pattern, width=12).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Remove", command=remove_selected, width=12).pack(side=tk.LEFT, padx=5)

        ttk.Button(btn_frame, text="Close", command=dialog.destroy, width=12).pack(side=tk.RIGHT, padx=5)

        def on_close():
            self.config.filename_track_patterns = patterns
            save_config(self.config)
            dialog.destroy()

        dialog.protocol("WM_DELETE_WINDOW", on_close)

    def check_for_updates_now(self):
        """Check for new releases on GitHub."""
        import json
        import re
        import webbrowser
        import urllib.request
        from tkinter import messagebox

        def parse_ver(v):
            nums = re.findall(r'\d+', v)
            return tuple(int(n) for n in nums) if nums else (0,)

        try:
            req = urllib.request.Request(
                "https://api.github.com/repos/Nai64/BandcampAutoUploader/releases/latest",
                headers={"Accept": "application/vnd.github.v3+json", "User-Agent": "BandcampAutoUploader"}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())

            latest_tag = data.get("tag_name", "").lstrip("v")
            current = __version__
            latest_ver = parse_ver(latest_tag)
            current_ver = parse_ver(current)

            if latest_ver > current_ver:
                result = messagebox.askyesno(
                    "Update Available",
                    f"A new version is available: v{latest_tag}\n"
                    f"You have: v{__version__}\n\n"
                    "Would you like to open the releases page to download it?"
                )
                if result:
                    webbrowser.open("https://github.com/Nai64/BandcampAutoUploader/releases")
            elif latest_ver < current_ver:
                messagebox.showinfo(
                    "Up to Date",
                    f"You're running a newer version ({__version__}) "
                    f"than the latest release (v{latest_tag})."
                )
            else:
                messagebox.showinfo(
                    "Up to Date",
                    f"You're running the latest version ({__version__})."
                )

        except Exception as e:
            messagebox.showerror(
                "Check Failed",
                f"Could not check for updates:\n{e}\n\n"
                "Open the releases page manually?"
            )
            if messagebox.askyesno("Open Releases?", "Open GitHub releases page?"):
                webbrowser.open("https://github.com/Nai64/BandcampAutoUploader/releases")

    def restart_application(self):
        """Restart the application"""
        import sys
        import os
        
        # Restart the application
        python = sys.executable
        os.execv(python, [python] + sys.argv)

    def open_preferences_dialog(self):
        """Open the preferences/settings dialog"""
        # Create a dialog window
        dialog = tk.Toplevel(self.root)
        self.preferences_dialog = dialog
        dialog.title("Preferences")
        dialog.resizable(True, True)  # Allow resizing
        dialog.transient(self.root)
        dialog.grab_set()
        self.center_dialog(dialog, 850, 700, self.root)

        def close_preferences():
            if getattr(self, 'preferences_dialog', None) is dialog:
                self.preferences_dialog = None
            dialog.destroy()

        dialog.protocol("WM_DELETE_WINDOW", close_preferences)
        
        # Create settings content
        self.create_settings_tab(dialog)
        
        # Close button
        close_frame = ttk.Frame(dialog)
        close_frame.pack(fill=tk.X, padx=15, pady=15)
        
        ttk.Button(close_frame, text="Close", command=close_preferences).pack(side=tk.RIGHT)

