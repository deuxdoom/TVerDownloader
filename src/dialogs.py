# 파일명: src/dialogs.py
# 안정 버전: 드래그 제거 + 우측 화살표로 이동
# 콤보박스 팝업 점프 이슈 해결: StableComboBox로 팝업 위치 고정
from __future__ import annotations

from PyQt6.QtCore import Qt, QSize, QPoint
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QComboBox, QSpinBox, QTabWidget, QWidget, QFileDialog,
    QDialogButtonBox, QListWidget, QListWidgetItem, QAbstractItemView,
    QToolButton, QStyle, QListView
)

from src.utils import save_config

ROLE_KEY = Qt.ItemDataRole.UserRole  # 각 항목의 실제 키(series/id 등) 저장


class StableComboBox(QComboBox):
    """QComboBox 팝업이 레이아웃/스타일 영향으로 점프하는 문제 방지."""
    def __init__(self, parent=None):
        super().__init__(parent)
        view = QListView()
        view.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setView(view)
        self.setMinimumContentsLength(14)
        self.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContentsOnFirstShow)

    def showPopup(self):
        super().showPopup()
        try:
            popup = self.view().window()  # QComboBoxPrivateContainer
            below = self.mapToGlobal(self.rect().bottomLeft())
            w = max(popup.width(), self.width())
            popup.resize(w, popup.height())
            popup.move(QPoint(below.x(), below.y()))
        except Exception:
            pass


