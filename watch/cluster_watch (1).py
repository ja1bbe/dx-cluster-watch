#!/usr/bin/env python3
"""JA局のスポット（DXSCAPE／DX Summit）から、JA1BBEが全バンド未交信のエンティティを見つけて通知する。

GitHub Actions（10分ごと、1回実行）と、PC（--loop で常駐）の両方で同じスクリプトを使う。

PCでは dxscape_watch.py（DXCC水先案内人）が同じ役目を受け持つ。
このスクリプトは、IC-7850のPCが止まっている間だけGitHubで代わりに動く。
判定はできるだけ dxscape_watch.py に合わせている。
  - 対象はJA局（cty.datで Japan と判定されるスポッター）のスポットのみ
  - モードはFT8のみ（標準周波数 +0〜+3kHz、またはコメントにFT8。FT4は除く）
  - スポット時刻が60分以内のものだけを対象
  - 同じコール＋バンドは6時間以内に再通知しない
  - 交信済みの照合はエンティティ名（PC側の load_worked_entities と同じキー）
  - 誤スポットは除外しない

公開リポジトリで動かすときは実行ログが誰でも見られるので、
ログには件数だけを出し、コールやエンティティ名は出さない（--quiet-log）。
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import ctydat  # noqa: E402
import mailer  # noqa: E402

UTC = dt.timezone.utc
UA = os.environ.get("WATCH_USER_AGENT", "dx-cluster-watch (amateur radio, non-commercial)")
DXSUMMIT_URL = os.environ.get("DXSUMMIT_URL", "https://www.dxsummit.fi/api/v1/spots?limit=500")

# dxscape_watch.py と同じ（ダイヤル周波数から +0〜+3 kHz を FT8 とみなす）
FT8_DIALS = [1840, 1908, 3531, 3573, 7041, 7074, 10136, 14074,
             18100, 21074, 24915, 28074, 50313, 50323]
BANDS = [
    (1800, 2000, "160m"), (3500, 4000, "80m"), (7000, 7300, "40m"), (10100, 10150, "30m"),
    (14000, 14350, "20m"), (18068, 18168, "17m"), (21000, 21450, "15m"),
    (24890, 24990, "12m"), (28000, 29700, "10m"), (50000, 54000, "6m"),
]


def band_of(khz: float) -> str | None:
    for lo, hi, name in BANDS:
        if lo <= khz <= hi:
            return name
    return None


def is_ft8(khz: float, comment: str) -> bool:
    c = (comment or "").upper()
    if "FT4" in c:
        return False
    if "FT8" in c:  # Fox/Hound など標準外の周波数もコメントで拾う
        return True
    return any(0 <= khz - d <= 3.0 for d in FT8_DIALS)


# ---------------------------------------------------------------- 取得
def http_get(url: str, timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def parse_time(v) -> dt.datetime | None:
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return dt.datetime.fromtimestamp(v, UTC)
    s = str(v).strip().replace("Z", "+00:00")
    try:
        t = dt.datetime.fromisoformat(s)
    except ValueError:
        t = None
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M:%S", "%Y/%m/%d %H:%M"):
            try:
                t = dt.datetime.strptime(s, fmt)
                break
            except ValueError:
                pass
        if t is None:
            return None
    if t.tzinfo is None:
        t = t.replace(tzinfo=UTC)
    return t.astimezone(UTC)


def to_khz(f) -> float | None:
    try:
        x = float(f)
    except (TypeError, ValueError):
        return None
    if x < 100:  # MHz
        x *= 1000
    elif x > 1_000_000:  # Hz
        x /= 1000
    return x


def pick(d: dict, *keys):
    for k in keys:
        if d.get(k) not in (None, ""):
            return d[k]
    return None


def fetch_dxsummit() -> list[dict]:
    """DX SummitのJSON。項目名が変わっても読めるよう、候補を複数見る。
    （項目名は運用前に一度、実際の応答で確認すること）"""
    data = json.loads(http_get(DXSUMMIT_URL))
    if isinstance(data, dict):
        data = pick(data, "spots", "data", "items") or []
    spots = []
    for d in data:
        spot = {
            "dx": pick(d, "dx_call", "dxcall", "dx", "callsign"),
            "spotter": pick(d, "de_call", "decall", "spotter", "de"),
            "khz": to_khz(pick(d, "frequency", "freq", "qrg")),
            "time": parse_time(pick(d, "time", "timestamp", "spot_time", "datetime")),
            "comment": pick(d, "info", "comment", "comments") or "",
        }
        if all(spot[k] for k in ("dx", "spotter", "khz", "time")):
            spots.append(spot)
    return spots


def fetch_dxscape() -> list[dict]:
    """DXSCAPEの取得は、作成済みのDXSCAPE監視スクリプトの取得部分を
    dxscape_adapter.py の fetch() に移して使う（dxscape_adapter.example.py 参照）。"""
    try:
        import dxscape_adapter  # type: ignore
    except ImportError:
        print("[DXSCAPE] dxscape_adapter.py が未配置のため省略", file=sys.stderr)
        return []
    spots = []
    for d in dxscape_adapter.fetch():
        spot = {
            "dx": d.get("dx"),
            "spotter": d.get("spotter"),
            "khz": to_khz(d.get("khz")),
            "time": parse_time(d.get("time")),
            "comment": d.get("comment") or "",
        }
        if all(spot[k] for k in ("dx", "spotter", "khz", "time")):
            spots.append(spot)
    return spots


SOURCES = (("DXSCAPE", fetch_dxscape), ("DXSummit", fetch_dxsummit))  # 同時刻ならDXSCAPEを優先


# ---------------------------------------------------------------- 判定
def load_worked(args) -> set[str]:
    if args.worked_file:
        text = Path(args.worked_file).read_text(encoding="utf-8")
    else:
        text = os.environ.get("WORKED_ENTITIES", "")
    worked = {w.strip() for w in text.splitlines() if w.strip()}
    pretend = args.pretend_unworked or os.environ.get("PRETEND_UNWORKED", "")
    for p in pretend.split(","):  # エンティティ名には空白が入るので、区切りはカンマだけ
        worked.discard(p.strip())
    if len(worked) < 10:
        # 一覧が空だと全スポットが「全バンドNEW」になり、通知が大量に出てしまう
        sys.exit("交信済みエンティティ一覧が空か極端に少ないため停止します")
    return worked


def run_once(args, cty: ctydat.CtyDat, worked: set[str], state: dict) -> None:
    now = dt.datetime.now(UTC)
    window = dt.timedelta(minutes=args.window_min)
    dedup = dt.timedelta(minutes=args.dedup_min)

    spots: list[dict] = []
    for name, fn in SOURCES:
        try:
            got = fn()
        except Exception as e:  # noqa: BLE001
            print(f"[{name}] 取得失敗: {type(e).__name__}", file=sys.stderr)
            continue
        for s in got:
            s["source"] = name
        spots += got

    counts = {"取得": len(spots), "JA局FT8": 0, "未交信": 0, "通知": 0}
    notices, log_rows = [], []
    for s in sorted(spots, key=lambda s: s["time"]):
        if not (now - window <= s["time"] <= now + dt.timedelta(minutes=2)):
            continue
        sp_ent = cty.lookup(s["spotter"])
        if not sp_ent or sp_ent.prefix not in args.spotter_entities:
            continue
        band = band_of(s["khz"])
        if not band or not is_ft8(s["khz"], s["comment"]):
            continue
        counts["JA局FT8"] += 1
        dx = s["dx"].strip().upper()
        ent = cty.lookup(dx)
        if not ent or ent.name in worked:
            continue
        counts["未交信"] += 1

        key = f"{dx}|{band}"
        rec = state.setdefault(key, {"history": [], "last_notified": None})
        item = [s["source"], s["time"].isoformat(timespec="minutes")]
        is_new_item = item not in rec["history"]
        if is_new_item:
            rec["history"] = (rec["history"] + [item])[-10:]
        last = parse_time(rec["last_notified"])
        if last and now - last < dedup:
            if is_new_item:
                log_rows.append([now.isoformat(timespec="seconds"), s["source"], dx, ent.name,
                                 band, f"{s['khz']:.1f}", s["spotter"], "重複のため省略"])
            continue
        rec["last_notified"] = now.isoformat(timespec="seconds")
        notices.append({**s, "dx": dx, "band": band, "entity": ent, "history": list(rec["history"])})
        log_rows.append([now.isoformat(timespec="seconds"), s["source"], dx, ent.name,
                         band, f"{s['khz']:.1f}", s["spotter"], "通知"])
    counts["通知"] = len(notices)

    # 48時間より古い記録は消す
    for key in list(state):
        last = parse_time(state[key].get("last_notified")) or parse_time(
            (state[key].get("history") or [[None, None]])[-1][1])
        if not last or now - last > dt.timedelta(hours=48):
            del state[key]

    print(" ".join(f"{k}={v}" for k, v in counts.items()))
    if not args.quiet_log:
        for n in notices:
            print(f"  通知: [{n['source']}] {n['dx']} {n['band']} {n['entity'].name}")

    if log_rows and args.log:
        p = Path(args.log)
        p.parent.mkdir(parents=True, exist_ok=True)
        new = not p.exists()
        with p.open("a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if new:
                w.writerow(["実行時刻UTC", "起源", "コール", "エンティティ", "バンド", "kHz", "スポッター", "結果"])
            w.writerows(log_rows)

    mailer.send_all(notices, dry_run=args.dry_run, outdir=Path(args.outdir),
                    test=args.test or os.environ.get("WATCH_TEST") == "true")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--state", default="state/notified.json", help="通知済みの記録")
    ap.add_argument("--log", default="state/log.csv", help="通知ログ（CSV）")
    ap.add_argument("--cty", default="state/cty.dat", help="cty.datの保存先")
    ap.add_argument("--worked-file", help="交信済みエンティティ一覧（省略時は環境変数 WORKED_ENTITIES）")
    ap.add_argument("--pretend-unworked", default="", help="試験用：未交信扱いにするエンティティ名（カンマ区切り。例: China,Asiatic Russia）")
    ap.add_argument("--spotter-entities", nargs="+", default=["JA"], help="対象とするスポッターのエンティティ")
    ap.add_argument("--window-min", type=int, default=60)
    ap.add_argument("--dedup-min", type=int, default=360)
    ap.add_argument("--loop", type=int, default=0, help="PC用：この秒数ごとに繰り返す（0なら1回）")
    ap.add_argument("--quiet-log", action="store_true", help="公開ログ用：件数だけ出す")
    ap.add_argument("--dry-run", action="store_true", help="送信せず .eml を保存する")
    ap.add_argument("--outdir", default="out")
    ap.add_argument("--test", action="store_true", help="件名に【試験】を付ける")
    args = ap.parse_args()

    state_path = Path(args.state)
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    cty = ctydat.load(Path(args.cty))

    while True:
        worked = load_worked(args)  # PCで常駐中も毎回読み直す
        run_once(args, cty, worked, state)
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
        if not args.loop:
            break
        time.sleep(args.loop)
        cty = ctydat.load(Path(args.cty))  # 7日より古ければ取り直す


if __name__ == "__main__":
    main()
