"""调试8: 测试候选小红书链接的活性与数据结构"""
import json
import sys
from pathlib import Path

BASE = Path(r"D:\workbuddyhuacunwenjianjjia\2026-10-24-17-18-44\video-parse-tool")
sys.path.insert(0, str(BASE / "backend"))
import main  # noqa: E402
from videodl.modules import BuildVideoClient  # noqa: E402

CANDIDATES = [
    "https://xhslink.cn/o/AxnRePgIokn",   # linkdigest 2026-09, type=normal (图集?)
    "https://xhslink.com/o/1WiQ1QI6Uc0",  # linkdigest 2026-09, type=video
    "http://xhslink.com/o/41ni8ZmAfcI",   # 微信公众号文章
]

PC_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36"
M_UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"


def extract_note(html):
    import re
    m = re.search(r"window\.__INITIAL_STATE__\s*=\s*(\{.*?\})</script>", html, re.S)
    if not m:
        return None, "no INITIAL_STATE"
    s = m.group(1)
    s = re.sub(r"\bundefined\b", "null", s)
    try:
        data = json.loads(s)
    except Exception as e:
        return None, f"json error: {e}"
    note = None
    first_id = (data.get("note") or {}).get("firstNoteId")
    if first_id:
        item = (data.get("note") or {}).get("noteDetailMap", {}).get(first_id) or {}
        note = item.get("note")
    if not note:
        note = ((data.get("noteData") or {}).get("data") or {}).get("noteData") or {}
    return note, "ok"


import requests  # noqa: E402

for url in CANDIDATES:
    print(f"\n=== {url} ===")
    for ua_name, ua in [("PC", PC_UA), ("Mobile", M_UA)]:
        try:
            session = requests.Session()
            r = session.get(url, headers={"User-Agent": ua, "Referer": "https://www.xiaohongshu.com/"}, timeout=20, allow_redirects=True)
            final = r.url
            is404 = "404" in final or "login" in final
            note, status = extract_note(r.text)
            has_note = bool(note)
            img_count = len(note.get("imageList") or []) if note else 0
            live_count = sum(1 for i in (note.get("imageList") or []) if isinstance(i, dict) and i.get("livePhoto")) if note else 0
            has_video = bool((note or {}).get("video"))
            print(f"  [{ua_name}] 状态={r.status_code} 最终URL={final[:70]}")
            print(f"        note={has_note} ({status}) | imageList={img_count} 张, livePhoto={live_count} | video={has_video}")
            if note:
                il = note.get("imageList") or []
                if il:
                    first = il[0]
                    print(f"        imageList[0] 键: {sorted(first.keys())[:14]}")
                    print(f"        imageList[0] livePhoto={first.get('livePhoto')} stream键={list((first.get('stream') or {}).keys())}")
                    for codec, arr in (first.get("stream") or {}).items():
                        if arr:
                            print(f"          {codec}[0] 键: {sorted(arr[0].keys())[:10]}")
                            print(f"          {codec}[0].masterUrl = {str(arr[0].get('masterUrl'))[:80]}")
                print(f"        title={str(note.get('title'))[:30]!r} type={note.get('type')}")
                break  # 成功即止
        except Exception as e:
            print(f"  [{ua_name}] 请求异常: {str(e)[:80]}")
