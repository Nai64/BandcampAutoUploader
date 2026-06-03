"""Experimental PySide6 shell for gradually migrating the desktop GUI."""

from __future__ import annotations

import http.cookiejar
import json
import logging
import os
import queue
import re
import sys
import threading
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin

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

from bandcamp_auto_uploader import __version__
from bandcamp_auto_uploader.bandcamp_http_adapter import BandcampHTTPAdapter
from bandcamp_auto_uploader.config import Config, load_config, save_config
from bandcamp_auto_uploader.gui.common import (
    DESCRIPTION_AUTO_FILL_MODES,
    QueueHandler,
)
from bandcamp_auto_uploader.qt_gui.formatting import (
    format_price,
    normalize_price,
    normalize_release_date,
)
from bandcamp_auto_uploader.upload import (
    Album,
    BandcampAlbumData,
    CoverArt,
    Track,
    UploadCancelled,
)

logger = logging.getLogger("bandcamp-auto-uploader")

try:
    from PySide6.QtCore import Qt, QDate, QTimer, QUrl, Signal
    from PySide6.QtGui import (
        QAction, QColor, QDesktopServices, QFont, QIcon, QPixmap, QTextCursor,
    )
    from PySide6.QtWidgets import (
        QApplication,
        QAbstractItemView,
        QCheckBox,
        QColorDialog,
        QComboBox,
        QDateEdit,
        QDialog,
        QDialogButtonBox,
        QDockWidget,
        QFileDialog,
        QFormLayout,
        QFrame,
        QGridLayout,
        QGroupBox,
        QHBoxLayout,
        QHeaderView,
        QLabel,
        QLineEdit,
        QListWidget,
        QListWidgetItem,
        QMainWindow,
        QMenu,
        QMessageBox,
        QPlainTextEdit,
        QProgressBar,
        QPushButton,
        QScrollArea,
        QSpinBox,
        QSplitter,
        QStackedWidget,
        QTableWidget,
        QTableWidgetItem,
        QTextEdit,
        QTreeWidget,
        QTreeWidgetItem,
        QVBoxLayout,
        QWidget,
    )
except ImportError as exc:  # pragma: no cover - depends on optional Qt install
    raise SystemExit(
        "PySide6 is not installed. Install it to try the migration preview:\n"
        "  python -m pip install PySide6"
    ) from exc


TRACK_COLUMNS = (
    "No.",
    "Artist",
    "Track Name",
    "Comment",
    "Length",
    "Format",
    "Price",
    "NYP",
    "File Path",
)

COL_NO = 0
COL_ARTIST = 1
COL_TITLE = 2
COL_COMMENT = 3
COL_LENGTH = 4
COL_FORMAT = 5
COL_PRICE = 6
COL_NYP = 7
COL_PATH = 8
EDITABLE_COLUMNS = {COL_ARTIST, COL_TITLE, COL_COMMENT, COL_PRICE, COL_NYP}
LICENSE_OPTIONS = (
    "All Rights Reserved",
    "CC Attribution",
    "CC Attribution-ShareAlike",
    "CC Attribution-NoDerivatives",
    "CC Attribution-NonCommercial",
    "CC Attribution-NonCommercial-ShareAlike",
    "CC Attribution-NonCommercial-NoDerivatives",
    "Public Domain",
)
LICENSE_MAP = {
    "All Rights Reserved": "1",
    "CC Attribution": "2",
    "CC Attribution-ShareAlike": "3",
    "CC Attribution-NoDerivatives": "4",
    "CC Attribution-NonCommercial": "5",
    "CC Attribution-NonCommercial-ShareAlike": "6",
    "CC Attribution-NonCommercial-NoDerivatives": "7",
    "Public Domain": "8",
}
COVER_NAMES = (
    "cover.jpg",
    "cover.png",
    "cover.jpeg",
    "cover.gif",
    "folder.jpg",
    "folder.png",
    "folder.jpeg",
    "front.jpg",
    "front.png",
    "front.jpeg",
    "album.jpg",
    "album.png",
    "album.jpeg",
    "artwork.jpg",
    "artwork.png",
    "artwork.jpeg",
)
COVER_SUFFIXES = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
AUDIO_FILTER = "Audio files (*.wav *.flac *.aiff *.aif *.mp3 *.ogg *.opus *.m4a *.aac *.mod *.xm);;All files (*.*)"
FILENAME_PATTERNS = (
    (r"^(\d+)\s*[.\-)_\s]+\s*(.+?)\s*-\s*(.+)", 1, 2, 3),
    (r"^Track\s*(\d+)\s*[.\-)_\s]+\s*(.+?)\s*-\s*(.+)", 1, 2, 3),
    (r"^(\d+)\s*[.\-)_\s]+\s*(.+)", 1, None, 2),
    (r"^Track\s*(\d+)\s*[.\-)_\s]+\s*(.+)", 1, None, 2),
    (r"^(\d+)\s*(.+)", 1, None, 2),
    (r"^(.+?)\s*-\s*(.+)", None, 1, 2),
)


