import os, sys
from PyQt6.QtCore import QEventLoop
from PyQt6.QtWidgets import QApplication

app = QApplication(sys.argv); app.setStyle("Fusion")

import _bootstrap
_bootstrap.setup()

import TVerDownloader as T
from src.qss import build_qss
from src.dialogs import SettingsDialog
from src.utils import load_config

T.setup_app_font(app)
SC = _bootstrap.OUT_DIR


def settle():
    """app이 살아 있는 동안 창을 실제로 거둔다.

    파이썬이 끝난 뒤 Qt가 위젯 그물을 헐면 이따금 access violation으로 끝난다.
    검사가 다 끝난 뒤의 일이지만 종료 코드가 139가 되어 결과를 가린다
    (세 번에 두 번꼴로 났다). test_log.teardown과 같은 이유다.
    """
    for _ in range(6):
        app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 40)


ok = True
for theme in ("light", "dark"):
    app.setStyleSheet(build_qss(theme))
    cfg = load_config(); cfg["theme"] = theme
    d = SettingsDialog(cfg, None)
    d.resize(760, 620); d.show()
    for _ in range(6):
        app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 40)
    cb = d.clipboard_watch_checkbox
    print(f"[{theme}] 체크박스 표시={cb.isVisible()} 체크={cb.isChecked()} "
          f"글꼴={cb.font().family()!r} 힌팅={cb.font().hintingPreference().name} "
          f"전략={cb.font().styleStrategy()!r}")
    ok = ok and cb.isVisible() and cb.isChecked() is False
    fav = d.fav_autocheck_checkbox
    started_as = cfg.get("auto_check_favorites_on_start", True)
    print(f"[{theme}] 즐겨찾기 자동 확인 표시={fav.isVisible()} 초기값={fav.isChecked()}")
    ok = ok and fav.isVisible() and fav.isChecked() is started_as
    d.grab().save(f"{SC}/clip_settings_{theme}.png")
    cb.setChecked(True)
    d._save_settings()
    saved = load_config()
    print(f"[{theme}] 저장 후 clipboard_watch={saved.get('clipboard_watch')!r}")
    ok = ok and saved.get("clipboard_watch") is True
    cb.setChecked(False); d._save_settings()
    saved = load_config()
    print(f"[{theme}] 해제 후 clipboard_watch={saved.get('clipboard_watch')!r}")
    ok = ok and saved.get("clipboard_watch") is False

    for want in (False, True):
        fav.setChecked(want); d._save_settings()
        got = load_config().get("auto_check_favorites_on_start")
        print(f"[{theme}] 저장 후 auto_check_favorites_on_start={got!r}")
        ok = ok and got is want
    d.close()
    d.deleteLater()
    settle()
if os.path.exists("downloader_config.json"): os.remove("downloader_config.json")
print("ALL PASS" if ok else "FAILED")
sys.exit(0 if ok else 1)