class SettingsDialog(QDialog):
    """설정: 일반 / 파일명 / 화질 / 다운로드 후 작업"""
    def __init__(self, config: dict, parent: QWidget | None = None):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("설정")
        self.setMinimumSize(560, 400)

        root = QVBoxLayout(self)
        self.tabs = QTabWidget(self)
        root.addWidget(self.tabs)

        self._create_general_tab()
        self._create_filename_tab()
        self._create_quality_tab()
        self._create_post_action_tab()

        # 하단 버튼
        self.buttons = QDialogButtonBox()
        save_btn = self.buttons.addButton("설정 저장", QDialogButtonBox.ButtonRole.AcceptRole)
        exit_btn = self.buttons.addButton("나가기", QDialogButtonBox.ButtonRole.RejectRole)
        root.addWidget(self.buttons)

        save_btn.clicked.connect(self._save_settings)
        exit_btn.clicked.connect(self.reject)

    # ---------- 일반 ----------
    def _create_general_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        row = QHBoxLayout()
        row.addWidget(QLabel("다운로드 폴더:"))
        self.folder_path_edit = QLineEdit(self.config.get("download_folder", ""))
        self.folder_path_edit.setReadOnly(True)
        row.addWidget(self.folder_path_edit, 1)
        browse = QPushButton("찾아보기...")
        browse.clicked.connect(self._browse_folder)
        row.addWidget(browse)
        layout.addLayout(row)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("최대 동시 다운로드 개수:"))
        self.concurrent_spinbox = QSpinBox()
        self.concurrent_spinbox.setRange(1, 5)
        self.concurrent_spinbox.setValue(self.config.get("max_concurrent_downloads", 3))
        row2.addWidget(self.concurrent_spinbox)
        row2.addStretch(1)
        layout.addLayout(row2)

        layout.addStretch(1)
        self.tabs.addTab(tab, "일반")

    # ---------- 파일명 ----------
    def _create_filename_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.addWidget(QLabel("파일명 구성 요소 선택 및 순서 설정:"))

        # 리스트 + 우측 화살표 버튼 스택
        list_row = QHBoxLayout()
        self.order_list = QListWidget()
        self.order_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.order_list.setDragDropMode(QAbstractItemView.DragDropMode.NoDragDrop)  # 드래그 비활성(안정성)
        self.order_list.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.order_list.setAlternatingRowColors(False)

        # 텍스트 뭉개짐/클리핑 방지: per-item sizeHint + 내부 패딩
        fm = self.order_list.fontMetrics()
        row_h = max(28, fm.height() + 12)
        self.order_list.setStyleSheet("QListWidget::item{ padding:6px 8px; }")

        # 우측 화살표 버튼들
        btn_col = QVBoxLayout()
        self.up_btn = QToolButton()
        self.down_btn = QToolButton()
        self.up_btn.setToolTip("위로")
        self.down_btn.setToolTip("아래로")
        self.up_btn.setFixedSize(32, 32)
        self.down_btn.setFixedSize(32, 32)
        self.up_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowUp))
        self.down_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowDown))
        self.up_btn.setShortcut("Alt+Up")
        self.down_btn.setShortcut("Alt+Down")

        btn_col.addWidget(self.up_btn)
        btn_col.addWidget(self.down_btn)
        btn_col.addStretch(1)

        list_row.addWidget(self.order_list, 1)
        list_row.addLayout(btn_col)
        layout.addLayout(list_row, 1)

        # 표시명 매핑
        self.part_names: dict[str, str] = {
            "series": "시리즈명",
            "upload_date": "방송날짜",
            "episode_number": "회차번호",
            "episode": "타이틀",
            "id": "고유ID",
        }
        parts_cfg: dict = self.config.get("filename_parts", {})
        current_order = self.config.get("filename_order", list(self.part_names.keys()))

        # 체크 가능한 QListWidgetItem 생성(✔ 기본 렌더링 유지)
        for key in current_order:
            if key not in self.part_names:
                continue
            item = QListWidgetItem(self.part_names[key])
            item.setData(ROLE_KEY, key)
            item.setFlags(
                Qt.ItemFlag.ItemIsEnabled
                | Qt.ItemFlag.ItemIsSelectable
                | Qt.ItemFlag.ItemIsUserCheckable
            )
            item.setCheckState(
                Qt.CheckState.Checked if parts_cfg.get(key, True) else Qt.CheckState.Unchecked
            )
            item.setSizeHint(QSize(0, row_h))
            self.order_list.addItem(item)

        # 미리보기
        pv = QHBoxLayout()
        pv.addWidget(QLabel("파일명 미리보기:"))
        self.preview_label = QLabel()
        pv.addWidget(self.preview_label, 1)
        layout.addLayout(pv)

        # 시그널
        self.order_list.itemChanged.connect(self._update_preview)
        self.order_list.currentRowChanged.connect(self._sync_move_buttons)
        self.up_btn.clicked.connect(lambda: self._move_selected(-1))
        self.down_btn.clicked.connect(lambda: self._move_selected(+1))

        self._update_preview()
        self._sync_move_buttons()
        self.tabs.addTab(tab, "파일명")

    def _move_selected(self, delta: int):
        row = self.order_list.currentRow()
        if row < 0:
            return
        new_row = row + delta
        if new_row < 0 or new_row >= self.order_list.count():
            return
        item = self.order_list.takeItem(row)
        self.order_list.insertItem(new_row, item)
        self.order_list.setCurrentRow(new_row)
        # ▼ 이동 후 선택 항목이 항상 보이도록 스크롤 맞춤(UX 개선)
        self.order_list.scrollToItem(item)
        self._update_preview()
        self._sync_move_buttons()

    def _sync_move_buttons(self, *_):
        row = self.order_list.currentRow()
        cnt = self.order_list.count()
        self.up_btn.setEnabled(cnt > 1 and row > 0)
        self.down_btn.setEnabled(cnt > 1 and 0 <= row < cnt - 1)

    def _selected_parts_texts(self) -> list[str]:
        parts: list[str] = []
        for i in range(self.order_list.count()):
            it = self.order_list.item(i)
            key = it.data(ROLE_KEY)
            text = it.text()
            if it.checkState() == Qt.CheckState.Checked:
                parts.append(f"[{text}]" if key == "id" else text)
        return parts

    def _update_preview(self, *args):
        txt = " ".join(self._selected_parts_texts())
        self.preview_label.setText(txt + (".mp4" if txt else " (선택된 항목 없음)"))

    # ---------- 화질 ----------
    def _create_quality_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.addWidget(QLabel("다운로드 화질/포맷 선택:"))

        self.quality_combo = StableComboBox()
        qualities = {
            "최상 화질 (기본값)": "bv*+ba/b",
            "1080p": "bestvideo[height<=1080]+bestaudio/best[height<=1080]",
            "720p": "bestvideo[height<=720]+bestaudio/best[height<=720]",
            "오디오만 추출 (MP3)": "audio_only",
        }
        for text, key in qualities.items():
            self.quality_combo.addItem(text, key)

        cur = self.config.get("quality", "bv*+ba/b")
        idx = self.quality_combo.findData(cur)
        if idx >= 0:
            self.quality_combo.setCurrentIndex(idx)

        layout.addWidget(self.quality_combo)
        layout.addStretch(1)
        self.tabs.addTab(tab, "화질")

    # ---------- 다운로드 후 작업 ----------
    def _create_post_action_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.addWidget(QLabel("모든 다운로드 완료 후 작업:"))

        self.post_action_combo = StableComboBox()
        for key, text in {
            "None": "아무 작업 안 함",
            "Open Folder": "다운로드 폴더 열기",
            "Shutdown": "1분 후 시스템 종료",
        }.items():
            self.post_action_combo.addItem(text, key)

        cur = self.config.get("post_action", "None")
        idx = self.post_action_combo.findData(cur)
        if idx >= 0:
            self.post_action_combo.setCurrentIndex(idx)

        layout.addWidget(self.post_action_combo)
        layout.addStretch(1)
        self.tabs.addTab(tab, "다운로드 후 작업")

    # ---------- 저장/폴더 ----------
    def _browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "다운로드 폴더 선택", self.folder_path_edit.text())
        if folder:
            self.folder_path_edit.setText(folder)

    def _save_settings(self):
        # 일반
        self.config["download_folder"] = self.folder_path_edit.text()
        self.config["max_concurrent_downloads"] = self.concurrent_spinbox.value()

        # 파일명(체크/순서)
        filename_parts: dict[str, bool] = {}
        filename_order: list[str] = []
        for i in range(self.order_list.count()):
            it = self.order_list.item(i)
            key = it.data(ROLE_KEY)
            filename_order.append(key)
            filename_parts[key] = (it.checkState() == Qt.CheckState.Checked)

        self.config["filename_parts"] = filename_parts
        self.config["filename_order"] = filename_order

        # 화질/후작업
        self.config["quality"] = self.quality_combo.currentData()
        self.config["post_action"] = self.post_action_combo.currentData()

        save_config(self.config)
        self.accept()

    # ---------- 드래그&드롭(옵션: 다이얼로그에 파일 드롭 시 큐 추가) ----------
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        if e.mimeData().hasUrls():
            url = e.mimeData().urls()[0].toLocalFile()
            parent = self.parent()
            if parent and hasattr(parent, "add_url_to_queue"):
                try:
                    parent.add_url_to_queue(url)  # type: ignore[attr-defined]
                    self.accept()  # 드롭으로 추가 후 설정창 닫기(기존 동작 유지)
                except Exception:
                    pass
            e.acceptProposedAction()
