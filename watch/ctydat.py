"""cty.dat（AD1C, country-files.com）によるDXCCエンティティ判定。

GitHub側・PC側の両方で同じこのモジュールを使うので、
交信済み一覧とスポットの判定キー（エンティティの主プレフィックス）が必ず一致する。
"""
from __future__ import annotations

import re
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path

CTY_URL = "https://www.country-files.com/cty/cty.dat"

# エイリアスに付く上書き指定 (CQ)[ITU]<緯度/経度>{大陸}~時差~ を取り除く
_OVR = re.compile(r"\(\d+\)|\[\d+\]|<[^>]*>|\{[^}]*\}|~[^~]*~")
# 移動・付加記号（エンティティ判定には使わない）
_SUFFIX = {"P", "M", "QRP", "QRPP", "A", "LH", "B", "J", "R", "T", "X", "N"}
# DXCCの対象外
_NO_DXCC = {"MM", "AM", "SAT"}


@dataclass(frozen=True)
class Entity:
    name: str
    prefix: str  # 主プレフィックス（例: JA, 3B8, VP8/h）。判定キーとして使う
    cont: str
    cq: str
    itu: str


class CtyDat:
    def __init__(self, text: str):
        self.prefixes: dict[str, Entity] = {}
        self.exact: dict[str, Entity] = {}
        self.entities: dict[str, Entity] = {}
        for chunk in text.split(";"):
            chunk = chunk.strip()
            if not chunk:
                continue
            parts = chunk.split(":")
            if len(parts) < 9:
                continue
            name, cq, itu, cont, _lat, _lon, _tz, main = (p.strip() for p in parts[:8])
            # 先頭が * のものはCQ WAE専用でDXCCエンティティではない（例: *IG9）
            if main.startswith("*"):
                continue
            ent = Entity(name, main, cont, cq, itu)
            self.entities[main] = ent
            for tok in ":".join(parts[8:]).replace("\n", " ").split(","):
                tok = _OVR.sub("", tok).strip()
                if not tok:
                    continue
                if tok.startswith("="):
                    self.exact[tok[1:].upper()] = ent
                else:
                    self.prefixes[tok.upper()] = ent

    def lookup(self, call: str) -> Entity | None:
        if not call:
            return None
        c = re.sub(r"-.*$", "", call.strip().upper())  # JA1ABC-# / JA1ABC-2 など
        if c in self.exact:
            return self.exact[c]
        parts = [p for p in c.split("/") if p]
        if any(p in _NO_DXCC for p in parts):
            return None
        parts = [p for p in parts if p not in _SUFFIX and not (len(p) == 1 and p.isdigit())]
        if not parts:
            return None
        # VP8/G3ABC, G3ABC/VP8 → 短い方を地域プレフィックスとみなす（簡易判定）
        base = parts[0] if len(parts) == 1 else min(parts, key=len)
        if base in self.exact:
            return self.exact[base]
        for i in range(len(base), 0, -1):
            ent = self.prefixes.get(base[:i])
            if ent:
                return ent
        return None


def load(cache: Path, max_age_days: float = 7.0) -> CtyDat:
    """cty.datを読む。古ければ取り直し、取得に失敗したら手元の版を使う。

    git checkoutではファイルの更新時刻が当てにならないので、取得時刻は別ファイルに残す。
    """
    stamp = cache.with_suffix(".stamp")
    try:
        fetched_at = float(stamp.read_text().strip())
    except (OSError, ValueError):
        fetched_at = 0.0
    if not cache.exists() or time.time() - fetched_at > max_age_days * 86400:
        try:
            req = urllib.request.Request(CTY_URL, headers={"User-Agent": "dx-cluster-watch"})
            with urllib.request.urlopen(req, timeout=30) as r:
                data = r.read().decode("latin-1")
            if "Japan" in data and len(data) > 10000:
                cache.parent.mkdir(parents=True, exist_ok=True)
                cache.write_text(data, encoding="latin-1")
                stamp.write_text(str(time.time()))
        except Exception as e:  # noqa: BLE001
            if not cache.exists():
                raise
            print(f"cty.datの更新に失敗（手元の版を使用）: {e}")
    return CtyDat(cache.read_text(encoding="latin-1"))
