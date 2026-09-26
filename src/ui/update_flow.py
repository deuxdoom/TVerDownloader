"""확인·받기·적용·완료를 두 프로세스에서 같은 화면 규칙으로 그린다."""

from __future__ import annotations

import re
import time
from collections import deque
from html import escape

from PyQt6.QtCore import QCoreApplication, QEvent, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import (QGridLayout, QHBoxLayout, QLabel, QProgressBar,
                             QPushButton, QVBoxLayout, QWidget)

from src.appicon import get_app_icon
from src.i18n import t
from src.qss import blend, palette
from src.qtparts import ElidedLabel
from src.window_frame import center_dialog


STEP_KEYS = ("step_check", "step_download", "step_apply", "step_done")
DOWNLOAD_TASKS = ("task_download", "task_verify", "task_extract")
APPLY_TASKS = ("task_wait_exit", "task_backup", "task_install", "task_launch")
MONO_FAMILY = "JetBrains Mono"


def parse_release_highlights(body: str) -> list[str]:
    """릴리스 본문 전체가 아니라 사용자가 먼저 읽을 변경 세 줄만 가져온다."""
    result = []
    for line in body.splitlines():
        match = re.match(r"\s*[-*]\s+(.+)", line)
        if not match:
            continue
        item = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", match.group(1))
        item = re.sub(r"[*_`]+", "", item).strip()
        if item:
            result.append(item)
        if len(result) == 3:
            break
    return result


def fit_window_height(window: QWidget) -> None:
    """창 높이를 지금 폭에서 실제로 필요한 만큼으로 맞춘다. adjustSize를 대신한다.

    adjustSize는 줄바꿈 라벨의 권장 크기(좁은 폭을 가정해 줄을 더 센다)로 높이를 잡아, 남는 높이가
    단계 줄과 단추 줄의 빈 공간이 됐다(실측: 필요한 470px에 한국어 502px, 일본어 538px).
    **밀린 LayoutRequest를 먼저 처리한다** - 글을 바꾼 직전의 안쪽 배치는 옛 값을 들고 있어, 그대로
    재면 적용 창이 68px 크거나 태국어 실패 화면이 16px 작아 글이 잘렸다(실측).
    """
    window.ensurePolished()
    layout = window.layout()
    if layout is None or not layout.hasHeightForWidth():
        window.adjustSize()
        return
    QCoreApplication.sendPostedEvents(None, QEvent.Type.LayoutRequest)
    layout.invalidate()
    layout.activate()
    window.resize(window.width(), layout.totalHeightForWidth(window.width()))


def refit_after_show(window: QWidget, recenter: bool) -> None:
    """뜬 직후 높이를 다시 맞춘다. 뜨기 전에 잰 값은 서체 적용 전이라 13~45px가 남았다(실측).

    자리는 _DialogPlacer가 옛 높이로 이미 잡았으므로, 높이가 바뀌면 가운데로 다시 놓는다.
    """
    before = window.height()
    fit_window_height(window)
    if recenter and window.height() != before:
        center_dialog(window)


def format_size_mb(size: int | float | None) -> str:
    return f"{max(0, size or 0) / (1024 * 1024):.1f} MB"


def format_eta(seconds: float | None) -> tuple[str, dict] | None:
    if seconds is None or seconds < 0:
        return None
    if seconds < 60:
        return "eta_seconds", {"seconds": max(1, round(seconds))}
    return "eta_minutes", {"minutes": max(1, round(seconds / 60))}


class SpeedMeter:
    """최근 구간만 써서 일시 정지나 시작 직후의 수치를 전체 평균에 묻히지 않게 한다."""

    def __init__(self, window: float = 2.0):
        self.window = window
        self.samples = deque()

    def add(self, received: int, now: float | None = None) -> float:
        now = time.monotonic() if now is None else now
        self.samples.append((now, received))
        while len(self.samples) > 2 and now - self.samples[0][0] > self.window:
            self.samples.popleft()
        if len(self.samples) < 2:
            return 0.0
        first_time, first_bytes = self.samples[0]
        return max(0.0, received - first_bytes) / max(0.001, now - first_time)


