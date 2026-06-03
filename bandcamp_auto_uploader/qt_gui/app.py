"""Experimental PySide6 shell for gradually migrating the desktop GUI."""

from __future__ import annotations

import sys
from pathlib import Path

from bandcamp_auto_uploader import __version__
from bandcamp_auto_uploader.config import Config, load_config
from bandcamp_auto_uploader.qt_gui.formatting import (
    format_price,
    normalize_price,
    normalize_release_date,
)
from bandcamp_auto_uploader.upload import Album

try:
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QAction
    from PySide6.QtWidgets import (
        QApplication,
        QAbstractItemView,
        QCheckBox,
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
        QPushButton,
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


class QtUploaderWindow(QMainWindow):
    """Qt shell that previews and edits album tracks using the existing model."""

    def __init__(self, config: Config):
        super().__init__()
        self.config = config
        self.current_album: Album | None = None
        self._loading_table = False
        self._loading_details = False

        self.setWindowTitle(f"Bandcamp Auto Uploader Qt Preview {__version__}")
        self.resize(1180, 760)
        self.setMinimumSize(960, 620)
        self._build_ui()

    def _build_ui(self):
        open_action = QAction("Open Album Folder", self)
        open_action.triggered.connect(self.browse_album)
        self.menuBar().addMenu("File").addAction(open_action)

        central = QWidget()
        root_layout = QHBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Horizontal)
        root_layout.addWidget(splitter)

        splitter.addWidget(self._build_sidebar())
        splitter.addWidget(self._build_content())
        splitter.setSizes([330, 850])

        self.setCentralWidget(central)
        self.statusBar().showMessage("Qt migration preview ready")

    def _build_sidebar(self):
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        title = QLabel("Album Details")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)

        self.album_path_edit = QLineEdit()
        self.album_path_edit.setPlaceholderText("Album folder")
        layout.addWidget(self.album_path_edit)

        browse_button = QPushButton("Browse")
        browse_button.clicked.connect(self.browse_album)
        layout.addWidget(browse_button)

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

        form.addRow("Name", self.album_name_edit)
        form.addRow("Artist", self.artist_edit)
        form.addRow("Release Date", self.release_date_edit)
        form.addRow("Price", self.album_price_edit)
        form.addRow("", self.album_nyp_check)
        form.addRow("", self.album_public_check)
        layout.addLayout(form)

        preview_button = QPushButton("Preview Album")
        preview_button.clicked.connect(self.preview_album)
        layout.addWidget(preview_button)

        layout.addStretch(1)

        self.album_price_edit.editingFinished.connect(lambda: self.sanitize_price_edit(self.album_price_edit, "0"))
        self.release_date_edit.editingFinished.connect(lambda: self.sanitize_date_edit(self.release_date_edit))
        return sidebar

    def _build_content(self):
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        header_row = QHBoxLayout()
        title = QLabel("Tracks")
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

        details = self._build_track_details()
        layout.addWidget(details)
        return content

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
        self.album_name_edit.setText(album.album_data.title or album_path.name)
        self.artist_edit.setText(album.album_data.artist or "")
        self.album_price_edit.setText(format_price(album.album_data.price, default="0"))
        self.album_nyp_check.setChecked(bool(album.album_data.nyp))
        self.album_public_check.setChecked(True)
        self.populate_track_table(album)
        self.statusBar().showMessage(f"Loaded {len(album.tracks)} track(s)")

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
        QFrame#sidebar {
            background: #ffffff;
            border-right: 1px solid #d8dee6;
        }
        QLabel#sectionTitle {
            font-weight: 600;
            font-size: 11pt;
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
        QLineEdit, QTableWidget {
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
        QHeaderView::section {
            background: #eef1f4;
            border: 0;
            border-right: 1px solid #d4dbe3;
            padding: 5px;
            font-weight: 600;
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
