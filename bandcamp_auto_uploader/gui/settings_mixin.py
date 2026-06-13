"""Settings and preferences mixin for the Tkinter GUI."""

import sys
import tkinter as tk
from tkinter import ttk, messagebox, colorchooser

from bandcamp_auto_uploader.config import Config, save_config, load_custom_description_templates, save_custom_description_template, delete_custom_description_template, get_templates_autofill_dir
from bandcamp_auto_uploader.gui.common import (
    DESCRIPTION_AUTO_FILL_MODES,
    DESCRIPTION_TEMPLATES,
    ToolTip,
    preserve_tk_text_colors,
    set_ui_theme,
    style_multiline_editbox,
)
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
        search_icon = getattr(self, 'icon_images', {}).get('Search')
        if search_icon:
            style = ttk.Style()
            style.configure('PrefSearch.TEntry', padding=(28, 0, 0, 0))
            self.settings_search_entry = ttk.Entry(search_frame, textvariable=self.settings_search_var, style='PrefSearch.TEntry')
            self.settings_search_entry.pack(fill=tk.X)
            icon_canvas = tk.Canvas(self.settings_search_entry, width=24, height=20, highlightthickness=0, bd=0, bg='SystemWindow')
            icon_canvas.create_image(12, 10, image=search_icon, anchor='center')
            icon_canvas.place(x=2, rely=0.5, anchor='w')
            icon_canvas.bind('<Button-1>', lambda e: self.settings_search_entry.focus_set())
        else:
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
        general_id = self.settings_tree.insert('', 'end', 'General', text=self.tr('General'))
        self.settings_tree.insert(general_id, 'end', 'interface', text=self.tr('Interface'))
        self.settings_tree.insert(general_id, 'end', 'metadata', text=self.tr('Metadata'))
        self.settings_tree.insert(general_id, 'end', 'cover_art', text=self.tr('Cover Art'))
        self.settings_tree.insert(general_id, 'end', 'description', text=self.tr('Description'))
        self.settings_tree.insert(general_id, 'end', 'track_table', text=self.tr('Track Table'))
        self.settings_tree.insert(general_id, 'end', 'files_sessions', text=self.tr('Files & Sessions'))
        self.settings_tree.insert(general_id, 'end', 'startup_updates', text=self.tr('Startup & Updates'))
        self.settings_tree.insert(general_id, 'end', 'context_menu', text=self.tr('Context Menu'))
        self.settings_tree.insert(general_id, 'end', 'sort_methods', text=self.tr('Sort Methods'))
        self.settings_tree.insert(general_id, 'end', 'auto_tagging', text=self.tr('Auto Tagging'))
        
        notifications_id = self.settings_tree.insert('', 'end', 'Notifications', text=self.tr('Notifications'))
        self.settings_tree.insert(notifications_id, 'end', 'toasts', text=self.tr('Toast Notifications'))
        self.settings_tree.insert(notifications_id, 'end', 'windows_notifications', text=self.tr('Windows Notifications'))
        self.settings_tree.insert(notifications_id, 'end', 'notification_triggers', text=self.tr('Notification Triggers'))
        
        upload_id = self.settings_tree.insert('', 'end', 'Upload', text=self.tr('Upload'))
        self.settings_tree.insert(upload_id, 'end', 'upload_settings', text=self.tr('Upload Settings'))
        
        # Interface with sub-items
        interface_id = self.settings_tree.insert('', 'end', 'Interface', text=self.tr('Interface'))
        self.settings_tree.insert(interface_id, 'end', 'columns', text=self.tr('Track Table Columns'))
        self.settings_tree.insert(interface_id, 'end', 'logs', text=self.tr('Logs'))

        # Hotkeys (top-level section, customizable key bindings)
        self.settings_tree.insert('', 'end', 'hotkeys', text=self.tr('Hotkeys'))

        self.settings_tree.insert('', 'end', 'Advanced', text=self.tr('Advanced'))
        self.settings_tree.insert('', 'end', 'About', text=self.tr('About'))
        
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
        
        # General sub-section frames
        interface_frame = ttk.Frame(content_frame)
        self.create_interface_settings(interface_frame)
        self.settings_frames["interface"] = interface_frame

        metadata_frame = ttk.Frame(content_frame)
        self.create_metadata_settings(metadata_frame)
        self.settings_frames["metadata"] = metadata_frame

        cover_art_frame = ttk.Frame(content_frame)
        self.create_cover_art_settings(cover_art_frame)
        self.settings_frames["cover_art"] = cover_art_frame

        description_frame = ttk.Frame(content_frame)
        self.create_description_settings(description_frame)
        self.settings_frames["description"] = description_frame

        track_table_frame = ttk.Frame(content_frame)
        self.create_track_table_settings(track_table_frame)
        self.settings_frames["track_table"] = track_table_frame

        files_sessions_frame = ttk.Frame(content_frame)
        self.create_files_sessions_settings(files_sessions_frame)
        self.settings_frames["files_sessions"] = files_sessions_frame

        startup_updates_frame = ttk.Frame(content_frame)
        self.create_startup_updates_settings(startup_updates_frame)
        self.settings_frames["startup_updates"] = startup_updates_frame

        # Context Menu frame
        context_menu_frame = ttk.Frame(content_frame)
        self.create_context_menu_settings(context_menu_frame)
        self.settings_frames["context_menu"] = context_menu_frame

        # Hotkeys frame
        hotkeys_frame = ttk.Frame(content_frame)
        self.create_hotkey_settings(hotkeys_frame)
        self.settings_frames["hotkeys"] = hotkeys_frame

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
        
        # Show Interface by default (first sub-item of General)
        self.settings_tree.selection_set('interface')
        self.switch_settings_tab("interface")
        
        # Expand all parent sections so sub-options are visible immediately.
        for section_id in self.settings_tree.get_children(''):
            if self.settings_tree.get_children(section_id):
                self.settings_tree.item(section_id, open=True)

        self.build_settings_search_index()

    def build_settings_search_index(self):
        """Index preference rows so search can jump to the real setting."""
        section_trees = [
            (self.tr("Interface"), "interface", "interface_tree"),
            (self.tr("Metadata"), "metadata", "metadata_tree"),
            (self.tr("Cover Art"), "cover_art", "cover_art_tree"),
            (self.tr("Description"), "description", "description_tree"),
            (self.tr("Track Table"), "track_table", "track_table_tree"),
            (self.tr("Files & Sessions"), "files_sessions", "files_sessions_tree"),
            (self.tr("Startup & Updates"), "startup_updates", "startup_updates_tree"),
            (self.tr("Context Menu"), "context_menu", "context_menu_tree"),
            (self.tr("Sort Methods"), "sort_methods", "sort_method_tree"),
            (self.tr("Auto Tagging"), "auto_tagging", "auto_tagging_tree"),
            (self.tr("Toast Notifications"), "toasts", "toast_tree"),
            (self.tr("Windows Notifications"), "windows_notifications", "windows_notifications_tree"),
            (self.tr("Notification Triggers"), "notification_triggers", "notification_triggers_tree"),
            (self.tr("Upload Settings"), "upload_settings", "upload_tree"),
            (self.tr("Track Table Columns"), "columns", "column_tree"),
            (self.tr("Logs"), "logs", "logs_tree"),
            (self.tr("Advanced"), "Advanced", "advanced_tree"),
            (self.tr("Hotkeys"), "hotkeys", "hotkey_tree"),
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
            item_id = self.settings_search_results.insert('', 'end', text=self.tr('No settings found'))
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
        
        # Parent items (General, Notifications, Interface) show a combined frame
        if item_id not in self.settings_frames:
            combined_key = item_id  # Parent keys match their combined frame key
            if combined_key in self.settings_frames:
                item_id = combined_key
            else:
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
    
    def _build_std_tree(self, parent, settings):
        """Create a standard settings treeview and populate it with items."""
        tree = ttk.Treeview(
            parent,
            columns=('setting', 'value'),
            show='tree',
            selectmode='browse'
        )
        tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=(5, 5))
        tree.column('#0', width=0, stretch=False)
        tree.column('setting', width=250, anchor=tk.W)
        tree.column('value', width=150, anchor=tk.W)

        vars_dict = {}
        item_mapping = {}

        for setting_data in settings:
            setting_name = setting_data[0]
            config_key = setting_data[1]
            setting_type = setting_data[2]

            if setting_type == "bool":
                var = tk.BooleanVar(value=getattr(self.config, config_key, True))
                display_value = "☑" if var.get() else "☐"
            elif setting_type == "disabled_bool":
                var = tk.BooleanVar(value=False)
                display_value = "☐"
            elif setting_type == "str":
                var = tk.StringVar(value=getattr(self.config, config_key, self.tr("Off")))
                display_value = var.get()
                if config_key == "language":
                    display_value = self.tr("English") if var.get() == "en" else self.tr("Russian")
                elif config_key == "description_auto_fill_mode":
                    display_value = self.tr(var.get())
            elif setting_type == "choice":
                choices = setting_data[3]
                current = getattr(self.config, config_key, choices[0])
                var = tk.StringVar(value=current)
                display_value = current
                vars_dict[f"{config_key}_choices"] = choices
            elif setting_type == "color":
                var = tk.StringVar(value=getattr(self.config, config_key, '#ffffff'))
                display_value = var.get()
            elif setting_type == "int":
                min_val = setting_data[3]
                max_val = setting_data[4]
                var = tk.IntVar(value=getattr(self.config, config_key, min_val))
                vars_dict[f"{config_key}_min"] = min_val
                vars_dict[f"{config_key}_max"] = max_val
                display_value = str(var.get())
            elif setting_type == "action":
                var = None
                display_value = self.tr("Remove...") if config_key == "remove_all_custom_templates" else self.tr("Preview...")
            else:
                var = None
                display_value = ""

            if var is not None:
                vars_dict[config_key] = var
            vars_dict[f"{config_key}_type"] = setting_type

            item_id = tree.insert('', 'end', values=(setting_name, display_value))
            item_mapping[item_id] = config_key

        return tree, vars_dict, item_mapping

    def _register_std_page(self, tree, vars_dict, item_mapping):
        """Register a standard settings page for the generic click handlers."""
        if not hasattr(self, '_std_settings_registry'):
            self._std_settings_registry = {}
        self._std_settings_registry[id(tree)] = {
            "vars": vars_dict,
            "mapping": item_mapping,
            "tree": tree,
        }
        tree.bind('<Button-1>', self._on_std_tree_click)
        tree.bind('<Double-Button-1>', self._on_std_tree_double_click)

    def create_interface_settings(self, parent):
        settings = [
            (self.tr("Language"), "language", "str"),
            (self.tr("Apply settings immediately"), "apply_settings_immediately", "bool"),
            (self.tr("Maximize app on open"), "maximize_on_open", "bool"),
            (self.tr("Disable tooltips"), "disable_tooltips", "bool"),
            (self.tr("Remove splash art"), "remove_splash_art", "disabled_bool"),
            (self.tr("Remember Last Opened Album"), "remember_last_album", "bool"),
        ]
        tree, vars_dict, mapping = self._build_std_tree(parent, settings)
        self.interface_tree = tree
        self.interface_vars = vars_dict
        self.interface_item_mapping = mapping
        self._register_std_page(tree, vars_dict, mapping)

    def create_metadata_settings(self, parent):
        settings = [
            (self.tr("Auto load metadata for album details"), "auto_load_metadata", "bool"),
            (self.tr("Use Album Artist metadata for Artist in Album details"), "use_album_artist_in_album_details", "bool"),
            (self.tr("Guess album title from track metadata"), "guess_album_title_from_track_metadata", "bool"),
            (self.tr("Guess release date from track metadata"), "guess_release_date_from_track_metadata", "bool"),
            (self.tr("Folder name if album tag missing"), "use_folder_name_when_album_missing", "bool"),
            (self.tr("Extract track cover if cover missing"), "extract_track_cover_if_missing", "bool"),
            (self.tr("Smart-randomize on album load"), "smart_randomize_on_album_load", "bool"),
            (self.tr("Auto guess case tracks on album load"), "auto_guess_case_on_album_load", "bool"),
            (self.tr("Ignore all metadata"), "ignore_all_metadata", "bool"),
            (self.tr("Use filename as track title"), "use_filename_as_title", "bool"),
            (self.tr("Ignore artist name from metadata"), "ignore_artist_name", "bool"),
            (self.tr("Remove splash art"), "remove_splash_art", "disabled_bool"),
        ]
        tree, vars_dict, mapping = self._build_std_tree(parent, settings)
        self.metadata_tree = tree
        self.metadata_vars = vars_dict
        self.metadata_item_mapping = mapping
        self._register_std_page(tree, vars_dict, mapping)

    def create_cover_art_settings(self, parent):
        settings = [
            (self.tr("Always auto-scale cover art"), "always_auto_scale_cover", "bool"),
            (self.tr("Cover scaling method"), "cover_scaling_method", "str"),
            (self.tr("Cover fit mode"), "cover_fit_mode", "str"),
        ]
        tree, vars_dict, mapping = self._build_std_tree(parent, settings)
        self.cover_art_tree = tree
        self.cover_art_vars = vars_dict
        self.cover_art_item_mapping = mapping
        self._register_std_page(tree, vars_dict, mapping)

    def create_description_settings(self, parent):
        settings = [
            (self.tr("Description auto-fill"), "description_auto_fill_mode", "str"),
            (self.tr("Preview Description"), "preview_description", "action"),
            (self.tr("Create description on upload"), "description_auto_fill_on_upload", "bool"),
            (self.tr("Remove All Custom Templates"), "remove_all_custom_templates", "action"),
        ]
        tree, vars_dict, mapping = self._build_std_tree(parent, settings)
        self.description_tree = tree
        self.description_vars = vars_dict
        self.description_item_mapping = mapping
        self._register_std_page(tree, vars_dict, mapping)

    def create_track_table_settings(self, parent):
        settings = [
            (self.tr("Auto Fit Columns"), "auto_fit_columns", "bool"),
            (self.tr("Lock Column Sizes"), "lock_column_sizes", "bool"),
            (self.tr("Highlight Search Matches (hide non-matches instead)"), "highlight_search_matches", "bool"),
            (self.tr("Locked Track Highlight Color"), "locked_track_highlight_color", "color"),
            (self.tr("Highlight Corrupted Tracks"), "highlight_corrupted_tracks", "bool"),
            (self.tr("Show Total Album Duration"), "show_total_album_duration", "bool"),
        ]
        tree, vars_dict, mapping = self._build_std_tree(parent, settings)
        self.track_table_tree = tree
        self.track_table_vars = vars_dict
        self.track_table_item_mapping = mapping
        self._register_std_page(tree, vars_dict, mapping)

    def create_files_sessions_settings(self, parent):
        settings = [
            (self.tr("Create session.txt files (Recommended)"), "create_album_session_files", "bool"),
            (self.tr("Clear progress on album change"), "clear_progress_on_album_change", "bool"),
            (self.tr("Limit Log Files"), "log_file_limit", "int", 1, 99),
            (self.tr("File Size Unit"), "file_size_unit", "str"),
        ]
        tree, vars_dict, mapping = self._build_std_tree(parent, settings)
        self.files_sessions_tree = tree
        self.files_sessions_vars = vars_dict
        self.files_sessions_item_mapping = mapping
        self._register_std_page(tree, vars_dict, mapping)

    def create_startup_updates_settings(self, parent):
        settings = [
            (self.tr("Auto load cookies on startup"), "auto_load_cookies", "bool"),
            (self.tr("Check for updates on startup"), "check_for_updates", "bool"),
            (self.tr("Check for updates now"), "check_updates_now", "action"),
        ]
        tree, vars_dict, mapping = self._build_std_tree(parent, settings)
        self.startup_updates_tree = tree
        self.startup_updates_vars = vars_dict
        self.startup_updates_item_mapping = mapping
        self._register_std_page(tree, vars_dict, mapping)


    def create_context_menu_settings(self, parent):
        """Create Context Menu settings section using Treeview"""
        # Context menu settings treeview
        settings = [
            (self.tr("Show Context Menu Icons"), "show_context_menu_icons", "bool"),
            (self.tr("Remove Dividers"), "context_menu_remove_dividers", "bool"),
            (self.tr("Play"), "context_menu_play", "bool"),
            (self.tr("Remove Track"), "context_menu_remove_track", "bool"),
            (self.tr("Move Up"), "context_menu_move_up", "bool"),
            (self.tr("Move Down"), "context_menu_move_down", "bool"),
            (self.tr("Move to Top"), "context_menu_move_to_top", "bool"),
            (self.tr("Move to Bottom"), "context_menu_move_to_bottom", "bool"),
            (self.tr("Open File Location"), "context_menu_open_file", "bool"),
            (self.tr("Replace File"), "context_menu_replace_file", "bool"),
            (self.tr("Extract Cover Art"), "context_menu_extract_cover_art", "bool"),
            (self.tr("Extract Tracklist"), "context_menu_extract_tracklist", "bool"),
            (self.tr("Open session.txt"), "context_menu_open_session", "bool"),
            (self.tr("Set Track Cover as Album Cover"), "context_menu_set_track_cover_as_album_cover", "bool"),
            (self.tr("Undo"), "context_menu_undo", "bool"),
            (self.tr("Redo"), "context_menu_redo", "bool"),
            (self.tr("Extract Track Information"), "context_menu_extract_track_info", "bool"),
            (self.tr("Copy Metadata"), "context_menu_copy_metadata", "bool"),
            (self.tr("Paste Metadata"), "context_menu_paste_metadata", "bool"),
            (self.tr("Revert to Original"), "context_menu_revert_to_original", "bool"),
            (self.tr("Lock/Unlock"), "context_menu_lock_unlock", "bool"),
            (self.tr("Randomize"), "context_menu_randomize", "bool"),
            (self.tr("Smart Randomize"), "context_menu_smart_randomize", "bool"),
            (self.tr("Sort By"), "context_menu_sort_by", "bool"),
            (self.tr("Clear Metadata"), "context_menu_clear_metadata", "bool"),
            (self.tr("Clear All Metadata"), "context_menu_clear_all_metadata", "bool"),
            (self.tr("Clear All Tracks"), "context_menu_clear_all", "bool"),
            (self.tr("Upload as Single"), "context_menu_upload_as_single", "bool"),
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
            "context_menu_clear_all", "context_menu_upload_as_single"
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
            item_id = self.sort_method_tree.insert('', 'end', values=(self.tr(setting_name), display_value))
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
            (self.tr("Enable Toast Notifications"), "enable_toasts", "bool"),
            (self.tr("Toast Duration (s)"), "toast_duration", "int"),
            (self.tr("Toast Position"), "toast_position", "str"),
            (self.tr("Test Toast Notification"), "test_toast_notification", "action"),
            (self.tr("Enable Fade Out Effect"), "toast_fade_out", "bool"),
            (self.tr("Enable Animations (slide/fade)"), "toast_animations_enabled", "bool"),
            (self.tr("Font Family"), "toast_font_family", "str"),
            (self.tr("Font Size"), "toast_font_size", "int"),
            (self.tr("Font Bold"), "toast_font_bold", "bool"),
            (self.tr("Text Color"), "toast_text_color", "color"),
            (self.tr("Background Color"), "toast_bg_color", "color"),
            (self.tr("Border Color"), "toast_border_color", "color"),
            (self.tr("Success Color"), "toast_success_color", "color"),
            (self.tr("Error Color"), "toast_error_color", "color"),
            (self.tr("Warning Color"), "toast_warning_color", "color"),
            (self.tr("Info Color"), "toast_info_color", "color")
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
                var = tk.StringVar(value=self.tr("Test"))
                display_value = self.tr("Test")
            
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
                positions = [self.tr('top-right'), self.tr('top-left'), self.tr('bottom-right'), self.tr('bottom-left')]
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
            color = colorchooser.askcolor(title=self.tr("Choose {} color").format(config_key),
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
        self.config.toast_animations_enabled = self.toast_vars['toast_animations_enabled'].get()
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
            (self.tr("Enable Windows Notifications"), "windows_notifications", "bool"),
            (self.tr("Test Notification"), "test_notification", "action")
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
                var = tk.StringVar(value=self.tr("Test"))
                display_value = self.tr("Test")
            
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
            messagebox.showerror(self.tr("Error"), self.tr("windows-toasts package is not installed. Please install it with: pip install windows-toasts"))
            return
        
        self.config.windows_notifications = new_value
        save_config(self.config)
    
    def test_toast_notification(self):
        """Test toast notification by sending a test notification"""
        # Force show the test notification regardless of trigger settings
        self.toast_queue.put((self.tr("This is a test toast notification"), 3000, "info"))
    
    def create_notification_triggers_settings(self, parent):
        """Create Notification Triggers settings section using Treeview"""
        # Notification trigger settings treeview
        settings = [
            (self.tr("Notify on Upload Success"), "notify_on_upload_success", "bool"),
            (self.tr("Notify on Upload Error"), "notify_on_upload_error", "bool"),
            (self.tr("Notify on Track Error"), "notify_on_track_error", "bool"),
            (self.tr("Notify on Conversion Complete"), "notify_on_conversion_complete", "bool"),
            (self.tr("Notify on Metadata Load"), "notify_on_metadata_load", "bool"),
            (self.tr("Notify on File Add"), "notify_on_file_add", "bool"),
            (self.tr("Notify on Track Add"), "notify_on_track_add", "bool"),
            (self.tr("Notify on Track Remove"), "notify_on_track_remove", "bool"),
            (self.tr("Notify on Cover Load"), "notify_on_cover_load", "bool"),
            (self.tr("Notify on Album Save"), "notify_on_album_save", "bool"),
            (self.tr("Notify on Settings Save"), "notify_on_settings_save", "bool"),
            (self.tr("Notify on Artists Load"), "notify_on_artists_load", "bool"),
            (self.tr("Notify on Template Save"), "notify_on_template_save", "bool")
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
            (self.tr("Toast: Enable Toast Notifications"), "enable_toasts", "bool"),
            (self.tr("Toast: Toast Duration (s)"), "toast_duration", "int"),
            (self.tr("Toast: Toast Position"), "toast_position", "str"),
            (self.tr("Toast: Test Toast Notification"), "test_toast_notification", "action"),
            (self.tr("Toast: Enable Fade Out Effect"), "toast_fade_out", "bool"),
            (self.tr("Toast: Enable Animations (slide/fade)"), "toast_animations_enabled", "bool"),
            (self.tr("Toast: Font Family"), "toast_font_family", "str"),
            (self.tr("Toast: Font Size"), "toast_font_size", "int"),
            (self.tr("Toast: Font Bold"), "toast_font_bold", "bool"),
            (self.tr("Toast: Text Color"), "toast_text_color", "color"),
            (self.tr("Toast: Background Color"), "toast_bg_color", "color"),
            (self.tr("Toast: Border Color"), "toast_border_color", "color"),
            (self.tr("Toast: Success Color"), "toast_success_color", "color"),
            (self.tr("Toast: Error Color"), "toast_error_color", "color"),
            (self.tr("Toast: Warning Color"), "toast_warning_color", "color"),
            (self.tr("Toast: Info Color"), "toast_info_color", "color"),
            (self.tr("Windows: Enable Windows Notifications"), "windows_notifications", "bool"),
            (self.tr("Windows: Test Notification"), "test_notification", "action"),
            (self.tr("Trigger: Notify on Upload Success"), "notify_on_upload_success", "bool"),
            (self.tr("Trigger: Notify on Upload Error"), "notify_on_upload_error", "bool"),
            (self.tr("Trigger: Notify on Track Error"), "notify_on_track_error", "bool"),
            (self.tr("Trigger: Notify on Conversion Complete"), "notify_on_conversion_complete", "bool"),
            (self.tr("Trigger: Notify on Metadata Load"), "notify_on_metadata_load", "bool"),
            (self.tr("Trigger: Notify on File Add"), "notify_on_file_add", "bool"),
            (self.tr("Trigger: Notify on Track Add"), "notify_on_track_add", "bool"),
            (self.tr("Trigger: Notify on Track Remove"), "notify_on_track_remove", "bool"),
            (self.tr("Trigger: Notify on Cover Load"), "notify_on_cover_load", "bool"),
            (self.tr("Trigger: Notify on Album Save"), "notify_on_album_save", "bool"),
            (self.tr("Trigger: Notify on Settings Save"), "notify_on_settings_save", "bool"),
            (self.tr("Trigger: Notify on Artists Load"), "notify_on_artists_load", "bool"),
            (self.tr("Trigger: Notify on Template Save"), "notify_on_template_save", "bool")
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
                var = tk.StringVar(value=self.tr("Test"))
                display_value = self.tr("Test")
            
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
        self.config.toast_animations_enabled = self.notifications_combined_vars['toast_animations_enabled'].get()
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
            messagebox.showerror(self.tr("Error"), self.tr("windows-toasts package is not installed. Please install it with: pip install windows-toasts"))
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
            messagebox.showinfo(self.tr("Test Notification"), self.tr("Windows notifications are only available on Windows."))
            return

        if not self.windows_toasts_available:
            messagebox.showerror(self.tr("Test Failed"), self.tr("windows-toasts package is not installed. Please install it with: pip install windows-toasts"))
            return
        
        try:
            from windows_toasts import Toast, WindowsToaster
            toaster = WindowsToaster('Bandcamp Auto Uploader')
            
            newToast = Toast()
            newToast.text_fields = ["This is a test notification to verify Windows notifications are working correctly."]
            
            toaster.show_toast(newToast)
            self.show_toast(self.tr("Test notification sent"), 2000, "success")
        except Exception as e:
            messagebox.showerror(self.tr("Test Failed"), self.tr("Failed to send test notification:") + f"\n{e}")

    def _on_std_tree_click(self, event):
        """Generic single-click handler for all standard settings pages."""
        tree = event.widget
        info = getattr(self, '_std_settings_registry', {}).get(id(tree))
        if not info:
            return
        item_id = tree.identify('item', event.x, event.y)
        column = tree.identify('column', event.x, event.y)
        if not item_id or column != '#2':
            return
        config_key = info["mapping"].get(item_id)
        if not config_key:
            return
        vars_dict = info["vars"]

        setting_type = vars_dict.get(f"{config_key}_type")
        if setting_type in ("disabled_bool", "action"):
            return
        if config_key == "description_auto_fill_mode":
            self.root.after_idle(lambda: self.open_description_autofill_dialog(
                tree, item_id, 'value',
                vars_dict[config_key].get(),
                lambda v: self._apply_std_str_setting(config_key, v)))
            return "break"

    def _on_std_tree_double_click(self, event):
        """Generic double-click handler for all standard settings pages."""
        tree = event.widget
        info = getattr(self, '_std_settings_registry', {}).get(id(tree))
        if not info:
            return
        item_id = tree.identify('item', event.x, event.y)
        if not item_id:
            return
        config_key = info["mapping"].get(item_id)
        if not config_key:
            return
        vars_dict = info["vars"]
        setting_type = vars_dict.get(f"{config_key}_type")

        if setting_type == "disabled_bool":
            return

        if setting_type == "action":
            if config_key == "preview_description":
                self.open_description_preview_dialog()
            elif config_key == "check_updates_now":
                self.check_for_updates_now()
            elif config_key == "remove_all_custom_templates":
                self._remove_all_custom_templates()
            return

        if setting_type == "bool":
            current_value = vars_dict[config_key].get()

        if setting_type == "bool":
            current_value = vars_dict[config_key].get()
            new_value = not current_value
            vars_dict[config_key].set(new_value)
            tree.set(item_id, 'value', '☑' if new_value else '☐')

            if config_key == "apply_settings_immediately":
                self.config.apply_settings_immediately = new_value
                save_config(self.config)
            elif config_key == "maximize_on_open":
                self.config.maximize_on_open = new_value
                save_config(self.config)
            elif config_key == "disable_tooltips":
                self.config.disable_tooltips = new_value
                ToolTip.disabled = new_value
                save_config(self.config)
            elif config_key == "remember_last_album":
                self.config.remember_last_album = new_value
                save_config(self.config)
            elif config_key == "auto_load_metadata":
                self.config.auto_load_metadata = new_value
                save_config(self.config)
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
                setattr(self.config, config_key, new_value)
                if config_key == "always_auto_scale_cover" and hasattr(self, 'scale_cover_var'):
                    self.scale_cover_var.set(new_value)
                save_config(self.config)
            elif config_key == "auto_load_cookies":
                self.config.auto_load_cookies = new_value
                save_config(self.config)
            elif config_key == "check_for_updates":
                self.config.check_for_updates = new_value
                save_config(self.config)
            elif config_key == "auto_fit_columns":
                self.config.auto_fit_columns = new_value
                save_config(self.config)
            elif config_key == "lock_column_sizes":
                self.config.lock_column_sizes = new_value
                save_config(self.config)
            elif config_key == "highlight_search_matches":
                self.config.highlight_search_matches = new_value
                save_config(self.config)
                if hasattr(self, '_filter_track_table'):
                    self._filter_track_table()
            elif config_key == "highlight_corrupted_tracks":
                self.config.highlight_corrupted_tracks = new_value
                save_config(self.config)
                if hasattr(self, 'refresh_all_track_row_tags'):
                    self.refresh_all_track_row_tags()
            elif config_key == "show_total_album_duration":
                self.config.show_total_album_duration = new_value
                save_config(self.config)
                if hasattr(self, 'update_preview_total_duration_label'):
                    self.update_preview_total_duration_label()

        elif setting_type == "str":
            if config_key == "description_auto_fill_mode":
                self.open_description_autofill_dialog(tree, item_id, 'value',
                    vars_dict[config_key].get(),
                    lambda v: self._apply_std_str_setting(config_key, v))
            elif config_key == "language":
                languages = [self.tr("English"), self.tr("Russian")]
                self.edit_treeview_cell_dropdown(
                    tree, item_id, 'value',
                    languages,
                    self.tr("English") if getattr(self.config, 'language', 'en') == 'en' else self.tr("Russian"),
                    lambda v: self._apply_language_setting(v),
                )
            elif config_key in ("cover_scaling_method", "cover_fit_mode", "file_size_unit"):
                options = {
                    "cover_scaling_method": [self.tr(m) for m in SCALING_METHOD_OPTIONS],
                    "cover_fit_mode": [self.tr("Crop (fill)"), self.tr("Fit (contain)"), self.tr("Stretch")],
                    "file_size_unit": [self.tr("Auto"), self.tr("MB"), self.tr("GB"), self.tr("KB"), self.tr("Bytes")],
                }
                self.edit_treeview_cell_dropdown(
                    tree, item_id, 'value',
                    options[config_key],
                    vars_dict[config_key].get(),
                    lambda v: self._apply_std_str_setting(config_key, v),
                )

        elif setting_type == "int":
            min_val = vars_dict.get(f"{config_key}_min", 1)
            max_val = vars_dict.get(f"{config_key}_max", 99)
            current_value = str(vars_dict[config_key].get())

            def validate_and_save(new_value, _key=config_key, _item_id=item_id,
                                   _tree=tree, _vars=vars_dict):
                try:
                    int_val = int(new_value)
                    if min_val <= int_val <= max_val:
                        _vars[_key].set(int_val)
                        _tree.set(_item_id, 'value', str(int_val))
                        setattr(self.config, _key, int_val)
                        save_config(self.config)
                        if hasattr(self, 'cleanup_old_log_files'):
                            self.cleanup_old_log_files()
                        return True
                except ValueError:
                    pass
                return False

            self.edit_treeview_cell(tree, item_id, 'value', current_value, validate_and_save)

        elif setting_type == "color":
            current_color = vars_dict[config_key].get()
            new_color = colorchooser.askcolor(color=current_color)[1]
            if new_color:
                vars_dict[config_key].set(new_color)
                tree.set(item_id, 'value', new_color)
                self.config.locked_track_highlight_color = new_color
                save_config(self.config)
                if hasattr(self, 'configure_track_table_tags'):
                    self.configure_track_table_tags()

    def _apply_std_str_setting(self, config_key, new_value):
        """Apply a string/dropdown setting from any standard settings page."""
        if config_key == "description_auto_fill_mode" and new_value not in DESCRIPTION_AUTO_FILL_MODES:
            return False
        if config_key == "cover_scaling_method" and new_value not in [self.tr(m) for m in SCALING_METHOD_OPTIONS]:
            return False
        if config_key == "cover_fit_mode" and new_value not in (self.tr("Crop (fill)"), self.tr("Fit (contain)"), self.tr("Stretch")):
            return False
        if config_key == "file_size_unit" and new_value not in (self.tr("Auto"), self.tr("MB"), self.tr("GB"), self.tr("KB"), self.tr("Bytes")):
            return False

        # Find the right vars dict from any registered section
        for info in getattr(self, '_std_settings_registry', {}).values():
            if config_key in info["vars"]:
                info["vars"][config_key].set(new_value)
                break
        setattr(self.config, config_key, new_value)
        if config_key == "cover_scaling_method" and hasattr(self, 'scaling_method_var'):
            self.scaling_method_var.set(new_value)
        if config_key == "cover_fit_mode" and hasattr(self, 'cover_fit_mode_var'):
            self.cover_fit_mode_var.set(new_value)
        if config_key == "file_size_unit" and hasattr(self, 'refresh_file_size_display'):
            self.refresh_file_size_display()
        save_config(self.config)
        if config_key == "description_auto_fill_mode" and getattr(self.config, 'notify_on_template_save', False):
            self.show_toast(self.tr("Description template set to: {}").format(new_value), 1800, "success", trigger="template_save")
        return True

    def _apply_language_setting(self, display_name):
        """Map display name to language code and apply."""
        from tkinter import messagebox
        lang_map = {self.tr("English"): "en", self.tr("Russian"): "ru"}
        old_code = getattr(self.config, "language", "en")
        lang_code = lang_map.get(display_name, "en")
        if lang_code == old_code:
            return True
        setattr(self.config, "language", lang_code)
        save_config(self.config)

        if not messagebox.askyesno(
            self.tr("Change Language"),
            self.tr("Changing the language will restart the application.\nContinue?"),
            icon='question'
        ):
            setattr(self.config, "language", old_code)
            save_config(self.config)
            for info in getattr(self, '_std_settings_registry', {}).values():
                if "language" in info["vars"]:
                    old_display = self.tr("English") if old_code == "en" else self.tr("Russian")
                    for item_id, key in info["mapping"].items():
                        if key == "language":
                            info["tree"].set(item_id, 'value', old_display)
                            break
                    break
            return True

        self.root.after_idle(self._restart_app)
        return True

    def _restart_app(self):
        """Restart the application."""
        import sys
        save_config(self.config)
        python = sys.executable
        args = [python] + sys.argv
        try:
            if sys.platform == "win32":
                import subprocess
                subprocess.Popen(args, creationflags=subprocess.DETACHED_PROCESS)
            else:
                import os
                os.spawnv(os.P_NOWAIT, python, args)
        except Exception:
            pass
        self.root.destroy()

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

    def _remove_all_custom_templates(self):
        """Remove all custom description templates and built-in overrides."""
        if not messagebox.askyesno(
            self.tr("Remove All Custom Templates"),
            self.tr("This will permanently delete all custom description templates\n"
            "and reset any built-in template overrides.\n\n"
            "This action cannot be undone. Continue?"),
            icon='warning'
        ):
            return
        count = 0
        for entry in load_custom_description_templates():
            delete_custom_description_template(entry["name"])
            count += 1
        if self.config.description_templates:
            self.config.description_templates.clear()
            save_config(self.config)
        self.show_toast(self.tr("Removed {} custom template(s)").format(count), 2000, "success")

    def open_description_preview_dialog(self):
        """Preview the description generated by the selected template."""
        generated_description = self.build_auto_description_from_mode().strip()
        description = generated_description
        mode = getattr(self.config, 'description_auto_fill_mode', "Off")
        if not description:
            if mode == "Off":
                description = self.tr("Description auto-fill is Off.")
            else:
                description = self.tr("No description could be generated from the current album preview.")

        parent = self.get_preferences_dialog_parent()
        dialog = tk.Toplevel(parent)
        dialog.title(self.tr("Preview Description"))
        dialog.transient(parent)
        dialog.withdraw()
        dialog.resizable(True, True)

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
            self.show_toast(self.tr("Description applied"), 1800, "success")
            close_preview()

        ttk.Button(
            button_frame,
            text=self.tr("Use Description"),
            command=use_description,
            state=tk.NORMAL if generated_description else tk.DISABLED
        ).pack(side=tk.RIGHT, padx=(5, 0))
        ttk.Button(button_frame, text=self.tr("Close"), command=close_preview).pack(side=tk.RIGHT)

        self.center_dialog(dialog, 640, 460, parent)
        dialog.deiconify()
        dialog.grab_set()

    def on_scale_cover_changed(self):
        """Persist the preferred cover auto-scale checkbox state."""
        try:
            self.config.always_auto_scale_cover = self.scale_cover_var.get()
            save_config(self.config)
        except Exception as e:
            logger.debug(f"Failed to save cover scaling preference: {e}")

    def _on_cover_fit_mode_changed(self):
        """Persist cover fit mode when changed via main page combobox."""
        try:
            self.config.cover_fit_mode = self.cover_fit_mode_var.get()
            save_config(self.config)
            self.update_cover_preview()
        except Exception as e:
            logger.debug(f"Failed to save cover fit mode: {e}")

    def _on_cover_scaling_method_changed(self):
        """Persist cover scaling method when changed via main page combobox."""
        try:
            self.config.cover_scaling_method = self.scaling_method_var.get()
            save_config(self.config)
        except Exception as e:
            logger.debug(f"Failed to save cover scaling method: {e}")

    def create_about_settings(self, parent):
        """Create About section"""
        import webbrowser

        container = ttk.Frame(parent)
        container.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        splash_label = self._build_about_icon(container)
        if splash_label is not None:
            splash_label.pack(pady=(0, 10))

        ttk.Label(container, text=self.tr("Bandcamp Auto Uploader"),
                  font=("Segoe UI", 16, "bold")).pack()

        ttk.Label(container, text=self.tr("Version:") + f" {__version__}",
                  font=("Segoe UI", 10)).pack(pady=(5, 15))

        ttk.Button(container, text=self.tr("GitHub Repository"),
                   command=lambda: webbrowser.open("https://github.com/Nai64/BandcampAutoUploader"),
                   width=25).pack(pady=3)
        ttk.Button(container, text=self.tr("Original Project (7x11x13)"),
                   command=lambda: webbrowser.open("https://github.com/7x11x13/bandcamp-auto-uploader"),
                   width=25).pack(pady=3)

        ttk.Label(container, text=self.tr("Based on bandcamp-auto-uploader by 7x11x13\n"
                                          "GUI fork and enhancements by Nai64"),
                  font=("Segoe UI", 8), justify=tk.CENTER,
                  foreground="gray").pack(pady=(15, 5))

    def _build_about_icon(self, parent):
        """Render the splash PNG as a centered icon above the About tab title."""
        try:
            from PIL import Image, ImageTk
        except ImportError:
            return None
        splash_path = None
        try:
            from bandcamp_auto_uploader.gui.gui import get_splash_image_path
            splash_path = get_splash_image_path()
        except Exception:
            splash_path = None
        if splash_path is None:
            from pathlib import Path
            project_root = Path(__file__).resolve().parents[2]
            for candidate in (project_root / "assets" / "splash.png", Path.cwd() / "assets" / "splash.png"):
                if candidate.exists():
                    splash_path = candidate
                    break
        if splash_path is None or not splash_path.exists():
            return None

        max_size = 128
        try:
            with Image.open(splash_path) as source:
                source = source.convert("RGBA")
                width, height = source.size
                scale = min(max_size / max(width, 1), max_size / max(height, 1), 1.0)
                if scale < 1.0:
                    new_size = (max(1, int(width * scale)), max(1, int(height * scale)))
                    resampling = getattr(getattr(Image, "Resampling", Image), "LANCZOS")
                    source = source.resize(new_size, resampling)
                photo = ImageTk.PhotoImage(source, master=parent.winfo_toplevel())
        except Exception:
            return None

        parent._about_icon_photo = photo
        return ttk.Label(parent, image=photo)

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
            (self.tr("Track No."), "show_track_no", "bool"),
            (self.tr("Artist"), "show_artist", "bool"),
            (self.tr("Track Name"), "show_track_name", "bool"),
            (self.tr("Comment"), "show_comment", "bool"),
            (self.tr("Length"), "show_length", "bool"),
            (self.tr("Extension"), "show_extension", "bool"),
            (self.tr("Price"), "show_price", "bool"),
            (self.tr("NYP"), "show_nyp", "bool"),
            (self.tr("Year"), "show_year", "bool"),
            (self.tr("Genre"), "show_genre", "bool"),
            (self.tr("Bitrate"), "show_bitrate", "bool"),
            (self.tr("File Size"), "show_file_size", "bool"),
            (self.tr("Sample Rate"), "show_sample_rate", "bool"),
            (self.tr("Channels"), "show_channels", "bool"),
            (self.tr("Bit Depth"), "show_bit_depth", "bool"),
            (self.tr("Album Metadata"), "show_album_metadata", "bool"),
            (self.tr("Album Artist Metadata"), "show_album_artist_metadata", "bool"),
            (self.tr("Composer"), "show_composer", "bool"),
            (self.tr("ISRC"), "show_isrc", "bool")
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
            (self.tr("Font Family"), "log_font_family", "choice", ["Segoe UI", "Consolas", "Courier New", "monospace", "Arial", "Tahoma"]),
            (self.tr("Font Size"), "log_font_size", "int", 8, 16),
            (self.tr("Font Bold"), "log_font_bold", "bool"),
            (self.tr("Text Color"), "log_text_color", "color"),
            (self.tr("Background Color"), "log_bg_color", "color"),
            (self.tr("INFO Color"), "log_info_color", "color"),
            (self.tr("WARNING Color"), "log_warning_color", "color"),
            (self.tr("ERROR Color"), "log_error_color", "color"),
            (self.tr("DEBUG Color"), "log_debug_color", "color"),
            (self.tr("Show Timestamps"), "log_show_timestamps", "bool"),
            (self.tr("Timestamp Format"), "log_timestamp_format", "choice", ["HH:MM:SS", "YYYY-MM-DD HH:MM:SS", "MM/DD/YYYY HH:MM:SS", "None"]),
            (self.tr("Show Log Levels"), "log_show_levels", "bool"),
            (self.tr("Word Wrap"), "log_word_wrap", "bool"),
            (self.tr("Line Spacing"), "log_line_spacing", "int", 1, 3),
            (self.tr("Auto-scroll to Bottom"), "log_auto_scroll", "bool"),
            (self.tr("Max Lines (0 = unlimited)"), "log_max_lines", "int", 0, 10000),
            (self.tr("Save Diagnostic Log File"), "log_to_file", "bool"),
            (self.tr("Diagnostic Log Level"), "log_file_level", "choice", ["DEBUG", "INFO", "WARNING", "ERROR"])
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
        preserve_tk_text_colors(
            self.log_text,
            background=self.config.log_bg_color,
            foreground=self.config.log_text_color,
            insertbackground=self.config.log_text_color,
            selectbackground="#0078d7",
            selectforeground="#ffffff",
        )

        # Apply word wrap
        wrap_mode = tk.WORD if self.config.log_word_wrap else tk.NONE
        self.log_text.configure(wrap=wrap_mode)

        # Note: Line spacing and timestamp formats require log message format changes
        # These will be applied in the log formatting logic

    def create_hotkey_settings(self, parent):
        """Create Hotkeys settings section (customizable key bindings)."""
        # Default values for reset
        defaults = {
            "undo_hotkey": "Ctrl+Z",
            "redo_hotkey": "Ctrl+Y",
            "upload_hotkey": "Ctrl+Enter",
            "cancel_hotkey": "Ctrl+Space+Enter",
            "cover_fullscreen_hotkey": "F11",
        }
        settings = [
            (self.tr("Undo"), "undo_hotkey", "hotkey", defaults["undo_hotkey"]),
            (self.tr("Redo"), "redo_hotkey", "hotkey", defaults["redo_hotkey"]),
            (self.tr("Upload album"), "upload_hotkey", "hotkey", defaults["upload_hotkey"]),
            (self.tr("Cancel album"), "cancel_hotkey", "hotkey", defaults["cancel_hotkey"]),
            (self.tr("Cover art fullscreen"), "cover_fullscreen_hotkey", "hotkey", defaults["cover_fullscreen_hotkey"]),
        ]

        self.hotkey_tree = ttk.Treeview(
            parent,
            columns=('setting', 'value'),
            show='tree',
            selectmode='browse',
        )
        self.hotkey_tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.hotkey_tree.column('#0', width=0, stretch=False)
        self.hotkey_tree.column('setting', width=250, anchor=tk.W)
        self.hotkey_tree.column('value', width=200, anchor=tk.W)

        self.hotkey_vars = {}
        self.hotkey_item_mapping = {}
        self._hotkey_defaults = defaults

        for setting_data in settings:
            setting_name = setting_data[0]
            config_key = setting_data[1]
            setting_type = setting_data[2]
            default_value = setting_data[3]

            current_value = getattr(self.config, config_key, default_value) or default_value
            var = tk.StringVar(value=current_value)
            self.hotkey_vars[config_key] = var
            self.hotkey_vars[f"{config_key}_type"] = setting_type
            self.hotkey_vars[f"{config_key}_default"] = default_value

            item_id = self.hotkey_tree.insert('', 'end', values=(setting_name, current_value))
            self.hotkey_item_mapping[item_id] = config_key

        # Reset button removed per user request.
        self.hotkey_tree.bind('<Double-Button-1>', self._on_hotkey_tree_double_click)

    def _on_hotkey_tree_double_click(self, event):
        """Handle double-click on a hotkey row: open the key capture dialog."""
        item_id = self.hotkey_tree.identify('item', event.x, event.y)
        if not item_id:
            return
        config_key = self.hotkey_item_mapping.get(item_id)
        if not config_key:
            return
        current = self.hotkey_vars[config_key].get()
        new_value = self._capture_hotkey_dialog(current)
        if new_value is None:
            return
        if not new_value:
            # Treat empty string as "unbound"
            new_value = ""
        self.hotkey_vars[config_key].set(new_value)
        self.hotkey_tree.set(item_id, 'value', new_value or self.tr("(unbound)"))
        setattr(self.config, config_key, new_value)
        try:
            from bandcamp_auto_uploader.config import save_config
            save_config(self.config)
        except Exception as e:
            logger.debug(f"Failed to save hotkey config: {e}")
        if hasattr(self, 'apply_hotkey_bindings'):
            self.apply_hotkey_bindings()
        if hasattr(self, 'show_toast'):
            label = self.tr("Unbound") if not new_value else self.tr("Hotkey set to {}").format(new_value)
            self.show_toast(label, 1500, "success")

    def _capture_hotkey_dialog(self, current_value=""):
        """Show a modal dialog that captures a key combination.

        Returns the captured hotkey as a string like 'Ctrl+Shift+Z' or a
        multi-key sequence like 'Ctrl+Space+Enter', an empty string if the
        user explicitly unbound the key, or None if cancelled.
        """
        dialog = tk.Toplevel(self.root)
        dialog.title(self.tr("Record hotkey"))
        dialog.transient(self.root)
        dialog.resizable(False, False)
        dialog.configure(padx=16, pady=12)

        result = {"value": None}
        SEQUENCE_TIMEOUT_MS = 900

        captured_var = tk.StringVar(value=current_value or self.tr("(unbound)"))
        captured_label = ttk.Label(
            dialog,
            textvariable=captured_var,
            font=("Consolas", 11),
            foreground="#1d4ed8",
            padding=(8, 6),
            relief="groove",
        )
        captured_label.pack(fill=tk.X, pady=(0, 10))

        button_frame = ttk.Frame(dialog)
        button_frame.pack(fill=tk.X)

        pending_after_id = [None]

        def finalize_sequence():
            pending_after_id[0] = None
            result["value"] = captured_var.get()
            dialog.destroy()

        def schedule_finalize():
            if pending_after_id[0] is not None:
                try:
                    dialog.after_cancel(pending_after_id[0])
                except Exception:
                    pass
            pending_after_id[0] = dialog.after(SEQUENCE_TIMEOUT_MS, finalize_sequence)

        def on_key(event):
            if event.keysym == 'Escape':
                if pending_after_id[0] is not None:
                    try:
                        dialog.after_cancel(pending_after_id[0])
                    except Exception:
                        pass
                result["value"] = None
                dialog.destroy()
                return "break"
            if event.keysym == 'BackSpace':
                if pending_after_id[0] is not None:
                    try:
                        dialog.after_cancel(pending_after_id[0])
                    except Exception:
                        pass
                pending_after_id[0] = None
                captured_var.set(self.tr("(unbound)"))
                result["value"] = ""
                return "break"
            hotkey_str = self._tk_event_to_hotkey_string(event)
            if hotkey_str:
                current = captured_var.get()
                if current in ("", self.tr("(unbound)")):
                    captured_var.set(hotkey_str)
                else:
                    captured_var.set(current + "+" + hotkey_str)
                result["value"] = captured_var.get()
                schedule_finalize()
            return "break"

        def on_save():
            if pending_after_id[0] is not None:
                try:
                    dialog.after_cancel(pending_after_id[0])
                except Exception:
                    pass
            if result["value"] is None and captured_var.get() not in (self.tr("(unbound)"), ""):
                result["value"] = captured_var.get()
            dialog.destroy()

        def on_cancel():
            if pending_after_id[0] is not None:
                try:
                    dialog.after_cancel(pending_after_id[0])
                except Exception:
                    pass
            result["value"] = None
            dialog.destroy()

        def on_clear():
            if pending_after_id[0] is not None:
                try:
                    dialog.after_cancel(pending_after_id[0])
                except Exception:
                    pass
            pending_after_id[0] = None
            captured_var.set(self.tr("(unbound)"))
            result["value"] = ""

        ttk.Button(button_frame, text=self.tr("Clear"), command=on_clear).pack(side=tk.LEFT)
        ttk.Button(button_frame, text=self.tr("Cancel"), command=on_cancel).pack(side=tk.RIGHT, padx=(4, 0))
        ttk.Button(button_frame, text=self.tr("Save"), command=on_save).pack(side=tk.RIGHT)

        dialog.bind('<Key>', on_key)
        captured_label.focus_set()
        dialog.grab_set()
        # Let Tk compute natural size, then center.
        self.root.update_idletasks()
        self.center_dialog(dialog)
        dialog.wait_window()
        return result["value"]

    def _tk_event_to_hotkey_string(self, event):
        """Convert a Tk KeyPress event into a human-readable hotkey string."""
        # Ignore bare modifier key presses
        modifier_keysyms = {
            'Shift_L', 'Shift_R', 'Control_L', 'Control_R',
            'Alt_L', 'Alt_R', 'Meta_L', 'Meta_R', 'Caps_Lock', 'Num_Lock',
        }
        if event.keysym in modifier_keysyms:
            return None

        parts = []
        # State bit masks (cross-platform)
        if event.state & 0x4:
            parts.append('Ctrl')
        if event.state & 0x8:
            parts.append('Alt')
        if event.state & 0x1:
            parts.append('Shift')
        if event.state & 0x40:
            parts.append('Meta')

        # Main key
        keysym = event.keysym
        if len(keysym) == 1 and keysym.isprintable():
            main_key = keysym.upper() if keysym.isalpha() else keysym
        elif keysym.startswith('F') and keysym[1:].isdigit():
            main_key = keysym.upper()
        else:
            pretty = {
                'Escape': 'Esc',
                'Return': 'Enter',
                'space': 'Space',
                'Tab': 'Tab',
                'BackSpace': 'Backspace',
                'Delete': 'Delete',
                'Insert': 'Insert',
                'Home': 'Home',
                'End': 'End',
                'Prior': 'PageUp',
                'Next': 'PageDown',
                'Up': 'Up',
                'Down': 'Down',
                'Left': 'Left',
                'Right': 'Right',
            }
            main_key = pretty.get(keysym, keysym)
        parts.append(main_key)
        return '+'.join(parts)

    def _hotkey_string_to_tk_binding(self, hotkey_str):
        """Convert a hotkey string like 'Ctrl+Shift+Z' to a Tk binding.

        Supports multi-key sequences: 'Ctrl+Space+Enter' becomes
        '<Control-space><Return>' (hold Ctrl, press Space, then press Enter).
        A step is a modifier-prefix followed by exactly one non-modifier key.
        """
        if not hotkey_str:
            return None
        try:
            parts = [p.strip() for p in hotkey_str.split('+') if p.strip()]
        except Exception:
            return None
        if not parts:
            return None

        mod_aliases = {
            'ctrl': 'Control', 'control': 'Control',
            'alt': 'Alt',
            'shift': 'Shift',
            'cmd': 'Meta', 'meta': 'Meta', 'super': 'Meta',
        }
        special_map = {
            'Esc': 'Escape',
            'Enter': 'Return',
            'Space': 'space',
            'Backspace': 'BackSpace',
            'PageUp': 'Prior',
            'PageDown': 'Next',
        }

        def norm_key(k):
            if len(k) == 1:
                return k.lower() if k.isalpha() else k
            if k.upper().startswith('F') and k[1:].isdigit():
                return k.upper()
            return special_map.get(k, k)

        # Split into steps: a step is consecutive modifiers followed by ONE key.
        steps = []
        current_mods = []
        for part in parts:
            mapped = mod_aliases.get(part.lower())
            if mapped:
                current_mods.append(mapped)
            else:
                # A non-modifier ends the current step.
                steps.append((list(current_mods), norm_key(part)))
                current_mods = []
        if current_mods:
            # Trailing modifiers with no key: ignore.
            pass

        if not steps:
            return None

        rendered = []
        for mods, key in steps:
            if mods:
                rendered.append(f"<{'-'.join(mods)}-{key}>")
            else:
                rendered.append(f"<{key}>")
        return ''.join(rendered)

    def create_interface_combined_settings(self, parent):
        """Create combined Interface settings section that includes all sub-sections"""
        # Combined settings from all interface sub-sections
        settings = [
            (self.tr("Interface Theme (Experimental)"), "theme", "choice", ["Light", "Sun-Valley Light", "Sun-Valley Dark", "Azure Light", "Azure Dark"]),
            (self.tr("Columns: Track No."), "show_track_no", "bool"),
            (self.tr("Columns: Artist"), "show_artist", "bool"),
            (self.tr("Columns: Track Name"), "show_track_name", "bool"),
            (self.tr("Columns: Comment"), "show_comment", "bool"),
            (self.tr("Columns: Length"), "show_length", "bool"),
            (self.tr("Columns: Extension"), "show_extension", "bool"),
            (self.tr("Columns: Price"), "show_price", "bool"),
            (self.tr("Columns: NYP"), "show_nyp", "bool"),
            (self.tr("Columns: Year"), "show_year", "bool"),
            (self.tr("Columns: Genre"), "show_genre", "bool"),
            (self.tr("Columns: Bitrate"), "show_bitrate", "bool"),
            (self.tr("Columns: File Size"), "show_file_size", "bool"),
            (self.tr("Columns: Sample Rate"), "show_sample_rate", "bool"),
            (self.tr("Columns: Channels"), "show_channels", "bool"),
            (self.tr("Columns: Bit Depth"), "show_bit_depth", "bool"),
            (self.tr("Columns: Album Metadata"), "show_album_metadata", "bool"),
            (self.tr("Columns: Album Artist Metadata"), "show_album_artist_metadata", "bool"),
            (self.tr("Columns: Composer"), "show_composer", "bool"),
            (self.tr("Columns: ISRC"), "show_isrc", "bool"),
            (self.tr("Logs: Font Family"), "log_font_family", "choice", ["Segoe UI", "Consolas", "Courier New", "monospace", "Arial", "Tahoma"]),
            (self.tr("Logs: Font Size"), "log_font_size", "int", 8, 16),
            (self.tr("Logs: Font Bold"), "log_font_bold", "bool"),
            (self.tr("Logs: Text Color"), "log_text_color", "color"),
            (self.tr("Logs: Background Color"), "log_bg_color", "color"),
            (self.tr("Logs: INFO Color"), "log_info_color", "color"),
            (self.tr("Logs: WARNING Color"), "log_warning_color", "color"),
            (self.tr("Logs: ERROR Color"), "log_error_color", "color"),
            (self.tr("Logs: DEBUG Color"), "log_debug_color", "color"),
            (self.tr("Logs: Show Timestamps"), "log_show_timestamps", "bool"),
            (self.tr("Logs: Timestamp Format"), "log_timestamp_format", "choice", ["HH:MM:SS", "YYYY-MM-DD HH:MM:SS", "MM/DD/YYYY HH:MM:SS", "None"]),
            (self.tr("Logs: Show Log Levels"), "log_show_levels", "bool"),
            (self.tr("Logs: Word Wrap"), "log_word_wrap", "bool"),
            (self.tr("Logs: Line Spacing"), "log_line_spacing", "int", 1, 3),
            (self.tr("Logs: Auto-scroll to Bottom"), "log_auto_scroll", "bool"),
            (self.tr("Logs: Max Lines (0 = unlimited)"), "log_max_lines", "int", 0, 10000),
            (self.tr("Logs: Save Diagnostic Log File"), "log_to_file", "bool"),
            (self.tr("Logs: Diagnostic Log Level"), "log_file_level", "choice", ["DEBUG", "INFO", "WARNING", "ERROR"])
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
                if config_key == "theme":
                    display_value = self.tr(var.get())
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

            if config_key == "theme":
                translated_choices = [self.tr(c) for c in choices]

                def validate_and_save(new_value):
                    eng_idx = translated_choices.index(new_value)
                    eng_value = choices[eng_idx]
                    self.interface_combined_vars[config_key].set(eng_value)
                    self.apply_interface_combined_settings()
                    return True

                self.edit_treeview_cell_dropdown(self.interface_combined_tree, item_id, 'value', translated_choices, self.tr(current_value), validate_and_save)
            else:
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
            "show_track_no", "show_artist", "show_track_name", "show_comment",
            "show_length", "show_extension", "show_price", "show_nyp",
            "show_year", "show_genre", "show_bitrate", "show_file_size",
            "show_sample_rate", "show_channels", "show_bit_depth",
            "show_album_metadata", "show_album_artist_metadata",
            "show_composer", "show_isrc"
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

        # Apply theme if changed and save config
        if 'theme' in self.interface_combined_vars:
            self.config.theme = self.interface_combined_vars['theme'].get()
            set_ui_theme(self.root, self.config.theme)

        save_config(self.config)

        # Apply visual changes
        self.apply_log_visual_settings()
        if hasattr(self, "setup_logging"):
            self.setup_logging()
        if hasattr(self, 'configure_track_table_tags'):
            self.configure_track_table_tags()
        if hasattr(self, 'refresh_all_track_row_tags'):
            self.refresh_all_track_row_tags()
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
        
        save_config(self.config)
        self.apply_column_visibility()
    
    def create_auto_tagging_settings(self, parent):
        """Create Auto Tagging settings section using Treeview"""
        # Auto tagging settings
        settings = [
            (self.tr("Year"), "auto_tag_year", "bool"),
            (self.tr("Genre"), "auto_tag_genre", "bool"),
            (self.tr("Artist"), "auto_tag_artist", "bool"),
            (self.tr("Album"), "auto_tag_album", "bool"),
            (self.tr("Comment"), "auto_tag_comment", "bool"),
            (self.tr("Track Title"), "auto_tag_track_title", "bool"),
            (self.tr("Album Artist"), "auto_tag_album_artist", "bool"),
            (self.tr("Composer"), "auto_tag_composer", "bool"),
            (self.tr("Track Number"), "auto_tag_track_number", "bool"),
            (self.tr("Duration"), "auto_tag_duration", "bool"),
            (self.tr("Bitrate"), "auto_tag_bitrate", "bool"),
            (self.tr("Release Type"), "auto_tag_release_type", "bool")
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
                self.show_toast(self.tr("Maximum 10 auto-tagging options allowed"), 2000, "warning")
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
            (self.tr("Auto-start upload after adding files"), "auto_start_upload", "bool"),
            (self.tr("Confirm before starting upload"), "confirm_before_upload", "bool"),
            (self.tr("Use track name for single release"), "use_track_name_for_single_release", "bool"),
            (self.tr("Open logs on album upload"), "open_logs_on_upload", "bool"),
            (self.tr("Open album page after upload"), "open_album_page_after_upload", "bool"),
            (self.tr("Copy album URL to clipboard after upload"), "copy_album_url_after_upload", "bool"),
            (self.tr("Use embedded cover art from tracks"), "extract_embedded_cover_art", "bool"),
            (self.tr("Detailed track information in progress"), "detailed_progress_track_info", "bool"),
            (self.tr("Show progress timing details"), "show_progress_timing_details", "bool"),
            (self.tr("Max concurrent uploads"), "max_concurrent_uploads", "int", 1, 5),
            (self.tr("Upload timeout (seconds)"), "upload_timeout", "int", 30, 600),
            (self.tr("Retry failed uploads"), "retry_failed_uploads", "bool"),
            (self.tr("Retry attempts"), "retry_attempts", "int", 1, 10),
            (self.tr("Retry delay (seconds)"), "retry_delay", "int", 1, 60),
            (self.tr("Enable conversion to FLAC"), "enable_flac_conversion", "bool"),
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
        self.config.use_track_name_for_single_release = self.upload_vars['use_track_name_for_single_release'].get()
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
        self.config.enable_flac_conversion = self.upload_vars['enable_flac_conversion'].get()
        save_config(self.config)
    
    def create_general_combined_settings(self, parent):
        """Create combined General settings section that includes all sub-sections"""
        # Combined settings from all general sub-sections
        settings = [
            (self.tr("Interface: Apply settings immediately"), "apply_settings_immediately", "bool"),
            (self.tr("Interface: Maximize app on open"), "maximize_on_open", "bool"),
            (self.tr("Interface: Disable tooltips"), "disable_tooltips", "bool"),
            (self.tr("Interface: Remove splash art"), "remove_splash_art", "disabled_bool"),
            (self.tr("Interface: Remember Last Opened Album"), "remember_last_album", "bool"),
            (self.tr("Metadata: Auto load metadata for album details"), "auto_load_metadata", "bool"),
            (self.tr("Metadata: Use Album Artist metadata for Artist in Album details"), "use_album_artist_in_album_details", "bool"),
            (self.tr("Metadata: Guess album title from track metadata"), "guess_album_title_from_track_metadata", "bool"),
            (self.tr("Metadata: Guess release date from track metadata"), "guess_release_date_from_track_metadata", "bool"),
            (self.tr("Metadata: Folder name if album tag missing"), "use_folder_name_when_album_missing", "bool"),
            (self.tr("Metadata: Extract track cover if cover missing"), "extract_track_cover_if_missing", "bool"),
            (self.tr("Metadata: Smart-randomize on album load"), "smart_randomize_on_album_load", "bool"),
            (self.tr("Metadata: Auto guess case tracks on album load"), "auto_guess_case_on_album_load", "bool"),
            (self.tr("Cover Art: Always auto-scale cover art"), "always_auto_scale_cover", "bool"),
            (self.tr("Cover Art: Cover scaling method"), "cover_scaling_method", "str"),
            (self.tr("Cover Art: Cover fit mode"), "cover_fit_mode", "str"),
            (self.tr("Description: Description auto-fill"), "description_auto_fill_mode", "str"),
            (self.tr("Description: Preview Description"), "preview_description", "action"),
            (self.tr("Description: Create description on upload"), "description_auto_fill_on_upload", "bool"),
            (self.tr("Track Table: Auto Fit Columns"), "auto_fit_columns", "bool"),
            (self.tr("Track Table: Lock Column Sizes"), "lock_column_sizes", "bool"),
            (self.tr("Track Table: Highlight Search Matches (hide non-matches instead)"), "highlight_search_matches", "bool"),
            (self.tr("Track Table: Locked Track Highlight Color"), "locked_track_highlight_color", "color"),
            (self.tr("Track Table: Highlight Corrupted Tracks"), "highlight_corrupted_tracks", "bool"),
            (self.tr("Track Table: Show Total Album Duration"), "show_total_album_duration", "bool"),
            (self.tr("Files: Create session.txt files (Recommended)"), "create_album_session_files", "bool"),
            (self.tr("Files: Clear progress on album change"), "clear_progress_on_album_change", "bool"),
            (self.tr("Files: Limit Log Files"), "log_file_limit", "int", 1, 99),
            (self.tr("Files: File Size Unit"), "file_size_unit", "str"),
            (self.tr("Startup: Auto load cookies on startup"), "auto_load_cookies", "bool"),
            (self.tr("Startup: Check for updates on startup"), "check_for_updates", "bool"),
            (self.tr("Startup: Check for updates now"), "check_updates_now", "action"),
            (self.tr("Context: Remove Dividers"), "context_menu_remove_dividers", "bool"),
            (self.tr("Context: Play"), "context_menu_play", "bool"),
            (self.tr("Context: Remove Track"), "context_menu_remove_track", "bool"),
            (self.tr("Context: Move Up"), "context_menu_move_up", "bool"),
            (self.tr("Context: Move Down"), "context_menu_move_down", "bool"),
            (self.tr("Context: Move to Top"), "context_menu_move_to_top", "bool"),
            (self.tr("Context: Move to Bottom"), "context_menu_move_to_bottom", "bool"),
            (self.tr("Context: Open File"), "context_menu_open_file", "bool"),
            (self.tr("Context: Replace File"), "context_menu_replace_file", "bool"),
            (self.tr("Context: Extract Cover Art"), "context_menu_extract_cover_art", "bool"),
            (self.tr("Context: Extract Tracklist"), "context_menu_extract_tracklist", "bool"),
            (self.tr("Context: Open session.txt"), "context_menu_open_session", "bool"),
            (self.tr("Context: Set Track Cover as Album Cover"), "context_menu_set_track_cover_as_album_cover", "bool"),
            (self.tr("Context: Undo"), "context_menu_undo", "bool"),
            (self.tr("Context: Redo"), "context_menu_redo", "bool"),
            (self.tr("Context: Extract Track Information"), "context_menu_extract_track_info", "bool"),
            (self.tr("Context: Copy Metadata"), "context_menu_copy_metadata", "bool"),
            (self.tr("Context: Paste Metadata"), "context_menu_paste_metadata", "bool"),
            (self.tr("Context: Revert to Original"), "context_menu_revert_to_original", "bool"),
            (self.tr("Context: Lock/Unlock"), "context_menu_lock_unlock", "bool"),
            (self.tr("Context: Randomize"), "context_menu_randomize", "bool"),
            (self.tr("Context: Smart Randomize"), "context_menu_smart_randomize", "bool"),
            (self.tr("Context: Sort By"), "context_menu_sort_by", "bool"),
            (self.tr("Context: Clear Metadata"), "context_menu_clear_metadata", "bool"),
            (self.tr("Context: Clear All Metadata"), "context_menu_clear_all_metadata", "bool"),
            (self.tr("Context: Clear All"), "context_menu_clear_all", "bool"),
            (self.tr("Context: Upload as Single"), "context_menu_upload_as_single", "bool"),
            *[(self.tr(f"Sort: {setting_name}"), config_key, "bool") for setting_name, config_key in SORT_METHOD_SETTINGS],
            (self.tr("Auto Tag: Year"), "auto_tag_year", "bool"),
            (self.tr("Auto Tag: Genre"), "auto_tag_genre", "bool"),
            (self.tr("Auto Tag: Artist"), "auto_tag_artist", "bool"),
            (self.tr("Auto Tag: Album"), "auto_tag_album", "bool"),
            (self.tr("Auto Tag: Comment"), "auto_tag_comment", "bool"),
            (self.tr("Auto Tag: Track Title"), "auto_tag_track_title", "bool"),
            (self.tr("Auto Tag: Album Artist"), "auto_tag_album_artist", "bool"),
            (self.tr("Auto Tag: Composer"), "auto_tag_composer", "bool"),
            (self.tr("Auto Tag: Track Number"), "auto_tag_track_number", "bool"),
            (self.tr("Auto Tag: Duration"), "auto_tag_duration", "bool"),
            (self.tr("Auto Tag: Bitrate"), "auto_tag_bitrate", "bool"),
            (self.tr("Auto Tag: Release Type"), "auto_tag_release_type", "bool")
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
        
        for setting_data in settings:
            setting_name = setting_data[0]
            config_key = setting_data[1]
            setting_type = setting_data[2]
            
            if setting_type == "bool":
                if config_key.startswith("auto_tag_"):
                    var = tk.BooleanVar(value=getattr(self.config, config_key, False))
                else:
                    var = tk.BooleanVar(value=getattr(self.config, config_key, True))
                display_value = "☑" if var.get() else "☐"
            elif setting_type == "str":
                var = tk.StringVar(value=getattr(self.config, config_key, self.tr("Off")))
                display_value = var.get()
            elif setting_type == "int":
                min_val = setting_data[3]
                max_val = setting_data[4]
                var = tk.IntVar(value=getattr(self.config, config_key, min_val))
                display_value = str(var.get())
            elif setting_type == "color":
                var = tk.StringVar(value=getattr(self.config, config_key, '#ffffff'))
                display_value = var.get()
            elif setting_type == "action":
                var = None
                display_value = self.tr("Remove...") if config_key == "remove_all_custom_templates" else self.tr("Preview...")
            
            if var is not None:
                self.general_combined_vars[config_key] = var
            self.general_combined_vars[f"{config_key}_type"] = setting_type
            if setting_type == "int":
                self.general_combined_vars[f"{config_key}_min"] = min_val
                self.general_combined_vars[f"{config_key}_max"] = max_val
            
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
        if config_key == "description_auto_fill_mode":
            self.root.after_idle(lambda: self.open_description_autofill_dialog(
                self.general_combined_tree,
                item_id, 'value',
                self.general_combined_vars[config_key].get(),
                lambda v: self.apply_general_combined_str_setting(config_key, v)))
            return "break"
        if config_key == "preview_description":
            self.root.after_idle(self.open_description_preview_dialog)
            return "break"
        if config_key == "check_updates_now":
            self.root.after_idle(self.check_for_updates_now)
            return "break"
        if config_key == "remove_all_custom_templates":
            self.root.after_idle(self._remove_all_custom_templates)
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
            elif config_key == "remove_all_custom_templates":
                self._remove_all_custom_templates()
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
                    self.show_toast(self.tr("Maximum 10 auto-tagging options allowed"), 2000, "warning")
                    return
            
            self.general_combined_vars[config_key].set(new_value)
            self.general_combined_tree.set(item_id, 'value', '☑' if new_value else '☐')
            self.apply_general_combined_settings()
        elif setting_type == "str":
            if config_key == "description_auto_fill_mode":
                self.open_description_autofill_dialog(self.general_combined_tree, item_id, 'value',
                    self.general_combined_vars[config_key].get(),
                    lambda v: self.apply_general_combined_str_setting(config_key, v))
            elif config_key == "cover_scaling_method":
                self.edit_treeview_cell_dropdown(
                    self.general_combined_tree,
                    item_id,
                    'value',
                    [self.tr(m) for m in SCALING_METHOD_OPTIONS],
                    self.general_combined_vars[config_key].get(),
                    lambda v: self.apply_general_combined_str_setting(config_key, v),
                )
            elif config_key == "cover_fit_mode":
                self.edit_treeview_cell_dropdown(
                    self.general_combined_tree,
                    item_id,
                    'value',
                    [self.tr("Crop (fill)"), self.tr("Fit (contain)"), self.tr("Stretch")],
                    self.general_combined_vars[config_key].get(),
                    lambda v: self.apply_general_combined_str_setting(config_key, v),
                )
            elif config_key == "file_size_unit":
                self.edit_treeview_cell_dropdown(
                    self.general_combined_tree,
                    item_id,
                    'value',
                    [self.tr("Auto"), self.tr("MB"), self.tr("GB"), self.tr("KB"), self.tr("Bytes")],
                    self.general_combined_vars[config_key].get(),
                    lambda v: self.apply_general_combined_str_setting(config_key, v),
                )
        elif setting_type == "int":
            min_val = self.general_combined_vars.get(f"{config_key}_min", 1)
            max_val = self.general_combined_vars.get(f"{config_key}_max", 99)
            current_value = str(self.general_combined_vars[config_key].get())

            def validate_and_save(new_value):
                try:
                    int_val = int(new_value)
                    if min_val <= int_val <= max_val:
                        self.general_combined_vars[config_key].set(int_val)
                        self.general_combined_tree.set(item_id, 'value', str(int_val))
                        setattr(self.config, config_key, int_val)
                        save_config(self.config)
                        if config_key == "log_file_limit" and hasattr(self, 'cleanup_old_log_files'):
                            self.cleanup_old_log_files()
                        return True
                except ValueError:
                    pass
                return False

            self.edit_treeview_cell(self.general_combined_tree, item_id, 'value', current_value, validate_and_save)
        elif setting_type == "color":
            current_color = self.general_combined_vars[config_key].get()
            new_color = colorchooser.askcolor(color=current_color)[1]
            if new_color:
                self.general_combined_vars[config_key].set(new_color)
                self.general_combined_tree.set(item_id, 'value', new_color)
                self.config.locked_track_highlight_color = new_color
                save_config(self.config)
                if hasattr(self, 'configure_track_table_tags'):
                    self.configure_track_table_tags()
    
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
        self.config.cover_fit_mode = self.general_combined_vars['cover_fit_mode'].get()
        self.config.description_auto_fill_mode = self.general_combined_vars['description_auto_fill_mode'].get()
        self.config.description_auto_fill_on_upload = self.general_combined_vars['description_auto_fill_on_upload'].get()
        self.config.extract_track_cover_if_missing = self.general_combined_vars['extract_track_cover_if_missing'].get()
        self.config.clear_progress_on_album_change = self.general_combined_vars['clear_progress_on_album_change'].get()
        self.config.auto_load_cookies = self.general_combined_vars['auto_load_cookies'].get()
        self.config.check_for_updates = self.general_combined_vars['check_for_updates'].get()
        self.config.auto_fit_columns = self.general_combined_vars['auto_fit_columns'].get()
        self.config.lock_column_sizes = self.general_combined_vars['lock_column_sizes'].get()
        self.config.highlight_search_matches = self.general_combined_vars['highlight_search_matches'].get()
        self.config.locked_track_highlight_color = self.general_combined_vars['locked_track_highlight_color'].get()
        self.config.highlight_corrupted_tracks = self.general_combined_vars['highlight_corrupted_tracks'].get()
        self.config.show_total_album_duration = self.general_combined_vars['show_total_album_duration'].get()
        self.config.remember_last_album = self.general_combined_vars['remember_last_album'].get()
        self.config.log_file_limit = self.general_combined_vars['log_file_limit'].get()
        self.config.file_size_unit = self.general_combined_vars['file_size_unit'].get()
        ToolTip.disabled = self.config.disable_tooltips
        if hasattr(self, 'scale_cover_var'):
            self.scale_cover_var.set(self.config.always_auto_scale_cover)
        if hasattr(self, 'scaling_method_var'):
            self.scaling_method_var.set(self.config.cover_scaling_method)
        if hasattr(self, 'cover_fit_mode_var'):
            self.cover_fit_mode_var.set(self.config.cover_fit_mode)
        
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
        self.config.context_menu_upload_as_single = self.general_combined_vars['context_menu_upload_as_single'].get()

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
        if hasattr(self, 'configure_track_table_tags'):
            self.configure_track_table_tags()
        if hasattr(self, 'refresh_all_track_row_tags'):
            self.refresh_all_track_row_tags()
        if hasattr(self, 'refresh_file_size_display'):
            self.refresh_file_size_display()
        if hasattr(self, 'update_preview_total_duration_label'):
            self.update_preview_total_duration_label()
        if hasattr(self, 'cleanup_old_log_files'):
            self.cleanup_old_log_files()

    def apply_general_combined_str_setting(self, config_key, new_value):
        """Apply a combined General string/dropdown setting."""
        if config_key == "description_auto_fill_mode" and new_value not in DESCRIPTION_AUTO_FILL_MODES:
            return False
        if config_key == "cover_scaling_method" and new_value not in [self.tr(m) for m in SCALING_METHOD_OPTIONS]:
            return False
        if config_key == "cover_fit_mode" and new_value not in (self.tr("Crop (fill)"), self.tr("Fit (contain)"), self.tr("Stretch")):
            return False
        if config_key == "file_size_unit" and new_value not in (self.tr("Auto"), self.tr("MB"), self.tr("GB"), self.tr("KB"), self.tr("Bytes")):
            return False

        self.general_combined_vars[config_key].set(new_value)
        setattr(self.config, config_key, new_value)
        if config_key == "cover_scaling_method" and hasattr(self, 'scaling_method_var'):
            self.scaling_method_var.set(new_value)
        if config_key == "cover_fit_mode" and hasattr(self, 'cover_fit_mode_var'):
            self.cover_fit_mode_var.set(new_value)
        if config_key == "file_size_unit" and hasattr(self, 'refresh_file_size_display'):
            self.refresh_file_size_display()
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
        item_id = self.advanced_tree.insert('', 'end', values=(self.tr("Reset all settings"), self.tr("Reset...")))
        self.advanced_item_mapping[item_id] = "reset_all_settings"
        item_id = self.advanced_tree.insert('', 'end', values=(self.tr("Custom Filename Patterns"), self.tr("Manage...")))
        self.advanced_item_mapping[item_id] = "custom_filename_patterns"

        self.advanced_tree.bind('<Button-1>', self.on_advanced_tree_click)

    def on_advanced_tree_click(self, event):
        """Handle single-click actions in the Advanced settings tree."""
        item_id = self.advanced_tree.identify('item', event.x, event.y)
        column = self.advanced_tree.identify('column', event.x, event.y)
        if not item_id or column != '#2':
            return

        if self.advanced_item_mapping.get(item_id) == "reset_all_settings":
            if not getattr(self, '_reset_in_progress', False):
                self.root.after_idle(self.reset_all_settings)
            return "break"
        if self.advanced_item_mapping.get(item_id) == "custom_filename_patterns":
            self.root.after_idle(self.open_custom_filename_patterns_dialog)
            return "break"

    def reset_all_settings(self):
        """Reset all settings to defaults with 3 confirmation dialogs"""
        if getattr(self, '_reset_in_progress', False):
            return
        self._reset_in_progress = True
        try:
            confirm1 = messagebox.askyesno(
                self.tr("Reset All Settings - Confirmation 1/3"),
                self.tr("Are you sure you want to reset ALL settings to defaults?\n\n"
                "This will reset:\n"
                "- All preferences and configurations\n"
                "- UI customizations (colors and fonts)\n"
                "- Column visibility settings\n"
                "- Context menu settings\n"
                "- Upload settings\n"
                "- Notification settings\n"
                "- And all other configurable options\n\n"
                "This action cannot be undone."),
                icon='warning'
            )

            if not confirm1:
                return

            confirm2 = messagebox.askyesno(
                self.tr("Reset All Settings - Confirmation 2/3"),
                self.tr("This is your second warning.\n\n"
                "All your carefully customized settings will be lost.\n"
                "You will need to reconfigure everything from scratch.\n\n"
                "Are you absolutely sure you want to proceed?"),
                icon='warning'
            )

            if not confirm2:
                return

            confirm3 = messagebox.askyesno(
                self.tr("Reset All Settings - Final Confirmation"),
                self.tr("FINAL WARNING: This is your last chance to cancel.\n\n"
                "Once you click Yes, all settings will be immediately reset\n"
                "to their default values and the application will restart.\n\n"
                "Click Yes to reset everything or No to cancel."),
                icon='warning'
            )

            if not confirm3:
                return

            default_config = Config()
            save_config(default_config)
            messagebox.showinfo(
                self.tr("Settings Reset Complete"),
                self.tr("All settings have been reset to defaults.\n\n"
                "The application will now restart to apply the changes.")
            )
            self.restart_application()

        except Exception as e:
            messagebox.showerror(
                self.tr("Reset Failed"),
                self.tr("Failed to reset settings:") + f"\n{str(e)}"
            )
        finally:
            self._reset_in_progress = False

    DEFAULT_FILENAME_PATTERNS = [
        (r"^(\d+)\s*[.\-)_\s]+\s*(.+?)\s*-\s*(.+)", 1, 2, 3),
        (r"^Track\s*(\d+)\s*[.\-)_\s]+\s*(.+?)\s*-\s*(.+)", 1, 2, 3),
        (r"^(\d+)\s*[.\-)_\s]+\s*(.+)", 1, None, 2),
        (r"^Track\s*(\d+)\s*[.\-)_\s]+\s*(.+)", 1, None, 2),
        (r"^(\d+)\s*(.+)", 1, None, 2),
        (r"^(.+?)\s*-\s*(.+)", None, 1, 2),
    ]

    def open_custom_filename_patterns_dialog(self):
        """Open dialog to manage custom filename regex patterns."""
        parent = self.get_preferences_dialog_parent()
        dialog = tk.Toplevel(parent)
        dialog.title(self.tr("Custom Filename Patterns"))
        dialog.transient(parent)
        dialog.withdraw()
        dialog.resizable(True, True)

        patterns = list(getattr(self.config, 'filename_track_patterns', []))

        frame = ttk.Frame(dialog, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)

        list_frame = ttk.Frame(frame)
        list_frame.pack(fill=tk.BOTH, expand=True)

        tree = ttk.Treeview(list_frame, columns=('pattern',), show='tree', selectmode='browse')
        tree.column('#0', width=0, stretch=False)
        tree.column('pattern', width=550, anchor=tk.W)

        scroll = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)

        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        tree.pack(fill=tk.BOTH, expand=True)

        def fmt(p):
            if isinstance(p, str):
                return p
            parts = [str(x) if x is not None else "" for x in p]
            return " | ".join(parts)

        def refresh():
            for item in tree.get_children():
                tree.delete(item)
            for p in self.DEFAULT_FILENAME_PATTERNS:
                tree.insert('', tk.END, values=(fmt(p),), tags=("default",))
            for p in patterns:
                tree.insert('', tk.END, values=(fmt(p),))

        refresh()

        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X, pady=(10, 0))

        def add_pattern():
            add_dialog = tk.Toplevel(dialog)
            add_dialog.title(self.tr("Add Pattern"))
            add_dialog.transient(dialog)
            add_dialog.grab_set()
            self.center_dialog(add_dialog, 500, 200, dialog)

            f = ttk.Frame(add_dialog, padding=10)
            f.pack(fill=tk.BOTH, expand=True)

            ttk.Label(f, text=self.tr("Regex:")).grid(row=0, column=0, sticky=tk.W, pady=3)
            regex_entry = ttk.Entry(f, width=40)
            regex_entry.grid(row=0, column=1, padx=(5, 0), pady=3)

            ttk.Label(f, text=self.tr("Track # group:")).grid(row=1, column=0, sticky=tk.W, pady=3)
            track_entry = ttk.Entry(f, width=40)
            track_entry.grid(row=1, column=1, sticky=tk.W, padx=(5, 0), pady=3)

            ttk.Label(f, text=self.tr("Artist group:")).grid(row=2, column=0, sticky=tk.W, pady=3)
            artist_entry = ttk.Entry(f, width=40)
            artist_entry.grid(row=2, column=1, sticky=tk.W, padx=(5, 0), pady=3)

            ttk.Label(f, text=self.tr("Title group:")).grid(row=3, column=0, sticky=tk.W, pady=3)
            title_entry = ttk.Entry(f, width=40)
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
                refresh()
                add_dialog.destroy()

            btn_f = ttk.Frame(f)
            btn_f.grid(row=4, column=0, columnspan=2, pady=(15, 0))
            ttk.Button(btn_f, text=self.tr("Add"), command=save_pattern, width=12).pack(side=tk.LEFT, padx=5)
            ttk.Button(btn_f, text=self.tr("Cancel"), command=add_dialog.destroy, width=12).pack(side=tk.LEFT)

        def remove_selected():
            sel = tree.selection()
            if not sel:
                return
            item = sel[0]
            tags = tree.item(item, "tags")
            if "default" in tags:
                return
            idx = tree.index(item) - len(self.DEFAULT_FILENAME_PATTERNS)
            if 0 <= idx < len(patterns):
                patterns.pop(idx)
                refresh()

        ttk.Button(btn_frame, text=self.tr("Add"), command=add_pattern, width=12).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text=self.tr("Remove"), command=remove_selected, width=12).pack(side=tk.LEFT, padx=5)

        ttk.Button(btn_frame, text=self.tr("Close"), command=dialog.destroy, width=12).pack(side=tk.RIGHT, padx=5)

        def on_close():
            self.config.filename_track_patterns = patterns
            save_config(self.config)
            dialog.destroy()

        dialog.protocol("WM_DELETE_WINDOW", on_close)
        self.center_dialog(dialog, 600, 400, parent)
        dialog.deiconify()
        dialog.grab_set()

    def open_description_autofill_dialog(self, tree, item_id, column, current_value, callback):
        """Open dialog to select a description auto-fill mode (single selection)."""
        parent = self.get_preferences_dialog_parent()
        dialog = tk.Toplevel(parent)
        dialog.title(self.tr("Description Auto-Fill"))
        dialog.transient(parent)
        dialog.withdraw()
        dialog.resizable(True, True)

        frame = ttk.Frame(dialog, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)

        list_frame = ttk.Frame(frame)
        list_frame.pack(fill=tk.BOTH, expand=True)

        mode_tree = ttk.Treeview(list_frame, columns=('mode',), show='tree', selectmode='browse')
        mode_tree.column('#0', width=440, stretch=True)
        mode_tree.column('mode', width=0, stretch=False)

        scroll = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=mode_tree.yview)
        mode_tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        mode_tree.pack(fill=tk.BOTH, expand=True)

        def refresh_tree():
            for item in mode_tree.get_children():
                mode_tree.delete(item)
            for mode in DESCRIPTION_AUTO_FILL_MODES:
                m = mode_tree.insert('', tk.END, text=self.tr(mode), values=(mode,), tags=("builtin",))
                if mode == current_value:
                    mode_tree.selection_set(m)
                    mode_tree.focus(m)
            for cm in load_custom_description_templates():
                name = cm.get("name", "?")
                m = mode_tree.insert('', tk.END, values=(name,), tags=("custom",))
                if name == current_value:
                    mode_tree.selection_set(m)
                    mode_tree.focus(m)

        mode_tree.tag_configure("builtin")
        mode_tree.tag_configure("custom")
        refresh_tree()

        def on_ok():
            sel = mode_tree.selection()
            if not sel:
                return
            new_val = mode_tree.item(sel[0], 'values')[0]
            if callback(new_val):
                tree.set(item_id, column, new_val)
            dialog.destroy()

        def edit_selected():
            sel = mode_tree.selection()
            if not sel:
                return
            mode = mode_tree.item(sel[0], 'values')[0]
            if mode == "Off":
                return
            tags = mode_tree.item(sel[0], "tags")
            is_custom = "custom" in tags

            edit_dialog = tk.Toplevel(dialog)
            edit_dialog.title(self.tr("Edit Template — {}").format(mode))
            edit_dialog.transient(dialog)
            edit_dialog.grab_set()
            edit_dialog.resizable(True, True)
            self.center_dialog(edit_dialog, 700, 400, dialog)

            f = ttk.Frame(edit_dialog, padding=10)
            f.pack(fill=tk.BOTH, expand=True)

            if is_custom:
                all_custom = load_custom_description_templates()
                current_template = next((cm["template"] for cm in all_custom if cm["name"] == mode), "")
            else:
                templates = self.config.description_templates.copy()
                current_template = templates.get(mode) or DESCRIPTION_TEMPLATES.get(mode, "")

            text = tk.Text(f, font=("Consolas", 10), wrap=tk.WORD, height=12)
            style_multiline_editbox(text)
            text.pack(fill=tk.BOTH, expand=True)
            text.insert("1.0", current_template)
            text.focus_set()

            def save():
                val = text.get("1.0", tk.END).strip()
                if is_custom:
                    save_custom_description_template(mode, val)
                else:
                    templates = self.config.description_templates.copy()
                    if val:
                        templates[mode] = val
                    else:
                        templates.pop(mode, None)
                    self.config.description_templates = templates
                    save_config(self.config)
                edit_dialog.destroy()

            def reset():
                if is_custom:
                    delete_custom_description_template(mode)
                else:
                    templates = self.config.description_templates.copy()
                    templates.pop(mode, None)
                    self.config.description_templates = templates
                    save_config(self.config)
                edit_dialog.destroy()
                refresh_tree()

            btn_f = ttk.Frame(f)
            btn_f.pack(fill=tk.X, pady=(10, 0))
            ttk.Button(btn_f, text=self.tr("Save"), command=save, width=10).pack(side=tk.RIGHT, padx=3)
            ttk.Button(btn_f, text=self.tr("Reset to Default"), command=reset, width=14).pack(side=tk.RIGHT, padx=3)
            ttk.Button(btn_f, text=self.tr("Cancel"), command=edit_dialog.destroy, width=10).pack(side=tk.RIGHT)

        def new_custom():
            name_dialog = tk.Toplevel(dialog)
            name_dialog.title(self.tr("New Template"))
            name_dialog.transient(dialog)
            name_dialog.grab_set()
            name_dialog.resizable(False, False)
            self.center_dialog(name_dialog, 350, 120, dialog)

            nf = ttk.Frame(name_dialog, padding=10)
            nf.pack(fill=tk.BOTH, expand=True)
            ttk.Label(nf, text=self.tr("Template name:")).pack(anchor=tk.W)
            name_entry = ttk.Entry(nf, width=40)
            name_entry.pack(fill=tk.X, pady=(5, 10))
            name_entry.focus_set()

            def create():
                name = name_entry.get().strip()
                if not name:
                    return
                save_custom_description_template(name, "{n}. {artist} - {title}")
                name_dialog.destroy()
                refresh_tree()
                for item in mode_tree.get_children():
                    if mode_tree.item(item, 'values')[0] == name:
                        mode_tree.selection_set(item)
                        mode_tree.focus(item)
                        break
                edit_selected()

            def on_enter(e):
                create()

            name_entry.bind('<Return>', on_enter)
            btn_f = ttk.Frame(nf)
            btn_f.pack()
            ttk.Button(btn_f, text=self.tr("Create"), command=create, width=10).pack(side=tk.LEFT, padx=3)
            ttk.Button(btn_f, text=self.tr("Cancel"), command=name_dialog.destroy, width=10).pack(side=tk.LEFT)

        def duplicate_selected():
            sel = mode_tree.selection()
            if not sel:
                return
            mode = mode_tree.item(sel[0], 'values')[0]
            if mode == "Off":
                return

            # Get template content from built-in or custom source
            template_content = ""
            tags = mode_tree.item(sel[0], "tags")
            if "custom" in tags:
                for cm in load_custom_description_templates():
                    if cm["name"] == mode:
                        template_content = cm["template"]
                        break
            else:
                templates = getattr(self.config, 'description_templates', {})
                template_content = templates.get(mode) or DESCRIPTION_TEMPLATES.get(mode, "")
            if not template_content:
                return

            name_dialog = tk.Toplevel(dialog)
            name_dialog.title(self.tr("Duplicate Template"))
            name_dialog.transient(dialog)
            name_dialog.grab_set()
            name_dialog.resizable(False, False)
            self.center_dialog(name_dialog, 350, 120, dialog)

            nf = ttk.Frame(name_dialog, padding=10)
            nf.pack(fill=tk.BOTH, expand=True)
            ttk.Label(nf, text=self.tr("New template name:")).pack(anchor=tk.W)
            name_entry = ttk.Entry(nf, width=40)
            name_entry.pack(fill=tk.X, pady=(5, 10))
            name_entry.insert(0, self.tr("{} (Copy)").format(mode))
            name_entry.select_range(0, tk.END)
            name_entry.focus_set()

            def create():
                name = name_entry.get().strip()
                if not name:
                    return
                save_custom_description_template(name, template_content)
                name_dialog.destroy()
                refresh_tree()
                for item in mode_tree.get_children():
                    if mode_tree.item(item, 'values')[0] == name:
                        mode_tree.selection_set(item)
                        mode_tree.focus(item)
                        break

            def on_enter(e):
                create()

            name_entry.bind('<Return>', on_enter)
            btn_f = ttk.Frame(nf)
            btn_f.pack()
            ttk.Button(btn_f, text=self.tr("Duplicate"), command=create, width=10).pack(side=tk.LEFT, padx=3)
            ttk.Button(btn_f, text=self.tr("Cancel"), command=name_dialog.destroy, width=10).pack(side=tk.LEFT)

        def remove_selected():
            sel = mode_tree.selection()
            if not sel:
                return
            tags = mode_tree.item(sel[0], "tags")
            if "custom" not in tags:
                return
            mode = mode_tree.item(sel[0], 'values')[0]
            delete_custom_description_template(mode)
            refresh_tree()

        mode_tree.bind('<Double-Button-1>', lambda e: edit_selected())

        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X, pady=(10, 0))
        ttk.Button(btn_frame, text=self.tr("Select"), command=on_ok, width=12).pack(side=tk.RIGHT, padx=(4, 0))
        ttk.Button(btn_frame, text=self.tr("Close"), command=dialog.destroy, width=12).pack(side=tk.RIGHT)
        ttk.Button(btn_frame, text=self.tr("New"), command=new_custom, width=8).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(btn_frame, text=self.tr("Duplicate"), command=duplicate_selected, width=10).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(btn_frame, text=self.tr("Delete"), command=remove_selected, width=8).pack(side=tk.LEFT)

        dialog.update_idletasks()
        self.center_dialog(dialog, 520, 400, parent)
        dialog.deiconify()
        dialog.grab_set()

    def check_for_updates_now(self, silent=False):
        """Check for new releases on GitHub. Only alerts if a newer version exists."""
        import json
        import re
        import webbrowser
        import urllib.request
        from tkinter import messagebox

        def parse_ver(v):
            nums = re.findall(r'\d+', v)
            if not nums:
                return (0, 0)
            ver_tuple = tuple(int(n) for n in nums)
            has_suffix = bool(re.search(r'[a-zA-Z]', v))
            return ver_tuple + (0,) if has_suffix else ver_tuple + (1,)

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
                    self.tr("Update Available"),
                    self.tr("A new version is available: v{}").format(latest_tag) + "\n" +
                    self.tr("You have: v{}").format(__version__) + "\n\n" +
                    self.tr("Would you like to open the releases page to download it?")
                )
                if result:
                    webbrowser.open("https://github.com/Nai64/BandcampAutoUploader/releases")
            elif not silent:
                self.show_toast(self.tr("You're on the latest version"), 2000, "success")

        except Exception:
            if not silent:
                self.show_toast(self.tr("Failed to check for updates"), 2000, "error")

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
        dialog.title(self.tr("Preferences"))
        dialog.resizable(True, True)
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
        
        ttk.Button(close_frame, text=self.tr("Close"), command=close_preferences).pack(side=tk.RIGHT)

    def open_preferences_to_section(self, section_id):
        """Open preferences dialog and navigate to a specific section."""
        if getattr(self, 'preferences_dialog', None) is None or not self.preferences_dialog.winfo_exists():
            self.open_preferences_dialog()
        self.root.after(100, lambda: self._navigate_settings_to(section_id))

    def _navigate_settings_to(self, section_id):
        """Select a section in the settings tree after preferences are open."""
        if not hasattr(self, 'settings_tree'):
            return
        self.settings_tree.selection_set(section_id)
        self.settings_tree.focus(section_id)
        self.settings_tree.see(section_id)
        self.on_settings_tree_select(None)