def view_model(stage: str, data: dict) -> dict:
    """프로세스와 무관하게 화면의 구역·작업·닫기 규칙을 한 번에 정한다."""
    steps = {
        "check": ("active", "pending", "pending", "pending"),
        "downloading": ("done", "active", "pending", "pending"),
        "download_failed": ("done", "failed", "pending", "pending"),
        "applying": ("done", "done", "active", "pending"),
        "done": ("done", "done", "done", "done"),
        "apply_failed": ("done", "done", "failed", "pending"),
    }[stage]
    titles = {
        "check": "title_check", "downloading": "title_downloading",
        "download_failed": "title_download_failed", "applying": "title_applying",
        "done": "title_done", "apply_failed": "title_apply_failed",
    }
    actions = {
        "check": ("btn_changelog", "btn_close" if data.get("single_button") else
                  "btn_later", "btn_update_now"),
        "downloading": ("btn_cancel",),
        "download_failed": ("btn_close", "btn_retry"),
        "applying": ("btn_close_disabled",),
        "done": ("btn_close",),
        "apply_failed": ("btn_release_page", "btn_close"),
    }[stage]
    tasks = []
    if stage in {"downloading", "download_failed"}:
        active = {"download": 0, "verify": 1, "extract": 2}.get(
            data.get("task", "download"), 0)
        for index, key in enumerate(DOWNLOAD_TASKS):
            if index == 1 and data.get("has_digest"):
                key = "task_verify_sha256"
            state = ("done" if index < active else "active" if index == active
                     else "pending")
            if stage == "download_failed" and index == active:
                state = "failed"
            tasks.append({"key": key, "state": state,
                          "detail": data.get("task_detail", "") if index == active else ""})
    if stage in {"applying", "apply_failed"}:
        active = {"waiting": 0, "backing_up": 1, "installing": 2,
                  "done": 3, "rolling_back": 2, "rolled_back": 2,
                  "wait_timeout": 0, "bad_arguments": 0, "failed": 2}.get(
            data.get("apply_stage", "waiting"), 0)
        if stage == "apply_failed" or data.get("apply_stage") == "rolling_back":
            active = data.get("failed_task_index", active)
        for index, key in enumerate(APPLY_TASKS):
            state = ("done" if index < active else "active" if index == active
                     else "pending")
            if (stage == "apply_failed" or data.get("apply_stage") == "rolling_back") and index == active:
                state = "failed"
            detail = data.get("task_detail", "") if index == active else ""
            tasks.append({"key": key, "state": state, "detail": detail})
        if stage == "apply_failed" and data.get("rolled_back"):
            tasks.append({"key": "task_rollback", "state": "done", "detail": ""})
        elif data.get("apply_stage") == "rolling_back":
            tasks.append({"key": "task_rollback", "state": "active", "detail": ""})
        elif stage == "apply_failed" and data.get("rollback_failed"):
            tasks.append({"key": "task_rollback", "state": "failed", "detail": ""})
    return {
        "stage": stage, "steps": steps, "title_key": titles[stage],
        "actions": actions, "closable": stage in {"check", "download_failed", "done",
                                                  "apply_failed"},
        "sections": {
            "info": stage == "check", "highlights": stage == "check" and
            bool(data.get("highlights")), "notes": stage == "check",
            "progress": stage in {"downloading", "applying", "done"},
            "tasks": bool(tasks), "lock": stage == "applying",
            "summary": stage == "done", "cause": stage in {"download_failed",
                                                           "apply_failed"},
        },
        "tasks": tasks,
        "restart_key": "note_restart" if data.get("pending_count", 0)
        else "note_restart_no_pending",
        "progress": max(0, min(100, int(data.get("progress", 0)))),
    }


