@echo off
rem ===== 開始操作（IC-7850用／IC-7851用PCの既存の開始batに追加） =====
rem SDR用PCでは使わない（夜間SDRのときは、IC-7850のPCの終了操作でGitHubが監視を引き継いでいる）
set WATCH_DIR=C:\dx-cluster-watch
set ADIF=C:\HAMLOG\export\all_qso.adi

rem 1) 交信済み一覧を作り、監視の担当をPCにする（GitHub側は止まる）
python "%WATCH_DIR%\pc\share_worked.py" --adif "%ADIF%" --no-upload --mode pc

rem 2) クラスター監視をPCで常駐（2分ごと）
start "cluster-watch" /min python "%WATCH_DIR%\watch\cluster_watch.py" --loop 120 ^
  --worked-file "%WATCH_DIR%\local\worked_entities.txt" ^
  --state "%WATCH_DIR%\local\notified.json" --log "%WATCH_DIR%\local\log.csv" ^
  --cty "%WATCH_DIR%\local\cty.dat"
