"""DXSCAPE取得部分のひな形。

作成済みのDXSCAPE監視スクリプト（JA25スポット）から「取得して1件ずつに分ける」部分を
fetch() の中に移し、このファイルを dxscape_adapter.py という名前で保存してください。

fetch() は、スポット1件ごとに次の辞書を並べたリストを返します。
    {
        "dx":      "3B8M",                 # DX局のコールサイン
        "spotter": "JA1XXX",               # スポットした局
        "khz":     7074.0,                 # 周波数（kHz。MHzでも自動で直します）
        "time":    "2026-11-06 12:05:00",  # スポット時刻（UTC）。datetimeでも可
        "comment": "FT8 -12dB",            # コメント（なければ空文字）
    }
※ DXSCAPEの時刻がJSTの場合は、9時間引いてUTCにしてから返してください。
"""


def fetch() -> list[dict]:
    raise NotImplementedError("既存のDXSCAPE取得部分をここに移してください")
