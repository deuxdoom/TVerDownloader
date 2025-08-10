# TVerDownloader.py
# 수정:
# - QLocalServer와 QLocalSocket을 이용한 단일 인스턴스 실행 기능 추가
# - 프로그램 중복 실행 시, 이미 실행된 창을 활성화하고 새 인스턴스는 종료

import sys
import os
import webbrowser
import subprocess
from typing import List, Dict, Optional

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QListWidgetItem, QMessageBox, QSystemTrayIcon,
    QFileDialog, QMenu
)
from PyQt6.QtCore import Qt, QEvent, QTimer
from PyQt6.QtGui import QCursor, QAction, QGuiApplication
from PyQt6.QtNetwork import QLocalServer, QLocalSocket

from src.utils import load_config, save_config, handle_exception, open_file_location
from src.qss import build_qss
from src.about_dialog import AboutDialog
from src.bulk_dialog import BulkAddDialog
from src.dialogs import SettingsDialog
from src.history_store import HistoryStore
from src.favorites_store import FavoritesStore
from src.widgets import DownloadItemWidget
from src.updater import maybe_show_update

from src.threads.setup_thread import SetupThread
from src.ui.main_window_ui import MainWindowUI
from src.series_parser import SeriesParser
from src.download_manager import DownloadManager

