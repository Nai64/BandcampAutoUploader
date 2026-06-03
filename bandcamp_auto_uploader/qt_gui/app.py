"""Experimental PySide6 shell for gradually migrating the desktop GUI."""

from __future__ import annotations

import sys
from pathlib import Path

from bandcamp_auto_uploader import __version__
from bandcamp_auto_uploader.config import Config, load_config
from bandcamp_auto_uploader.upload import Album

try:
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QAction
    from PySide6.QtWidgets import (
        QApplication,
        QFileDialog,
        QFrame,
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


class QtUploaderWindow(QMainWindow):
    """Small Qt shell that previews album tracks using the existing upload model."""

    def __init__(self, config: Config):
        super().__init__()
        self.config = config
        self.current_album: Album | None = None

        self.setWindowTitle(f"Bandcamp Auto Uploader Qt Preview {__version__}")
        self.resize(1120, 720)
        self.setMinimumSize(920, 600)
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

        sidebar = self._build_sidebar()
        content = self._build_content()
        splitter.addWidget(sidebar)
        splitter.addWidget(content)
        splitter.setSizes([310, 810])

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

        self.album_name_edit = QLineEdit()
        self.album_name_edit.setPlaceholderText("Album name")
        layout.addWidget(self.album_name_edit)

        self.artist_edit = QLineEdit()
        self.artist_edit.setPlaceholderText("Artist")
        layout.addWidget(self.artist_edit)

        preview_button = QPushButton("Preview Album")
        preview_button.clicked.connect(self.preview_album)
        layout.addWidget(preview_button)

        layout.addStretch(1)
        return sidebar

    def _build_content(self):
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        title = QLabel("Tracks")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)

        self.track_table = QTableWidget(0, len(TRACK_COLUMNS))
        self.track_table.setHorizontalHeaderLabels(TRACK_COLUMNS)
        self.track_table.setAlternatingRowColors(True)
        self.track_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.track_table.verticalHeader().setVisible(False)
        self.track_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.track_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.track_table, 1)

        return content

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
        self.populate_track_table(album)
        self.statusBar().showMessage(f"Loaded {len(album.tracks)} track(s)")

    def populate_track_table(self, album: Album):
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
                self.format_price(data.price),
                "Yes" if data.nyp else "No",
                str(track.path),
            )
            row = self.track_table.rowCount()
            self.track_table.insertRow(row)
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 0:
                    item.setTextAlignment(Qt.AlignCenter)
                self.track_table.setItem(row, column, item)

    @staticmethod
    def format_price(value: str) -> str:
        text = str(value or "").strip().lstrip("$")
        return f"${text}" if text else ""


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