class StepDot(QWidget):
    """색과 함께 숫자·체크·X를 그려 단계 상태를 구별한다."""

    def __init__(self, theme: str, size: int = 20):
        super().__init__()
        self.theme = theme
        self.mode = "pending"
        self.number = 0
        self.angle = 0
        self.setFixedSize(size, size)
        self.timer = QTimer(self)
        self.timer.setInterval(40)
        self.timer.timeout.connect(self._advance)

    def set_status(self, mode: str, number: int = 0):
        self.mode = mode
        self.number = number
        if mode == "active_ring" and self.isVisible():
            self.timer.start()
        else:
            self.timer.stop()
        self.update()

    def _advance(self):
        self.angle = (self.angle + 14) % 360
        self.update()

    def hideEvent(self, event):
        self.timer.stop()
        super().hideEvent(event)

    def showEvent(self, event):
        if self.mode == "active_ring":
            self.timer.start()
        super().showEvent(event)

    def paintEvent(self, event):
        colors = palette(self.theme)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(2, 2, -2, -2)
        mode = self.mode
        if mode == "active_ring":
            painter.setPen(QPen(QColor(colors["border"]), 1.5))
            painter.drawEllipse(rect)
            painter.setPen(QPen(QColor(colors["accent"]), 2))
            painter.drawArc(rect, self.angle * 16, 100 * 16)
        elif mode == "done_large":
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(blend(colors["refresh"], colors["surface"], 0.13)))
            painter.drawEllipse(rect)
            painter.setPen(QPen(QColor(colors["refresh"]), 3))
            width, height = self.width(), self.height()
            painter.drawLine(int(width * 0.28), int(height * 0.52),
                             int(width * 0.44), int(height * 0.66))
            painter.drawLine(int(width * 0.44), int(height * 0.66),
                             int(width * 0.73), int(height * 0.35))
        elif mode == "pending":
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(colors["border_strong"]), 1.5))
            painter.drawEllipse(rect)
            if self.number:
                painter.setPen(QColor(colors["text_dim"]))
                font = painter.font()
                font.setFamily(MONO_FAMILY)
                font.setPixelSize(max(9, self.width() - 9))
                painter.setFont(font)
                painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, str(self.number))
        else:
            key = {"done": "refresh", "active": "primary", "failed": "danger",
                   "warn": "warn"}[mode]
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(colors[key]))
            painter.drawEllipse(rect)
            painter.setPen(QPen(QColor(palette("light")["surface"]), 2))
            if mode == "done":
                painter.drawLine(rect.left() + 4, rect.center().y(),
                                 rect.center().x() - 1, rect.bottom() - 4)
                painter.drawLine(rect.center().x() - 1, rect.bottom() - 4,
                                 rect.right() - 3, rect.top() + 4)
            elif mode == "failed":
                painter.drawLine(rect.left() + 5, rect.top() + 5,
                                 rect.right() - 5, rect.bottom() - 5)
                painter.drawLine(rect.right() - 5, rect.top() + 5,
                                 rect.left() + 5, rect.bottom() - 5)
            else:
                font = painter.font()
                font.setFamily(MONO_FAMILY)
                font.setPixelSize(max(9, self.width() - 9))
                font.setBold(True)
                painter.setFont(font)
                painter.drawText(rect, Qt.AlignmentFlag.AlignCenter,
                                 "!" if mode == "warn" else str(self.number))
        painter.end()


