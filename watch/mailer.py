"""全バンドNEW通知のHTMLメール（起源ラベル付き、Kp・太陽風速度のグラフ付き）。

IC-7850運用時の通知と同じ形にそろえるため、件名は
  [起源] 全バンドNEW <コール> <バンド> FT8 ...
とし、本文の先頭に起源ごとに色分けしたラベルを置く。
既存の通知システムのHTML生成部分があれば、build_html() をそちらに差し替えてよい。
"""
from __future__ import annotations

import datetime as dt
import html
import io
import json
import os
import smtplib
import ssl
import urllib.request
from email.message import EmailMessage
from email.utils import make_msgid
from pathlib import Path

UTC = dt.timezone.utc
JST = dt.timezone(dt.timedelta(hours=9))

KP_URL = "https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json"
SW_URL = "https://services.swpc.noaa.gov/products/solar-wind/plasma-1-day.json"

# 自局受信は青系、クラスターは赤・橙系
LABEL_COLORS = {
    "IC-7850": "#1f6fb2",
    "IC-7851": "#2a8fd6",
    "SDR": "#4fa3e0",
    "DXSCAPE": "#c0392b",
    "DXSummit": "#e67e22",
    "DX Summit": "#e67e22",
}
CLUSTER_SOURCES = ("DXSCAPE", "DXSummit", "DX Summit")


def label_color(source: str) -> str:
    for key, color in LABEL_COLORS.items():
        if source.startswith(key):  # 「SDR-湯河原」なども SDR の色
            return color
    return "#555555"


