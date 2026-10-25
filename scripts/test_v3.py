"""测试V3: 图集分区 + 按类型/勾选下载 + 四平台回归"""
import json
import sys
import time
import urllib.request
from pathlib import Path

BASE = Path(r"D:\workbuddyhuacunwenjianjjia\2026-10-24-17-18-44\video-parse-tool")
API = "http://127.0.0.1:8000"


def req(path, method="GET", body=None, timeout=240):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(API + path, data=data, method=method,
                               headers={"Content-Type": "application/json"} if data else {})
    with urllib.request.urlopen(r, timeout=timeout) as resp:
        return resp.status, resp.read()


def wait_task(task_id, limit=240):
    t0 = time.time()
    t = {}
    for _ in range(limit):
        time.sleep(2)
        _, raw = req(f"/api/tasks/{task_id}")
        t = json.loads(raw)
        if t["status"] in ("done", "error"):
            break
    return t, time.time() - t0


print("=" * 62)
print("一、小红书图集解析（分区结构）")
print("=" * 62)
XHS = "https://xhslink.cn/o/AxnRePgIokn"
t0 = time.time()
_, raw = req("/api/parse", "POST", {"url": XHS})
p = json.loads(raw)
dt = time.time() - t0
print(f"  解析 {dt:.1f}s | ok={p['ok']} | 平台={p['platform']['label']}")
for it in p["items"]:
    print(f"  kind={it['kind']} | 静态图 {len(it['images'])} | 实况视频 {len(it['live_videos'])} | formats={len(it.get('formats') or [])}")
    for c in (it.get("contents") or [])[:4]:
        print(f"    - {c['type']:11s} {c['url'][:70]}")
parse_id = p.get("parse_id")
album_idx = next((i for i, it in enumerate(p["items"]) if it["kind"] == "album"), None)

if album_idx is not None:
    print("\n  → 下载全部图片 (album_mode=images)")
    _, raw = req("/api/download", "POST", {"url": XHS, "index": album_idx, "album_mode": "images", "parse_id": parse_id})
    t, d = wait_task(json.loads(raw)["task_id"])
    if t["status"] == "done":
        print(f"    成功 ({d:.1f}s) | {t['filename']} | {len(t.get('all_paths') or [])} 个文件")
        print(f"    目录: {Path(t['save_path']).parent}")
    else:
        print(f"    失败: {t.get('error', '')[:150]}")

    print("\n  → 下载勾选内容 (album_mode=selected, 下标[0])")
    _, raw = req("/api/download", "POST", {"url": XHS, "index": album_idx, "album_mode": "selected", "album_indices": [0], "parse_id": parse_id})
    t, d = wait_task(json.loads(raw)["task_id"])
    print(f"    结果: {t['status']} ({d:.1f}s) | {len(t.get('all_paths') or [])} 个文件")

    print("\n  → 下载实况视频 (该笔记无实况, 应明确报错)")
    _, raw = req("/api/download", "POST", {"url": XHS, "index": album_idx, "album_mode": "live_videos", "parse_id": parse_id})
    t, d = wait_task(json.loads(raw)["task_id"])
    print(f"    结果: {t['status']} | {str(t.get('error'))[:80]}")

print()
print("=" * 62)
print("二、四平台回归")
print("=" * 62)
CASES = [
    ("B站", "https://www.bilibili.com/video/BV16Z4y1X784/"),
    ("皮皮虾", "https://h5.pipix.com/s/OI2PNF-T0Mc/"),
    ("抖音", "https://www.douyin.com/jingxuan?modal_id=7584665891071282432"),
    ("小红书", XHS),
]
for label, url in CASES:
    t0 = time.time()
    _, raw = req("/api/parse", "POST", {"url": url})
    p = json.loads(raw)
    dt = time.time() - t0
    first = p["items"][0] if p.get("items") else {}
    print(f"  [{label:4s}] {dt:5.1f}s | ok={p.get('ok')} | kind={first.get('kind', '-')} | 格式={len(first.get('formats') or [])}")

print()
print("=" * 62)
print("三、B站清晰度选择回归")
print("=" * 62)
BURL = "https://www.bilibili.com/video/BV16Z4y1X784/"
_, raw = req("/api/parse", "POST", {"url": BURL})
p = json.loads(raw)
fmts = p["items"][0].get("formats") or []
print(f"  格式: {[(f['id'], f['label']) for f in fmts]}")
if len(fmts) >= 2:
    low = fmts[-1]
    _, raw = req("/api/download", "POST", {"url": BURL, "index": 0, "format_id": low["id"], "parse_id": p.get("parse_id")})
    t, d = wait_task(json.loads(raw)["task_id"])
    if t["status"] == "done":
        size = Path(t["save_path"]).stat().st_size / 1048576
        print(f"  [{low['label']}] 成功 {size:.2f}MB (接口报告 {low['filesize']/1048576:.1f}MB)")
    else:
        print(f"  失败: {t.get('error', '')[:150]}")

print()
print("=" * 62)
print("四、前端页面检查")
print("=" * 62)
_, raw = req("/")
html = raw.decode("utf-8", "replace")
for token in ["filter-bar", "segmented", "item-head", "album-group", "实况视频（动态内容）", "静态图片", "download 全部实况", "album_mode"]:
    print(f"  包含 {token!r}: {token in html}")
print("\n测试完成")
