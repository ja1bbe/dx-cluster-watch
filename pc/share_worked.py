#!/usr/bin/env python3
"""終了操作（および開始操作）で使う：JA1BBEの交信済みエンティティ一覧を作り、
GitHubのSecret（WORKED_ENTITIES）へ送り、監視の担当（WATCH_MODE）を切り替える。

  終了時: python share_worked.py --adif 全交信.adi --mode github
  開始時: python share_worked.py --adif 全交信.adi --no-upload --mode pc

--adif には HAMLOG から書き出した「全交信」のADIFを指定する（新しい交信だけのADIFでは不足）。
判定はJA1BBEの交信のみ（JP3WVZ・JA9NBB等の交信は数えない）。
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "watch"))
import ctydat  # noqa: E402

TAG = re.compile(r"<([A-Za-z0-9_]+)(?::(\d+)(?::[^>]*)?)?>")


def adif_records(text: str):
    """ADIFの長さ指定はバイト数なので、latin-1で読んだ文字列のまま数える。"""
    pos = 0
    h = re.search(r"<eoh>", text, re.I)
    if h:
        pos = h.end()
    rec: dict[str, str] = {}
    while True:
        m = TAG.search(text, pos)
        if not m:
            break
        name = m.group(1).upper()
        if name == "EOR":
            if rec:
                yield rec
            rec, pos = {}, m.end()
            continue
        n = int(m.group(2) or 0)
        rec[name] = text[m.end():m.end() + n]
        pos = m.end() + n
    if rec:
        yield rec


def main() -> None:
    ap = argparse.ArgumentParser()
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--adif", help="全交信のADIF")
    src.add_argument("--calls", help="交信済みコールサインの一覧（1行1局、JA1BBEの交信のみ）")
    ap.add_argument("--station", default="JA1BBE")
    ap.add_argument("--repo", default="ja1bbe/dx-cluster-watch")
    ap.add_argument("--cty", default=str(ROOT / "local" / "cty.dat"))
    ap.add_argument("--out", default=str(ROOT / "local" / "worked_entities.txt"))
    ap.add_argument("--mode", choices=["github", "pc", "none"], default="none")
    ap.add_argument("--no-upload", action="store_true")
    args = ap.parse_args()

    cty = ctydat.load(Path(args.cty))
    calls: list[str] = []
    if args.adif:
        text = Path(args.adif).read_bytes().decode("latin-1")
        has_station_field = False
        for r in adif_records(text):
            st = r.get("STATION_CALLSIGN") or r.get("OPERATOR")
            if st:
                has_station_field = True
                if st.strip().upper().split("/")[0] != args.station:
                    continue
            if r.get("CALL"):
                calls.append(r["CALL"])
        if not has_station_field:
            print("注意: ADIFに STATION_CALLSIGN／OPERATOR がないため、全交信を"
                  f"{args.station}の交信として数えました", file=sys.stderr)
    else:
        calls = Path(args.calls).read_text(encoding="utf-8").split()

    worked = sorted({e.prefix for c in calls if (e := cty.lookup(c))})
    if len(worked) < 10:
        sys.exit(f"交信済みエンティティが{len(worked)}件しかないため中止します（入力を確認してください）")
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(worked) + "\n", encoding="utf-8")
    print(f"交信済みエンティティ {len(worked)}件 → {out}")

    if not args.no_upload:
        subprocess.run(["gh", "secret", "set", "WORKED_ENTITIES", "--repo", args.repo],
                       input="\n".join(worked), text=True, check=True)
        print("GitHubのSecret（WORKED_ENTITIES）を更新しました")
    if args.mode != "none":
        subprocess.run(["gh", "variable", "set", "WATCH_MODE", "--body", args.mode, "--repo", args.repo],
                       check=True)
        print(f"監視の担当を {args.mode} にしました")


if __name__ == "__main__":
    main()
