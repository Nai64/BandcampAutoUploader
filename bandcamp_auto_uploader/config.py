import dataclasses
import json
import os
from pathlib import Path

from InquirerPy import inquirer


@dataclasses.dataclass
class Config:
    album_price: float = 0
    track_price: float = 0
    name_your_price: bool = True
    track_streaming: bool = True
    track_downloading: bool = True
    use_filename_as_title: bool = False  # Force use filename as track title
    ignore_all_metadata: bool = False  # Ignore all metadata from audio files
    ignore_artist_name: bool = False  # Ignore artist name from metadata
    cookies_file: str = ""
    auto_load_cookies: bool = False  # Auto load cookies on startup
    debug: bool = False
    last_selected_artist: str = ""  # Remember last selected artist
    recent_albums: list = dataclasses.field(default_factory=list)  # Recent album paths
    window_geometry: str = "1000x750"  # Window size and position
    upload_history: list = dataclasses.field(default_factory=list)  # Upload history with timestamps
    recent_artists: list = dataclasses.field(default_factory=list)  # Recent artists list
    cover_art_library: list = dataclasses.field(default_factory=list)  # Recent cover arts
    enable_toasts: bool = True  # Enable toast notifications
    toast_duration: int = 3  # Toast notification duration in seconds
    toast_position: str = "top-right"  # Toast notification position
    # Toast visual customization
    toast_font_family: str = "Segoe UI"  # Toast font family
    toast_font_size: int = 10  # Toast font size
    toast_font_bold: bool = False  # Toast font bold style
    toast_text_color: str = "#f8fafc"  # Toast text color
    toast_bg_color: str = "#1f2933"  # Toast background color
    toast_border_color: str = "#334155"  # Toast border color
    toast_success_color: str = "#22c55e"  # Success toast color
    toast_error_color: str = "#ef4444"  # Error toast color
    toast_warning_color: str = "#f59e0b"  # Warning toast color
    toast_info_color: str = "#38bdf8"  # Info toast color
    toast_fade_out: bool = True  # Enable fade out effect when toast closes
    show_context_menu_icons: bool = True  # Show icons in context menus
    windows_notifications: bool = False  # Use Windows native notifications
    apply_settings_immediately: bool = True  # Apply settings immediately without Save button
    maximize_on_open: bool = False  # Maximize window on startup
    disable_tooltips: bool = True  # Disable UI tooltips
    auto_load_metadata: bool = True  # Auto load metadata for album details
    create_album_session_files: bool = True  # Save/load album state in session.txt sidecar files
    guess_album_title_from_track_metadata: bool = True  # Guess album title from track album metadata
    guess_release_date_from_track_metadata: bool = True  # Guess release date from track date metadata
    use_folder_name_when_album_missing: bool = True  # Use folder name when album tag is missing
    use_album_artist_in_album_details: bool = True  # Use Album Artist metadata for Artist in Album details
    smart_randomize_on_album_load: bool = False  # Smart-randomize tracks after loading an album
    auto_guess_case_on_album_load: bool = False  # Apply Guess Case to track titles after loading an album
    always_auto_scale_cover: bool = True  # Start with cover auto-scaling enabled
    cover_scaling_method: str = "Lanczos"  # Preferred cover art scaling method
    description_auto_fill_mode: str = "Off"  # Auto-fill album description behavior
    description_auto_fill_on_upload: bool = True  # Create auto-description when upload starts
    extract_track_cover_if_missing: bool = True  # Extract embedded cover art when no cover file is found
    clear_progress_on_album_change: bool = True  # Clear upload progress rows after selecting another album
    auto_tag_year: bool = False  # Auto add year to tags from metadata
    auto_tag_genre: bool = False  # Auto add genre to tags from metadata
    auto_tag_artist: bool = False  # Auto add artist to tags from metadata
    auto_tag_album: bool = False  # Auto add album to tags from metadata
    auto_tag_comment: bool = False  # Auto add comment to tags from metadata
    auto_tag_track_title: bool = False  # Auto add track title to tags from metadata
    auto_tag_album_artist: bool = False  # Auto add album artist to tags from metadata
    auto_tag_composer: bool = False  # Auto add composer to tags from metadata
    auto_tag_track_number: bool = False  # Auto add track number to tags from metadata
    auto_tag_duration: bool = False  # Auto add track duration to tags from metadata
    auto_tag_bitrate: bool = False  # Auto add bitrate to tags from metadata
    auto_tag_release_type: bool = False  # Auto add release type (Single/EP/Album) to tags
    # Log visual customization
    log_font_family: str = "Segoe UI"  # Log font family
    log_font_size: int = 9  # Log font size
    log_font_bold: bool = False  # Log font bold style
    log_text_color: str = "#ffffff"  # Log text color
    log_bg_color: str = "#1e1e1e"  # Log background color
    log_info_color: str = "#00ff00"  # INFO log color
    log_warning_color: str = "#ffff00"  # WARNING log color
    log_error_color: str = "#ff0000"  # ERROR log color
    log_debug_color: str = "#888888"  # DEBUG log color
    log_show_timestamps: bool = True  # Show timestamps in logs
    log_timestamp_format: str = "HH:MM:SS"  # Timestamp format
    log_show_levels: bool = True  # Show log level labels
    log_word_wrap: bool = True  # Enable word wrap
    log_line_spacing: int = 1  # Line spacing
    log_auto_scroll: bool = True  # Auto-scroll to bottom on new logs
    log_max_lines: int = 1000  # Maximum lines to keep (0 for unlimited)
    log_to_file: bool = True  # Save diagnostic logs to bau_<date>.log
    log_file_level: str = "INFO"  # Minimum level for persistent diagnostic logs
    # Track table column visibility
    show_track_no: bool = True
    show_artist: bool = True
    show_track_name: bool = True
    show_comment: bool = True
    show_length: bool = True
    show_extension: bool = True
    show_price: bool = True
    show_nyp: bool = True
    # Additional columns (disabled by default)
    show_year: bool = False
    show_genre: bool = False
    show_bitrate: bool = False
    show_file_size: bool = False
    show_sample_rate: bool = False
    show_channels: bool = False
    show_bit_depth: bool = False
    show_album_metadata: bool = False
    show_album_artist_metadata: bool = False
    show_composer: bool = False
    show_isrc: bool = False
    auto_fit_columns: bool = True  # Automatically fit preview table columns after updates
    locked_track_highlight_color: str = "#fff4ce"  # Track table row highlight for locked tracks
    # Context menu settings
    context_menu_remove_dividers: bool = False  # Hide separator dividers in track context menu
    context_menu_play: bool = True  # Show Play option in track context menu
    context_menu_remove_track: bool = True  # Show Remove Track option
    context_menu_move_up: bool = True  # Show Move Up option
    context_menu_move_down: bool = True  # Show Move Down option
    context_menu_move_to_top: bool = True  # Show Move to Top option
    context_menu_move_to_bottom: bool = True  # Show Move to Bottom option
    context_menu_extract_cover_art: bool = True  # Show Extract Cover Art option
    context_menu_open_file: bool = True  # Show Open File Location option
    context_menu_replace_file: bool = True  # Show Replace File option
    context_menu_copy_metadata: bool = True  # Show Copy Metadata option
    context_menu_paste_metadata: bool = True  # Show Paste Metadata option
    context_menu_revert_to_original: bool = True  # Show Revert to Original option
    context_menu_extract_tracklist: bool = True  # Show Extract Tracklist option
    context_menu_open_session: bool = True  # Show Open session.txt option
    context_menu_set_track_cover_as_album_cover: bool = True  # Show Set Track Cover as Album Cover option
    context_menu_undo: bool = True  # Show Undo option
    context_menu_redo: bool = True  # Show Redo option
    context_menu_extract_track_info: bool = True  # Show Extract Track Information option
    context_menu_lock_unlock: bool = True  # Show Lock/Unlock option
    context_menu_randomize: bool = True  # Show Randomize option
    context_menu_smart_randomize: bool = True  # Show Smart Randomize option
    context_menu_sort_by: bool = True  # Show Sort By submenu
    sort_by_file_size: bool = True  # Show Sort by file size
    sort_by_length: bool = True  # Show Sort by length
    sort_by_alphabetically: bool = True  # Show Sort alphabetically
    sort_by_artist: bool = True  # Show Sort by artist
    sort_by_track_number: bool = True  # Show Sort by track number
    sort_by_metadata_track_number: bool = True  # Show Sort by embedded track number
    sort_by_extension: bool = True  # Show Sort by extension
    sort_by_price: bool = True  # Show Sort by price
    sort_by_year: bool = True  # Show Sort by year
    sort_by_genre: bool = True  # Show Sort by genre
    sort_by_bitrate: bool = True  # Show Sort by bitrate
    sort_by_sample_rate: bool = True  # Show Sort by sample rate
    sort_by_channels: bool = True  # Show Sort by channels
    sort_by_bit_depth: bool = True  # Show Sort by bit depth
    sort_by_album: bool = True  # Show Sort by album metadata
    sort_by_album_artist: bool = True  # Show Sort by album artist metadata
    sort_by_composer: bool = True  # Show Sort by composer
    sort_by_isrc: bool = True  # Show Sort by ISRC
    context_menu_clear_metadata: bool = True  # Show Clear Metadata option
    context_menu_clear_all_metadata: bool = True  # Show Clear All Metadata option
    context_menu_clear_all: bool = True  # Show Clear All Tracks option
    # Upload settings
    auto_start_upload: bool = False  # Auto-start upload after adding files
    confirm_before_upload: bool = False  # Confirm before starting upload
    max_concurrent_uploads: int = 1  # Max concurrent uploads
    upload_timeout: int = 300  # Upload timeout in seconds
    retry_failed_uploads: bool = False  # Retry failed uploads
    retry_attempts: int = 3  # Number of retry attempts
    retry_delay: int = 5  # Delay between retries in seconds
    open_logs_on_upload: bool = False  # Switch to Logs tab when an upload starts
    open_album_page_after_upload: bool = True  # Open the uploaded Bandcamp album page
    copy_album_url_after_upload: bool = False  # Copy uploaded album URL to clipboard
    detailed_progress_track_info: bool = False  # Show detailed track info in upload progress
    show_progress_timing_details: bool = False  # Show elapsed/ETA suffixes in per-track progress
    # Notification triggers
    notify_on_upload_success: bool = True  # Notify when album upload succeeds
    notify_on_upload_error: bool = True  # Notify when album upload fails
    notify_on_track_error: bool = True  # Notify when individual track upload fails
    notify_on_conversion_complete: bool = False  # Notify when audio conversion completes
    notify_on_metadata_load: bool = False  # Notify when metadata is loaded
    notify_on_file_add: bool = False  # Notify when files are added to album
    notify_on_track_add: bool = False  # Notify when tracks are added
    notify_on_track_remove: bool = False  # Notify when tracks are removed
    notify_on_cover_load: bool = False  # Notify when cover art is loaded
    notify_on_album_save: bool = False  # Notify when album is saved
    notify_on_settings_save: bool = False  # Notify when settings are saved
    notify_on_artists_load: bool = False  # Notify when artists are loaded
    notify_on_template_save: bool = False  # Notify when template is saved


