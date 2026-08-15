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
    d.close()
if os.path.exists("downloader_config.json"): os.remove("downloader_config.json")
print("ALL PASS" if ok else "FAILED")
sys.exit(0 if ok else 1)
