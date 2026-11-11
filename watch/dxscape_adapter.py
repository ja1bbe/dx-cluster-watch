"""DXSCAPE（JA25）の取得。dxscape_watch.py の fetch()・parse() と同じ読み方。"""
from __future__ import annotations

import html
import re
import urllib.request
from datetime import datetime, timedelta, timezone

URL = "http://www.dxscape.com/ja25.html"
UA = "JA1BBE-dxscape-watch/0.3 (personal, non-commercial; GitHub fallback)"

# 例: "6W/I2YSB  0851Z  14240.0 5-10up   JA3USA-9"（コメントは空のこともある）
LINE_RE = re.compile(r"^(\S+)\s+(\d{4})Z\s+(\d+\.\d)\s*(.*?)\s+(\S+)\s*$")


def _get(timeout: int = 20) -> str:
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
    for enc in ("utf-8", "shift_jis"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            pass
    return raw.decode("latin-1", errors="replace")


def fetch() -> list[dict]:
    now = datetime.now(timezone.utc)
    text = html.unescape(re.sub(r"<[^>]+>", "", _get()))
    spots = []
    for line in text.splitlines():
        m = LINE_RE.match(line.strip())
        if not m:
            continue
        call, hhmm, freq, comment, spotter = m.groups()
        t = now.replace(hour=int(hhmm[:2]), minute=int(hhmm[2:]), second=0, microsecond=0)
        if t > now + timedelta(minutes=5):  # 日付をまたいだスポット
            t -= timedelta(days=1)
        spots.append({"dx": call.upper(), "spotter": spotter, "khz": float(freq),
                      "time": t, "comment": comment.strip()})
    return spots
