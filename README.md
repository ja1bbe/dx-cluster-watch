# dx-cluster-watch（試験運用）

JA局のスポット（DXSCAPE／DX Summit）から、JA1BBEが**全バンド未交信**のエンティティを見つけ、
IC-7850運用時と同じ形のHTMLメールで通知します。
PCで運用している間はPCが、終了操作の後はGitHub Actionsが監視を受け持ちます。

## 決めごと（2026年11月）

| 項目 | 内容 |
|---|---|
| 対象スポット | JA局（cty.datでJapan）のスポットのみ。誤スポットは除外しない |
| モード | FT8のみ（周波数±3kHz、またはコメントにFT8） |
| 鮮度 | スポット時刻が15分以内 |
| 重複 | 同じコール＋バンドは30分以内に再通知しない |
| 実行間隔 | GitHub 10分ごと（遅れ・欠けあり）、PC 2分ごと |
| 切り替え | 開始操作で `WATCH_MODE=pc`、終了操作で `WATCH_MODE=github` |
| 異常停止 | PCが終了操作なしで止まった場合は、次の終了操作まで監視なし（了承済み） |
| 通知時間帯 | 終日 |
| 起源の表示 | 件名の先頭に `[IC-7850]` `[IC-7851]` `[SDR]` `[DXSCAPE]` `[DX Summit]` |

## 準備

1. **リポジトリを2つ作る**
   - `ja1bbe/dx-cluster-watch`（公開）：このフォルダの中身を入れる
   - `ja1bbe/dx-cluster-watch-state`（**非公開**、README付きで作成）：通知済みの記録・通知ログ・cty.datを保存
     （未交信エンティティが読み取れる情報は、すべてこちらに置く）
2. **トークンを作る**：GitHubの Settings → Developer settings → Fine-grained tokens で、
   対象を `dx-cluster-watch-state` だけにし、Contents を Read and write にする。
3. **公開リポジトリの Secrets に登録**（Settings → Secrets and variables → Actions）
   - `STATE_TOKEN`：上のトークン
   - `GMAIL_USER`、`GMAIL_APP_PASSWORD`、`MAIL_TO`：既存の通知と同じGmail設定
   - `WORKED_ENTITIES`：`share_worked.py` が自動で登録する
4. **Variables に `WATCH_MODE` = `pc` を登録**（準備が終わるまでGitHub側を動かさないため）
5. **DXSCAPEの取得部分**：既存のDXSCAPE監視スクリプトの取得部分を
   `watch/dxscape_adapter.example.py` の説明どおりに移し、`watch/dxscape_adapter.py` として保存する。
6. **各PC（IC-7850用・IC-7851用）**
   - `pip install matplotlib`
   - GitHub CLI（gh）を入れて、一度 `gh auth login`
   - Gmailの設定を環境変数に登録（`setx GMAIL_USER ...` など。既存の設定があればそれを使う）
   - `pc/start_watch.bat`・`pc/end_watch.bat` の中身を既存の開始・終了batに追加し、
     `WATCH_DIR` と `ADIF`（HAMLOGから書き出した**全交信**のADIF）のパスを合わせる
   - SDR用PCには入れない

## 試験の手順

1. PCで `python pc\share_worked.py --adif 全交信.adi --no-upload` を実行し、
   `local\worked_entities.txt` の件数が、把握しているJA1BBEのエンティティ数と合うか確認する。
2. PCで `--dry-run` を付けて `cluster_watch.py` を実行し、`out\*.eml` を開いて見た目を確認する。
3. 終了batを実行して `WATCH_MODE=github` にする。
4. GitHubの Actions → dx-cluster-watch → Run workflow で、`pretend_unworked` に
   交信済みのエンティティ（例：よくスポットされる `UA9` や `BY`）を入れて実行し、
   【試験】付きの通知が届くことを確かめる。

## 注意

- **公開リポジトリの実行ログは誰でも見られます。**このため、GitHub側では件数だけをログに出し
  （`--quiet-log`）、コールやエンティティはログに出しません。通知内容は非公開リポジトリとメールにだけ残ります。
- 公開リポジトリに60日間コミットがないと、GitHubが定期実行を自動で止めます（事前にメールで知らせが来ます）。
  知らせが来たら、Actionsの画面で再度有効にしてください。
- DX SummitのJSONの項目名は、運用前に一度実際の応答で確認してください（`fetch_dxsummit()`）。
- DX SummitとDXSCAPEの利用条件を確認し、必要なら運営者に「個人の非営利利用、10分間隔」と伝えてください。
- エンティティ判定はcty.datの簡易判定です。`VP8/G3ABC` のような移動運用は短い方を地域とみなします。
