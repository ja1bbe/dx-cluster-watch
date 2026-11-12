# dx-cluster-watch

IC-7850のPCが止まっている間だけ、GitHub Actionsで DXSCAPE（JA25）と DX Summit を見て、
JA1BBEが全バンド未交信のエンティティをJA局がFT8でスポットしたら、メールで知らせます。
PCで運用している間は、PCの `dxscape_watch.py`（DXCC水先案内人）が同じ役目を受け持ちます。

## 仕組み

| 場面 | 担当 | 切り替え |
|---|---|---|
| IC-7850で運用中 | PCの `dxscape_watch.py` | 開始のbatで `python export_worked.py --mode pc`（変数 `WATCH_MODE=pc`、GitHubは休む） |
| IC-7850の停止中 | GitHubの `watch/cluster_watch.py` | 終了のbatで `python export_worked.py --mode github`（交信済み一覧を送り、`WATCH_MODE=github`） |

- `export_worked.py` は `%OneDrive%\DXCC` にあり、`dxscape_watch.load_worked_entities` で交信済みを判定します
  （HAMLOG.hdb の自局の交信 + logs\*.adi、ゲスト運用は除外）。一覧はエンティティ名で、Secret `WORKED_ENTITIES` に入ります。
- GitHubの起動は cron-job.org から10分ごと（GitHub自身の定時起動は間引かれるため）。
- 判定は `dxscape_watch.py` に合わせています：JA局のスポットのみ、FT8のみ、60分以内のスポット、同じ局・バンドは6時間再通知しない。
- 件名の印は変数 `ATNO_MARK`（`dxcc_notify.SUBJECT_MARK['ATNO']` と同じ）。

## ファイル

- `watch/cluster_watch.py` … 本体（公開ログには件数だけを出す）
- `watch/dxscape_adapter.py` … DXSCAPEの読み取り（`dxscape_watch.py` と同じ読み方）
- `watch/mailer.py` … HTMLメール（Kp・太陽風のグラフ付き）
- `watch/ctydat.py` … cty.dat によるエンティティ判定
- `.github/workflows/watch.yml` … 実行の設定

## 設定（Settings → Secrets and variables → Actions）

- Secrets：`STATE_TOKEN`（非公開の dx-cluster-watch-state への書き込み用）、`GMAIL_USER`、`GMAIL_APP_PASSWORD`、`MAIL_TO`、`WORKED_ENTITIES`
- Variables：`WATCH_MODE`（pc / github）、`ATNO_MARK`

## 確認の仕方

Actionsの実行ログの「監視（公開ログには件数だけを出す）」に、次の1行が出ます。

```
交信済み=251 取得=525 JA局FT8=○ 未交信=○ 通知=○
```

- 交信済みの件数が、PCの `dxscape_watch.py` の起動時の表示と同じであること
- 未交信が JA局FT8 とほぼ同じ数なら、一覧か照合に問題があります

## 注意

- 公開リポジトリの実行ログは誰でも見られるため、コールやエンティティはログに出しません。通知の記録は非公開の dx-cluster-watch-state に残します。
- ファイルをWebからアップロードするときは、名前が `cluster_watch (1).py` のように変わっていないか確かめてください（別のファイルとして入ってしまいます）。