class QtUploaderWindow(QMainWindow):
    """Qt shell that previews and edits album tracks using the existing model."""

    progress_signal = Signal(str, object)

    def __init__(self, config: Config):
        super().__init__()
        self.config = config
        self.current_album: Album | None = None
        self._loading_table = False
        self._loading_details = False
        self._loading_album_details = False
        self.cover_path: Path | None = None
        self.track_editor_data: dict[str, dict] = {}
        self._track_details_path: str | None = None
        self.urls: dict[str, http.cookiejar.CookieJar] = {}
        self.selected_artist_url: str | None = None
        self.session: requests.Session | None = None
        self._album_session_loading = False
        self._album_session_autosave_ready = False
        self._album_session_save_timer = None
        self._album_path_for_session: Path | None = None
        self.log_queue: queue.Queue = queue.Queue()
        self.toast_queue: queue.Queue = queue.Queue()
        self.upload_thread: threading.Thread | None = None
        self.upload_cancel_event = threading.Event()

        self.progress_signal.connect(self.handle_upload_progress_event)

        self.setWindowTitle(f"Bandcamp Auto Uploader Qt Preview {__version__}")
        self.resize(1060, 660)
        self.setMinimumSize(900, 560)
        self.setAcceptDrops(True)
        self._build_ui()
        from PySide6.QtCore import QTimer
        QTimer.singleShot(200, self.load_artists)

    def _build_ui(self):
        open_action = QAction("Open Album Folder", self)
        open_action.triggered.connect(self.browse_album)
        self.menuBar().addMenu("File").addAction(open_action)

        central = QWidget()
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(8, 8, 8, 8)
        root_layout.setSpacing(6)

        root_layout.addWidget(self._build_top_bar())

        splitter = QSplitter(Qt.Horizontal)
        root_layout.addWidget(splitter, 1)

        splitter.addWidget(self._build_details_panel())
        splitter.addWidget(self._build_album_preview_panel())
        splitter.addWidget(self._build_right_panel())
        splitter.setSizes([285, 595, 240])

        root_layout.addWidget(self._build_bottom_bar())

        self.setCentralWidget(central)

        self._build_log_dock()
        self._build_view_menu()
        self.setup_logging()
        self._start_log_monitor()
        self._start_toast_monitor()

        self.statusBar().showMessage("Qt migration preview ready")

    def _build_top_bar(self):
        top_bar = QWidget()
        top_bar.setObjectName("topBar")
        layout = QHBoxLayout(top_bar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        artist_group = QGroupBox("Artist / Band")
        artist_layout = QVBoxLayout(artist_group)
        artist_layout.setContentsMargins(6, 10, 6, 6)
        artist_layout.setSpacing(4)
        self.artist_combo = QComboBox()
        self.artist_combo.setEditable(False)
        self.artist_combo.addItem("No artist selected")
        self.artist_combo.currentTextChanged.connect(self.on_artist_selected)
        artist_layout.addWidget(self.artist_combo)
        artist_buttons = QHBoxLayout()

        self.load_cookies_button = QPushButton("Load Cookies")
        self.load_cookies_button.clicked.connect(self.load_cookies_file)
        self.refresh_artists_button = QPushButton("Refresh Artists")
        self.refresh_artists_button.clicked.connect(self.load_artists)
        artist_buttons.addWidget(self.refresh_artists_button)
        artist_buttons.addWidget(self.load_cookies_button)
        artist_layout.addLayout(artist_buttons)
        layout.addWidget(artist_group, 1)

        album_group = QGroupBox("Album Folder")
        album_layout = QVBoxLayout(album_group)
        album_layout.setContentsMargins(6, 10, 6, 6)
        album_layout.setSpacing(4)

        self.album_path_edit = QLineEdit()
        self.album_path_edit.setPlaceholderText("Album directory")
        album_layout.addWidget(self.album_path_edit)

        album_buttons = QHBoxLayout()
        browse_button = QPushButton("Browse")
        browse_button.clicked.connect(self.browse_album)
        album_buttons.addWidget(browse_button)
        open_folder_button = QPushButton("Open Folder")
        open_folder_button.clicked.connect(self.open_album_folder)
        album_buttons.addWidget(open_folder_button)
        preview_button = QPushButton("Reload Album")
        preview_button.clicked.connect(self.preview_album)
        album_buttons.addWidget(preview_button)
        album_layout.addLayout(album_buttons)
        layout.addWidget(album_group, 1)
        return top_bar

    def _build_bottom_bar(self):
        bottom_bar = QWidget()
        bottom_bar.setObjectName("bottomBar")
        layout = QHBoxLayout(bottom_bar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        preferences_button = QPushButton("Preferences")
        preferences_button.clicked.connect(self.show_preferences_dialog)
        layout.addWidget(preferences_button)

        logs_button = QPushButton("Logs")
        logs_button.clicked.connect(self._toggle_log_dock)
        layout.addWidget(logs_button)

        self.upload_button = QPushButton("UPLOAD ALBUM")
        self.upload_button.setObjectName("primaryButton")
        self.upload_button.setEnabled(False)
        self.upload_button.clicked.connect(self.start_upload)
        layout.addWidget(self.upload_button, 1)

        self.cancel_upload_button = QPushButton("Cancel Upload")
        self.cancel_upload_button.setEnabled(False)
        self.cancel_upload_button.clicked.connect(self.cancel_upload)
        layout.addWidget(self.cancel_upload_button, 1)
        return bottom_bar

    def _build_details_panel(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        panel = QFrame()
        panel.setObjectName("detailsPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(3)

        title = QLabel("Album / Track Details")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)

        self.album_details_group = self._build_album_details()
        self.track_details_group = self._build_track_details()

        layout.addWidget(self.album_details_group)
        layout.addWidget(self.track_details_group)
        layout.addStretch(1)

        self.track_details_group.hide()

        scroll.setWidget(panel)
        return scroll

    def _build_album_details(self):
        group = QGroupBox("Album Details")
        outer_layout = QVBoxLayout(group)
        outer_layout.setContentsMargins(4, 8, 4, 4)
        outer_layout.setSpacing(2)

        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        form.setHorizontalSpacing(4)
        form.setVerticalSpacing(2)

        name_row = QWidget()
        name_layout = QHBoxLayout(name_row)
        name_layout.setContentsMargins(0, 0, 0, 0)
        name_layout.setSpacing(3)
        self.album_name_edit = QLineEdit()
        self.album_name_edit.setPlaceholderText("Album name")
        name_layout.addWidget(self.album_name_edit, 1)
        album_name_auto = QPushButton("Auto")
        album_name_auto.setFixedWidth(40)
        album_name_auto.clicked.connect(self.auto_fill_album_name)
        name_layout.addWidget(album_name_auto)

        artist_row = QWidget()
        artist_layout = QHBoxLayout(artist_row)
        artist_layout.setContentsMargins(0, 0, 0, 0)
        artist_layout.setSpacing(3)
        self.artist_edit = QLineEdit()
        self.artist_edit.setPlaceholderText("Artist")
        artist_layout.addWidget(self.artist_edit, 1)
        artist_auto = QPushButton("Auto")
        artist_auto.setFixedWidth(40)
        artist_auto.clicked.connect(self.auto_fill_artist_name)
        artist_layout.addWidget(artist_auto)

        release_row = QWidget()
        release_layout = QHBoxLayout(release_row)
        release_layout.setContentsMargins(0, 0, 0, 0)
        release_layout.setSpacing(3)
        self.release_date_edit = QLineEdit()
        self.release_date_edit.setPlaceholderText("YYYY-MM-DD")
        release_layout.addWidget(self.release_date_edit, 1)
        calendar_btn = QPushButton("Edit")
        calendar_btn.setFixedWidth(40)
        calendar_btn.clicked.connect(self.show_album_calendar)
        release_layout.addWidget(calendar_btn)

        self.album_price_edit = QLineEdit("$0")
        self.album_nyp_check = QCheckBox("Name Your Price")
        self.album_nyp_check.setChecked(True)
        self.album_public_check = QCheckBox("Public")
        self.album_public_check.setChecked(True)
        self.require_email_check = QCheckBox("Require email")
        self.pro_check = QCheckBox("Registered with collection society")
        self.tags_edit = QLineEdit()
        self.tags_edit.setPlaceholderText("tags, comma separated")
        self.license_combo = QComboBox()
        self.license_combo.addItems(LICENSE_OPTIONS)
        self.download_desc_edit = QLineEdit()
        self.release_message_edit = QLineEdit()
        self.record_label_edit = QLineEdit()
        self.catalog_number_edit = QLineEdit()
        self.upc_edit = QLineEdit()
        self.subscriber_message_edit = QLineEdit()
        self.composer_edit = QLineEdit()
        self.publisher_edit = QLineEdit()

        form.addRow("Album Name", name_row)
        form.addRow("Artist", artist_row)
        form.addRow("Release Date", release_row)
        form.addRow("Price", self.album_price_edit)
        form.addRow("Tags", self.tags_edit)
        form.addRow("License", self.license_combo)
        form.addRow("Download Desc", self.download_desc_edit)
        form.addRow("Release Msg", self.release_message_edit)
        form.addRow("Record Label", self.record_label_edit)
        form.addRow("Catalog #", self.catalog_number_edit)
        form.addRow("UPC/EAN", self.upc_edit)
        form.addRow("Subscriber Msg", self.subscriber_message_edit)
        form.addRow("Composer", self.composer_edit)
        form.addRow("Publisher", self.publisher_edit)
        form.addRow("", self.album_nyp_check)
        form.addRow("", self.album_public_check)
        form.addRow("", self.require_email_check)
        form.addRow("", self.pro_check)
        outer_layout.addLayout(form)

        self.description_edit = QPlainTextEdit()
        self.description_edit.setPlaceholderText("Description")
        self.description_edit.setMaximumHeight(62)
        outer_layout.addWidget(QLabel("Description"))
        outer_layout.addWidget(self.description_edit)

        self.credits_edit = QPlainTextEdit()
        self.credits_edit.setPlaceholderText("Credits")
        self.credits_edit.setMaximumHeight(54)
        outer_layout.addWidget(QLabel("Credits"))
        outer_layout.addWidget(self.credits_edit)

        self.album_price_edit.editingFinished.connect(
            lambda: self.sanitize_price_edit(self.album_price_edit, "0")
        )
        self.release_date_edit.editingFinished.connect(
            lambda: self.sanitize_date_edit(self.release_date_edit)
        )
        for widget in (
            self.album_name_edit,
            self.artist_edit,
            self.release_date_edit,
            self.album_price_edit,
            self.tags_edit,
            self.download_desc_edit,
            self.release_message_edit,
            self.record_label_edit,
            self.catalog_number_edit,
            self.upc_edit,
            self.subscriber_message_edit,
            self.composer_edit,
            self.publisher_edit,
        ):
            widget.editingFinished.connect(self.apply_album_details_to_model)
            widget.editingFinished.connect(lambda: self.queue_album_session_save())
        self.description_edit.textChanged.connect(self.apply_album_details_to_model)
        self.description_edit.textChanged.connect(lambda: self.queue_album_session_save())
        self.credits_edit.textChanged.connect(self.apply_album_details_to_model)
        self.credits_edit.textChanged.connect(lambda: self.queue_album_session_save())
        self.license_combo.currentTextChanged.connect(
            lambda _text: self.apply_album_details_to_model()
        )
        self.license_combo.currentTextChanged.connect(
            lambda _text: self.queue_album_session_save()
        )
        for checkbox in (
            self.album_nyp_check,
            self.album_public_check,
            self.require_email_check,
            self.pro_check,
        ):
            checkbox.toggled.connect(lambda _checked: self.apply_album_details_to_model())
            checkbox.toggled.connect(lambda _checked: self.queue_album_session_save())

        self._album_session_autosave_ready = True
        return group

    def _build_track_details(self):
        group = QGroupBox("Track Details")
        outer_layout = QVBoxLayout(group)
        outer_layout.setContentsMargins(4, 8, 4, 4)
        outer_layout.setSpacing(2)

        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        form.setHorizontalSpacing(4)
        form.setVerticalSpacing(2)

        td_name_row = QWidget()
        td_name_layout = QHBoxLayout(td_name_row)
        td_name_layout.setContentsMargins(0, 0, 0, 0)
        td_name_layout.setSpacing(3)
        self.track_name_edit = QLineEdit()
        td_name_layout.addWidget(self.track_name_edit, 1)
        td_name_auto = QPushButton("Auto")
        td_name_auto.setFixedWidth(40)
        td_name_auto.clicked.connect(self.td_auto_fill_name)
        td_name_layout.addWidget(td_name_auto)

        td_artist_row = QWidget()
        td_artist_layout = QHBoxLayout(td_artist_row)
        td_artist_layout.setContentsMargins(0, 0, 0, 0)
        td_artist_layout.setSpacing(3)
        self.track_artist_edit = QLineEdit()
        td_artist_layout.addWidget(self.track_artist_edit, 1)
        td_artist_auto = QPushButton("Auto")
        td_artist_auto.setFixedWidth(40)
        td_artist_auto.clicked.connect(self.td_auto_fill_artist)
        td_artist_layout.addWidget(td_artist_auto)

        td_release_row = QWidget()
        td_release_layout = QHBoxLayout(td_release_row)
        td_release_layout.setContentsMargins(0, 0, 0, 0)
        td_release_layout.setSpacing(3)
        self.track_release_date_edit = QLineEdit()
        self.track_release_date_edit.setPlaceholderText("YYYY-MM-DD")
        td_release_layout.addWidget(self.track_release_date_edit, 1)
        td_cal_btn = QPushButton("Edit")
        td_cal_btn.setFixedWidth(40)
        td_cal_btn.clicked.connect(self.show_track_calendar)
        td_release_layout.addWidget(td_cal_btn)

        self.track_price_edit = QLineEdit()
        self.track_nyp_check = QCheckBox("Name Your Price")
        self.track_nyp_check.setChecked(True)
        self.track_tags_edit = QLineEdit()
        self.track_tags_edit.setPlaceholderText("tags, comma separated")
        self.track_license_combo = QComboBox()
        self.track_license_combo.addItems(LICENSE_OPTIONS)
        self.track_download_desc_edit = QLineEdit()
        self.track_isrc_edit = QLineEdit()
        self.track_iswc_edit = QLineEdit()
        self.track_video_id_edit = QLineEdit()
        self.track_video_caption_edit = QLineEdit()
        self.track_featured_check = QCheckBox("Featured")
        self.track_streaming_check = QCheckBox("Streaming")
        self.track_streaming_check.setChecked(True)
        self.track_enable_dl_check = QCheckBox("Download")
        self.track_enable_dl_check.setChecked(True)
        self.track_bonus_check = QCheckBox("Bonus track")

        form.addRow("Track Name", td_name_row)
        form.addRow("Artist", td_artist_row)
        form.addRow("Release Date", td_release_row)
        price_row = QWidget()
        price_layout = QHBoxLayout(price_row)
        price_layout.setContentsMargins(0, 0, 0, 0)
        price_layout.setSpacing(6)
        price_layout.addWidget(self.track_price_edit, 1)
        price_layout.addWidget(self.track_nyp_check)
        form.addRow("Track Price", price_row)
        tags_row = QWidget()
        tags_layout = QHBoxLayout(tags_row)
        tags_layout.setContentsMargins(0, 0, 0, 0)
        tags_layout.setSpacing(3)
        tags_layout.addWidget(self.track_tags_edit, 1)
        td_tags_edit_btn = QPushButton("Edit")
        td_tags_edit_btn.setFixedWidth(40)
        td_tags_edit_btn.clicked.connect(self.open_td_tag_edit_dialog)
        tags_layout.addWidget(td_tags_edit_btn)
        form.addRow("Tags", tags_row)
        form.addRow("License", self.track_license_combo)
        form.addRow("Download Desc", self.track_download_desc_edit)
        form.addRow("ISRC", self.track_isrc_edit)
        form.addRow("ISWC", self.track_iswc_edit)
        form.addRow("Video ID", self.track_video_id_edit)
        form.addRow("Video Caption", self.track_video_caption_edit)
        form.addRow("", self.track_featured_check)
        form.addRow("", self.track_streaming_check)
        form.addRow("", self.track_enable_dl_check)
        form.addRow("", self.track_bonus_check)
        outer_layout.addLayout(form)

        self.td_desc_edit = QPlainTextEdit()
        self.td_desc_edit.setPlaceholderText("Description")
        self.td_desc_edit.setMaximumHeight(62)
        outer_layout.addWidget(QLabel("Description"))
        outer_layout.addWidget(self.td_desc_edit)

        self.td_lyrics_edit = QPlainTextEdit()
        self.td_lyrics_edit.setPlaceholderText("Lyrics")
        self.td_lyrics_edit.setMaximumHeight(62)
        outer_layout.addWidget(QLabel("Lyrics"))
        outer_layout.addWidget(self.td_lyrics_edit)

        self.td_credits_edit = QPlainTextEdit()
        self.td_credits_edit.setPlaceholderText("Credits")
        self.td_credits_edit.setMaximumHeight(54)
        outer_layout.addWidget(QLabel("Credits"))
        outer_layout.addWidget(self.td_credits_edit)

        for edit in (
            self.track_name_edit,
            self.track_artist_edit,
            self.track_price_edit,
            self.track_release_date_edit,
            self.track_isrc_edit,
            self.track_iswc_edit,
            self.track_download_desc_edit,
            self.track_video_id_edit,
            self.track_video_caption_edit,
            self.track_tags_edit,
        ):
            edit.editingFinished.connect(self.save_selected_track_details)
        for edit in (self.td_desc_edit, self.td_lyrics_edit, self.td_credits_edit):
            edit.textChanged.connect(self.save_selected_track_details)
        for checkbox in (
            self.track_nyp_check,
            self.track_featured_check,
            self.track_streaming_check,
            self.track_enable_dl_check,
            self.track_bonus_check,
        ):
            checkbox.toggled.connect(lambda _checked: self.save_selected_track_details())
        self.track_license_combo.currentTextChanged.connect(
            lambda _text: self.save_selected_track_details()
        )
        self.track_price_edit.editingFinished.connect(
            lambda: self.sanitize_price_edit(self.track_price_edit, "")
        )
        self.track_release_date_edit.editingFinished.connect(
            lambda: self.sanitize_date_edit(self.track_release_date_edit)
        )
        return group

    def _build_album_preview_panel(self):
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        header_row = QHBoxLayout()
        header_row.setSpacing(6)
        title = QLabel("Album Preview")
        title.setObjectName("sectionTitle")
        header_row.addWidget(title)
        header_row.addStretch(1)

        for label, callback in (
            ("Move Up", self.move_selected_track_up),
            ("Move Down", self.move_selected_track_down),
            ("Remove", self.remove_selected_track),
        ):
            button = QPushButton(label)
            button.clicked.connect(callback)
            header_row.addWidget(button)
        layout.addLayout(header_row)

        layout.addWidget(self._build_preview_controls())

        self.track_table = QTableWidget(0, len(TRACK_COLUMNS))
        self.track_table.setHorizontalHeaderLabels(TRACK_COLUMNS)
        self.track_table.setShowGrid(False)
        self.track_table.setAlternatingRowColors(True)
        self.track_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.track_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.track_table.setWordWrap(False)
        self.track_table.verticalHeader().setDefaultSectionSize(24)
        self.track_table.verticalHeader().setVisible(False)
        self.track_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.track_table.horizontalHeader().setStretchLastSection(True)
        self.track_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.track_table.customContextMenuRequested.connect(self._show_track_context_menu)
        self.track_table.cellChanged.connect(self.on_track_cell_changed)
        self.track_table.itemSelectionChanged.connect(self.on_track_select)
        layout.addWidget(self.track_table, 1)

        return content

    def _build_preview_controls(self):
        controls = QWidget()
        layout = QHBoxLayout(controls)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.ignore_artist_check = QCheckBox("Ignore artist")
        self.ignore_artist_check.setChecked(
            bool(getattr(self.config, "ignore_artist_name", False))
        )
        self.ignore_artist_check.toggled.connect(self.on_preview_option_changed)
        layout.addWidget(self.ignore_artist_check)

        self.filename_as_title_check = QCheckBox("Filename as title")
        self.filename_as_title_check.setChecked(
            bool(getattr(self.config, "use_filename_as_title", False))
        )
        self.filename_as_title_check.toggled.connect(self.on_preview_option_changed)
        layout.addWidget(self.filename_as_title_check)

        self.ignore_metadata_check = QCheckBox("Ignore metadata")
        self.ignore_metadata_check.setChecked(
            bool(getattr(self.config, "ignore_all_metadata", False))
        )
        self.ignore_metadata_check.toggled.connect(self.on_preview_option_changed)
        layout.addWidget(self.ignore_metadata_check)

        layout.addStretch(1)

        add_track_button = QPushButton("Add Track")
        add_track_button.clicked.connect(self.add_tracks)
        layout.addWidget(add_track_button)

        extract_button = QPushButton("Extract from Filename")
        extract_button.clicked.connect(self.apply_extract_from_filename)
        layout.addWidget(extract_button)

        guess_case_button = QPushButton("Guess Case")
        guess_case_button.clicked.connect(self.apply_guess_case_to_track_titles)
        layout.addWidget(guess_case_button)
        return controls

    def _build_right_panel(self):
        right_panel = QWidget()
        layout = QVBoxLayout(right_panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        layout.addWidget(self._build_cover_panel())
        layout.addWidget(self._build_progress_panel(), 1)
        return right_panel

    def _build_cover_panel(self):
        group = QGroupBox("Cover Art")
        rl = QHBoxLayout(group); rl.setContentsMargins(0, 0, 0, 0); rl.setSpacing(0)
        self.cover_preview = QLabel("No cover art\n\nClick Browse")
        self.cover_preview.setObjectName("coverPreview")
        self.cover_preview.setAlignment(Qt.AlignCenter)
        self.cover_preview.setFixedSize(156, 156)
        self.cover_preview.setContextMenuPolicy(Qt.CustomContextMenu)
        self.cover_preview.customContextMenuRequested.connect(self._show_cover_context_menu)
        rl.addWidget(self.cover_preview)
        c = QWidget(); cl = QVBoxLayout(c); cl.setContentsMargins(0, 0, 0, 0); cl.setSpacing(0)
        self.cover_path_edit = QLineEdit()
        self.cover_path_edit.setPlaceholderText("Cover image path")
        self.cover_path_edit.editingFinished.connect(self.resolve_cover_path_edit)
        cl.addWidget(self.cover_path_edit)
        bf = QWidget(); bg = QGridLayout(bf); bg.setContentsMargins(0, 0, 0, 0); bg.setSpacing(0)
        for i, (t, m) in enumerate([("Browse", self.browse_cover), ("View", self.view_cover_art),
                                     ("Library", self.manage_cover_art_library), ("Detect", self.detect_cover_from_tracks)]):
            b = QPushButton(t); b.clicked.connect(m)
            bg.addWidget(b, i // 2, i % 2)
        cl.addWidget(bf)
        self.scale_cover_check = QCheckBox("Auto-scale to Bandcamp specs")
        self.scale_cover_check.setChecked(getattr(self.config, "always_auto_scale_cover", True))
        self.scale_cover_check.toggled.connect(self._on_scale_cover_changed)
        cl.addWidget(self.scale_cover_check)
        sr = QHBoxLayout(); sr.setSpacing(0); sr.setContentsMargins(0, 0, 0, 0)
        sr.addWidget(QLabel("Size:"))
        self.scale_size_combo = QComboBox()
        self.scale_size_combo.addItems(["1400x1400", "2000x2000", "3000x3000"])
        self.scale_size_combo.setCurrentText("1400x1400"); sr.addWidget(self.scale_size_combo)
        sr.addWidget(QLabel("Fit:"))
        self.cover_fit_mode_combo = QComboBox()
        self.cover_fit_mode_combo.addItems(["Crop (fill)", "Fit (contain)", "Stretch"])
        self.cover_fit_mode_combo.setCurrentText(getattr(self.config, "cover_fit_mode", "Crop (fill)"))
        self.cover_fit_mode_combo.currentTextChanged.connect(self._on_fit_mode_changed)
        sr.addWidget(self.cover_fit_mode_combo)
        cl.addLayout(sr)
        rl.addWidget(c, 1)
        return group

    def _build_progress_panel(self):
        progress_group = QGroupBox("Progress")
        layout = QVBoxLayout(progress_group)
        layout.setContentsMargins(6, 10, 6, 6)
        layout.setSpacing(4)
        self.progress_rows: list[tuple[QLabel, QLabel, QProgressBar]] = []
        self.progress_placeholder = QLabel("No upload in progress")
        self.progress_placeholder.setObjectName("mutedLabel")
        self.progress_placeholder.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.progress_placeholder)
        self.progress_list = QWidget()
        self.progress_list_layout = QVBoxLayout(self.progress_list)
        self.progress_list_layout.setContentsMargins(0, 0, 0, 0)
        self.progress_list_layout.setSpacing(6)
        layout.addWidget(self.progress_list)
        layout.addStretch(1)
        return progress_group

    def on_track_select(self):
        self._save_current_track_details()
        row = self.selected_row()
        if row >= 0:
            self.album_details_group.hide()
            self.track_details_group.show()
            self._load_track_details_for_row(row)
        else:
            self.track_details_group.hide()
            self.album_details_group.show()
            self._track_details_path = None

    def _load_track_details_for_row(self, row: int):
        self._loading_details = True
        try:
            path = self.table_text(row, COL_PATH)
            self._track_details_path = path
            editor = self.track_editor_data.get(path, {})
            track = self.track_for_row(row)
            data = track.track_data if track else None

            self.track_name_edit.setText(
                editor.get("name", self.table_text(row, COL_TITLE))
            )
            self.track_artist_edit.setText(
                editor.get("artist", self.table_text(row, COL_ARTIST))
            )
            self.track_price_edit.setText(
                format_price(editor.get("price", self.table_text(row, COL_PRICE)))
            )
            self.track_nyp_check.setChecked(
                editor.get(
                    "nyp",
                    self.table_text(row, COL_NYP).lower()
                    not in {"0", "false", "no", "n", "off"},
                )
            )
            self.track_release_date_edit.setText(
                editor.get(
                    "release_date",
                    getattr(data, "release_date", "") if data else "",
                )
            )
            self.track_isrc_edit.setText(
                editor.get("isrc", getattr(data, "isrc", "") if data else "")
            )
            self.track_iswc_edit.setText(
                editor.get("iswc", getattr(data, "iswc", "") if data else "")
            )
            self.track_bonus_check.setChecked(
                editor.get(
                    "private",
                    bool(getattr(data, "private", False)) if data else False,
                )
            )
            self.track_download_desc_edit.setText(
                editor.get(
                    "download_desc",
                    getattr(data, "download_desc", "") if data else "",
                )
            )
            self.track_tags_edit.setText(
                editor.get("tags", getattr(data, "tags", "") if data else "")
            )

            license_val = editor.get("license", "")
            if not license_val and data:
                raw = getattr(data, "license_type", "")
                if raw:
                    for name, num in LICENSE_MAP.items():
                        if num == raw:
                            license_val = name
                            break
            idx = self.track_license_combo.findText(license_val)
            self.track_license_combo.setCurrentIndex(idx if idx >= 0 else 0)

            self.track_video_id_edit.setText(
                editor.get("video_id", getattr(data, "video_id", "") if data else "")
            )
            self.track_video_caption_edit.setText(
                editor.get(
                    "video_caption",
                    getattr(data, "video_caption", "") if data else "",
                )
            )
            self.track_featured_check.setChecked(
                editor.get(
                    "featured",
                    bool(getattr(data, "featured", False)) if data else False,
                )
            )
            self.track_streaming_check.setChecked(
                editor.get("streaming")
                if "streaming" in editor
                else bool(getattr(data, "streaming", True)) if data else True
            )
            self.track_enable_dl_check.setChecked(
                editor.get("enable_download")
                if "enable_download" in editor
                else bool(getattr(data, "enable_download", True)) if data else True
            )
            self.td_desc_edit.setPlainText(
                editor.get("description", getattr(data, "about", "") if data else "")
            )
            self.td_lyrics_edit.setPlainText(
                editor.get("lyrics", getattr(data, "lyrics", "") if data else "")
            )
            self.td_credits_edit.setPlainText(
                editor.get("credits", getattr(data, "credits", "") if data else "")
            )
        finally:
            self._loading_details = False

    def _save_current_track_details(self):
        if self._loading_details:
            return
        path = self._track_details_path
        if not path:
            return

        price = normalize_price(self.track_price_edit.text(), default="")
        release_date = normalize_release_date(self.track_release_date_edit.text())
        self.track_price_edit.setText(format_price(price))
        self.track_release_date_edit.setText(release_date)

        editor_data = {
            "name": self.track_name_edit.text().strip(),
            "artist": self.track_artist_edit.text().strip(),
            "price": price,
            "nyp": self.track_nyp_check.isChecked(),
            "release_date": release_date,
            "isrc": self.track_isrc_edit.text().strip(),
            "iswc": self.track_iswc_edit.text().strip(),
            "private": self.track_bonus_check.isChecked(),
            "download_desc": self.track_download_desc_edit.text().strip(),
            "tags": self.track_tags_edit.text().strip(),
            "license": self.track_license_combo.currentText(),
            "video_id": self.track_video_id_edit.text().strip(),
            "video_caption": self.track_video_caption_edit.text().strip(),
            "featured": self.track_featured_check.isChecked(),
            "streaming": self.track_streaming_check.isChecked(),
            "enable_download": self.track_enable_dl_check.isChecked(),
            "description": self.td_desc_edit.toPlainText().strip(),
            "lyrics": self.td_lyrics_edit.toPlainText().strip(),
            "credits": self.td_credits_edit.toPlainText().strip(),
        }

        if editor_data["featured"]:
            for other_path, other_data in self.track_editor_data.items():
                if other_path != path and other_data.get("featured", False):
                    other_data["featured"] = False
                    break

        self.track_editor_data[path] = editor_data

        row = self._row_for_path(path)
        if row is not None:
            self._loading_table = True
            try:
                self.set_table_text(row, COL_TITLE, editor_data["name"])
                self.set_table_text(row, COL_ARTIST, editor_data["artist"])
                self.set_table_text(row, COL_PRICE, format_price(price))
                self.set_table_text(
                    row, COL_NYP, "Yes" if editor_data["nyp"] else "No"
                )
                self.set_table_text(
                    row, COL_COMMENT, editor_data["download_desc"]
                )
            finally:
                self._loading_table = False
        self.sync_table_to_album()

    def _row_for_path(self, path: str) -> int | None:
        for row in range(self.track_table.rowCount()):
            if self.table_text(row, COL_PATH) == path:
                return row
        return None

    def browse_album(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Select Album Folder", self.album_path_edit.text()
        )
        if not folder:
            return
        self.album_path_edit.setText(folder)
        self.preview_album()

    def load_cookies_file(self):
        filename, _selected_filter = QFileDialog.getOpenFileName(
            self,
            "Load Cookies File",
            "",
            "Cookie files (*.txt);;All files (*.*)",
        )
        if not filename:
            return
        self.config.cookies_file = filename
        save_config(self.config)
        self.load_artists()
        self.statusBar().showMessage(f"Cookies file selected: {Path(filename).name}")

    def load_artists(self):
        """Load available artists/bands from cookies in a background thread."""
        self.artist_combo.clear()
        self.artist_combo.addItem("Loading artists...")
        self.artist_combo.setEnabled(False)
        self.refresh_artists_button.setEnabled(False)

        def _load():
            try:
                self.urls = {}
                all_urls: dict[str, http.cookiejar.CookieJar] = {}

                if self.config.cookies_file:
                    urls = self._try_get_owned_bands_from_cookies_file(self.config.cookies_file)
                    if urls:
                        all_urls.update(urls)
                        logger.info(f"Loaded {len(urls)} artist(s) from cookies file")

                browser_urls = self._try_get_owned_bands_from_browsers()
                if browser_urls:
                    all_urls.update(browser_urls)

                if all_urls:
                    self.urls = all_urls
                    self._update_artist_dropdown()
                else:
                    self._show_no_artists_dialog()
            except Exception as e:
                logger.exception(e)
                self._show_no_artists_dialog()
            finally:
                self.artist_combo.setEnabled(True)
                self.refresh_artists_button.setEnabled(True)

        import threading
        threading.Thread(target=_load, daemon=True).start()

    def _try_get_owned_bands_from_cookies_file(
        self, cookies_file: str
    ) -> Optional[dict[str, http.cookiejar.CookieJar]]:
        try:
            cj = http.cookiejar.MozillaCookieJar(cookies_file)
            cj.load()
            bands = self._get_owned_bands(cj)
            return {url: cj for url in bands} if bands else None
        except Exception as e:
            logger.error(f"Failed to load cookies file: {e}")
            return None

    def _try_get_owned_bands_from_browsers(self) -> Optional[dict[str, http.cookiejar.CookieJar]]:
        try:
            url_to_cj: dict[str, http.cookiejar.CookieJar] = {}
            for cookie_fn in (brave, chrome, chromium, edge, firefox, opera, opera_gx, safari, vivaldi):
                cj = http.cookiejar.CookieJar()
                try:
                    logged_in = False
                    for cookie in cookie_fn(domain_name="bandcamp.com"):
                        cj.set_cookie(cookie)
                        if cookie.name == "js_logged_in" and cookie.value == "1":
                            logged_in = True
                    if not logged_in:
                        continue
                    for url in self._get_owned_bands(cj):
                        logger.info(f"[{cookie_fn.__name__}] Found band - {url}")
                        url_to_cj[url] = cj
                except BrowserCookieError:
                    pass
                except Exception as e:
                    logger.debug(f"[{cookie_fn.__name__}] {e}")
            return url_to_cj if url_to_cj else None
        except Exception as e:
            logger.exception(e)
            return None

    def _get_owned_bands(self, cj: http.cookiejar.CookieJar) -> list[str]:
        session = requests.Session()
        session.mount("https://", BandcampHTTPAdapter())

        essential_cookies = http.cookiejar.CookieJar()
        essential_cookie_names = {
            'js_logged_in', 'client_id', 'session', 'logged_in',
            'BACKENDID', 'customer_id',
        }
        for cookie in cj:
            if 'bandcamp.com' in cookie.domain:
                if cookie.name in essential_cookie_names:
                    essential_cookies.set_cookie(cookie)
                elif any(k in cookie.name.lower() for k in ('session', 'auth', 'token', 'login', 'id')):
                    essential_cookies.set_cookie(cookie)

        session.cookies.update(essential_cookies)
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'Origin': 'https://bandcamp.com',
            'Referer': 'https://bandcamp.com/',
        }
        r = session.post("https://bandcamp.com/api/design_system/1/menubar", headers=headers)
        r.raise_for_status()
        data = r.json()

        bands = [data.get("activeBand")]
        if data.get("labelBands"):
            bands.extend(data["labelBands"])
        if data.get("additionalLabelBands"):
            bands.extend(data["additionalLabelBands"])
        if data.get("connectedBands"):
            bands.extend(data["connectedBands"])
        if data.get("pageOwnerBand"):
            bands.append(data["pageOwnerBand"])

        band_urls = []
        for band in bands:
            if band and band.get("url"):
                band_urls.append(band["url"])
        return list(set(band_urls))

    def _update_artist_dropdown(self):
        names = list(self.urls.keys())
        self.artist_combo.clear()
        self.artist_combo.addItems(names)
        last = getattr(self.config, 'last_selected_artist', None)
        if last and last in self.urls:
            self.artist_combo.setCurrentText(last)
        elif names:
            self.artist_combo.setCurrentIndex(0)
        artist_count = len(self.urls)
        self.statusBar().showMessage(f"{artist_count} artist(s) loaded")

    def _show_no_artists_dialog(self):
        self.artist_combo.clear()
        self.artist_combo.addItem("No artists found")
        QMessageBox.warning(
            self,
            "No Artists Found",
            "Could not find any Bandcamp artists.\n\n"
            "Please make sure you're logged in to Bandcamp in at least one browser.\n\n"
            "Steps:\n"
            "1. Log in to your Bandcamp account in your browser\n"
            "2. Visit your artist/label page\n"
            "3. CLOSE the browser completely\n"
            "4. Click 'Refresh Artists' in this app\n\n"
            "Or export cookies.txt and configure it via 'Load Cookies'."
        )

    def on_artist_selected(self, text: str):
        if not text or text in ("No artist selected", "Loading artists...", "No artists found"):
            return
        if text not in self.urls:
            return
        self.selected_artist_url = text
        self.setup_session()
        self.config.last_selected_artist = text
        save_config(self.config)
        self.upload_button.setEnabled(
            bool(self.album_path_edit.text().strip())
        )
        self.statusBar().showMessage(f"Selected artist: {text}")

    def setup_session(self):
        if not self.selected_artist_url or self.selected_artist_url not in self.urls:
            return
        cj = self.urls[self.selected_artist_url]
        self.session = requests.Session()
        self.session.mount("https://", BandcampHTTPAdapter())

        essential_cookies = http.cookiejar.CookieJar()
        essential_cookie_names = {
            'js_logged_in', 'client_id', 'session', 'logged_in',
            'BACKENDID', 'customer_id',
        }
        for cookie in cj:
            if 'bandcamp.com' in cookie.domain:
                if cookie.name in essential_cookie_names:
                    essential_cookies.set_cookie(cookie)
                elif any(k in cookie.name.lower() for k in ('session', 'auth', 'token', 'login', 'id')):
                    essential_cookies.set_cookie(cookie)

        self.session.cookies = essential_cookies
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })

        def verify():
            try:
                test_url = urljoin(self.selected_artist_url, "edit_album")
                test_response = self.session.get(test_url, timeout=10)
                if "login" in test_response.url.lower() or "signin" in test_response.url.lower():
                    self.statusBar().showMessage("Session may be expired - redirected to login")
                else:
                    self.statusBar().showMessage("Session verified successfully")
            except Exception as e:
                self.statusBar().showMessage(f"Session verification failed: {e}")

        import threading
        threading.Thread(target=verify, daemon=True).start()

    def show_preferences_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Preferences")
        dialog.resize(760, 520)
        dialog.setMinimumSize(640, 400)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        mid = QWidget()
        mid_layout = QHBoxLayout(mid)
        mid_layout.setContentsMargins(0, 0, 0, 0)
        mid_layout.setSpacing(0)

        sidebar = QTreeWidget()
        sidebar.setHeaderHidden(True)
        sidebar.setFixedWidth(150)
        sidebar.setObjectName("prefsSidebar")

        stacked = QStackedWidget()
        mid_layout.addWidget(sidebar)
        mid_layout.addWidget(stacked, 1)
        layout.addWidget(mid, 1)

        pages = [
            self._build_prefs_general_page(),
            self._build_prefs_context_menu_page(),
            self._build_prefs_sort_page(),
            self._build_prefs_autotag_page(),
            self._build_prefs_toast_page(),
            self._build_prefs_winnotif_page(),
            self._build_prefs_notif_triggers_page(),
            self._build_prefs_upload_page(),
            self._build_prefs_columns_page(),
            self._build_prefs_logs_page(),
            self._build_prefs_advanced_page(),
            self._build_prefs_about_page(),
        ]
        for p in pages:
            stacked.addWidget(p)

        gen = QTreeWidgetItem(["General"])
        sidebar.addTopLevelItem(gen)
        for label, idx in (("General Settings", 0), ("Context Menu", 1),
                           ("Sort Methods", 2), ("Auto Tagging", 3)):
            item = QTreeWidgetItem([label])
            item.setData(0, Qt.UserRole, idx)
            gen.addChild(item)

        notif = QTreeWidgetItem(["Notifications"])
        sidebar.addTopLevelItem(notif)
        for label, idx in (("Toasts", 4), ("Windows Notifications", 5),
                           ("Notification Triggers", 6)):
            item = QTreeWidgetItem([label])
            item.setData(0, Qt.UserRole, idx)
            notif.addChild(item)

        upload_cat = QTreeWidgetItem(["Upload"])
        sidebar.addTopLevelItem(upload_cat)
        item = QTreeWidgetItem(["Upload Settings"])
        item.setData(0, Qt.UserRole, 7)
        upload_cat.addChild(item)

        interface = QTreeWidgetItem(["Interface"])
        sidebar.addTopLevelItem(interface)
        for label, idx in (("Column Visibility", 8), ("Logs", 9)):
            item = QTreeWidgetItem([label])
            item.setData(0, Qt.UserRole, idx)
            interface.addChild(item)

        for label, idx in (("Advanced", 10), ("About", 11)):
            item = QTreeWidgetItem([label])
            item.setData(0, Qt.UserRole, idx)
            sidebar.addTopLevelItem(item)

        sidebar.expandAll()
        sidebar.setCurrentItem(gen.child(0))

        sidebar.currentItemChanged.connect(
            lambda current, _prev: self._switch_prefs_page(current, stacked)
        )

        btn_bar = QWidget()
        btn_layout = QHBoxLayout(btn_bar)
        btn_layout.setContentsMargins(10, 6, 10, 6)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dialog.accept)
        btn_layout.addStretch(1)
        btn_layout.addWidget(close_btn)
        layout.addWidget(btn_bar)

        dialog.exec()

    def _apply_setting(self, attr: str):
        handler = getattr(self, f"_apply_{attr}", None)
        if handler:
            handler()

    def _on_pref_check_toggled(self, cb: QCheckBox):
        attr = cb.property("prefAttr")
        if attr:
            setattr(self.config, attr, cb.isChecked())
            save_config(self.config)
            self._apply_setting(attr)

    def _on_pref_spin_changed(self, spin: QSpinBox, value: int):
        attr = spin.property("prefAttr")
        if attr:
            setattr(self.config, attr, value)
            save_config(self.config)
            self._apply_setting(attr)

    def _on_pref_combo_changed(self, combo: QComboBox):
        attr = combo.property("prefAttr")
        if attr:
            setattr(self.config, attr, combo.currentText())
            save_config(self.config)
            self._apply_setting(attr)

    def _on_pref_color_changed(self, attr: str, swatch: QLabel):
        color = QColorDialog.getColor(QColor(getattr(self.config, attr, "#000000")))
        if color.isValid():
            hex_color = color.name()
            setattr(self.config, attr, hex_color)
            save_config(self.config)
            swatch.setStyleSheet(f"background-color: {hex_color}; border: 1px solid #888;")
            self._apply_setting(attr)

    def _pref_color_widget(self, attr: str, default: str):
        w = QWidget()
        hl = QHBoxLayout(w)
        hl.setContentsMargins(0, 0, 0, 0)
        swatch = QLabel()
        swatch.setFixedSize(22, 22)
        val = getattr(self.config, attr, default)
        swatch.setStyleSheet(f"background-color: {val}; border: 1px solid #888; border-radius: 2px;")
        btn = QPushButton("Pick...")
        btn.clicked.connect(lambda: self._on_pref_color_changed(attr, swatch))
        hl.addWidget(swatch)
        hl.addWidget(btn)
        hl.addStretch(1)
        return w

    def _switch_prefs_page(self, current: QTreeWidgetItem, stacked: QStackedWidget):
        if not current:
            return
        idx = current.data(0, Qt.UserRole)
        if idx is not None and 0 <= idx < stacked.count():
            stacked.setCurrentIndex(idx)

    def _build_check_page(self, items):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(10, 10, 10, 10)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        inner = QWidget()
        il = QVBoxLayout(inner)
        il.setSpacing(4)
        for label, attr, default in items:
            cb = QCheckBox(label)
            cb.setChecked(getattr(self.config, attr, default))
            cb.setProperty("prefAttr", attr)
            cb.toggled.connect(lambda _checked, c=cb: self._on_pref_check_toggled(c))
            il.addWidget(cb)
        il.addStretch(1)
        scroll.setWidget(inner)
        layout.addWidget(scroll)
        return page

    def _build_prefs_general_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(10, 10, 10, 10)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        inner = QWidget()
        form = QFormLayout(inner)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        form.setSpacing(2)
        form.setContentsMargins(0, 0, 0, 0)

        for label, attr, default in [
            ("Create album session files (session.txt)", "create_album_session_files", True),
            ("Auto-load cookies on startup", "auto_load_cookies", False),
            ("Remember last opened album", "remember_last_album", True),
            ("Apply settings immediately", "apply_settings_immediately", True),
            ("Maximize app on open", "maximize_on_open", False),
            ("Disable tooltips", "disable_tooltips", True),
            ("Auto-load metadata for album details", "auto_load_metadata", True),
            ("Use Album Artist metadata for Artist in Album details", "use_album_artist_in_album_details", True),
            ("Guess album title from track metadata", "guess_album_title_from_track_metadata", True),
            ("Guess release date from track metadata", "guess_release_date_from_track_metadata", True),
            ("Use folder name when album tag missing", "use_folder_name_when_album_missing", True),
            ("Smart-randomize on album load", "smart_randomize_on_album_load", False),
            ("Auto guess case tracks on album load", "auto_guess_case_on_album_load", False),
            ("Always auto-scale cover art", "always_auto_scale_cover", True),
            ("Create description on upload", "description_auto_fill_on_upload", True),
            ("Extract track cover if cover missing", "extract_track_cover_if_missing", True),
            ("Clear progress on album change", "clear_progress_on_album_change", True),
            ("Check for updates on startup", "check_for_updates", True),
            ("Auto-fit columns", "auto_fit_columns", True),
            ("Highlight corrupted tracks", "highlight_corrupted_tracks", True),
            ("Show total album duration", "show_total_album_duration", True),
        ]:
            cb = QCheckBox(label)
            cb.setChecked(getattr(self.config, attr, default))
            cb.setProperty("prefAttr", attr)
            cb.toggled.connect(lambda _checked, c=cb: self._on_pref_check_toggled(c))
            form.addRow("", cb)

        cover_fit = QComboBox()
        cover_fit.addItems(["Crop (fill)", "Fit (contain)", "Stretch"])
        cover_fit.setCurrentText(getattr(self.config, "cover_fit_mode", "Crop (fill)"))
        cover_fit.setProperty("prefAttr", "cover_fit_mode")
        cover_fit.currentIndexChanged.connect(lambda _: self._on_pref_combo_changed(cover_fit))
        form.addRow("Cover fit mode:", cover_fit)

        scaling = QComboBox()
        scaling.addItems([
            "Nearest", "Box", "Bilinear", "Hamming", "Bicubic", "Lanczos",
            "Area", "Mitchell", "Catmull-Rom", "Sinc", "Gaussian", "Pixelate",
            "Hermite", "Blackman", "Kaiser", "Welch", "Parzen", "Bartlett",
            "Cubic", "Quadratic", "Average", "Max", "Min", "Median", "Sharpen",
            "Edge-Enhanced", "B-Spline", "Rational",
        ])
        scaling.setCurrentText(getattr(self.config, "cover_scaling_method", "Lanczos"))
        scaling.setProperty("prefAttr", "cover_scaling_method")
        scaling.currentIndexChanged.connect(lambda _: self._on_pref_combo_changed(scaling))
        form.addRow("Cover scaling method:", scaling)

        desc_combo = QComboBox()
        desc_combo.addItems(DESCRIPTION_AUTO_FILL_MODES)
        desc_combo.setCurrentText(getattr(self.config, "description_auto_fill_mode", "Off"))
        desc_combo.setProperty("prefAttr", "description_auto_fill_mode")
        desc_combo.currentIndexChanged.connect(lambda _: self._on_pref_combo_changed(desc_combo))
        form.addRow("Description auto-fill:", desc_combo)

        file_unit = QComboBox()
        file_unit.addItems(["Auto", "B", "KB", "MB", "GB"])
        file_unit.setCurrentText(getattr(self.config, "file_size_unit", "Auto"))
        file_unit.setProperty("prefAttr", "file_size_unit")
        file_unit.currentIndexChanged.connect(lambda _: self._on_pref_combo_changed(file_unit))
        form.addRow("File size unit:", file_unit)

        log_limit = QSpinBox()
        log_limit.setRange(1, 99)
        log_limit.setValue(getattr(self.config, "log_file_limit", 7))
        log_limit.setProperty("prefAttr", "log_file_limit")
        log_limit.valueChanged.connect(lambda val, s=log_limit: self._on_pref_spin_changed(s, val))
        form.addRow("Log file limit:", log_limit)

        form.addRow("Locked track highlight:", self._pref_color_widget("locked_track_highlight_color", "#fff4ce"))

        scroll.setWidget(inner)
        layout.addWidget(scroll)
        return page

    def _build_prefs_context_menu_page(self):
        return self._build_check_page([
            ("Show context menu icons", "show_context_menu_icons", True),
            ("Remove dividers", "context_menu_remove_dividers", False),
            ("Play", "context_menu_play", True),
            ("Remove Track", "context_menu_remove_track", True),
            ("Move Up", "context_menu_move_up", True),
            ("Move Down", "context_menu_move_down", True),
            ("Move to Top", "context_menu_move_to_top", True),
            ("Move to Bottom", "context_menu_move_to_bottom", True),
            ("Open File Location", "context_menu_open_file", True),
            ("Replace File", "context_menu_replace_file", False),
            ("Extract Cover Art", "context_menu_extract_cover_art", True),
            ("Extract Tracklist", "context_menu_extract_tracklist", False),
            ("Open session.txt", "context_menu_open_session", False),
            ("Set Track Cover as Album Cover", "context_menu_set_track_cover_as_album_cover", False),
            ("Undo", "context_menu_undo", True),
            ("Redo", "context_menu_redo", True),
            ("Extract Track Information", "context_menu_extract_track_info", False),
            ("Copy Metadata", "context_menu_copy_metadata", True),
            ("Paste Metadata", "context_menu_paste_metadata", True),
            ("Revert to Original", "context_menu_revert_to_original", False),
            ("Lock/Unlock", "context_menu_lock_unlock", True),
            ("Randomize", "context_menu_randomize", False),
            ("Smart Randomize", "context_menu_smart_randomize", False),
            ("Sort By", "context_menu_sort_by", True),
            ("Clear Metadata", "context_menu_clear_metadata", False),
            ("Clear All Metadata", "context_menu_clear_all_metadata", False),
            ("Clear All Tracks", "context_menu_clear_all", False),
            ("Upload as Single", "context_menu_upload_as_single", True),
        ])

    def _build_prefs_sort_page(self):
        return self._build_check_page([
            ("File Size", "sort_by_file_size", True),
            ("Length", "sort_by_length", True),
            ("Alphabetically", "sort_by_alphabetically", True),
            ("Artist Name", "sort_by_artist", True),
            ("Track Number", "sort_by_track_number", True),
            ("Metadata Track #", "sort_by_metadata_track_number", True),
            ("Extension", "sort_by_extension", True),
            ("Price", "sort_by_price", True),
            ("Year", "sort_by_year", True),
            ("Genre", "sort_by_genre", True),
            ("Bitrate", "sort_by_bitrate", True),
            ("Sample Rate", "sort_by_sample_rate", True),
            ("Channels", "sort_by_channels", True),
            ("Bit Depth", "sort_by_bit_depth", True),
            ("Album Metadata", "sort_by_album", True),
            ("Album Artist Metadata", "sort_by_album_artist", True),
            ("Composer", "sort_by_composer", True),
            ("ISRC", "sort_by_isrc", True),
        ])

    def _build_prefs_autotag_page(self):
        return self._build_check_page([
            ("Year", "auto_tag_year", False),
            ("Genre", "auto_tag_genre", False),
            ("Artist", "auto_tag_artist", False),
            ("Album", "auto_tag_album", False),
            ("Comment", "auto_tag_comment", False),
            ("Track Title", "auto_tag_track_title", False),
            ("Album Artist", "auto_tag_album_artist", False),
            ("Composer", "auto_tag_composer", False),
            ("Track Number", "auto_tag_track_number", False),
            ("Duration", "auto_tag_duration", False),
            ("Bitrate", "auto_tag_bitrate", False),
            ("Release Type", "auto_tag_release_type", False),
        ])

    def _build_prefs_toast_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(10, 10, 10, 10)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        inner = QWidget()
        form = QFormLayout(inner)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        form.setSpacing(2)
        form.setContentsMargins(0, 0, 0, 0)

        for label, attr, default in [
            ("Enable Toast Notifications", "enable_toasts", True),
            ("Enable Fade Out Effect", "toast_fade_out", True),
            ("Font Bold", "toast_font_bold", False),
        ]:
            cb = QCheckBox(label)
            cb.setChecked(getattr(self.config, attr, default))
            cb.setProperty("prefAttr", attr)
            cb.toggled.connect(lambda _checked, c=cb: self._on_pref_check_toggled(c))
            form.addRow("", cb)

        dur = QSpinBox()
        dur.setRange(1, 30)
        dur.setValue(getattr(self.config, "toast_duration", 3))
        dur.setProperty("prefAttr", "toast_duration")
        dur.valueChanged.connect(lambda val, s=dur: self._on_pref_spin_changed(s, val))
        form.addRow("Duration (seconds):", dur)

        fs = QSpinBox()
        fs.setRange(8, 30)
        fs.setValue(getattr(self.config, "toast_font_size", 10))
        fs.setProperty("prefAttr", "toast_font_size")
        fs.valueChanged.connect(lambda val, s=fs: self._on_pref_spin_changed(s, val))
        form.addRow("Font size:", fs)

        pos = QComboBox()
        pos.addItems(["top-right", "top-left", "bottom-right", "bottom-left"])
        pos.setCurrentText(getattr(self.config, "toast_position", "top-right"))
        pos.setProperty("prefAttr", "toast_position")
        pos.currentIndexChanged.connect(lambda _: self._on_pref_combo_changed(pos))
        form.addRow("Position:", pos)

        ff = QComboBox()
        ff.addItems(["Segoe UI", "Arial", "Consolas", "Courier New", "monospace", "Tahoma"])
        ff.setCurrentText(getattr(self.config, "toast_font_family", "Segoe UI"))
        ff.setProperty("prefAttr", "toast_font_family")
        ff.currentIndexChanged.connect(lambda _: self._on_pref_combo_changed(ff))
        form.addRow("Font family:", ff)

        for label, attr, default in [
            ("Text color", "toast_text_color", "#f8fafc"),
            ("Background color", "toast_bg_color", "#1f2933"),
            ("Border color", "toast_border_color", "#334155"),
            ("Success color", "toast_success_color", "#22c55e"),
            ("Error color", "toast_error_color", "#ef4444"),
            ("Warning color", "toast_warning_color", "#f59e0b"),
            ("Info color", "toast_info_color", "#38bdf8"),
        ]:
            form.addRow(label + ":", self._pref_color_widget(attr, default))

        scroll.setWidget(inner)
        layout.addWidget(scroll)
        return page

    def _build_prefs_winnotif_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(10, 10, 10, 10)
        cb = QCheckBox("Enable Windows notifications")
        cb.setChecked(getattr(self.config, "windows_notifications", False))
        cb.setProperty("prefAttr", "windows_notifications")
        cb.toggled.connect(lambda _checked, c=cb: self._on_pref_check_toggled(c))
        layout.addWidget(cb)
        layout.addStretch(1)
        return page

    def _build_prefs_notif_triggers_page(self):
        return self._build_check_page([
            ("Notify on Upload Success", "notify_on_upload_success", True),
            ("Notify on Upload Error", "notify_on_upload_error", True),
            ("Notify on Track Error", "notify_on_track_error", True),
            ("Notify on Conversion Complete", "notify_on_conversion_complete", False),
            ("Notify on Metadata Load", "notify_on_metadata_load", False),
            ("Notify on File Add", "notify_on_file_add", False),
            ("Notify on Track Add", "notify_on_track_add", False),
            ("Notify on Track Remove", "notify_on_track_remove", False),
            ("Notify on Cover Load", "notify_on_cover_load", False),
            ("Notify on Album Save", "notify_on_album_save", False),
            ("Notify on Settings Save", "notify_on_settings_save", False),
            ("Notify on Artists Load", "notify_on_artists_load", False),
            ("Notify on Template Save", "notify_on_template_save", False),
        ])

    def _build_prefs_upload_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(10, 10, 10, 10)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        inner = QWidget()
        form = QFormLayout(inner)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        form.setSpacing(2)
        form.setContentsMargins(0, 0, 0, 0)

        for label, attr, default in [
            ("Auto-start upload after adding files", "auto_start_upload", False),
            ("Confirm before starting upload", "confirm_before_upload", False),
            ("Use track name for single release", "use_track_name_for_single_release", True),
            ("Open logs on album upload", "open_logs_on_upload", False),
            ("Open album page after upload", "open_album_page_after_upload", True),
            ("Copy album URL to clipboard after upload", "copy_album_url_after_upload", False),
            ("Use embedded cover art from tracks", "extract_embedded_cover_art", False),
            ("Detailed track information in progress", "detailed_progress_track_info", False),
            ("Show progress timing details", "show_progress_timing_details", False),
            ("Retry failed uploads", "retry_failed_uploads", False),
        ]:
            cb = QCheckBox(label)
            cb.setChecked(getattr(self.config, attr, default))
            cb.setProperty("prefAttr", attr)
            cb.toggled.connect(lambda _checked, c=cb: self._on_pref_check_toggled(c))
            form.addRow("", cb)

        for label, attr, default, lo, hi in [
            ("Max concurrent uploads:", "max_concurrent_uploads", 1, 1, 5),
            ("Upload timeout (seconds):", "upload_timeout", 300, 30, 600),
            ("Retry attempts:", "retry_attempts", 3, 1, 10),
            ("Retry delay (seconds):", "retry_delay", 5, 1, 60),
        ]:
            spin = QSpinBox()
            spin.setRange(lo, hi)
            spin.setValue(getattr(self.config, attr, default))
            spin.setProperty("prefAttr", attr)
            spin.valueChanged.connect(lambda val, s=spin: self._on_pref_spin_changed(s, val))
            form.addRow(label, spin)

        scroll.setWidget(inner)
        layout.addWidget(scroll)
        return page

    def _build_prefs_columns_page(self):
        return self._build_check_page([
            ("Track No.", "show_track_no", True),
            ("Artist", "show_artist", True),
            ("Track Name", "show_track_name", True),
            ("Comment", "show_comment", True),
            ("Length", "show_length", True),
            ("Extension", "show_extension", True),
            ("Price", "show_price", True),
            ("NYP", "show_nyp", True),
            ("Year", "show_year", False),
            ("Genre", "show_genre", False),
            ("Bitrate", "show_bitrate", False),
            ("File Size", "show_file_size", False),
            ("Sample Rate", "show_sample_rate", False),
            ("Channels", "show_channels", False),
            ("Bit Depth", "show_bit_depth", False),
            ("Album Metadata", "show_album_metadata", False),
            ("Album Artist Metadata", "show_album_artist_metadata", False),
            ("Composer", "show_composer", False),
            ("ISRC", "show_isrc", False),
        ])

    def _build_prefs_logs_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(10, 10, 10, 10)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        inner = QWidget()
        form = QFormLayout(inner)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        form.setSpacing(2)
        form.setContentsMargins(0, 0, 0, 0)

        for label, attr, default in [
            ("Show timestamps", "log_show_timestamps", True),
            ("Show log levels", "log_show_levels", True),
            ("Word wrap", "log_word_wrap", True),
            ("Auto-scroll to bottom", "log_auto_scroll", True),
            ("Save diagnostic log file", "log_to_file", True),
            ("Font bold", "log_font_bold", False),
        ]:
            cb = QCheckBox(label)
            cb.setChecked(getattr(self.config, attr, default))
            cb.setProperty("prefAttr", attr)
            cb.toggled.connect(lambda _checked, c=cb: self._on_pref_check_toggled(c))
            form.addRow("", cb)

        for label, attr, default, lo, hi in [
            ("Font size:", "log_font_size", 9, 8, 30),
            ("Line spacing:", "log_line_spacing", 1, 1, 5),
            ("Max lines (0 = unlimited):", "log_max_lines", 1000, 0, 10000),
        ]:
            spin = QSpinBox()
            spin.setRange(lo, hi)
            spin.setValue(getattr(self.config, attr, default))
            spin.setProperty("prefAttr", attr)
            spin.valueChanged.connect(lambda val, s=spin: self._on_pref_spin_changed(s, val))
            form.addRow(label, spin)

        ff = QComboBox()
        ff.addItems(["Segoe UI", "Arial", "Consolas", "Courier New", "monospace", "Tahoma"])
        ff.setCurrentText(getattr(self.config, "log_font_family", "Segoe UI"))
        ff.setProperty("prefAttr", "log_font_family")
        ff.currentIndexChanged.connect(lambda _: self._on_pref_combo_changed(ff))
        form.addRow("Font family:", ff)

        ts = QComboBox()
        ts.addItems(["HH:MM:SS", "YYYY-MM-DD HH:MM:SS", "MM/DD/YYYY HH:MM:SS", "None"])
        ts.setCurrentText(getattr(self.config, "log_timestamp_format", "HH:MM:SS"))
        ts.setProperty("prefAttr", "log_timestamp_format")
        ts.currentIndexChanged.connect(lambda _: self._on_pref_combo_changed(ts))
        form.addRow("Timestamp format:", ts)

        lvl = QComboBox()
        lvl.addItems(["DEBUG", "INFO", "WARNING", "ERROR"])
        lvl.setCurrentText(getattr(self.config, "log_file_level", "INFO"))
        lvl.setProperty("prefAttr", "log_file_level")
        lvl.currentIndexChanged.connect(lambda _: self._on_pref_combo_changed(lvl))
        form.addRow("Log file level:", lvl)

        for label, attr, default in [
            ("Text color", "log_text_color", "#ffffff"),
            ("Background color", "log_bg_color", "#1e1e1e"),
            ("INFO color", "log_info_color", "#00ff00"),
            ("WARNING color", "log_warning_color", "#ffff00"),
            ("ERROR color", "log_error_color", "#ff0000"),
            ("DEBUG color", "log_debug_color", "#888888"),
        ]:
            form.addRow(label + ":", self._pref_color_widget(attr, default))

        scroll.setWidget(inner)
        layout.addWidget(scroll)
        return page

    def _build_prefs_advanced_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(8)
        info = QLabel("Reset all settings to their factory defaults. This cannot be undone.")
        info.setWordWrap(True)
        layout.addWidget(info)
        reset_btn = QPushButton("Reset All Settings")
        reset_btn.clicked.connect(self._reset_prefs)
        reset_btn.setStyleSheet("QPushButton { color: #fff; background-color: #c0392b; padding: 6px 16px; border-radius: 3px; }")
        layout.addWidget(reset_btn)
        layout.addStretch(1)
        return page

    def _build_prefs_about_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setAlignment(Qt.AlignCenter)
        title = QLabel("Bandcamp Auto Uploader")
        title.setFont(QFont("Segoe UI", 14, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        ver = QLabel(f"Version {__version__}")
        ver.setAlignment(Qt.AlignCenter)
        layout.addWidget(ver)
        layout.addWidget(QLabel(""))
        desc = QLabel(
            "Upload your music to Bandcamp with ease.\n\n"
            "PySide6 Qt migration preview.\n\n"
            "https://github.com/7x11x13/bandcamp-auto-uploader"
        )
        desc.setAlignment(Qt.AlignCenter)
        desc.setWordWrap(True)
        layout.addWidget(desc)
        layout.addStretch(1)
        return page

    def _reset_prefs(self):
        reply = QMessageBox.warning(
            self, "Reset Settings",
            "Reset all settings to factory defaults and restart?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            save_config(Config())
            QMessageBox.information(self, "Reset Complete", "Settings reset. Restart the application.")

    # ── Immediate-apply handlers for preferences ──

    def _apply_show_track_no(self):
        self.track_table.setColumnHidden(0, not self.config.show_track_no)
    def _apply_show_artist(self):
        self.track_table.setColumnHidden(1, not self.config.show_artist)
    def _apply_show_track_name(self):
        self.track_table.setColumnHidden(2, not self.config.show_track_name)
    def _apply_show_comment(self):
        self.track_table.setColumnHidden(3, not self.config.show_comment)
    def _apply_show_length(self):
        self.track_table.setColumnHidden(4, not self.config.show_length)
    def _apply_show_extension(self):
        self.track_table.setColumnHidden(5, not self.config.show_extension)
    def _apply_show_price(self):
        self.track_table.setColumnHidden(6, not self.config.show_price)
    def _apply_show_nyp(self):
        self.track_table.setColumnHidden(7, not self.config.show_nyp)
    def _apply_auto_fit_columns(self):
        mode = QHeaderView.ResizeToContents if self.config.auto_fit_columns else QHeaderView.Interactive
        self.track_table.horizontalHeader().setSectionResizeMode(mode)

    def _apply_log_auto_scroll(self):
        pass  # handled in log polling loop
    def _apply_log_max_lines(self):
        doc = self.log_text.document()
        doc.setMaximumBlockCount(self.config.log_max_lines if self.config.log_max_lines > 0 else -1)
    def _apply_log_font_family(self):
        f = self.log_text.font(); f.setFamily(self.config.log_font_family); self.log_text.setFont(f)
    def _apply_log_font_size(self):
        f = self.log_text.font(); f.setPointSize(self.config.log_font_size); self.log_text.setFont(f)
    def _apply_log_font_bold(self):
        f = self.log_text.font(); f.setBold(self.config.log_font_bold); self.log_text.setFont(f)
    def _apply_log_text_color(self):
        self.log_text.setStyleSheet(self._log_stylesheet())
    def _apply_log_bg_color(self):
        self.log_text.setStyleSheet(self._log_stylesheet())

    def _log_stylesheet(self):
        c = self.config
        return (
            f"QTextEdit#logText {{"
            f"  background: {c.log_bg_color};"
            f"  color: {c.log_text_color};"
            f"  border: 1px solid #3c3c3c;"
            f"  font-family: {c.log_font_family};"
            f"  font-size: {c.log_font_size}pt;"
            f"}}"
        )

    def start_upload(self):
        if self.is_upload_in_progress():
            return
        if self.current_album is None or self.selected_artist_url is None:
            QMessageBox.warning(
                self, "Upload", "Load an album and select an artist first."
            )
            return
        if self.session is None:
            self.setup_session()
            if self.session is None:
                QMessageBox.warning(
                    self,
                    "Session Required",
                    "Could not set up session. Load cookies for the selected artist first.",
                )
                return

        self._save_current_track_details()
        self.apply_album_details_to_model()
        self.sync_table_to_album()

        album = self.current_album
        artist_url = self.selected_artist_url
        session = self.session
        cancel_event = threading.Event()
        self.upload_cancel_event = cancel_event

        self._update_upload_buttons(True)
        self.statusBar().showMessage(
            f"Uploading {len(album.tracks)} track(s) to {artist_url}..."
        )
        logger.info(f"Starting upload: {album.album_data.title} -> {artist_url}")

        def _upload_worker():
            try:
                result = album.upload(
                    session=session,
                    artist_url=artist_url,
                    progress_callback=self._on_upload_progress,
                    cancel_event=cancel_event,
                )
                logger.info(f"Upload completed: {result}")
            except UploadCancelled:
                logger.info("Upload cancelled by user")
            except Exception as exc:
                logger.error(f"Upload failed: {exc}", exc_info=True)
                QTimer.singleShot(0, lambda: self.statusBar().showMessage(
                    f"Upload failed: {exc}"
                ))
            finally:
                QTimer.singleShot(0, self._on_upload_finished)

        self.upload_thread = threading.Thread(target=_upload_worker, daemon=True)
        self.upload_thread.start()

    def _on_upload_progress(self, event: str, payload: dict):
        self.progress_signal.emit(event, payload)

    def _on_upload_finished(self):
        self.upload_thread = None
        self._update_upload_buttons(False)
        self.statusBar().showMessage("Upload finished")

    def _update_upload_buttons(self, uploading: bool):
        self.upload_button.setEnabled(not uploading)
        self.cancel_upload_button.setEnabled(uploading)

    def is_upload_in_progress(self) -> bool:
        return self.upload_thread is not None and self.upload_thread.is_alive()

    def cancel_upload(self):
        if not self.is_upload_in_progress():
            self.statusBar().showMessage("No upload in progress")
            return
        self.upload_cancel_event.set()
        self.statusBar().showMessage("Cancelling upload...")

    def handle_upload_progress_event(self, event: str, payload: dict):
        if event == "album_start":
            self.statusBar().showMessage(
                f"Uploading {payload.get('total', 0)} track(s)..."
            )
            self.clear_progress_rows()
            self.progress_placeholder.hide()
            for i in range(payload.get("total", 0)):
                self.add_progress_row(
                    f"Track {i + 1}", "Waiting", 0,
                )

        elif event == "track_start":
            index = payload.get("index", 0)
            if index < len(self.progress_rows):
                _, status, bar = self.progress_rows[index]
                status.setText(payload.get("status", "Uploading"))
                bar.setValue(payload.get("progress", 10))

        elif event == "conversion_done":
            index = payload.get("index", 0)
            if index < len(self.progress_rows):
                _, status, _ = self.progress_rows[index]
                status.setText("Converting to FLAC...")

        elif event in ("track_uploaded", "track_saving"):
            index = payload.get("index", 0)
            if index < len(self.progress_rows):
                _, status, bar = self.progress_rows[index]
                status.setText(payload.get("status", "Saving metadata"))
                bar.setValue(payload.get("progress", 65))

        elif event == "track_done":
            index = payload.get("index", 0)
            if index < len(self.progress_rows):
                title, status, bar = self.progress_rows[index]
                status.setText("Complete")
                bar.setValue(100)

        elif event == "track_skipped":
            index = payload.get("index", 0)
            if index < len(self.progress_rows):
                _, status, bar = self.progress_rows[index]
                status.setText(payload.get("status", "Skipped"))
                bar.setValue(100)

        elif event == "cover_start":
            self.statusBar().showMessage("Uploading cover art...")

        elif event == "cover_done":
            self.statusBar().showMessage("Cover art uploaded")

        elif event == "album_done":
            total = payload.get("total", 0)
            successful = payload.get("successful", 0)
            skipped = payload.get("skipped", 0)
            album_url = payload.get("album_url", "")
            self.statusBar().showMessage(
                f"Upload complete: {successful}/{total} successful"
                + (f", {skipped} skipped" if skipped else "")
            )

            self._update_upload_buttons(False)

            if album_url and self.config.copy_album_url_after_upload:
                QApplication.clipboard().setText(album_url)
                self.statusBar().showMessage(
                    f"Album URL copied to clipboard: {album_url}"
                )

            reply = QMessageBox.information(
                self,
                "Upload Complete",
                f"Uploaded {successful}/{total} tracks successfully."
                + (f"\n{skipped} skipped." if skipped else "")
                + ("\n\nView album page?" if album_url else ""),
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply == QMessageBox.Yes and album_url:
                QDesktopServices.openUrl(QUrl(album_url))

        elif event == "album_cancelled":
            self.statusBar().showMessage("Upload cancelled")
            self._update_upload_buttons(False)

        else:
            self.statusBar().showMessage(
                f"Upload event: {event} - {payload.get('status', '')}"
            )

    def open_album_folder(self):
        album_path = Path(self.album_path_edit.text().strip())
        if not album_path.is_dir():
            QMessageBox.warning(
                self, "Album Folder", "Choose a valid album folder first."
            )
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(album_path)))

    def preview_album(self):
        path_text = self.album_path_edit.text().strip()
        if not path_text:
            QMessageBox.information(
                self, "Album Folder", "Choose an album folder first."
            )
            return

        album_path = Path(path_text)
        if not album_path.is_dir():
            QMessageBox.warning(self, "Invalid Folder", "Choose a valid album folder.")
            return

        try:
            album = Album.from_directory(album_path, self.config)
        except Exception as exc:
            QMessageBox.critical(
                self, "Preview Failed", f"Could not preview album:\n{exc}"
            )
            return

        self.current_album = album
        self.track_editor_data.clear()
        self.load_album_details(album, album_path)
        self.populate_track_table(album)
        self.prepare_progress_from_album(album)
        self.load_or_create_album_session_file(album_path)
        self.statusBar().showMessage(f"Loaded {len(album.tracks)} track(s)")

    def on_preview_option_changed(self):
        self.config.ignore_artist_name = self.ignore_artist_check.isChecked()
        self.config.use_filename_as_title = self.filename_as_title_check.isChecked()
        self.config.ignore_all_metadata = self.ignore_metadata_check.isChecked()
        save_config(self.config)
        album_path = Path(self.album_path_edit.text().strip())
        if album_path.is_dir():
            self.preview_album()
        elif self.current_album is not None:
            paths = [track.path for track in self.current_album.tracks]
            self.reload_tracks_from_paths(paths, keep_album_details=True)

    def add_tracks(self):
        filenames, _selected_filter = QFileDialog.getOpenFileNames(
            self, "Select Track Files", "", AUDIO_FILTER
        )
        if not filenames:
            return

        existing_paths = set()
        if self.current_album is not None:
            existing_paths = {
                Path(track.path).resolve() for track in self.current_album.tracks
            }

        tracks = []
        skipped = []
        for filename in filenames:
            path = Path(filename)
            try:
                resolved = path.resolve()
            except OSError:
                resolved = path
            if resolved in existing_paths:
                continue
            try:
                track = Track.from_file(path, self.config)
            except Exception:
                track = None
            if track is None:
                skipped.append(path.name)
                continue
            tracks.append(track)
            existing_paths.add(resolved)

        if not tracks:
            message = "No supported audio tracks were added."
            if skipped:
                message += "\n\nSkipped:\n" + "\n".join(skipped[:8])
            QMessageBox.warning(self, "Add Track", message)
            return

        if self.current_album is None:
            first_parent = tracks[0].path.parent
            album_data = BandcampAlbumData(
                title=first_parent.name or "Manual Album",
                price=str(getattr(self.config, "album_price", "0")),
                nyp=int(getattr(self.config, "name_your_price", True)),
            )
            self.current_album = Album(
                album_data=album_data, tracks=[], cover_art=None
            )
            self.album_path_edit.setText("")
            self.load_album_details(self.current_album, first_parent)

        self.current_album.tracks.extend(tracks)
        self.populate_track_table(self.current_album)
        self.sync_table_to_album()
        if skipped:
            self.statusBar().showMessage(
                f"Added {len(tracks)} track(s), skipped {len(skipped)} unsupported file(s)"
            )
        else:
            self.statusBar().showMessage(f"Added {len(tracks)} track(s)")

    def reload_tracks_from_paths(self, paths: list[Path], keep_album_details: bool):
        tracks = []
        for path in paths:
            track = Track.from_file(path, self.config)
            if track is not None:
                tracks.append(track)
        if self.current_album is None:
            return
        self.current_album.tracks = tracks
        if not keep_album_details and paths:
            self.load_album_details(self.current_album, paths[0].parent)
        self.populate_track_table(self.current_album)
        self.prepare_progress_from_album(self.current_album)

    def load_album_details(self, album: Album, album_path: Path):
        data = album.album_data
        self._loading_album_details = True
        try:
            self.album_name_edit.setText(data.title or album_path.name)
            self.artist_edit.setText(data.artist or "")
            self.release_date_edit.setText(normalize_release_date(data.release_date))
            self.album_price_edit.setText(format_price(data.price, default="0"))
            self.album_nyp_check.setChecked(bool(data.nyp))
            self.album_public_check.setChecked(True)
            self.require_email_check.setChecked(bool(data.require_email))
            self.pro_check.setChecked(bool(data.pro))
            self.tags_edit.setText(data.tags or "")
            self.download_desc_edit.setText(data.download_desc or "")
            self.release_message_edit.setText(data.tralbum_release_message or "")
            self.record_label_edit.setText(data.label_name or "")
            self.catalog_number_edit.setText(data.cat_number or "")
            self.upc_edit.setText(data.upc or "")
            self.subscriber_message_edit.setText(data.subscriber_only_message or "")
            self.composer_edit.setText(data.composer or "")
            self.publisher_edit.setText(data.publisher or "")
            self.description_edit.setPlainText(data.about or "")
            self.credits_edit.setPlainText(data.credits or "")
            self.cover_path = (
                album.cover_art.path
                if album.cover_art and album.cover_art.path
                else None
            )
            self.cover_path_edit.setText(
                str(self.cover_path) if self.cover_path else ""
            )
            self.update_cover_preview()
        finally:
            self._loading_album_details = False

    def apply_album_details_to_model(self):
        if self._loading_album_details or self.current_album is None:
            return

        data = self.current_album.album_data
        data.title = self.album_name_edit.text().strip()
        data.artist = self.artist_edit.text().strip()
        data.release_date = normalize_release_date(self.release_date_edit.text())
        data.price = normalize_price(self.album_price_edit.text(), default="0")
        data.nyp = int(self.album_nyp_check.isChecked())
        data.public = 0 if self.album_public_check.isChecked() else 1
        data.require_email = int(self.require_email_check.isChecked())
        data.pro = int(self.pro_check.isChecked())
        data.tags = self.tags_edit.text().strip()
        data.download_desc = self.download_desc_edit.text().strip()
        data.tralbum_release_message = self.release_message_edit.text().strip()
        data.label_name = self.record_label_edit.text().strip()
        data.cat_number = self.catalog_number_edit.text().strip()
        data.upc = self.upc_edit.text().strip()
        data.subscriber_only_message = self.subscriber_message_edit.text().strip()
        data.composer = self.composer_edit.text().strip()
        data.publisher = self.publisher_edit.text().strip()
        data.about = self.description_edit.toPlainText().strip()
        data.credits = self.credits_edit.toPlainText().strip()
        self.current_album.cover_art = (
            CoverArt(path=self.cover_path) if self.cover_path else None
        )

    def auto_fill_album_name(self):
        album_path = Path(self.album_path_edit.text().strip())
        if album_path.is_dir():
            self._loading_album_details = True
            try:
                self.album_name_edit.setText(album_path.name)
            finally:
                self._loading_album_details = False
            self.apply_album_details_to_model()

    def auto_fill_artist_name(self):
        if self.current_album is None or not self.current_album.tracks:
            return
        for track in self.current_album.tracks:
            artist = getattr(track.track_data, "artist", "")
            if artist:
                self._loading_album_details = True
                try:
                    self.artist_edit.setText(artist)
                finally:
                    self._loading_album_details = False
                self.apply_album_details_to_model()
                return

    def td_auto_fill_name(self):
        row = self.selected_row()
        if row < 0:
            return
        path = self.table_text(row, COL_PATH)
        if path:
            stem = Path(path).stem
            self.track_name_edit.setText(stem)
            self.save_selected_track_details()

    def td_auto_fill_artist(self):
        row = self.selected_row()
        if row < 0:
            return
        track = self.track_for_row(row)
        if track is not None:
            artist = getattr(track.track_data, "artist", "")
            if artist:
                self.track_artist_edit.setText(artist)
                self.save_selected_track_details()

    def show_album_calendar(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Select Release Date")
        dlg_layout = QVBoxLayout(dialog)
        date_edit = QDateEdit()
        date_edit.setCalendarPopup(True)
        current_text = self.release_date_edit.text().strip()
        if current_text:
            try:
                parsed = QDate.fromString(current_text, "yyyy-MM-dd")
                if parsed.isValid():
                    date_edit.setDate(parsed)
            except Exception:
                date_edit.setDate(QDate.currentDate())
        else:
            date_edit.setDate(QDate.currentDate())
        dlg_layout.addWidget(date_edit)
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        dlg_layout.addWidget(buttons)
        if dialog.exec() == QDialog.Accepted:
            selected = date_edit.date()
            self.release_date_edit.setText(selected.toString("yyyy-MM-dd"))
            self.apply_album_details_to_model()

    def show_track_calendar(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Select Track Release Date")
        dlg_layout = QVBoxLayout(dialog)
        date_edit = QDateEdit()
        date_edit.setCalendarPopup(True)
        current_text = self.track_release_date_edit.text().strip()
        if current_text:
            try:
                parsed = QDate.fromString(current_text, "yyyy-MM-dd")
                if parsed.isValid():
                    date_edit.setDate(parsed)
            except Exception:
                date_edit.setDate(QDate.currentDate())
        else:
            date_edit.setDate(QDate.currentDate())
        dlg_layout.addWidget(date_edit)
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        dlg_layout.addWidget(buttons)
        if dialog.exec() == QDialog.Accepted:
            selected = date_edit.date()
            self.track_release_date_edit.setText(selected.toString("yyyy-MM-dd"))
            self.save_selected_track_details()

    def open_td_tag_edit_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Edit Track Tags")
        dialog.setMinimumWidth(350)
        dlg_layout = QVBoxLayout(dialog)
        dlg_layout.addWidget(QLabel("Comma-separated tags (max 10):"))
        tag_edit = QLineEdit(self.track_tags_edit.text())
        dlg_layout.addWidget(tag_edit)
        count_label = QLabel()
        dlg_layout.addWidget(count_label)

        def update_count():
            tags = [t.strip() for t in tag_edit.text().split(",") if t.strip()]
            count_label.setText(f"{len(tags)} / 10 tags")
            count_label.setStyleSheet("color: red;" if len(tags) > 10 else "")

        tag_edit.textChanged.connect(update_count)
        update_count()
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        dlg_layout.addWidget(buttons)
        if dialog.exec() == QDialog.Accepted:
            tags = [
                t.strip() for t in tag_edit.text().split(",") if t.strip()
            ][:10]
            self.track_tags_edit.setText(", ".join(tags))
            self.save_selected_track_details()

    def _is_url(self, t): return t.startswith(("http://", "https://"))

    def browse_cover(self):
        if self.is_upload_in_progress(): return
        f, _ = QFileDialog.getOpenFileName(self, "Select Cover Art", str(self.cover_path or ""), "Image files (*.jpg *.jpeg *.png *.gif);;All files (*.*)")
        if f: self.set_cover_path(Path(f)); self.add_to_cover_library(f)

    def clear_cover(self): self.set_cover_path(None)

    def resolve_cover_path_edit(self):
        t = self.cover_path_edit.text().strip()
        if not t: self.set_cover_path(None)
        elif self._is_url(t): self._download_cover_url(t)
        else: self.set_cover_path(Path(t))

    def _download_cover_url(self, url):
        import hashlib, tempfile, os
        try:
            r = requests.get(url, timeout=10); r.raise_for_status()
            sfx = Path(url.split("?")[0]).suffix or ".jpg"
            td = Path(tempfile.gettempdir()) / "bandcamp_auto_uploader_covers"; td.mkdir(parents=True, exist_ok=True)
            tp = td / (hashlib.md5(url.encode()).hexdigest() + sfx); tp.write_bytes(r.content)
            self.set_cover_path(tp); self.add_to_cover_library(str(tp))
            self.statusBar().showMessage("Cover art loaded from URL")
        except Exception as e: self.statusBar().showMessage(f"Failed to download cover: {e}")

    def set_cover_path(self, path):
        self.cover_path = path if path and path.exists() else None
        self.cover_path_edit.setText(str(self.cover_path) if self.cover_path else "")
        self.update_cover_preview(); self.apply_album_details_to_model(); self.queue_album_session_save()

    def auto_detect_cover(self):
        c = self.find_cover_art(Path(self.album_path_edit.text().strip()))
        if c: self.set_cover_path(c); self.statusBar().showMessage(f"Detected cover art: {c.name}")
        else: self.statusBar().showMessage("No cover art found")

    def find_cover_art(self, ap):
        if not ap.is_dir(): return None
        for n in COVER_NAMES:
            c = ap / n
            if c.exists(): return c
        for f in ap.iterdir():
            if f.is_file() and f.suffix.lower() in COVER_SUFFIXES: return f
        return None

    def _pil_image(self, path):
        from PIL import Image, ImageOps
        with Image.open(path) as src:
            img = ImageOps.exif_transpose(src)
            if img.mode in ("RGBA", "LA") or "transparency" in img.info:
                bg = Image.new("RGBA", img.size, "#ffffff"); bg.alpha_composite(img.convert("RGBA"))
                return bg.convert("RGB")
            return img.convert("RGB")

    def _pil_to_pixmap(self, img):
        import io
        b = io.BytesIO(); img.save(b, format="PNG")
        p = QPixmap(); p.loadFromData(b.getvalue(), "PNG"); return p

    def _cover_fit(self, img, sz):
        from PIL import Image
        fm = self.cover_fit_mode_combo.currentText() if hasattr(self, "cover_fit_mode_combo") else "Crop (fill)"
        if fm == "Crop (fill)":
            w, h = img.size; s = min(w, h); l = (w - s) // 2; t = (h - s) // 2
            return img.crop((l, t, l + s, t + s))
        elif fm == "Fit (contain)":
            w, h = img.size; sc = min(sz / w, sz / h); nw, nh = int(w * sc), int(h * sc)
            sq = Image.new("RGB", (sz, sz), (0, 0, 0))
            sq.paste(img.resize((nw, nh), Image.Resampling.LANCZOS), ((sz - nw) // 2, (sz - nh) // 2))
            return sq
        return img.resize((sz, sz), Image.Resampling.LANCZOS)

    def _cover_preview_img(self, path, sz):
        return self._cover_fit(self._pil_image(path), sz).resize((sz, sz), Image.Resampling.LANCZOS)

    def update_cover_preview(self):
        if not self.cover_path or not self.cover_path.exists():
            self.cover_preview.setPixmap(QPixmap())
            self.cover_preview.setText("No cover art\n\nClick Browse" if not self.cover_path else "Cover not found")
            return
        try:
            s = max(self.cover_preview.width(), 150)
            self.cover_preview.setPixmap(self._pil_to_pixmap(self._cover_preview_img(self.cover_path, s)))
            self.cover_preview.setText("")
        except Exception:
            self.cover_preview.setPixmap(QPixmap()); self.cover_preview.setText("Could not load cover")

    def _show_cover_context_menu(self, pos):
        m = QMenu(self); m.addAction("Clear Cover Art", lambda: self.set_cover_path(None))
        m.addAction("View Cover Art", self.view_cover_art); m.exec(self.cover_preview.mapToGlobal(pos))

    def _show_track_context_menu(self, pos):
        row = self.track_table.indexAt(pos).row()
        if row >= 0:
            self.track_table.selectRow(row)

        menu = QMenu(self)

        def a(label, callback, enabled=True, icon=None):
            action = QAction(label, self)
            if icon:
                action.setIcon(QIcon(icon))
            action.setEnabled(enabled)
            action.triggered.connect(callback)
            return action

        sep = False

        if row >= 0:
            if self.config.context_menu_play:
                menu.addAction(a("Play", self._play_selected_track))
                sep = True

            if getattr(self.config, 'context_menu_lock_unlock', True):
                if sep:
                    menu.addSeparator()
                menu.addAction(a("Lock/Unlock", self._lock_unlock_track))
                sep = False

            if self.config.context_menu_remove_track:
                if not sep:
                    menu.addSeparator()
                    sep = False
                menu.addAction(a("Remove Track", self.remove_selected_track))

            moves = []
            if self.config.context_menu_move_up:
                moves.append(("Move Up", self.move_selected_track_up))
            if self.config.context_menu_move_down:
                moves.append(("Move Down", self.move_selected_track_down))
            if getattr(self.config, 'context_menu_move_to_top', True):
                moves.append(("Move to Top", self._move_selected_to_top))
            if getattr(self.config, 'context_menu_move_to_bottom', True):
                moves.append(("Move to Bottom", self._move_selected_to_bottom))
            if moves:
                if not getattr(self.config, 'context_menu_remove_dividers', False):
                    menu.addSeparator()
                for label, cb in moves:
                    menu.addAction(a(label, cb))

            file_ops = []
            if self.config.context_menu_open_file:
                file_ops.append(("Open File Location", self._open_track_file_location))
            if self.config.context_menu_replace_file:
                file_ops.append(("Replace File", self._replace_track_file))
            if getattr(self.config, 'context_menu_extract_cover_art', True):
                file_ops.append(("Extract Cover Art", self._extract_cover_from_track))
            if getattr(self.config, 'context_menu_set_track_cover_as_album_cover', True):
                file_ops.append(("Set Track Cover as Album Cover", self._set_track_cover_as_album_cover))
            if getattr(self.config, 'context_menu_extract_track_info', True):
                file_ops.append(("Extract Track Information", self._extract_track_information))
            if file_ops:
                if not getattr(self.config, 'context_menu_remove_dividers', False):
                    menu.addSeparator()
                for label, cb in file_ops:
                    menu.addAction(a(label, cb))

            meta_ops = []
            if self.config.context_menu_copy_metadata:
                meta_ops.append(("Copy Metadata", self._copy_track_metadata))
            if self.config.context_menu_paste_metadata:
                meta_ops.append(("Paste Metadata", self._paste_track_metadata))
            if getattr(self.config, 'context_menu_revert_to_original', True):
                meta_ops.append(("Revert to Original", self._revert_track_to_original))
            if getattr(self.config, 'context_menu_clear_metadata', True):
                meta_ops.append(("Clear Metadata", self._clear_track_metadata))
            if meta_ops:
                if not getattr(self.config, 'context_menu_remove_dividers', False):
                    menu.addSeparator()
                for label, cb in meta_ops:
                    menu.addAction(a(label, cb))

            if getattr(self.config, 'context_menu_upload_as_single', True):
                if not getattr(self.config, 'context_menu_remove_dividers', False):
                    menu.addSeparator()
                menu.addAction(a("Upload as Single", self._upload_selected_as_single))

        session_ops = []
        if getattr(self.config, 'context_menu_extract_tracklist', True):
            session_ops.append(("Extract Tracklist", self._extract_tracklist))
        if getattr(self.config, 'context_menu_open_session', True):
            session_ops.append(("Open session.txt", self._open_session_file))
        if getattr(self.config, 'context_menu_undo', True):
            session_ops.append(("Undo", self._undo_track_action))
        if getattr(self.config, 'context_menu_redo', True):
            session_ops.append(("Redo", self._redo_track_action))
        if session_ops:
            if not getattr(self.config, 'context_menu_remove_dividers', False):
                menu.addSeparator()
            for label, cb in session_ops:
                menu.addAction(a(label, cb))

        global_ops = []
        if self.config.context_menu_randomize:
            global_ops.append(("Randomize", self._shuffle_tracks))
        if getattr(self.config, 'context_menu_smart_randomize', True):
            global_ops.append(("Smart Randomize", self._smart_randomize_tracks))
        if global_ops:
            if not getattr(self.config, 'context_menu_remove_dividers', False):
                menu.addSeparator()
            for label, cb in global_ops:
                menu.addAction(a(label, cb))

        if getattr(self.config, 'context_menu_sort_by', True) and self.track_table.rowCount() > 0:
            if not getattr(self.config, 'context_menu_remove_dividers', False):
                menu.addSeparator()
            sort_menu = QMenu("Sort By...", self)
            for sort_label, sort_attr in [
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
            ]:
                if getattr(self.config, sort_attr, True):
                    sort_menu.addAction(a(sort_label, lambda a=sort_attr: self._sort_tracks_by(a)))
            if sort_menu.actions():
                menu.addMenu(sort_menu)

        clear_ops = []
        if getattr(self.config, 'context_menu_clear_all_metadata', True):
            clear_ops.append(("Clear All Metadata", self._clear_all_track_metadata))
        if self.config.context_menu_clear_all:
            clear_ops.append(("Clear All Tracks", self._clear_all_tracks))
        if clear_ops:
            if not getattr(self.config, 'context_menu_remove_dividers', False):
                menu.addSeparator()
            for label, cb in clear_ops:
                menu.addAction(a(label, cb))

        if menu.actions():
            menu.exec(self.track_table.viewport().mapToGlobal(pos))

    # ── Track context menu action stubs ──

    def _play_selected_track(self):
        QMessageBox.information(self, "Play", "Audio playback not yet implemented in Qt preview.")

    def _lock_unlock_track(self):
        QMessageBox.information(self, "Lock/Unlock", "Track locking not yet implemented in Qt preview.")

    def _move_selected_to_top(self):
        row = self.selected_row()
        if row <= 0:
            return
        for _ in range(row):
            self.swap_rows(row, row - 1)
            row -= 1
        self.track_table.selectRow(0)
        self.sync_table_to_album()

    def _move_selected_to_bottom(self):
        row = self.selected_row()
        last = self.track_table.rowCount() - 1
        if row < 0 or row >= last:
            return
        for _ in range(last - row):
            self.swap_rows(row, row + 1)
            row += 1
        self.track_table.selectRow(last)
        self.sync_table_to_album()

    def _open_track_file_location(self):
        row = self.selected_row()
        if row < 0:
            return
        path = self.table_text(row, COL_PATH)
        QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(path)))

    def _replace_track_file(self):
        QMessageBox.information(self, "Replace File", "File replacement not yet implemented in Qt preview.")

    def _extract_cover_from_track(self):
        QMessageBox.information(self, "Extract Cover", "Cover extraction not yet implemented in Qt preview.")

    def _set_track_cover_as_album_cover(self):
        QMessageBox.information(self, "Set Cover", "Setting track cover as album cover not yet implemented in Qt preview.")

    def _extract_track_information(self):
        QMessageBox.information(self, "Track Info", "Track info extraction not yet implemented in Qt preview.")

    def _copy_track_metadata(self):
        QMessageBox.information(self, "Copy Metadata", "Metadata copy not yet implemented in Qt preview.")

    def _paste_track_metadata(self):
        QMessageBox.information(self, "Paste Metadata", "Metadata paste not yet implemented in Qt preview.")

    def _revert_track_to_original(self):
        QMessageBox.information(self, "Revert", "Revert to original not yet implemented in Qt preview.")

    def _clear_track_metadata(self):
        QMessageBox.information(self, "Clear Metadata", "Clear metadata not yet implemented in Qt preview.")

    def _upload_selected_as_single(self):
        QMessageBox.information(self, "Upload as Single", "Upload as single not yet implemented in Qt preview.")

    def _extract_tracklist(self):
        QMessageBox.information(self, "Tracklist", "Tracklist extraction not yet implemented in Qt preview.")

    def _open_session_file(self):
        QMessageBox.information(self, "Session", "Session file not yet implemented in Qt preview.")

    def _undo_track_action(self):
        QMessageBox.information(self, "Undo", "Undo not yet implemented in Qt preview.")

    def _redo_track_action(self):
        QMessageBox.information(self, "Redo", "Redo not yet implemented in Qt preview.")

    def _shuffle_tracks(self):
        QMessageBox.information(self, "Shuffle", "Shuffle not yet implemented in Qt preview.")

    def _smart_randomize_tracks(self):
        QMessageBox.information(self, "Smart Randomize", "Smart randomize not yet implemented in Qt preview.")

    def _sort_tracks_by(self, sort_attr):
        QMessageBox.information(self, "Sort", f"Sort by {sort_attr} not yet implemented in Qt preview.")

    def _clear_all_track_metadata(self):
        QMessageBox.information(self, "Clear All Metadata", "Clear all metadata not yet implemented in Qt preview.")

    def _clear_all_tracks(self):
        QMessageBox.information(self, "Clear All", "Clear all tracks not yet implemented in Qt preview.")

    def view_cover_art(self):
        if not self.cover_path or not self.cover_path.exists():
            QMessageBox.information(self, "No Cover Art", "No cover art selected."); return
        try:
            img = self._cover_fit(self._pil_image(self.cover_path), 2000)
            w, h = img.size; md = 800
            if w > md or h > md: s = md / max(w, h); dw, dh = int(w * s), int(h * s)
            else: dw, dh = w, h
            d = QDialog(self); d.setWindowTitle(f"Cover Art ({w}x{h})"); d.resize(dw, dh)
            l = QLabel(); l.setPixmap(self._pil_to_pixmap(img.resize((dw, dh), Image.Resampling.LANCZOS)))
            l.setAlignment(Qt.AlignCenter); l.setStyleSheet("background: black;")
            vl = QVBoxLayout(d); vl.setContentsMargins(0, 0, 0, 0); vl.addWidget(l)
            d.setAttribute(Qt.WA_DeleteOnClose); d.exec()
        except Exception as e: QMessageBox.critical(self, "Error", f"Failed to view cover:\n{e}")

    def _build_cover_grid(self, items, win_title, btn_size):
        d = QDialog(self); d.setWindowTitle(win_title); d.resize(640, 500)
        s = QScrollArea(d); s.setWidgetResizable(True); c = QWidget(); g = QGridLayout(c); g.setSpacing(8)
        from PIL import Image
        r = co = 0; cols = 4
        for path, label in items:
            if not Path(path).exists(): continue
            try:
                im = Image.open(path); im.thumbnail((120, 120), Image.Resampling.LANCZOS)
                px = self._pil_to_pixmap(im.convert("RGB"))
                b = QPushButton(label); b.setIcon(QIcon(px)); b.setIconSize(px.size())
                b.setFixedSize(*btn_size); b.setToolTip(path)
                b.clicked.connect(lambda _checked, p=path: [self.set_cover_path(Path(p)), d.accept()])
                g.addWidget(b, r, co); co += 1
                if co >= cols: co = 0; r += 1
            except Exception: continue
        s.setWidget(c); vl = QVBoxLayout(d); vl.addWidget(s)
        if g.count(): d.exec()

    def manage_cover_art_library(self):
        lib = getattr(self.config, "cover_art_library", [])
        if not lib: QMessageBox.information(self, "Cover Library", "No cover art in library yet."); return
        self._build_cover_grid([(p, "") for p in lib], "Cover Art Library", (130, 130))

    def add_to_cover_library(self, p):
        if not p or not Path(p).exists() or not hasattr(self.config, "cover_art_library"): return
        if p not in self.config.cover_art_library:
            self.config.cover_art_library.insert(0, p)
            self.config.cover_art_library = self.config.cover_art_library[:20]; save_config(self.config)

    def _extract_cover_data(self, fd):
        cd = mime = None
        from mutagen.flac import FLAC as _F; from mutagen.oggvorbis import OggVorbis as _O; from mutagen.oggopus import OggOpus as _P
        if isinstance(fd, (_F, _O, _P)) and fd.pictures:
            cd = fd.pictures[0].data; mime = fd.pictures[0].mime
        elif hasattr(fd, "tags") and fd.tags is not None:
            pics = fd.tags.getall("APIC")
            if pics: cd = pics[0].data; mime = pics[0].mime
            from mutagen.mp4 import MP4Cover as _M
            if cd is None and "covr" in fd.tags:
                c = fd.tags["covr"][0]; cd = bytes(c)
                mime = "image/png" if isinstance(c, _M) and c.imageformat == _M.FORMAT_PNG else "image/jpeg"
        return cd, mime

    def detect_cover_from_tracks(self):
        if self.is_upload_in_progress(): return
        import tempfile, os, mutagen
        ap = Path(self.album_path_edit.text().strip())
        tracks = [f for e in ["*.wav", "*.flac", "*.aiff", "*.mp3", "*.ogg", "*.opus", "*.m4a", "*.aac", "*.mod", "*.xm"]
                  for f in ([*ap.glob(e)] + [*ap.glob(e.upper())])] if ap.is_dir() else []
        if not tracks: QMessageBox.information(self, "Detect Cover", "No tracks found in album folder."); return
        covers = []
        for tp in tracks:
            try:
                fd = mutagen.File(tp)
                cd, mime = self._extract_cover_data(fd) if fd else (None, None)
                if cd:
                    ext = ".jpg" if "jpeg" in mime else ".png"
                    tf, tn = tempfile.mkstemp(suffix=ext)
                    with os.fdopen(tf, "wb") as f: f.write(cd)
                    from PIL import Image; im = Image.open(tn)
                    covers.append({"path": tn, "track": tp.name, "size": f"{im.width}x{im.height}"})
            except Exception: continue
        if not covers: QMessageBox.information(self, "Detect Cover", "No embedded cover art found."); return
        self._build_cover_grid([(c["path"], f"{c['track']}\n{c['size']}") for c in covers], "Select Detected Cover Art", (140, 150))

    def _on_scale_cover_changed(self, c):
        self.config.always_auto_scale_cover = c; save_config(self.config); self.update_cover_preview()

    def _on_fit_mode_changed(self, t):
        self.config.cover_fit_mode = t; save_config(self.config); self.update_cover_preview()

    def prepare_progress_from_album(self, album: Album):
        self.clear_progress_rows()
        if not album.tracks:
            self.progress_placeholder.setText("No tracks queued")
            self.progress_placeholder.show()
            return
        self.progress_placeholder.hide()
        for index, track in enumerate(album.tracks, 1):
            self.add_progress_row(
                f"{index}. {track.track_data.title or track.path.name}",
                "Queued",
                0,
            )

    def clear_progress_rows(self):
        while self.progress_list_layout.count():
            item = self.progress_list_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.progress_rows = []
        self.progress_placeholder.setText("No upload in progress")
        self.progress_placeholder.show()

    def add_progress_row(self, title: str, status: str, value: int):
        row = QWidget()
        layout = QVBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        header = QHBoxLayout()
        title_label = QLabel(title)
        title_label.setObjectName("progressTitle")
        status_label = QLabel(status)
        status_label.setObjectName("mutedLabel")
        header.addWidget(title_label, 1)
        header.addWidget(status_label)
        layout.addLayout(header)
        progress = QProgressBar()
        progress.setRange(0, 100)
        progress.setValue(max(0, min(100, value)))
        layout.addWidget(progress)
        self.progress_list_layout.addWidget(row)
        self.progress_rows.append((title_label, status_label, progress))

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if not urls:
            return
        path = Path(urls[0].toLocalFile())
        if path.is_dir():
            self.album_path_edit.setText(str(path))
            self.preview_album()
            return
        if path.is_file() and path.suffix.lower() in COVER_SUFFIXES:
            self.set_cover_path(path)
            return

    def populate_track_table(self, album: Album):
        self._loading_table = True
        try:
            self.track_table.setRowCount(0)
            for index, track in enumerate(album.tracks, 1):
                data = track.track_data
                values = (
                    str(index),
                    data.artist or "",
                    data.title or "",
                    data.download_desc or getattr(data, "about", "") or "",
                    "",
                    track.path.suffix,
                    format_price(data.price),
                    "Yes" if data.nyp else "No",
                    str(track.path),
                )
                row = self.track_table.rowCount()
                self.track_table.insertRow(row)
                for column, value in enumerate(values):
                    item = QTableWidgetItem(value)
                    if column not in EDITABLE_COLUMNS:
                        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                    if column in (COL_NO, COL_NYP):
                        item.setTextAlignment(Qt.AlignCenter)
                    self.track_table.setItem(row, column, item)
        finally:
            self._loading_table = False
        if self.track_table.rowCount():
            self.track_table.selectRow(0)
        else:
            self.on_track_select()
        for attr in ("show_track_no", "show_artist", "show_track_name",
                      "show_comment", "show_length", "show_extension",
                      "show_price", "show_nyp"):
            handler = getattr(self, f"_apply_{attr}", None)
            if handler:
                handler()

    def selected_row(self) -> int:
        ranges = self.track_table.selectedRanges()
        if not ranges:
            return -1
        return ranges[0].topRow()

    def table_text(self, row: int, column: int) -> str:
        item = self.track_table.item(row, column)
        return item.text().strip() if item else ""

    def set_table_text(self, row: int, column: int, value: str):
        item = self.track_table.item(row, column)
        if item is None:
            item = QTableWidgetItem()
            self.track_table.setItem(row, column, item)
        item.setText(value)

    def on_track_cell_changed(self, row: int, column: int):
        if self._loading_table:
            return
        if column == COL_PRICE:
            self._loading_table = True
            try:
                self.set_table_text(
                    row, column, format_price(self.table_text(row, column))
                )
            finally:
                self._loading_table = False
        elif column == COL_NYP:
            value = self.table_text(row, column).lower()
            self._loading_table = True
            try:
                self.set_table_text(
                    row,
                    column,
                    "No" if value in {"0", "false", "no", "n", "off"} else "Yes",
                )
            finally:
                self._loading_table = False
        self.sync_table_to_album()
        if row == self.selected_row():
            self._load_track_details_for_row(row)

    def sync_table_to_album(self):
        if self.current_album is None:
            return
        tracks_by_path = {
            str(track.path): track for track in self.current_album.tracks
        }
        tracks = []
        for row in range(self.track_table.rowCount()):
            path = self.table_text(row, COL_PATH)
            track = tracks_by_path.get(path)
            if track is None:
                continue
            data = track.track_data
            data.track_number = row + 1
            data.artist = self.table_text(row, COL_ARTIST)
            data.title = self.table_text(row, COL_TITLE)
            data.download_desc = self.table_text(row, COL_COMMENT)
            data.price = normalize_price(
                self.table_text(row, COL_PRICE), default=""
            )
            data.nyp = int(
                self.table_text(row, COL_NYP).lower()
                not in {"0", "false", "no", "n", "off"}
            )

            editor = self.track_editor_data.get(path, {})
            if editor:
                if editor.get("tags"):
                    data.tags = editor["tags"]
                if editor.get("description"):
                    data.about = editor["description"]
                if editor.get("lyrics"):
                    data.lyrics = editor["lyrics"]
                if editor.get("credits"):
                    data.credits = editor["credits"]
                if editor.get("license") and editor["license"] in LICENSE_MAP:
                    data.license_type = LICENSE_MAP[editor["license"]]
                if editor.get("release_date"):
                    data.release_date = editor["release_date"]
                if editor.get("isrc"):
                    data.isrc = editor["isrc"]
                if editor.get("iswc"):
                    data.iswc = editor["iswc"]
                data.streaming = int(editor.get("streaming", True))
                data.enable_download = int(editor.get("enable_download", True))
                data.private = int(editor.get("private", False))
                data.featured = int(editor.get("featured", False))
                if editor.get("price"):
                    data.price = editor["price"]
                if "nyp" in editor:
                    data.nyp = int(editor["nyp"])
                if editor.get("video_id"):
                    data.video_id = editor["video_id"]
                if editor.get("video_caption"):
                    data.video_caption = editor["video_caption"]

            tracks.append(track)
        self.current_album.tracks = tracks
        self.renumber_table()
        self.prepare_progress_from_album(self.current_album)
        self.queue_album_session_save()
        self.statusBar().showMessage(f"{len(tracks)} track(s) in preview")

    def renumber_table(self):
        self._loading_table = True
        try:
            for row in range(self.track_table.rowCount()):
                self.set_table_text(row, COL_NO, str(row + 1))
        finally:
            self._loading_table = False

    def guess_track_title_case(self, title: str) -> str:
        small_words = {
            "a", "an", "and", "as", "at", "but", "by", "for", "from", "in",
            "into", "nor", "of", "on", "onto", "or", "over", "per", "so",
            "the", "to", "up", "via", "vs", "with", "yet",
        }
        preserve_upper = {
            "AI", "CD", "DJ", "EP", "LP", "MC", "TV", "UK", "US", "USA",
            "USB", "VIP", "VR", "III", "IV", "VI", "VII", "VIII", "IX", "XI",
            "XII", "XIII", "XIV", "XV", "XVI", "XVII", "XVIII", "XIX", "XX",
        }

        cleaned = re.sub(r"[_\s]+", " ", str(title).strip())
        if not cleaned:
            return ""

        tokens = re.findall(
            r"[A-Za-z0-9]+(?:'[A-Za-z0-9]+)?|[^A-Za-z0-9]+", cleaned
        )
        word_indexes = [
            index
            for index, token in enumerate(tokens)
            if re.match(r"[A-Za-z0-9]", token)
        ]
        if not word_indexes:
            return cleaned
        first_word = word_indexes[0]
        last_word = word_indexes[-1]

        def format_word(word: str, token_index: int) -> str:
            upper_word = word.upper()
            lower_word = word.lower()
            if upper_word in preserve_upper:
                return upper_word
            if (
                token_index not in (first_word, last_word)
                and lower_word in small_words
            ):
                return lower_word
            parts = lower_word.split("'")
            cased = "'".join(
                part[:1].upper() + part[1:] if part else part for part in parts
            )
            cased = re.sub(
                r"'(M|S|T|Re|Ve|Ll|D)\b",
                lambda match: "'" + match.group(1).lower(),
                cased,
            )
            return re.sub(
                r"\bMc([a-z])",
                lambda match: "Mc" + match.group(1).upper(),
                cased,
            )

        result = []
        force_cap_next = True
        for index, token in enumerate(tokens):
            if re.match(r"[A-Za-z0-9]", token):
                token_index = (
                    first_word
                    if force_cap_next and token.lower() in small_words
                    else index
                )
                result.append(format_word(token, token_index))
                force_cap_next = False
            else:
                result.append(token)
                if any(
                    mark in token
                    for mark in (":", "?", "!", ".", "-", "(", "[", "{", "/", "\\")
                ):
                    force_cap_next = True
        return "".join(result)

    def apply_guess_case_to_track_titles(self):
        if self.track_table.rowCount() == 0:
            self.statusBar().showMessage("No tracks to update")
            return
        changed = 0
        self._loading_table = True
        try:
            for row in range(self.track_table.rowCount()):
                old_title = self.table_text(row, COL_TITLE)
                new_title = self.guess_track_title_case(old_title)
                if new_title and new_title != old_title:
                    self.set_table_text(row, COL_TITLE, new_title)
                    changed += 1
        finally:
            self._loading_table = False
        self.sync_table_to_album()
        self.statusBar().showMessage(
            f"Guess Case applied to {changed} track title(s)"
            if changed
            else "Track titles already look good"
        )

    def parse_track_from_filename(self, stem: str):
        for pattern, track_group, artist_group, title_group in FILENAME_PATTERNS:
            match = re.match(pattern, stem, re.IGNORECASE)
            if not match:
                continue
            track_no = None
            artist = None
            title = None
            if track_group is not None:
                try:
                    track_no = int(match.group(track_group))
                except (IndexError, ValueError):
                    pass
            if artist_group is not None:
                try:
                    artist = re.sub(
                        r"[_\s]+", " ", match.group(artist_group)
                    ).strip()
                except IndexError:
                    pass
            if title_group is not None:
                try:
                    title = re.sub(
                        r"[_\s]+", " ", match.group(title_group)
                    ).strip()
                except IndexError:
                    pass
            return track_no, artist, title
        return None, None, None

    def apply_extract_from_filename(self):
        if self.track_table.rowCount() == 0:
            self.statusBar().showMessage("No tracks to update")
            return

        changed = 0
        parsed_numbers = {}
        self._loading_table = True
        try:
            for row in range(self.track_table.rowCount()):
                path = self.table_text(row, COL_PATH)
                if not path:
                    continue
                old_artist = self.table_text(row, COL_ARTIST)
                old_title = self.table_text(row, COL_TITLE)
                (
                    parsed_no,
                    parsed_artist,
                    parsed_title,
                ) = self.parse_track_from_filename(Path(path).stem)
                if parsed_no is not None:
                    parsed_numbers[row] = parsed_no
                    self.set_table_text(row, COL_NO, str(parsed_no))
                if parsed_artist:
                    self.set_table_text(row, COL_ARTIST, parsed_artist)
                if parsed_title:
                    self.set_table_text(row, COL_TITLE, parsed_title)
                if (
                    old_artist != self.table_text(row, COL_ARTIST)
                    or old_title != self.table_text(row, COL_TITLE)
                ):
                    changed += 1
            if parsed_numbers:
                self.sort_table_by_display_numbers(parsed_numbers)
        finally:
            self._loading_table = False
        self.sync_table_to_album()
        self.statusBar().showMessage(
            f"Extracted filename data from {changed} track(s)"
            if changed
            else "No filename changes needed"
        )

    def sort_table_by_display_numbers(
        self, parsed_numbers: dict[int, int]
    ):
        rows = []
        for row in range(self.track_table.rowCount()):
            values = [
                self.table_text(row, column)
                for column in range(self.track_table.columnCount())
            ]
            rows.append((parsed_numbers.get(row, row + 1), row, values))
        rows.sort(key=lambda item: (item[0], item[1]))
        for row_index, (_parsed_no, _old_row, values) in enumerate(rows):
            for column, value in enumerate(values):
                self.set_table_text(row_index, column, value)

    def remove_selected_track(self):
        row = self.selected_row()
        if row < 0:
            return
        path = self.table_text(row, COL_PATH)
        if path in self.track_editor_data:
            del self.track_editor_data[path]
        self.track_table.removeRow(row)
        self.sync_table_to_album()
        if self.track_table.rowCount():
            self.track_table.selectRow(
                min(row, self.track_table.rowCount() - 1)
            )
        else:
            self.on_track_select()

    def move_selected_track_up(self):
        row = self.selected_row()
        if row <= 0:
            return
        self.swap_rows(row, row - 1)
        self.track_table.selectRow(row - 1)
        self.sync_table_to_album()

    def move_selected_track_down(self):
        row = self.selected_row()
        if row < 0 or row >= self.track_table.rowCount() - 1:
            return
        self.swap_rows(row, row + 1)
        self.track_table.selectRow(row + 1)
        self.sync_table_to_album()

    def swap_rows(self, first: int, second: int):
        self._loading_table = True
        try:
            first_values = [
                self.table_text(first, column)
                for column in range(self.track_table.columnCount())
            ]
            second_values = [
                self.table_text(second, column)
                for column in range(self.track_table.columnCount())
            ]
            for column, value in enumerate(second_values):
                self.set_table_text(first, column, value)
            for column, value in enumerate(first_values):
                self.set_table_text(second, column, value)
        finally:
            self._loading_table = False

    def save_selected_track_details(self):
        if self._loading_details:
            return
        self._save_current_track_details()

    def track_for_row(self, row: int):
        if self.current_album is None:
            return None
        path = self.table_text(row, COL_PATH)
        for track in self.current_album.tracks:
            if str(track.path) == path:
                return track
        return None

    def sanitize_price_edit(self, edit: QLineEdit, default: str):
        edit.setText(format_price(edit.text(), default=default))

    def sanitize_date_edit(self, edit: QLineEdit):
        edit.setText(normalize_release_date(edit.text()))

    # ── Log Panel ────────────────────────────────────────────────────

    def _build_log_dock(self):
        self.log_dock = QDockWidget("Logs", self)
        self.log_dock.setObjectName("logDock")
        self.log_dock.setFeatures(
            QDockWidget.DockWidgetClosable | QDockWidget.DockWidgetMovable
        )

        log_container = QWidget()
        log_layout = QVBoxLayout(log_container)
        log_layout.setContentsMargins(6, 6, 6, 6)
        log_layout.setSpacing(4)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setObjectName("logText")
        self.log_text.setFont(QFont("Consolas", 9))
        log_layout.addWidget(self.log_text, 1)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)

        clear_btn = QPushButton("Clear Logs")
        clear_btn.clicked.connect(self.log_text.clear)
        btn_row.addWidget(clear_btn)

        copy_btn = QPushButton("Copy Logs")
        copy_btn.clicked.connect(self._copy_logs)
        btn_row.addWidget(copy_btn)

        open_folder_btn = QPushButton("Open Log Folder")
        open_folder_btn.clicked.connect(self._open_log_folder)
        btn_row.addWidget(open_folder_btn)

        export_btn = QPushButton("Export Bug Report")
        export_btn.clicked.connect(self._export_bug_report)
        btn_row.addWidget(export_btn)

        btn_row.addStretch(1)
        log_layout.addLayout(btn_row)

        self.log_dock.setWidget(log_container)
        self.addDockWidget(Qt.BottomDockWidgetArea, self.log_dock)
        self.log_dock.hide()

    def _build_view_menu(self):
        view_menu = self.menuBar().addMenu("View")
        self.toggle_log_action = view_menu.addAction("Show Logs")
        self.toggle_log_action.setCheckable(True)
        self.toggle_log_action.setChecked(False)
        self.toggle_log_action.triggered.connect(self._toggle_log_dock)
        self.log_dock.visibilityChanged.connect(
            lambda visible: self.toggle_log_action.setChecked(visible)
        )

    def _toggle_log_dock(self):
        if self.log_dock.isVisible():
            self.log_dock.hide()
        else:
            self.log_dock.show()
            self.log_dock.raise_()

    def _copy_logs(self):
        clipboard = QApplication.clipboard()
        clipboard.setText(self.log_text.toPlainText())
        self.statusBar().showMessage("Logs copied to clipboard")

    def _open_log_folder(self):
        import subprocess
        log_dir = self._get_app_log_dir()
        log_dir.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(log_dir)))

    def _get_app_log_dir(self) -> Path:
        from bandcamp_auto_uploader.config import get_app_data_dir
        return get_app_data_dir() / "Logs"

    def _get_app_log_file_path(self) -> Path:
        if not hasattr(self, "_app_log_file_path"):
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            self._app_log_file_path = self._get_app_log_dir() / f"bau_{timestamp}.log"
        return self._app_log_file_path

    def _cleanup_old_log_files(self):
        log_dir = self._get_app_log_dir()
        if not log_dir.exists():
            return
        limit = getattr(self.config, "log_file_limit", 3)
        if limit < 1:
            limit = 3
        log_files = sorted(
            log_dir.glob("bau_*.log"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for old_file in log_files[limit:]:
            try:
                old_file.unlink()
            except Exception:
                pass

    def _export_bug_report(self):
        log_path = self._get_app_log_file_path()
        try:
            self._write_support_snapshot(log_path)
            self.statusBar().showMessage(f"Bug report appended to {log_path}")
            QMessageBox.information(
                self,
                "Bug Report Saved",
                f"A diagnostic snapshot has been appended to:\n{log_path}\n\n"
                "Review the file before sharing it publicly.",
            )
        except Exception as e:
            QMessageBox.warning(self, "Export Failed", str(e))

    def _write_support_snapshot(self, log_path: Path):
        lines = ["", "=" * 60, "SUPPORT SNAPSHOT", "=" * 60]
        lines.append(f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"Version: {__version__}")
        lines.append(f"Artist: {self.selected_artist_url or 'None'}")
        lines.append(f"Album: {self.album_name_edit.text() or 'None'}")
        lines.append(f"Tracks: {self.track_table.rowCount()}")
        lines.append("")
        lines.append("Recent logs:")
        text = self.log_text.toPlainText()
        last_lines = text.split("\n")[-200:]
        lines.extend(last_lines)
        with log_path.open("a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

    def setup_logging(self):
        logger.setLevel(
            logging.DEBUG
            if (self.config.debug or getattr(self.config, "log_to_file", True))
            else logging.INFO
        )
        for handler in list(logger.handlers):
            if getattr(handler, "_bau_qt_handler", False):
                logger.removeHandler(handler)
                try:
                    handler.close()
                except Exception:
                    pass

        queue_handler = QueueHandler(self.log_queue)
        queue_handler.setLevel(
            logging.INFO if not self.config.debug else logging.DEBUG
        )
        queue_handler._bau_qt_handler = True
        gui_formatter = logging.Formatter(
            "%(asctime)s - %(levelname)s - %(message)s", datefmt="%H:%M:%S"
        )
        queue_handler.setFormatter(gui_formatter)
        logger.addHandler(queue_handler)

        if getattr(self.config, "log_to_file", True):
            log_path = self._get_app_log_file_path()
            log_path.parent.mkdir(parents=True, exist_ok=True)
            file_handler = logging.FileHandler(log_path, encoding="utf-8")
            file_level_name = str(
                getattr(self.config, "log_file_level", "INFO")
            ).upper()
            file_handler.setLevel(
                getattr(logging, file_level_name, logging.INFO)
            )
            file_formatter = logging.Formatter(
                "%(asctime)s.%(msecs)03d | %(levelname)-8s | %(threadName)s | %(name)s | %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
            file_handler.setFormatter(file_formatter)
            logger.addHandler(file_handler)

        self._cleanup_old_log_files()
        logger.info("Qt logging initialized")

    def _start_log_monitor(self):
        self._log_timer = QTimer()
        self._log_timer.timeout.connect(self.monitor_logs)
        self._log_timer.start(100)

    def monitor_logs(self):
        try:
            while True:
                item = self.log_queue.get_nowait()
                if isinstance(item, tuple):
                    message, levelno = item
                else:
                    message = item
                    levelno = logging.INFO

                color_map = {
                    logging.DEBUG: "#888888",
                    logging.INFO: "#00ff00",
                    logging.WARNING: "#ffff00",
                    logging.ERROR: "#ff0000",
                    logging.CRITICAL: "#ff0000",
                }
                color = color_map.get(levelno, "#ffffff")

                self.log_text.setTextColor(QColor(color))
                self.log_text.append(message)
                self.log_text.setTextColor(QColor("#ffffff"))

                max_lines = getattr(self.config, "log_max_lines", 1000)
                if max_lines > 0:
                    doc = self.log_text.document()
                    if doc.blockCount() > max_lines:
                        cursor = QTextCursor(doc.begin())
                        cursor.movePosition(
                            QTextCursor.Down,
                            QTextCursor.KeepAnchor,
                            doc.blockCount() - max_lines,
                        )
                        cursor.removeSelectedText()
                        doc.setPlainText(doc.toPlainText().strip() + "\n")
        except queue.Empty:
            pass

    def _start_toast_monitor(self):
        self._toast_timer = QTimer()
        self._toast_timer.timeout.connect(self._process_toast_queue)
        self._toast_timer.start(200)

    def _process_toast_queue(self):
        try:
            msg, dur, typ = self.toast_queue.get_nowait()
            self._display_toast(msg, dur, typ)
        except queue.Empty:
            pass

    def show_toast(self, msg, dur=3000, typ="info", trigger=None):
        if not getattr(self.config, "enable_toasts", True):
            return
        if trigger:
            key = f"notify_on_{trigger}"
            if not getattr(self.config, key, False):
                return
        dur = getattr(self.config, "toast_duration", 3) * 1000
        self.toast_queue.put((msg, dur, typ))

    def _display_toast(self, msg, dur, typ):
        accent = {"info": "#38bdf8", "success": "#22c55e", "warning": "#f59e0b", "error": "#ef4444"}.get(typ, "#38bdf8")
        t = QDialog(self)
        t.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint)
        t.setAttribute(Qt.WA_TranslucentBackground)
        t.setAttribute(Qt.WA_DeleteOnClose)
        bg = getattr(self.config, "toast_bg_color", "#1f2933")
        t.setStyleSheet(f"#toast{{background:{bg};border:1px solid {accent};border-radius:8px;}}"
                        f"#l{{color:{getattr(self.config,'toast_text_color','#f8fafc')};padding:10px 32px 10px 14px;font-size:10pt;}}")
        t.setObjectName("toast")
        l = QLabel(msg, t); l.setObjectName("l"); l.setWordWrap(True)
        cb = QLabel("\u00d7", t); cb.setStyleSheet("color:#94a3b8;font-size:14pt;padding:4px;")
        cb.adjustSize()
        vl = QVBoxLayout(t); vl.setContentsMargins(0, 0, 0, 0); vl.addWidget(l)
        t.adjustSize(); tw = min(t.width() + 28, 400); t.setFixedWidth(tw)
        cb.move(tw - cb.width() - 6, 4)
        cb.mousePressEvent = lambda e: t.close()
        cb.enterEvent = lambda e: cb.setStyleSheet(f"color:{accent};font-size:14pt;padding:4px;")
        cb.leaveEvent = lambda e: cb.setStyleSheet("color:#94a3b8;font-size:14pt;padding:4px;")
        pos = getattr(self.config, "toast_position", "top-right")
        rx = self.x() + (self.width() - tw - 20 if "right" in pos else 20)
        ry = self.y() + (60 if "top" in pos else self.height() - t.height() - 20)
        t.move(rx, ry); t.show()
        QTimer.singleShot(dur, t.close)

    # ── Album Session Files ──────────────────────────────────────────

    def get_album_session_file_path(self, album_path: Path | None = None) -> Path | None:
        ap = album_path or self._album_path_for_session
        if not ap or not ap.is_dir():
            return None
        return ap / "session.txt"

    def get_album_session_details(self) -> dict:
        return {
            "album_name": self.album_name_edit.text().strip(),
            "artist": self.artist_edit.text().strip(),
            "release_date": normalize_release_date(self.release_date_edit.text()),
            "tags": self.tags_edit.text().strip(),
            "description": self.description_edit.toPlainText().strip(),
            "credits": self.credits_edit.toPlainText().strip(),
            "license": self.license_combo.currentText(),
            "download_description": self.download_desc_edit.text().strip(),
            "release_message": self.release_message_edit.text().strip(),
            "album_price": normalize_price(self.album_price_edit.text(), default="0"),
            "album_nyp": self.album_nyp_check.isChecked(),
            "subscriber_message": self.subscriber_message_edit.text().strip(),
            "record_label": self.record_label_edit.text().strip(),
            "catalog_number": self.catalog_number_edit.text().strip(),
            "upc": self.upc_edit.text().strip(),
            "cover_art": str(self.cover_path) if self.cover_path else "",
            "require_email": self.require_email_check.isChecked(),
            "public": self.album_public_check.isChecked(),
            "pro": self.pro_check.isChecked(),
            "composer": self.composer_edit.text().strip(),
            "publisher": self.publisher_edit.text().strip(),
        }

    def get_album_session_payload(self) -> dict:
        rows = []
        for row in range(self.track_table.rowCount()):
            rows.append({
                "track_no": self.table_text(row, COL_NO),
                "artist": self.table_text(row, COL_ARTIST),
                "track_name": self.table_text(row, COL_TITLE),
                "comment": self.table_text(row, COL_COMMENT),
                "file_path": self.table_text(row, COL_PATH),
                "price": self.table_text(row, COL_PRICE),
                "nyp": self.table_text(row, COL_NYP),
            })
        return {
            "version": 1,
            "saved_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "album_path": str(self._album_path_for_session) if self._album_path_for_session else "",
            "album_details": self.get_album_session_details(),
            "track_columns": list(TRACK_COLUMNS),
            "tracks": rows,
            "track_editor_data": {
                k: v for k, v in self.track_editor_data.items() if v
            },
        }

    def render_album_session_text(self, payload: dict) -> str:
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
            num = row.get("track_no", "")
            artist = row.get("artist", "")
            title = row.get("track_name", "")
            comment = row.get("comment", "")
            fp = row.get("file_path", "")
            line = f"{num}. {artist} - {title}".strip()
            lines.append(line)
            if comment:
                lines.append(f"   Comment: {comment}")
            lines.append(f"   File: {fp}")

        lines.extend([
            "",
            "--- BEGIN BAU SESSION JSON ---",
            json.dumps(payload, indent=2, ensure_ascii=False),
            "--- END BAU SESSION JSON ---",
            "",
        ])
        return "\n".join(lines)

    def read_album_session_payload(self, session_path: Path) -> dict | None:
        try:
            text = session_path.read_text(encoding="utf-8")
        except Exception:
            return None
        begin = "--- BEGIN BAU SESSION JSON ---"
        end = "--- END BAU SESSION JSON ---"
        if begin not in text or end not in text:
            return None
        json_text = text.split(begin, 1)[1].split(end, 1)[0].strip()
        try:
            return json.loads(json_text)
        except json.JSONDecodeError:
            return None

    def queue_album_session_save(self, delay_ms: int = 700):
        if not getattr(self.config, "create_album_session_files", True):
            return
        if self._album_session_loading:
            return
        if not self._album_path_for_session:
            return
        if self._album_session_save_timer is not None:
            self._album_session_save_timer.stop()
        self._album_session_save_timer = QTimer.singleShot(delay_ms, self.save_album_session_file)

    def save_album_session_file(self):
        self._album_session_save_timer = None
        if not getattr(self.config, "create_album_session_files", True):
            return
        if self._album_session_loading:
            return
        session_path = self.get_album_session_file_path()
        if not session_path:
            return
        try:
            payload = self.get_album_session_payload()
            session_path.write_text(self.render_album_session_text(payload), encoding="utf-8")
        except Exception as e:
            logger.warning(f"Failed to save album session file: {e}")

    def apply_album_session_details(self, details: dict):
        self._loading_album_details = True
        try:
            self.album_name_edit.setText(details.get("album_name", ""))
            self.artist_edit.setText(details.get("artist", ""))
            self.release_date_edit.setText(
                normalize_release_date(details.get("release_date", ""))
            )
            self.tags_edit.setText(details.get("tags", ""))
            self.description_edit.setPlainText(details.get("description", ""))
            self.credits_edit.setPlainText(details.get("credits", ""))
            license_text = details.get("license", "All Rights Reserved")
            idx = self.license_combo.findText(license_text)
            self.license_combo.setCurrentIndex(idx if idx >= 0 else 0)
            self.download_desc_edit.setText(details.get("download_description", ""))
            self.release_message_edit.setText(details.get("release_message", ""))
            self.album_price_edit.setText(
                format_price(details.get("album_price", "0"), default="0")
            )
            self.album_nyp_check.setChecked(details.get("album_nyp", True))
            self.subscriber_message_edit.setText(details.get("subscriber_message", ""))
            self.record_label_edit.setText(details.get("record_label", ""))
            self.catalog_number_edit.setText(details.get("catalog_number", ""))
            self.upc_edit.setText(details.get("upc", ""))
            self.require_email_check.setChecked(details.get("require_email", False))
            self.album_public_check.setChecked(details.get("public", True))
            self.pro_check.setChecked(details.get("pro", False))
            self.composer_edit.setText(details.get("composer", ""))
            self.publisher_edit.setText(details.get("publisher", ""))
            cover = details.get("cover_art", "")
            self.set_cover_path(Path(cover) if cover else None)
        finally:
            self._loading_album_details = False

    def apply_album_session_tracks(self, payload: dict):
        saved_rows = payload.get("tracks", [])
        if not saved_rows:
            return
        current_by_path: dict[str, list[str]] = {}
        for row in range(self.track_table.rowCount()):
            fp = self.table_text(row, COL_PATH)
            if fp:
                vals = [
                    self.table_text(row, c) for c in range(len(TRACK_COLUMNS))
                ]
                current_by_path[fp] = vals

        used_paths: set[str] = set()
        restored: list[list[str]] = []
        for srow in saved_rows:
            fp = str(srow.get("file_path", "")).strip()
            if fp and fp not in current_by_path:
                continue
            vals = list(current_by_path.get(fp, [""] * len(TRACK_COLUMNS)))
            for ci, col in enumerate(TRACK_COLUMNS):
                col_key = {
                    "No.": "track_no",
                    "Artist": "artist",
                    "Track Name": "track_name",
                    "Comment": "comment",
                    "File Path": "file_path",
                    "Price": "price",
                    "NYP": "nyp",
                }.get(col)
                if col_key and col_key in srow:
                    vals[ci] = str(srow[col_key])
            restored.append(vals)
            if fp:
                used_paths.add(fp)

        for vals in current_by_path.values():
            fp = vals[COL_PATH] if len(vals) > COL_PATH else ""
            if fp and fp not in used_paths:
                restored.append(vals)

        if not restored:
            return
        self._loading_table = True
        try:
            self.track_table.setRowCount(0)
            for vals in restored:
                row = self.track_table.rowCount()
                self.track_table.insertRow(row)
                for ci, val in enumerate(vals):
                    if ci < len(TRACK_COLUMNS):
                        item = QTableWidgetItem(val)
                        if ci not in EDITABLE_COLUMNS:
                            item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                        if ci in (COL_NO, COL_NYP):
                            item.setTextAlignment(Qt.AlignCenter)
                        self.track_table.setItem(row, ci, item)
        finally:
            self._loading_table = False
        self.renumber_table()

    def apply_album_session_track_editor_data(self, payload: dict):
        saved = payload.get("track_editor_data", {})
        if not saved:
            return
        valid_paths: set[str] = set()
        for row in range(self.track_table.rowCount()):
            fp = self.table_text(row, COL_PATH)
            if fp:
                valid_paths.add(fp)
        for path, data in saved.items():
            if path in valid_paths and isinstance(data, dict):
                self.track_editor_data[path] = data

    def load_or_create_album_session_file(self, album_path: Path):
        if not getattr(self.config, "create_album_session_files", True):
            return
        self._album_path_for_session = album_path
        session_path = self.get_album_session_file_path(album_path)
        if not session_path:
            return
        if not session_path.exists():
            self.save_album_session_file()
            return

        try:
            payload = self.read_album_session_payload(session_path)
            if not payload:
                return
            self._album_session_loading = True
            try:
                self.apply_album_session_details(payload.get("album_details", {}))
                self.apply_album_session_tracks(payload)
                self.apply_album_session_track_editor_data(payload)
                self.sync_table_to_album()
            finally:
                self._album_session_loading = False
        except Exception as e:
            logger.warning(f"Failed to load album session file: {e}")

    def closeEvent(self, event):
        if self._album_session_save_timer is not None:
            self._album_session_save_timer = None
        self.save_album_session_file()
        super().closeEvent(event)


def apply_preview_style(app: QApplication):
    app.setStyleSheet(
        """
        QMainWindow, QWidget {
            background: #1e1e2e;
            color: #cdd6f4;
            font-family: Segoe UI;
            font-size: 8.5pt;
        }
        QWidget#topBar, QWidget#bottomBar {
            background: #181825;
        }
        QFrame#detailsPanel {
            background: #313244;
            border: 1px solid #45475a;
            border-radius: 4px;
        }
        QLabel#sectionTitle {
            font-weight: 600;
            font-size: 10pt;
        }
        QLabel#mutedLabel {
            color: #6c7086;
        }
        QLabel#progressTitle {
            font-weight: 600;
        }
        QGroupBox {
            border: 1px solid #45475a;
            border-radius: 3px;
            margin-top: 5px;
            padding: 2px;
            font-weight: 600;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 5px;
            padding: 0 3px;
        }
        QLabel#coverPreview {
            background: #313244;
            border: 1px solid #45475a;
            border-radius: 4px;
            color: #6c7086;
        }
        QTextEdit#logText {
            background: #11111b;
            color: #cdd6f4;
            border: 1px solid #313244;
            font-family: Consolas;
            font-size: 9pt;
        }
        QDockWidget {
            font-weight: 600;
        }
        QLineEdit, QPlainTextEdit, QTableWidget {
            background: #313244;
            border: 1px solid #45475a;
            border-radius: 4px;
            padding: 3px;
        }
        QTreeWidget {
            background: #181825;
            border: 0;
        }
        QTreeWidget::item {
            padding: 3px 6px;
        }
        QTreeWidget::item:selected {
            background: #45475a;
        }
        QPushButton {
            background: #313244;
            border: 1px solid #45475a;
            border-radius: 4px;
            padding: 4px 8px;
            color: #cdd6f4;
        }
        QPushButton:hover {
            background: #45475a;
            border-color: #89b4fa;
        }
        QPushButton:disabled {
            background: #181825;
            border-color: #313244;
            color: #585b70;
        }
        QPushButton#primaryButton {
            background: #89b4fa;
            border-color: #89b4fa;
            color: #1e1e2e;
            font-weight: 700;
        }
        QPushButton#primaryButton:disabled {
            background: #45475a;
            border-color: #45475a;
            color: #6c7086;
        }
        QHeaderView::section {
            background: #313244;
            border: 0;
            border-right: 1px solid #45475a;
            padding: 3px;
        }
        QProgressBar {
            background: #313244;
            border: 1px solid #45475a;
            border-radius: 4px;
            height: 10px;
            text-align: center;
        }
        QProgressBar::chunk {
            background: #89b4fa;
            border-radius: 3px;
        }
        QCheckBox {
            spacing: 4px;
        }
        QComboBox {
            background: #313244;
            border: 1px solid #45475a;
            border-radius: 3px;
            padding: 2px 4px;
        }
        QSpinBox {
            background: #313244;
            border: 1px solid #45475a;
            border-radius: 3px;
            padding: 2px 4px;
        }
        """
    )


def main():
    app = QApplication(sys.argv)
    config = load_config() or Config()
    apply_preview_style(app)
    window = QtUploaderWindow(config)
    window.show()
    return app.exec()