APP_NAME_EN = "TVer Downloader"
APP_VERSION = "2.3.1"
SOCKET_NAME = "TVerDownloader_IPC_Socket" # 단일 인스턴스 확인을 위한 고유 소켓 이름

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME_EN} v{APP_VERSION}")
        self.force_quit = False

        self.config = load_config()
        self.history_store = HistoryStore()
        self.history_store.load()
        self.fav_store = FavoritesStore("favorites.json")
        self.fav_store.load()

        self.ui = MainWindowUI(self)
        self.ui.setup_ui()
        self.tray_icon = QSystemTrayIcon(self)
        self.ui.setup_tray(APP_VERSION)
        
        self.series_parser = SeriesParser(ytdlp_path="")
        self.download_manager = DownloadManager(self.config, self.history_store)
        
        self._connect_signals()
        
        self._set_input_enabled(False)
        self.set_always_on_top(self.config.get("always_on_top", False))
        self.refresh_history_list()
        self.refresh_fav_list()

        self.append_log("프로그램 시작. 환경 설정을 시작합니다...")
        self.setup_thread = SetupThread(self)
        self.setup_thread.log.connect(self.append_log)
        self.setup_thread.finished.connect(self._on_setup_finished)
        self.setup_thread.start()

    def _connect_signals(self):
        """UI와 매니저 간의 시그널-슬롯을 연결합니다."""
        self.ui.add_button.clicked.connect(self.process_input_url)
        self.ui.url_input.returnPressed.connect(self.process_input_url)
        self.ui.bulk_button.clicked.connect(self.open_bulk_add)
        self.ui.settings_button.clicked.connect(self.open_settings)
        self.ui.about_button.clicked.connect(lambda: AboutDialog(APP_VERSION, self).exec())
        self.ui.clear_log_button.clicked.connect(self.clear_log)
        self.ui.on_top_btn.toggled.connect(self.set_always_on_top)
        
        self.ui.download_list.customContextMenuRequested.connect(self.show_download_context_menu)
        
        self.ui.history_list.customContextMenuRequested.connect(self.show_history_menu)
        
        self.ui.fav_add_btn.clicked.connect(self.add_favorite)
        self.ui.fav_del_btn.clicked.connect(self.remove_selected_favorite)
        self.ui.fav_chk_btn.clicked.connect(self.check_all_favorites)
        self.ui.fav_list.customContextMenuRequested.connect(self.show_fav_menu)

        self.download_manager.log.connect(self.append_log)
        self.download_manager.item_added.connect(self._add_item_widget)
        self.download_manager.progress_updated.connect(self._update_item_widget)
        self.download_manager.task_finished.connect(self._on_task_finished)
        self.download_manager.queue_changed.connect(
            lambda q, a: self.ui.queue_count_label.setText(f"{q} 대기 / {a} 진행")
        )
        self.download_manager.all_tasks_completed.connect(self._on_all_downloads_finished)

        self.series_parser.log.connect(lambda ctx, msg: self.append_log(msg))
        self.series_parser.finished.connect(self._on_series_parsed)

        self.tray_icon.activated.connect(self._on_tray_icon_activated)

    def _handle_new_instance(self):
        """새로운 인스턴스가 실행되었을 때 호출되는 슬롯."""
        # 혹시 모를 연결은 무시하고, 창을 활성화하는 데 집중
        server = self.sender()
        if isinstance(server, QLocalServer):
            server.nextPendingConnection().close()
        
        # 창이 최소화되어 있다면 원래 크기로 복원하고, 맨 앞으로 가져와 활성화
        self.showNormal()
        self.activateWindow()
        self.raise_()

    def _set_input_enabled(self, enabled: bool):
        self.ui.url_input.setEnabled(enabled)
        self.ui.add_button.setEnabled(enabled)
        self.ui.bulk_button.setEnabled(enabled)
        self.ui.fav_chk_btn.setEnabled(enabled)
        
    def _ensure_download_folder(self) -> bool:
        folder = self.config.get("download_folder")
        if folder and os.path.isdir(folder):
            return True

        new_folder = QFileDialog.getExistingDirectory(self, "다운로드 폴더 선택")
        if new_folder:
            self.config["download_folder"] = new_folder
            save_config(self.config)
            self.download_manager.update_config(self.config)
            self.append_log(f"다운로드 폴더가 '{new_folder}'(으)로 설정되었습니다.")
            return True
        
        return False

    def process_input_url(self):
        url = self.ui.url_input.text().strip()
        if not url: return

        if not self._ensure_download_folder():
            self.append_log("[알림] 다운로드 폴더가 선택되지 않아 작업이 취소되었습니다.")
            return

        if "/series/" in url:
            self._set_input_enabled(False)
            self.series_parser.parse('single', [url])
        else:
            self._request_add_task(url)
        self.ui.url_input.clear()

    def _request_add_task(self, url: str):
        if self.history_store.exists(url):
            title = self.history_store.get_title(url)
            reply = QMessageBox.question(self, '중복 다운로드', 
                f"이미 다운로드한 항목입니다:\n\n{title}\n\n다시 다운로드할까요?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.No:
                self.append_log(f"[알림] 중복 다운로드 취소: {url}")
                return
        
        self.download_manager.add_task(url)

    def open_bulk_add(self):
        if not self._ensure_download_folder():
            self.append_log("[알림] 다운로드 폴더가 선택되지 않아 작업이 취소되었습니다.")
            return

        dialog = BulkAddDialog(self)
        if dialog.exec():
            urls = dialog.get_urls()
            if not urls: return

            normal_urls = [u for u in urls if "/series/" not in u]
            series_urls = [u for u in urls if "/series/" in u]

            for url in normal_urls:
                self._request_add_task(url)
            
            if series_urls:
                self.series_parser.parse('bulk', series_urls)

    def _on_setup_finished(self, ok: bool, ytdlp_path: str, ffmpeg_path: str):
        if not ok:
            self.append_log("[오류] 초기 준비 실패: yt-dlp/ffmpeg를 준비하지 못했습니다.")
            QMessageBox.critical(self, "오류", "초기 준비에 실패했습니다. 로그를 확인하세요.")
            return

        self.download_manager.set_paths(ytdlp_path, ffmpeg_path)
        self.series_parser.set_ytdlp_path(ytdlp_path)
        self._set_input_enabled(True)

        self.append_log(f"{'=' * 44}\n📢 [안내] TVer는 일본 지역 제한이 있습니다.\n📢 원활한 다운로드를 위해 반드시 일본 VPN을 켜고 사용해주세요.\n{'=' * 44}")
        self.append_log("환경 설정 완료. 다운로드를 시작할 수 있습니다.")
        
        QTimer.singleShot(1000, lambda: maybe_show_update(self, APP_VERSION))

        if self.config.get("auto_check_favorites_on_start", True):
            self.check_all_favorites()

    def _on_series_parsed(self, context: str, series_url: str, episode_urls: List[str]):
        if context == 'single':
            self._set_input_enabled(True)
            self.append_log(f"[시리즈] 분석 완료. {len(episode_urls)}개 에피소드를 추가합니다.")

        added_count = 0
        for url in episode_urls:
            if context == 'fav-check' and self.history_store.exists(url):
                continue
            
            self._request_add_task(url)
            added_count += 1
        
        if context == 'fav-check':
            self.fav_store.touch_last_check(series_url)
            self.refresh_fav_list()
            self.append_log(f"[즐겨찾기] '{series_url}' 확인 -> 신규 {added_count}개 추가 요청")

    def _add_item_widget(self, url: str):
        item = QListWidgetItem()
        widget = DownloadItemWidget(url)
        widget.play_requested.connect(self.play_file)
        item.setSizeHint(widget.sizeHint())
        self.ui.download_list.insertItem(0, item)
        self.ui.download_list.setItemWidget(item, widget)

    def _find_item_widget(self, url: str) -> Optional[DownloadItemWidget]:
        for i in range(self.ui.download_list.count()):
            item = self.ui.download_list.item(i)
            widget = self.ui.download_list.itemWidget(item)
            if isinstance(widget, DownloadItemWidget) and widget.url == url:
                return widget
        return None

    def _update_item_widget(self, url: str, payload: Dict):
        widget = self._find_item_widget(url)
        if widget:
            widget.update_progress(payload)

    def _on_task_finished(self, url: str, success: bool):
        widget = self._find_item_widget(url)
        if not widget: return

        if success:
            title = widget.title_label.text()
            self.history_store.add(url, title, widget.final_filepath)
            self.history_store.save()
            self.refresh_history_list()
    
    def _on_all_downloads_finished(self):
        self.append_log("모든 다운로드가 완료되었습니다.")
        self.tray_icon.showMessage("다운로드 완료", "모든 작업이 끝났습니다!", self.windowIcon(), 5000)
        
        post_action = self.config.get("post_action", "None")
        if post_action == "Open Folder":
            folder = self.config.get("download_folder")
            if folder and os.path.isdir(folder):
                try: os.startfile(folder)
                except Exception as e: self.append_log(f"[오류] 폴더 열기 실패: {e}")
        elif post_action == "Shutdown":
            try:
                self.append_log("1분 후 시스템을 종료합니다...")
                subprocess.run(["shutdown", "/s", "/t", "60"])
            except Exception as e: self.append_log(f"[오류] 시스템 종료 명령 실패: {e}")

    def show_download_context_menu(self, pos):
        item = self.ui.download_list.itemAt(pos)
        if not item: return
        widget = self.ui.download_list.itemWidget(item)
        if not isinstance(widget, DownloadItemWidget): return
        
        url = widget.url; menu = QMenu()
        if url in self.download_manager._active_threads:
            menu.addAction("중지", lambda: self.download_manager.stop_task(url))
        elif url in self.download_manager._task_queue:
            def remove_from_queue():
                if self.download_manager.remove_task_from_queue(url): self.ui.download_list.takeItem(self.ui.download_list.row(item))
            menu.addAction("대기열에서 제거", remove_from_queue)
        else:
            menu.addAction("목록에서 삭제", lambda: self.ui.download_list.takeItem(self.ui.download_list.row(item)))
        if widget.final_filepath and os.path.exists(widget.final_filepath):
            menu.addAction("파일 위치 열기", lambda: open_file_location(widget.final_filepath))
        menu.exec(QCursor.pos())
    
    def append_log(self, text: str):
        color_map = {"[오류]": "#EF4444", "[치명적 오류]": "#EF4444", "완료": "#22C55E", "성공": "#22C55E"}
        color = next((c for k, c in color_map.items() if k in text), None)
        self.ui.log_output.append(f'<span style="color: {color};">{text}</span>' if color else text)
        self.ui.log_output.verticalScrollBar().setValue(self.ui.log_output.verticalScrollBar().maximum())

    def clear_log(self): self.ui.log_output.clear()
    def play_file(self, filepath: str):
        try: os.startfile(filepath); self.append_log(f"영상 재생: {filepath}")
        except Exception as e: self.append_log(f"[오류] 재생 실패: {e}")
    
    def refresh_history_list(self):
        self.ui.history_list.clear()
        for url, meta in self.history_store.sorted_entries():
            title = meta.get("title", "(제목 없음)"); date = meta.get("date", "")
            item = QListWidgetItem(f"{title}  •  {date}\n{url}"); item.setData(Qt.ItemDataRole.UserRole, url)
            self.ui.history_list.addItem(item)
            
    def show_history_menu(self, pos):
        item = self.ui.history_list.itemAt(pos);
        if not item: return
        url = item.data(Qt.ItemDataRole.UserRole); menu = QMenu()
        menu.addAction("URL 복사", lambda: QGuiApplication.clipboard().setText(url))
        menu.addAction("다시 다운로드", lambda: self._request_add_task(url))
        menu.addAction("기록에서 제거", lambda: self.remove_from_history(url))
        menu.exec(QCursor.pos())

    def remove_from_history(self, url: str):
        self.history_store.remove(url); self.history_store.save(); self.refresh_history_list()
        self.append_log(f"[알림] 기록에서 제거됨: {url}")
        
    def refresh_fav_list(self):
        self.ui.fav_list.clear()
        for url, meta in self.fav_store.sorted_entries():
            last_check = meta.get("last_check", "-")
            item = QListWidgetItem(f"{url}\n마지막 확인: {last_check}"); item.setData(Qt.ItemDataRole.UserRole, url)
            self.ui.fav_list.addItem(item)

    def add_favorite(self):
        url = self.ui.fav_input.text().strip()
        if not url or "/series/" not in url: QMessageBox.information(self, "알림", "유효한 TVer 시리즈 URL을 입력하세요."); return
        if self.fav_store.exists(url): QMessageBox.information(self, "알림", "이미 즐겨찾기에 있습니다."); return
        self.fav_store.add(url); self.ui.fav_input.clear(); self.refresh_fav_list(); self.append_log(f"[즐겨찾기] 추가: {url}")

    def remove_selected_favorite(self):
        selected_items = self.ui.fav_list.selectedItems()
        if not selected_items:
            QMessageBox.information(self, "알림", "삭제할 항목을 목록에서 선택하세요.")
            return
        
        reply = QMessageBox.question(self, "삭제 확인", f"{len(selected_items)}개의 항목을 삭제할까요?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                     QMessageBox.StandardButton.No)
        
        if reply == QMessageBox.StandardButton.Yes:
            for item in selected_items:
                url = item.data(Qt.ItemDataRole.UserRole)
                self.fav_store.remove(url)
                self.append_log(f"[즐겨찾기] 삭제: {url}")
            self.refresh_fav_list()

    def check_all_favorites(self):
        folder = self.config.get("download_folder")
        if not folder or not os.path.isdir(folder):
            self.append_log("[알림] 다운로드 폴더가 설정되지 않아 시작 시 즐겨찾기 자동 확인을 건너뜁니다.")
            return
        urls = self.fav_store.list_series()
        if not urls:
            if self.sender() == self.ui.fav_chk_btn: QMessageBox.information(self, "알림", "등록된 즐겨찾기가 없습니다.")
            return
        self.append_log(f"[즐겨찾기] 전체 확인 시작 ({len(urls)}개 시리즈)"); self.series_parser.parse('fav-check', urls)
        
    def show_fav_menu(self, pos):
        item = self.ui.fav_list.itemAt(pos);
        if not item: return
        url = item.data(Qt.ItemDataRole.UserRole); menu = QMenu()
        menu.addAction("이 시리즈 확인", lambda: self.series_parser.parse('fav-check', [url]))
        menu.addAction("브라우저에서 열기", lambda: webbrowser.open(url))
        menu.addAction("삭제", lambda: self.remove_favorite(url))
        menu.exec(QCursor.pos())

    def remove_favorite(self, url: str):
        self.fav_store.remove(url); self.refresh_fav_list(); self.append_log(f"[즐겨찾기] 삭제: {url}")

    def open_settings(self):
        dialog = SettingsDialog(self.config, self)
        if dialog.exec():
            self.config = load_config()
            self.download_manager.update_config(self.config)
            self.append_log(f"설정이 저장되었습니다. 동시 다운로드: {self.config['max_concurrent_downloads']}개")

    def set_always_on_top(self, on: bool):
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, on); self.show()
        self.ui.on_top_btn.setChecked(on); self.ui.on_top_btn.setText("●" if on else "")
        self.config["always_on_top"] = on; save_config(self.config)

    def _on_tray_icon_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick: self.showNormal()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange and self.isMinimized():
            self.hide()
            self.tray_icon.showMessage(APP_NAME_EN, "프로그램이 트레이로 이동했습니다.", self.windowIcon(), 2000)

    def closeEvent(self, event):
        if self.force_quit: event.accept(); return
        reply = QMessageBox.question(self, '종료 확인', '종료하시겠습니까?', QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes: self.quit_application(); event.accept()
        else: event.ignore()

    def quit_application(self):
        self.append_log("프로그램을 종료합니다...")
        for url in list(self.download_manager._active_threads.keys()):
            self.download_manager.stop_task(url)
        self.force_quit = True
        self.tray_icon.hide()
        QApplication.instance().quit()


if __name__ == "__main__":
    sys.excepthook = handle_exception
    
    app = QApplication(sys.argv)
    
    # --- 단일 인스턴스 확인 로직 ---
    socket = QLocalSocket()
    socket.connectToServer(SOCKET_NAME)
    
    # 서버에 연결되면 이미 실행 중인 것으로 판단
    if socket.waitForConnected(500):
        # 간단한 메시지를 보내 기존 창을 활성화하도록 요청
        socket.writeData(b'show')
        socket.flush()
        socket.waitForBytesWritten(1000)
        socket.close()
        sys.exit(0) # 현재 인스턴스 종료
    else:
        # 연결 실패 시, 기존에 비정상 종료된 서버가 있을 수 있으므로 정리
        QLocalServer.removeServer(SOCKET_NAME)
        
        server = QLocalServer()
        server.listen(SOCKET_NAME)
        
        app.setApplicationName("티버 다운로더")
        app.setApplicationVersion(APP_VERSION)
        app.setStyle("Fusion")
        app.setStyleSheet(build_qss())
        
        window = MainWindow()
        
        # 서버의 newConnection 시그널을 MainWindow의 슬롯과 연결
        server.newConnection.connect(window._handle_new_instance)
        
        window.show()
        sys.exit(app.exec())