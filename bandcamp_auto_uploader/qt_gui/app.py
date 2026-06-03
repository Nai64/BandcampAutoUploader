"""Experimental PySide6 shell for gradually migrating the desktop GUI."""

from __future__ import annotations

import sys
from pathlib import Path

from bandcamp_auto_uploader import __version__
from bandcamp_auto_uploader.config import Config, load_config, save_config
from bandcamp_auto_uploader.qt_gui.formatting import (
    format_price,
    normalize_price,
    normalize_release_date,
)
from bandcamp_auto_uploader.upload import Album, CoverArt

try:
    from PySide6.QtCore import Qt, QUrl
    from PySide6.QtGui import QAction, QDesktopServices, QPixmap
    from PySide6.QtWidgets import (
        QApplication,
        QAbstractItemView,
        QCheckBox,
        QComboBox,
        QFileDialog,
        QFormLayout,
        QFrame,
        QGroupBox,
        QHBoxLayout,
        QHeaderView,
        QLabel,
        QLineEdit,
        QMainWindow,
        QMessageBox,
        QPlainTextEdit,
        QProgressBar,
        QPushButton,
        QScrollArea,
        QSplitter,
        QTableWidget,
        QTableWidgetItem,
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


class QtUploaderWindow(QMainWindow):
    """Qt shell that previews and edits album tracks using the existing model."""

    def __init__(self, config: Config):
        super().__init__()
        self.config = config
        self.current_album: Album | None = None
        self._loading_table = False
        self._loading_details = False
        self._loading_album_details = False
        self.cover_path: Path | None = None

        self.setWindowTitle(f"Bandcamp Auto Uploader Qt Preview {__version__}")
        self.resize(1180, 760)
        self.setMinimumSize(960, 620)
        self.setAcceptDrops(True)
        self._build_ui()

    def _build_ui(self):
        open_action = QAction("Open Album Folder", self)
        open_action.triggered.connect(self.browse_album)
        self.menuBar().addMenu("File").addAction(open_action)

        central = QWidget()
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(10, 10, 10, 10)
        root_layout.setSpacing(8)

        root_layout.addWidget(self._build_top_bar())

        splitter = QSplitter(Qt.Horizontal)
        root_layout.addWidget(splitter, 1)

        splitter.addWidget(self._build_details_panel())
        splitter.addWidget(self._build_album_preview_panel())
        splitter.addWidget(self._build_right_panel())
        splitter.setSizes([320, 610, 300])

        root_layout.addWidget(self._build_bottom_bar())

        self.setCentralWidget(central)
        self.statusBar().showMessage("Qt migration preview ready")

    def _build_top_bar(self):
        top_bar = QWidget()
        top_bar.setObjectName("topBar")
        layout = QHBoxLayout(top_bar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        artist_group = QGroupBox("Artist / Band")
        artist_layout = QVBoxLayout(artist_group)
        self.artist_combo = QComboBox()
        self.artist_combo.setEditable(False)
        self.artist_combo.addItem("No artist selected")
        artist_layout.addWidget(self.artist_combo)
        artist_buttons = QHBoxLayout()

        self.load_cookies_button = QPushButton("Load Cookies")
        self.load_cookies_button.clicked.connect(self.load_cookies_file)
        self.refresh_artists_button = QPushButton("Refresh Artists")
        self.refresh_artists_button.clicked.connect(self.show_artist_placeholder)
        artist_buttons.addWidget(self.refresh_artists_button)
        artist_buttons.addWidget(self.load_cookies_button)
        artist_layout.addLayout(artist_buttons)
        layout.addWidget(artist_group, 1)

        album_group = QGroupBox("Album Folder")
        album_layout = QVBoxLayout(album_group)

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
        preferences_button.clicked.connect(self.show_preferences_placeholder)
        layout.addWidget(preferences_button)

        self.upload_button = QPushButton("UPLOAD ALBUM")
        self.upload_button.setObjectName("primaryButton")
        self.upload_button.setEnabled(False)
        self.upload_button.clicked.connect(self.show_upload_placeholder)
        layout.addWidget(self.upload_button, 1)

        self.cancel_upload_button = QPushButton("Cancel Upload")
        self.cancel_upload_button.setEnabled(False)
        self.cancel_upload_button.clicked.connect(self.show_cancel_placeholder)
        layout.addWidget(self.cancel_upload_button, 1)
        return bottom_bar

    def _build_details_panel(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        panel = QFrame()
        panel.setObjectName("detailsPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        title = QLabel("Album / Track Details")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)

        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.album_name_edit = QLineEdit()
        self.album_name_edit.setPlaceholderText("Album name")
        self.artist_edit = QLineEdit()
        self.artist_edit.setPlaceholderText("Artist")
        self.release_date_edit = QLineEdit()
        self.release_date_edit.setPlaceholderText("YYYY-MM-DD")
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

        form.addRow("Name", self.album_name_edit)
        form.addRow("Artist", self.artist_edit)
        form.addRow("Release Date", self.release_date_edit)
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
        layout.addLayout(form)

        self.description_edit = QPlainTextEdit()
        self.description_edit.setPlaceholderText("Description")
        self.description_edit.setMaximumHeight(90)
        layout.addWidget(QLabel("Description"))
        layout.addWidget(self.description_edit)

        self.credits_edit = QPlainTextEdit()
        self.credits_edit.setPlaceholderText("Credits")
        self.credits_edit.setMaximumHeight(80)
        layout.addWidget(QLabel("Credits"))
        layout.addWidget(self.credits_edit)

        layout.addWidget(self._build_track_details())
        layout.addStretch(1)

        self.album_price_edit.editingFinished.connect(lambda: self.sanitize_price_edit(self.album_price_edit, "0"))
        self.release_date_edit.editingFinished.connect(lambda: self.sanitize_date_edit(self.release_date_edit))
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
        self.description_edit.textChanged.connect(self.apply_album_details_to_model)
        self.credits_edit.textChanged.connect(self.apply_album_details_to_model)
        self.license_combo.currentTextChanged.connect(lambda _text: self.apply_album_details_to_model())
        for checkbox in (
            self.album_nyp_check,
            self.album_public_check,
            self.require_email_check,
            self.pro_check,
        ):
            checkbox.toggled.connect(lambda _checked: self.apply_album_details_to_model())

        scroll.setWidget(panel)
        return scroll

    def _build_album_preview_panel(self):
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        header_row = QHBoxLayout()
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

        self.track_table = QTableWidget(0, len(TRACK_COLUMNS))
        self.track_table.setHorizontalHeaderLabels(TRACK_COLUMNS)
        self.track_table.setAlternatingRowColors(True)
        self.track_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.track_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.track_table.verticalHeader().setVisible(False)
        self.track_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.track_table.horizontalHeader().setStretchLastSection(True)
        self.track_table.cellChanged.connect(self.on_track_cell_changed)
        self.track_table.itemSelectionChanged.connect(self.load_selected_track_details)
        layout.addWidget(self.track_table, 1)

        return content

    def _build_right_panel(self):
        right_panel = QWidget()
        layout = QVBoxLayout(right_panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        layout.addWidget(self._build_cover_panel())
        layout.addWidget(self._build_progress_panel(), 1)
        return right_panel

    def _build_cover_panel(self):
        cover_group = QGroupBox("Cover Art")
        cover_layout = QVBoxLayout(cover_group)
        self.cover_preview = QLabel("No cover art")
        self.cover_preview.setObjectName("coverPreview")
        self.cover_preview.setAlignment(Qt.AlignCenter)
        self.cover_preview.setMinimumSize(220, 220)
        self.cover_preview.setMaximumHeight(260)
        cover_layout.addWidget(self.cover_preview)
        self.cover_path_edit = QLineEdit()
        self.cover_path_edit.setPlaceholderText("Cover image path")
        self.cover_path_edit.editingFinished.connect(self.resolve_cover_path_edit)
        cover_layout.addWidget(self.cover_path_edit)
        cover_buttons = QHBoxLayout()
        browse_cover_button = QPushButton("Browse")
        browse_cover_button.clicked.connect(self.browse_cover)
        cover_buttons.addWidget(browse_cover_button)
        detect_cover_button = QPushButton("Auto")
        detect_cover_button.clicked.connect(self.auto_detect_cover)
        cover_buttons.addWidget(detect_cover_button)
        clear_cover_button = QPushButton("Clear")
        clear_cover_button.clicked.connect(self.clear_cover)
        cover_buttons.addWidget(clear_cover_button)
        cover_layout.addLayout(cover_buttons)
        return cover_group

    def _build_progress_panel(self):
        progress_group = QGroupBox("Progress")
        layout = QVBoxLayout(progress_group)
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

    def _build_track_details(self):
        group = QGroupBox("Details")
        layout = QFormLayout(group)
        layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

        self.track_name_edit = QLineEdit()
        self.track_artist_edit = QLineEdit()
        self.track_price_edit = QLineEdit()
        self.track_release_date_edit = QLineEdit()
        self.track_isrc_edit = QLineEdit()
        self.track_iswc_edit = QLineEdit()
        self.track_bonus_check = QCheckBox("Bonus track")
        self.track_comment_edit = QLineEdit()

        layout.addRow("Track Name", self.track_name_edit)
        layout.addRow("Artist", self.track_artist_edit)
        layout.addRow("Price", self.track_price_edit)
        layout.addRow("Release Date", self.track_release_date_edit)
        layout.addRow("ISRC", self.track_isrc_edit)
        layout.addRow("ISWC", self.track_iswc_edit)
        layout.addRow("", self.track_bonus_check)
        layout.addRow("Comment", self.track_comment_edit)

        for edit in (
            self.track_name_edit,
            self.track_artist_edit,
            self.track_price_edit,
            self.track_release_date_edit,
            self.track_isrc_edit,
            self.track_iswc_edit,
            self.track_comment_edit,
        ):
            edit.editingFinished.connect(self.save_selected_track_details)
        self.track_bonus_check.toggled.connect(lambda _checked: self.save_selected_track_details())
        self.track_price_edit.editingFinished.connect(lambda: self.sanitize_price_edit(self.track_price_edit, ""))
        self.track_release_date_edit.editingFinished.connect(lambda: self.sanitize_date_edit(self.track_release_date_edit))
        return group

    def browse_album(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Album Folder", self.album_path_edit.text())
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
        self.artist_combo.clear()
        self.artist_combo.addItem("Refresh artists to load from cookies")
        self.statusBar().showMessage(f"Cookies file selected: {Path(filename).name}")

    def show_artist_placeholder(self):
        if self.config.cookies_file:
            self.artist_combo.clear()
            self.artist_combo.addItem("Artist loading pending migration")
        QMessageBox.information(
            self,
            "Artists",
            "Artist loading will be migrated after the preview/edit workflow is stable.",
        )

    def show_preferences_placeholder(self):
        QMessageBox.information(
            self,
            "Preferences",
            "Preferences will be migrated after the upload preview surface is stable.",
        )

    def show_upload_placeholder(self):
        QMessageBox.information(
            self,
            "Upload Album",
            "Album upload is still handled by the Tkinter app while the Qt migration catches up.",
        )

    def show_cancel_placeholder(self):
        self.statusBar().showMessage("No Qt upload is running")

    def open_album_folder(self):
        album_path = Path(self.album_path_edit.text().strip())
        if not album_path.is_dir():
            QMessageBox.warning(self, "Album Folder", "Choose a valid album folder first.")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(album_path)))

    def preview_album(self):
        path_text = self.album_path_edit.text().strip()
        if not path_text:
            QMessageBox.information(self, "Album Folder", "Choose an album folder first.")
            return

        album_path = Path(path_text)
        if not album_path.is_dir():
            QMessageBox.warning(self, "Invalid Folder", "Choose a valid album folder.")
            return

        try:
            album = Album.from_directory(album_path, self.config)
        except Exception as exc:
            QMessageBox.critical(self, "Preview Failed", f"Could not preview album:\n{exc}")
            return

        self.current_album = album
        self.load_album_details(album, album_path)
        self.populate_track_table(album)
        self.prepare_progress_from_album(album)
        self.statusBar().showMessage(f"Loaded {len(album.tracks)} track(s)")

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
            self.cover_path = album.cover_art.path if album.cover_art and album.cover_art.path else None
            self.cover_path_edit.setText(str(self.cover_path) if self.cover_path else "")
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
        self.current_album.cover_art = CoverArt(path=self.cover_path) if self.cover_path else None

    def browse_cover(self):
        filename, _selected_filter = QFileDialog.getOpenFileName(
            self,
            "Select Cover Art",
            self.cover_path_edit.text(),
            "Image files (*.jpg *.jpeg *.png *.gif *.webp);;All files (*.*)",
        )
        if filename:
            self.set_cover_path(Path(filename))

    def clear_cover(self):
        self.set_cover_path(None)

    def resolve_cover_path_edit(self):
        text = self.cover_path_edit.text().strip()
        if not text:
            self.set_cover_path(None)
            return
        self.set_cover_path(Path(text))

    def set_cover_path(self, path: Path | None):
        self.cover_path = path if path and path.exists() else None
        self.cover_path_edit.setText(str(self.cover_path) if self.cover_path else "")
        self.update_cover_preview()
        self.apply_album_details_to_model()

    def auto_detect_cover(self):
        album_path = Path(self.album_path_edit.text().strip())
        cover = self.find_cover_art(album_path)
        if cover:
            self.set_cover_path(cover)
            self.statusBar().showMessage(f"Detected cover art: {cover.name}")
        else:
            self.statusBar().showMessage("No cover art found")

    def find_cover_art(self, album_path: Path) -> Path | None:
        if not album_path.is_dir():
            return None
        for cover_name in COVER_NAMES:
            candidate = album_path / cover_name
            if candidate.exists():
                return candidate
        for file in album_path.iterdir():
            if file.is_file() and file.suffix.lower() in COVER_SUFFIXES:
                return file
        return None

    def update_cover_preview(self):
        if not self.cover_path:
            self.cover_preview.setPixmap(QPixmap())
            self.cover_preview.setText("No cover art")
            return
        if not self.cover_path.exists():
            self.cover_preview.setPixmap(QPixmap())
            self.cover_preview.setText("Cover not found")
            return
        pixmap = QPixmap(str(self.cover_path))
        if pixmap.isNull():
            self.cover_preview.setText("Could not load cover")
            return
        scaled = pixmap.scaled(210, 210, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.cover_preview.setPixmap(scaled)
        self.cover_preview.setText("")

    def prepare_progress_from_album(self, album: Album):
        self.clear_progress_rows()
        if not album.tracks:
            self.progress_placeholder.setText("No tracks queued")
            self.progress_placeholder.show()
            return
        self.progress_placeholder.hide()
        for index, track in enumerate(album.tracks, 1):
            self.add_progress_row(f"{index}. {track.track_data.title or track.path.name}", "Queued", 0)

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
            self.load_selected_track_details()

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
                self.set_table_text(row, column, format_price(self.table_text(row, column)))
            finally:
                self._loading_table = False
        elif column == COL_NYP:
            value = self.table_text(row, column).lower()
            self._loading_table = True
            try:
                self.set_table_text(row, column, "No" if value in {"0", "false", "no", "n", "off"} else "Yes")
            finally:
                self._loading_table = False
        self.sync_table_to_album()
        if row == self.selected_row():
            self.load_selected_track_details()

    def sync_table_to_album(self):
        if self.current_album is None:
            return
        tracks_by_path = {str(track.path): track for track in self.current_album.tracks}
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
            data.price = normalize_price(self.table_text(row, COL_PRICE), default="")
            data.nyp = int(self.table_text(row, COL_NYP).lower() not in {"0", "false", "no", "n", "off"})
            tracks.append(track)
        self.current_album.tracks = tracks
        self.renumber_table()
        self.prepare_progress_from_album(self.current_album)
        self.statusBar().showMessage(f"{len(tracks)} track(s) in preview")

    def renumber_table(self):
        self._loading_table = True
        try:
            for row in range(self.track_table.rowCount()):
                self.set_table_text(row, COL_NO, str(row + 1))
        finally:
            self._loading_table = False

    def remove_selected_track(self):
        row = self.selected_row()
        if row < 0:
            return
        self.track_table.removeRow(row)
        self.sync_table_to_album()
        if self.track_table.rowCount():
            self.track_table.selectRow(min(row, self.track_table.rowCount() - 1))
        else:
            self.load_selected_track_details()

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
            first_values = [self.table_text(first, column) for column in range(self.track_table.columnCount())]
            second_values = [self.table_text(second, column) for column in range(self.track_table.columnCount())]
            for column, value in enumerate(second_values):
                self.set_table_text(first, column, value)
            for column, value in enumerate(first_values):
                self.set_table_text(second, column, value)
        finally:
            self._loading_table = False

    def load_selected_track_details(self):
        row = self.selected_row()
        self._loading_details = True
        try:
            if row < 0:
                for edit in (
                    self.track_name_edit,
                    self.track_artist_edit,
                    self.track_price_edit,
                    self.track_release_date_edit,
                    self.track_isrc_edit,
                    self.track_iswc_edit,
                    self.track_comment_edit,
                ):
                    edit.clear()
                self.track_bonus_check.setChecked(False)
                return

            track = self.track_for_row(row)
            data = track.track_data if track else None
            self.track_name_edit.setText(self.table_text(row, COL_TITLE))
            self.track_artist_edit.setText(self.table_text(row, COL_ARTIST))
            self.track_price_edit.setText(format_price(self.table_text(row, COL_PRICE)))
            self.track_release_date_edit.setText(getattr(data, "release_date", "") if data else "")
            self.track_isrc_edit.setText(getattr(data, "isrc", "") if data else "")
            self.track_iswc_edit.setText(getattr(data, "iswc", "") if data else "")
            self.track_bonus_check.setChecked(bool(getattr(data, "private", False)) if data else False)
            self.track_comment_edit.setText(self.table_text(row, COL_COMMENT))
        finally:
            self._loading_details = False

    def save_selected_track_details(self):
        if self._loading_details:
            return
        row = self.selected_row()
        if row < 0:
            return

        price = normalize_price(self.track_price_edit.text(), default="")
        release_date = normalize_release_date(self.track_release_date_edit.text())
        self.track_price_edit.setText(format_price(price))
        self.track_release_date_edit.setText(release_date)

        self._loading_table = True
        try:
            self.set_table_text(row, COL_TITLE, self.track_name_edit.text().strip())
            self.set_table_text(row, COL_ARTIST, self.track_artist_edit.text().strip())
            self.set_table_text(row, COL_PRICE, format_price(price))
            self.set_table_text(row, COL_COMMENT, self.track_comment_edit.text().strip())
        finally:
            self._loading_table = False

        track = self.track_for_row(row)
        if track is not None:
            data = track.track_data
            data.release_date = release_date
            data.isrc = self.track_isrc_edit.text().strip()
            data.iswc = self.track_iswc_edit.text().strip()
            data.private = int(self.track_bonus_check.isChecked())
        self.sync_table_to_album()

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


def apply_preview_style(app: QApplication):
    app.setStyleSheet(
        """
        QMainWindow, QWidget {
            background: #f6f7f8;
            color: #1f2933;
            font-family: Segoe UI;
            font-size: 9pt;
        }
        QWidget#topBar, QWidget#bottomBar {
            background: #f6f7f8;
        }
        QFrame#detailsPanel {
            background: #ffffff;
            border: 1px solid #d8dee6;
            border-radius: 4px;
        }
        QLabel#sectionTitle {
            font-weight: 600;
            font-size: 11pt;
        }
        QLabel#mutedLabel {
            color: #6b7280;
        }
        QLabel#progressTitle {
            font-weight: 600;
        }
        QGroupBox {
            border: 1px solid #d8dee6;
            border-radius: 4px;
            margin-top: 8px;
            padding: 8px;
            font-weight: 600;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 8px;
            padding: 0 4px;
        }
        QLabel#coverPreview {
            background: #ffffff;
            border: 1px solid #cfd7df;
            border-radius: 4px;
            color: #6b7280;
        }
        QLineEdit, QPlainTextEdit, QTableWidget {
            background: #ffffff;
            border: 1px solid #cfd7df;
            border-radius: 4px;
            padding: 5px;
        }
        QPushButton {
            background: #ffffff;
            border: 1px solid #b7c1cc;
            border-radius: 4px;
            padding: 6px 10px;
        }
        QPushButton:hover {
            background: #eef5ff;
            border-color: #6aa3e8;
        }
        QPushButton:disabled {
            background: #eef1f4;
            border-color: #d4dbe3;
            color: #8a95a3;
        }
        QPushButton#primaryButton {
            background: #1f6feb;
            border-color: #1f6feb;
            color: #ffffff;
            font-weight: 700;
        }
        QPushButton#primaryButton:disabled {
            background: #a9bfdc;
            border-color: #a9bfdc;
            color: #f5f7fb;
        }
        QHeaderView::section {
            background: #eef1f4;
            border: 0;
            border-right: 1px solid #d4dbe3;
            padding: 5px;
            font-weight: 600;
        }
        QProgressBar {
            background: #edf1f5;
            border: 1px solid #d4dbe3;
            border-radius: 4px;
            height: 12px;
            text-align: center;
        }
        QProgressBar::chunk {
            background: #2680eb;
            border-radius: 3px;
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