# ---------------------------------------------------------------- 宇宙天気
def _get_json(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": "dx-cluster-watch"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def _t(s) -> dt.datetime:
    s = str(s).replace("T", " ")[:19]
    return dt.datetime.strptime(s, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)


def _series(url: str, field: str) -> list[tuple[dt.datetime, float]]:
    """NOAAのJSONを読む（先頭行が見出しの配列形式／オブジェクト配列形式の両方に対応）。"""
    data = _get_json(url)
    out: list[tuple[dt.datetime, float]] = []
    if not data:
        return out
    if isinstance(data[0], list):
        head = [str(h).lower() for h in data[0]]
        ti, vi = head.index("time_tag"), head.index(field)
        rows = [(r[ti], r[vi]) for r in data[1:]]
    else:
        low = [{str(k).lower(): v for k, v in r.items()} for r in data]
        rows = [(r.get("time_tag"), r.get(field)) for r in low]
    for t, v in rows:
        try:
            out.append((_t(t), float(v)))
        except (TypeError, ValueError):
            pass
    return out


def fetch_space_weather() -> dict:
    sw: dict = {"kp": [], "speed": [], "error": ""}
    try:
        sw["kp"] = _series(KP_URL, "kp")
    except Exception as e:  # noqa: BLE001
        sw["error"] += f"Kp取得失敗: {e} "
    try:
        sw["speed"] = _series(SW_URL, "speed")
    except Exception as e:  # noqa: BLE001
        sw["error"] += f"太陽風取得失敗: {e}"
    return sw


def make_charts(sw: dict) -> list[tuple[str, bytes]]:
    """グラフはPNGで本文に埋め込む（GmailはSVGやdata URIを表示しないため）。
    GitHubの実行環境には日本語フォントがないので、グラフ内の文字は英語にする。"""
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.dates as mdates
        import matplotlib.pyplot as plt
    except ImportError:
        return []
    now = dt.datetime.now(UTC)
    charts: list[tuple[str, bytes]] = []

    kp = [(t, v) for t, v in sw["kp"] if now - t <= dt.timedelta(days=3)]
    if kp:
        fig, ax = plt.subplots(figsize=(6, 2.2), dpi=110)
        colors = ["#2e8b57" if v < 4 else "#e0a800" if v < 5 else "#c0392b" for _, v in kp]
        ax.bar([t for t, _ in kp], [v for _, v in kp], width=0.11, align="edge", color=colors)
        ax.axhline(4, ls="--", lw=0.8, color="gray")
        ax.set_ylim(0, 9)
        ax.set_title("Planetary Kp (last 3 days, UTC)", fontsize=9)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d %H", tz=UTC))
        ax.tick_params(labelsize=7)
        fig.tight_layout()
        buf = io.BytesIO()
        fig.savefig(buf, format="png")
        plt.close(fig)
        charts.append(("kp", buf.getvalue()))

    sp = [(t, v) for t, v in sw["speed"] if now - t <= dt.timedelta(hours=24)]
    if sp:
        fig, ax = plt.subplots(figsize=(6, 2.2), dpi=110)
        ax.plot([t for t, _ in sp], [v for _, v in sp], lw=1.0, color="#1f6fb2")
        ax.axhline(500, ls="--", lw=0.8, color="gray")
        ax.set_title("Solar wind speed, km/s (last 24 h, UTC)", fontsize=9)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M", tz=UTC))
        ax.tick_params(labelsize=7)
        fig.tight_layout()
        buf = io.BytesIO()
        fig.savefig(buf, format="png")
        plt.close(fig)
        charts.append(("speed", buf.getvalue()))
    return charts


# ---------------------------------------------------------------- メール本文
def subject(n: dict, test: bool = False) -> str:
    # dxscape_watch.py と同じ形: [起源] 印 バンド コール (エンティティ)
    # 印は dxcc_notify.SUBJECT_MARK['ATNO'] と同じものを、リポジトリ変数 ATNO_MARK に入れておく
    mark = os.environ.get("ATNO_MARK") or "全バンド初"
    s = f"[{n['source']}] {mark} {n['band']} {n['dx']} ({n['entity'].name})"
    return ("【試験】" if test else "") + s


def _history_text(n: dict) -> str:
    items = []
    for src, iso in n.get("history", []):
        try:
            items.append(f"{src} {dt.datetime.fromisoformat(iso).astimezone(UTC):%H:%M}")
        except (TypeError, ValueError):
            items.append(src)
    return " → ".join(items) + "（UTC）" if items else ""


def build_html(n: dict, sw: dict, cids: dict[str, str]) -> str:
    e = html.escape
    ent = n["entity"]
    t: dt.datetime = n["time"]
    color = label_color(n["source"])
    kind = "クラスター（JA局のスポット）" if n["source"].startswith(CLUSTER_SOURCES) else "自局受信"
    kp_now = f"{sw['kp'][-1][1]:.2f}" if sw.get("kp") else "取得できず"
    sp_now = f"{sw['speed'][-1][1]:.0f} km/s" if sw.get("speed") else "取得できず"

    rows = [
        ("コール", n["dx"]),
        ("エンティティ", f"{ent.name}（{ent.prefix}、{ent.cont}）"),
        ("周波数", f"{n['khz']:.1f} kHz（{n['band']}, FT8）"),
        ("スポット時刻", f"{t:%H:%M} UTC（{t.astimezone(JST):%H:%M} JST）"),
        ("コメント", n.get("comment") or "-"),
        ("スポッター", n.get("spotter") or "-"),
        ("通知したPC", "GitHub（IC-7850停止中の代行）"),
    ]
    hist = _history_text(n)
    if hist:
        rows.append(("捉えた起源", hist))
    rows += [("最新のKp", kp_now), ("太陽風速度", sp_now)]

    table = "".join(
        f'<tr><td style="padding:4px 10px;color:#666;white-space:nowrap">{e(k)}</td>'
        f'<td style="padding:4px 10px">{e(v)}</td></tr>'
        for k, v in rows
    )
    imgs = "".join(
        f'<div style="margin-top:8px"><img src="cid:{cid}" alt="{e(name)}" style="max-width:100%"></div>'
        for name, cid in cids.items()
    )
    err = f'<p style="color:#999;font-size:12px">{e(sw["error"])}</p>' if sw.get("error") else ""
    return f"""<html><body style="font-family:sans-serif">
<div><span style="background:{color};color:#fff;padding:3px 10px;border-radius:4px;font-weight:bold">{e(n['source'])}</span>
<span style="color:#666;margin-left:8px">{e(kind)}</span></div>
<h2 style="margin:10px 0 6px">全バンド初　{e(n['band'])} {e(n['dx'])}</h2>
<table style="border-collapse:collapse;font-size:14px">{table}</table>
<p style="font-size:small;color:#666">国内局のスポットです。誤ったコールサインの場合があります。</p>
{imgs}{err}
</body></html>"""


def build_message(n: dict, sw: dict, charts, sender: str, to: str, test: bool) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = subject(n, test)
    msg["From"] = sender
    msg["To"] = to
    msg.set_content(f"{subject(n, test)}\n{n['entity'].name}  {n['khz']:.1f} kHz  {n['time']:%H:%M} UTC")
    cids = {name: make_msgid(domain="dx-cluster-watch")[1:-1] for name, _ in charts}
    msg.add_alternative(build_html(n, sw, cids), subtype="html")
    html_part = msg.get_payload()[1]
    for name, png in charts:
        html_part.add_related(png, "image", "png", cid=f"<{cids[name]}>")
    return msg


def send_all(notices: list[dict], dry_run: bool = False, outdir: Path = Path("out"),
             test: bool = False) -> None:
    if not notices:
        return
    sw = fetch_space_weather()
    charts = make_charts(sw)
    sender = os.environ.get("GMAIL_USER", "dry-run@example.invalid")
    to = os.environ.get("MAIL_TO", sender)
    msgs = [build_message(n, sw, charts, sender, to, test) for n in notices]
    if dry_run:
        outdir.mkdir(parents=True, exist_ok=True)
        for i, m in enumerate(msgs, 1):
            (outdir / f"notice_{i:02d}.eml").write_bytes(bytes(m))
        print(f"{len(msgs)}件のメールを {outdir} に保存（送信なし）")
        return
    ctx = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ctx) as s:
        s.login(os.environ["GMAIL_USER"], os.environ["GMAIL_APP_PASSWORD"])
        for m in msgs:
            s.send_message(m)
    print(f"{len(msgs)}件の通知を送信")