def get_app_data_dir() -> Path:
    return Path.home() / "Documents" / "Bandcamp Auto Uploader"


config_file = get_app_data_dir() / "config.json"


def get_legacy_config_file_path() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "7x11x13" / "bandcamp-auto-uploader" / "config.json"
    return Path.home() / "AppData" / "Local" / "7x11x13" / "bandcamp-auto-uploader" / "config.json"


def get_config_file_path() -> Path:
    return config_file


def load_config():
    source_file = config_file
    if not source_file.exists():
        legacy_file = get_legacy_config_file_path()
        if legacy_file.exists():
            source_file = legacy_file
        else:
            return None
    with open(source_file, "r") as f:
        data = json.load(f)
        # Filter out keys that are not in the current Config dataclass
        valid_fields = {field.name for field in dataclasses.fields(Config)}
        filtered_data = {k: v for k, v in data.items() if k in valid_fields}
        config = Config(**filtered_data)
        if source_file != config_file:
            save_config(config)
        return config


def save_config(config: Config):
    config_file.parent.mkdir(parents=True, exist_ok=True)
    with open(config_file, "w") as f:
        json.dump(dataclasses.asdict(config), f, indent=4)


def init_config():
    def price_validator(price):
        try:
            price = float(price)
            if price >= 0:
                return True
        except Exception:
            return False

    config = Config()
    config.album_price = inquirer.text(
        message="Default album price:",
        filter=lambda price: round(float(price), 2),
        validate=price_validator,
        invalid_message="Price must be a number >= 0",
    ).execute()
    config.track_price = inquirer.text(
        message="Default track price:",
        filter=lambda price: round(float(price), 2),
        validate=price_validator,
        invalid_message="Price must be a number >= 0",
    ).execute()
    config.name_your_price = inquirer.select(
        message="Default name-your-price?",
        filter=lambda choice: choice == "Yes",
        choices=["Yes", "No"],
    ).execute()
    config.track_streaming = inquirer.select(
        message="Default allow streaming?",
        filter=lambda choice: choice == "Yes",
        choices=["Yes", "No"],
    ).execute()
    config.track_downloading = inquirer.select(
        message="Default allow track downloading?",
        filter=lambda choice: choice == "Yes",
        choices=["Yes", "No"],
    ).execute()
    return config