class TaskRow(QWidget):
    """점 · 글 · 오른쪽 값 한 줄. **글이 남는 폭을 모두 가져야 한다.**

    사이에 stretch를 두면 줄바꿈하는 QLabel은 제 권장 폭만 받아, 한 줄에 들어갈 안내가 폭
    130px 남짓에서 두 줄로 꺾이고 창이 그만큼 길어졌다(실측: 줄 폭 372px, 글 폭 121~134px).
    """

    def __init__(self, theme: str):
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.dot = StepDot(theme, 16)
        self.label = QLabel()
        self.label.setWordWrap(True)
        self.detail = QLabel(objectName="UpdateFlowMono")
        layout.addWidget(self.dot)
        layout.addWidget(self.label, 1)
        layout.addWidget(self.detail)

    def set_task(self, task: dict):
        self.dot.set_status("active_ring" if task["state"] == "active" else
                            task["state"])
        self.label.setText(t(f"update_flow.{task['key']}"))
        self.detail.setText(task.get("detail", ""))
        self.label.setProperty("tone", task["state"])
        self.label.style().unpolish(self.label)
        self.label.style().polish(self.label)


class UpdateFlowView(QWidget):
    """확인·받기·적용·완료 화면. **주요 변경은 항목마다 한 줄로 줄이고 전체는 툴팁으로 보인다.**

    릴리스 요약 줄은 450~2,000px라(실측: 지난 릴리스 53줄 중 창 폭에 드는 것 9줄) 줄바꿈하면
    창 높이가 본문에 끌려 다닌다. 전체 내용은 `변경 내역`이 연다.
    """
    action = pyqtSignal(str)

    def __init__(self, theme: str = "light"):
        super().__init__()
        self.theme = theme
        self.state = ""
        self.data = {}
        self.setObjectName("UpdateFlow")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.header = QWidget(objectName="UpdateFlowHeader")
        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(24, 22, 24, 18)
        header_layout.setSpacing(12)
        self.hero_icon = QLabel()
        self.hero_icon.setPixmap(get_app_icon().pixmap(44, 44))
        header_layout.addWidget(self.hero_icon)
        hero_text = QVBoxLayout()
        hero_text.setSpacing(3)
        self.title = QLabel(objectName="UpdateFlowTitle")
        self.title.setWordWrap(True)
        self.subtitle = QLabel(objectName="UpdateFlowSubtitle")
        self.subtitle.setWordWrap(True)
        hero_text.addWidget(self.title)
        hero_text.addWidget(self.subtitle)
        self.header_hint = QLabel(objectName="UpdateFlowDim")
        self.header_hint.setWordWrap(True)
        hero_text.addWidget(self.header_hint)
        header_layout.addLayout(hero_text, 1)
        outer.addWidget(self.header)
        self.done_hero = QWidget(objectName="UpdateFlowHeader")
        done_layout = QVBoxLayout(self.done_hero)
        done_layout.setContentsMargins(24, 22, 24, 18)
        done_layout.setSpacing(6)
        self.done_dot = StepDot(theme, 52)
        self.done_dot.set_status("done_large")
        self.done_title = QLabel(objectName="UpdateFlowTitle")
        self.done_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.done_title.setWordWrap(True)
        self.done_versions = QLabel(objectName="UpdateFlowSubtitle")
        self.done_versions.setAlignment(Qt.AlignmentFlag.AlignCenter)
        done_layout.addWidget(self.done_dot, alignment=Qt.AlignmentFlag.AlignHCenter)
        done_layout.addWidget(self.done_title)
        done_layout.addWidget(self.done_versions)
        outer.addWidget(self.done_hero)

        self.steps_box = QWidget(objectName="UpdateFlowSteps")
        steps_layout = QHBoxLayout(self.steps_box)
        steps_layout.setContentsMargins(24, 11, 24, 11)
        steps_layout.setSpacing(5)
        self.step_dots = []
        self.step_labels = []
        self.step_lines = []
        for index, key in enumerate(STEP_KEYS):
            dot = StepDot(theme)
            label = QLabel(t(f"update_flow.{key}"), objectName="UpdateFlowStepText")
            steps_layout.addWidget(dot)
            steps_layout.addWidget(label)
            self.step_dots.append(dot)
            self.step_labels.append(label)
            if index < 3:
                line = QWidget(objectName="UpdateFlowStepLine")
                line.setFixedHeight(1)
                steps_layout.addWidget(line, 1)
                self.step_lines.append(line)
        outer.addWidget(self.steps_box)

        self.content = QWidget()
        body = QVBoxLayout(self.content)
        body.setContentsMargins(24, 18, 24, 18)
        body.setSpacing(12)
        self.info_box = QWidget()
        info = QGridLayout(self.info_box)
        info.setContentsMargins(0, 0, 0, 0)
        info.setHorizontalSpacing(10)
        info.setVerticalSpacing(6)
        self.size_value = QLabel(objectName="UpdateFlowMono")
        self.date_value = QLabel(objectName="UpdateFlowMono")
        for row, (key, value) in enumerate((("label_size", self.size_value),
                                             ("label_released", self.date_value))):
            label = QLabel(t(f"update_flow.{key}"), objectName="UpdateFlowDim")
            label.setFixedWidth(72)
            info.addWidget(label, row, 0)
            info.addWidget(value, row, 1)
        body.addWidget(self.info_box)
        self.highlights_box = QWidget()
        highlights = QVBoxLayout(self.highlights_box)
        highlights.setContentsMargins(0, 0, 0, 0)
        highlights.setSpacing(5)
        highlights.addWidget(QLabel(t("update_flow.label_highlights"),
                                    objectName="UpdateFlowSmallTitle"))
        self.highlight_labels = []
        for _ in range(3):
            label = ElidedLabel(tooltip_when_elided=True)
            highlights.addWidget(label)
            self.highlight_labels.append(label)
        body.addWidget(self.highlights_box)
        self.notes_box = QWidget()
        notes = QVBoxLayout(self.notes_box)
        notes.setContentsMargins(0, 0, 0, 0)
        notes.setSpacing(7)
        self.note_rows = []
        for key, tone in (("note_keep_using", "active"),
                          ("note_restart", "warn"), ("note_data_kept", "done")):
            row = TaskRow(theme)
            row.dot.set_status(tone)
            notes.addWidget(row)
            self.note_rows.append((key, row))
        body.addWidget(self.notes_box)
        self.progress_box = QWidget()
        progress_layout = QVBoxLayout(self.progress_box)
        progress_layout.setContentsMargins(0, 0, 0, 0)
        progress_layout.setSpacing(7)
        metrics = QHBoxLayout()
        self.percent_label = QLabel(objectName="UpdateFlowPercent")
        self.eta_label = QLabel(objectName="UpdateFlowDim")
        metrics.addWidget(self.percent_label)
        metrics.addStretch(1)
        metrics.addWidget(self.eta_label)
        progress_layout.addLayout(metrics)
        self.bar = QProgressBar(objectName="UpdateFlowProgress")
        self.bar.setRange(0, 100)
        self.bar.setTextVisible(False)
        progress_layout.addWidget(self.bar)
        transfer = QHBoxLayout()
        self.amount_label = QLabel(objectName="UpdateFlowMono")
        self.speed_label = QLabel(objectName="UpdateFlowMono")
        transfer.addWidget(self.amount_label)
        transfer.addStretch(1)
        transfer.addWidget(self.speed_label)
        progress_layout.addLayout(transfer)
        body.addWidget(self.progress_box)
        self.tasks_box = QWidget()
        task_layout = QVBoxLayout(self.tasks_box)
        task_layout.setContentsMargins(0, 0, 0, 0)
        task_layout.setSpacing(8)
        self.task_rows = [TaskRow(theme) for _ in range(5)]
        for row in self.task_rows:
            task_layout.addWidget(row)
        body.addWidget(self.tasks_box)
        self.lock_box = QLabel(t("update_flow.lock_notice"),
                               objectName="UpdateFlowNotice")
        self.lock_box.setWordWrap(True)
        body.addWidget(self.lock_box)
        self.summary_box = QWidget(objectName="UpdateFlowSummary")
        summary = QVBoxLayout(self.summary_box)
        summary.setContentsMargins(12, 12, 12, 12)
        summary.setSpacing(6)
        self.summary_labels = [QLabel() for _ in range(3)]
        for label in self.summary_labels:
            label.setWordWrap(True)
            summary.addWidget(label)
        body.addWidget(self.summary_box)
        self.hint = QLabel(objectName="UpdateFlowDim")
        self.hint.setWordWrap(True)
        body.addWidget(self.hint)
        self.cause_box = QWidget(objectName="UpdateFlowCause")
        cause_layout = QVBoxLayout(self.cause_box)
        cause_layout.setContentsMargins(12, 10, 12, 10)
        cause_layout.setSpacing(4)
        cause_layout.addWidget(QLabel(t("update_flow.cause_title"),
                                      objectName="UpdateFlowCauseTitle"))
        self.cause_label = QLabel()
        self.cause_label.setWordWrap(True)
        cause_layout.addWidget(self.cause_label)
        body.addWidget(self.cause_box)
        outer.addWidget(self.content)

        self.footer = QWidget(objectName="UpdateFlowFooter")
        buttons = QHBoxLayout(self.footer)
        buttons.setContentsMargins(24, 11, 24, 18)
        buttons.setSpacing(8)
        self.link_button = QPushButton(objectName="LinkButton")
        self.secondary_button = QPushButton(objectName="UpdateFlowSecondary")
        self.primary_button = QPushButton(objectName="PrimaryButton")
        for button in (self.link_button, self.secondary_button, self.primary_button):
            button.setFixedHeight(38)
            button.clicked.connect(lambda checked=False, widget=button:
                                   self.action.emit(widget.property("flow_action")))
        buttons.addWidget(self.link_button)
        buttons.addStretch(1)
        buttons.addWidget(self.secondary_button)
        buttons.addWidget(self.primary_button)
        outer.addWidget(self.footer)
        self.set_state("check", {})

    def set_state(self, stage: str, data: dict):
        self.state = stage
        self.data = dict(data)
        model = view_model(stage, data)
        self.title.setText(t(f"update_flow.{model['title_key']}"))
        self.header.setVisible(stage != "done")
        self.done_hero.setVisible(stage == "done")
        self.done_title.setText(t("update_flow.title_done"))
        old = data.get("from_version", "")
        new = data.get("to_version", "")
        if old and new:
            colors = palette(self.theme)
            accent = colors["refresh"] if stage == "done" else (
                colors["danger"] if stage == "apply_failed" else colors["accent"])
            self.subtitle.setText(f'<span style="color:{colors["text_dim"]}">'
                                  f'{escape(str(old))} → </span>'
                                  f'<span style="color:{accent}">{escape(str(new))}</span>')
        else:
            self.subtitle.setText(t("update_flow.applying_sub") if stage == "applying"
                                  else "")
        self.done_versions.setText(self.subtitle.text())
        self.header_hint.setText(t("update_flow.applying_sub") if stage == "applying"
                                 else t("update_flow.failed_sub", version=old)
                                 if stage == "apply_failed" and data.get("rolled_back")
                                 else "")
        self.header_hint.setVisible(bool(self.header_hint.text()))
        self.subtitle.setProperty("tone", "done" if stage == "done" else
                                  "failed" if stage == "apply_failed" else "active")
        self._repolish(self.subtitle)
        for index, mode in enumerate(model["steps"]):
            self.step_dots[index].set_status(mode, index + 1)
            self.step_labels[index].setProperty("tone", mode)
            self._repolish(self.step_labels[index])
            if index < 3:
                self.step_lines[index].setProperty("tone", "done" if mode == "done"
                                                   else "pending")
                self._repolish(self.step_lines[index])
        sections = model["sections"]
        self.info_box.setVisible(sections["info"])
        self.highlights_box.setVisible(sections["highlights"])
        self.notes_box.setVisible(sections["notes"])
        self.progress_box.setVisible(sections["progress"])
        self.tasks_box.setVisible(sections["tasks"])
        self.lock_box.setVisible(sections["lock"])
        self.summary_box.setVisible(sections["summary"])
        self.cause_box.setVisible(sections["cause"])
        self.size_value.setText(format_size_mb(data.get("size", 0)))
        self.date_value.setText(str(data.get("published", "")))
        for label, item in zip(self.highlight_labels,
                               list(data.get("highlights", [])) + [""] * 3):
            label.setText("• " + item if item else "")
            label.setVisible(bool(item))
        for index, (key, row) in enumerate(self.note_rows):
            actual = model["restart_key"] if index == 1 else key
            row.label.setText(t(f"update_flow.{actual}",
                                count=data.get("pending_count", 0)))
            row.detail.setText("")
            row.dot.set_status(("active", "warn", "done")[index])
        percent = model["progress"]
        self.percent_label.setText(f"{percent}%")
        self.percent_label.setVisible(stage == "downloading")
        eta = format_eta(data.get("eta_s"))
        self.eta_label.setText(t(f"update_flow.{eta[0]}", **eta[1]) if eta else "")
        self.eta_label.setVisible(stage == "downloading" and bool(eta))
        self.bar.setValue(100 if stage == "done" else percent)
        self.bar.setProperty("state", "done" if stage == "done" else
                             "error" if stage.endswith("failed") else "active")
        self._repolish(self.bar)
        self.amount_label.setText(f"{format_size_mb(data.get('received'))} / "
                                  f"{format_size_mb(data.get('total'))}")
        self.speed_label.setText(f"{(data.get('speed_bps') or 0) / (1024 * 1024):.1f} MB/s"
                                 if data.get("speed_bps") else "")
        self.amount_label.setVisible(stage == "downloading")
        self.speed_label.setVisible(stage == "downloading" and bool(data.get("speed_bps")))
        for row, task in zip(self.task_rows, model["tasks"]):
            row.set_task(task)
            row.setVisible(True)
        for row in self.task_rows[len(model["tasks"]):]:
            row.setVisible(False)
        self.summary_labels[0].setText(t("update_flow.summary_files",
                                        count=data.get("installed_count", 0)))
        self.summary_labels[1].setText(t("update_flow.summary_queue",
                                        count=data.get("queued_count", 0)))
        self.summary_labels[1].setVisible(bool(data.get("queued_count", 0)))
        self.summary_labels[2].setText(t("update_flow.summary_kept"))
        self.hint.setText(t("update_flow.done_hint") if stage == "done" else "")
        self.hint.setVisible(stage == "done")
        self.cause_label.setText(next(iter(str(data.get("error", "")).splitlines()), "") +
                                 (("\n" + str(data["manual"])) if data.get("manual") else ""))
        self._set_actions(model["actions"])
        self.updateGeometry()
        if self.isVisible():
            self.adjustSize()

    def _set_actions(self, actions: tuple[str, ...]):
        link = next((key for key in actions if key in {"btn_changelog",
                                                       "btn_release_page"}), None)
        regular = [key for key in actions if key not in {"btn_changelog",
                                                          "btn_release_page"}]
        self.link_button.setVisible(link is not None)
        if link:
            self._button(self.link_button, link)
        only_secondary = len(regular) == 1 and regular[0] in {
            "btn_cancel", "btn_close_disabled"}
        self.secondary_button.setVisible(len(regular) > 1 or only_secondary)
        if len(regular) > 1 or only_secondary:
            self._button(self.secondary_button, regular[0])
        self.primary_button.setVisible(bool(regular) and not only_secondary)
        if regular and not only_secondary:
            self._button(self.primary_button, regular[-1])

    def _button(self, button: QPushButton, key: str):
        button.setText(t(f"update_flow.{key.replace('_disabled', '')}"))
        button.setProperty("flow_action", key)
        button.setEnabled(not key.endswith("_disabled"))

    @staticmethod
    def _repolish(widget):
        widget.style().unpolish(widget)
        widget.style().polish(widget)
