@echo off
rem ===== 終了操作（既存の終了batの、LoTW自動アップロードの後に追加） =====
set WATCH_DIR=C:\dx-cluster-watch
set ADIF=C:\HAMLOG\export\all_qso.adi

rem 1) PCのクラスター監視を止める
taskkill /FI "WINDOWTITLE eq cluster-watch*" /T /F >nul 2>&1

rem 2) 交信済み一覧をGitHubへ送り、監視の担当をGitHubにする
python "%WATCH_DIR%\pc\share_worked.py" --adif "%ADIF%" --mode github
