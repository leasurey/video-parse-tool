"""最终测试: 解析速度 + 分辨率选择 + 抖音/小红书下载全流程"""
import json
import sys
import time
import urllib.request
from pathlib import Path

BASE = Path(r"D:\workbuddyhuacunwenjianjjia\2026-10-24-17-18-44\video-parse-tool")
sys.path.insert(0, str(BASE / "backend"))

API = "http://127.0.0.1:8000"


def req(path, method="GET", body=None, timeout=240):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(API + path, data=data, method=method,
                               headers={"Content-Type": "application/json"} if data else {})
    with urllib.request.urlopen(r, timeout=timeout) as resp:
        return resp.status, resp.read()


def wait_task(task_id, limit=240):
    t0 = time.time()
    for _ in range(limit):
        time.sleep(2)
        _, raw = req(f"/api/tasks/{task_id}")
        t = json.loads(raw)
        if t["status"] in ("done", "error"):
            return t, time.time() - t0
    return t, time.time() - t0


print("=" * 62)
print("一、解析速度 (最终版)")
print("=" * 62)
CASES = [
    ("B站", "https://www.bilibili.com/video/BV16Z4y1X784/"),
    ("皮皮虾", "https://h5.pipix.com/s/OI2PNF-T0Mc/"),
    ("抖音", "https://www.douyin.com/jingxuan?modal_id=7584665891071282432"),
    ("小红书", "http://xhslink.com/o/90PTZaZuCvC"),
]
for label, url in CASES:
    t0 = time.time()
    _, raw = req("/api/parse", "POST", {"url": url})
    dt = time.time() - t0
    p = json.loads(raw)
    n = len(p["items"][0].get("formats") or []) if p.get("ok") and p["items"] else 0
    print(f"  [{label:4s}] {dt:5.1f}s | ok={p.get('ok')} | 格式={n} | {p['items'][0]['title'][:22] if p.get('items') else p.get('detail', '')[:40]}")

print()
print("=" * 62)
print("二、抖音下载 (经 Ray 路由)")
print("=" * 62)
_, raw = req("/api/parse", "POST", {"url": "https://www.douyin.com/jingxuan?modal_id=7584665891071282432"})
p = json.loads(raw)
_, raw = req("/api/download", "POST", {"url": "https://www.douyin.com/jingxuan?modal_id=7584665891071282432", "index": 0, "parse_id": p.get("parse_id")})
task_id = json.loads(raw)["task_id"]
t, dt = wait_task(task_id)
if t["status"] == "done":
    size = Path(t["save_path"]).stat().st_size / 1048576
    print(f"  成功 ({dt:.1f}s) | {t['filename'][:40]}")
    print(f"  大小 {size:.1f}MB | 平均 {size/dt:.2f}MB/s | 保存于 {Path(t['save_path']).parent.name}/")
else:
    print(f"  失败: {t.get('error', '')[:200]}")

print()
print("=" * 62)
print("三、小红书下载 (经 Ray 路由)")
print("=" * 62)
_, raw = req("/api/parse", "POST", {"url": "http://xhslink.com/o/90PTZaZuCvC"})
p = json.loads(raw)
_, raw = req("/api/download", "POST", {"url": "http://xhslink.com/o/90PTZaZuCvC", "index": 0, "parse_id": p.get("parse_id")})
task_id = json.loads(raw)["task_id"]
t, dt = wait_task(task_id)
if t["status"] == "done":
    size = Path(t["save_path"]).stat().st_size / 1048576
    print(f"  成功 ({dt:.1f}s) | {t['filename'][:40]}")
    print(f"  大小 {size:.1f}MB | 保存于 {Path(t['save_path']).parent.name}/")
else:
    print(f"  失败: {t.get('error', '')[:200]}")

print()
print("=" * 62)
print("四、B站分辨率选择 (最低/最高)")
print("=" * 62)
burl = "https://www.bilibili.com/video/BV16Z4y1X784/"
_, raw = req("/api/parse", "POST", {"url": burl})
p = json.loads(raw)
fmts = p["items"][0]["formats"]
for f in (fmts[-1], fmts[0]):
    _, raw = req("/api/download", "POST", {"url": burl, "index": 0, "format_id": f["id"], "parse_id": p.get("parse_id")})
    t, dt = wait_task(json.loads(raw)["task_id"])
    if t["status"] == "done":
        size = Path(t["save_path"]).stat().st_size / 1048576
        print(f"  [{f['label']}] 成功 ({dt:.1f}s) {size:.2f}MB (接口报告 {f['filesize']/1048576:.1f}MB)")
    else:
        print(f"  [{f['label']}] 失败: {t.get('error', '')[:150]}")

print("\n测试完成")
