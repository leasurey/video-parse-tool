"""测试V2: 解析速度优化 + 分辨率选择 + 下载全流程"""
import json
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

BASE = Path(r"D:\workbuddyhuacunwenjianjjia\2026-10-24-17-18-44\video-parse-tool")
sys.path.insert(0, str(BASE / "backend"))
import main  # noqa: E402

API = "http://127.0.0.1:8000"


def req(path, method="GET", body=None, timeout=180):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(API + path, data=data, method=method,
                               headers={"Content-Type": "application/json"} if data else {})
    with urllib.request.urlopen(r, timeout=timeout) as resp:
        return resp.status, resp.read()


print("=" * 60)
print("一、解析速度测试 (优化后)")
print("=" * 60)
CASES = [
    ("B站", "https://www.bilibili.com/video/BV16Z4y1X784/"),
    ("皮皮虾", "https://h5.pipix.com/s/OI2PNF-T0Mc/"),
    ("抖音", "https://www.douyin.com/jingxuan?modal_id=7584665891071282432"),
    ("小红书", "http://xhslink.com/o/90PTZaZuCvC"),
]
speed = {}
for label, url in CASES:
    t0 = time.time()
    status, raw = req("/api/parse", "POST", {"url": url})
    dt = time.time() - t0
    p = json.loads(raw)
    speed[label] = dt
    n_fmt = len(p["items"][0].get("formats") or []) if p.get("ok") and p["items"] else 0
    print(f"  [{label}] {dt:5.1f}s | ok={p.get('ok')} | 格式数={n_fmt} | {p['items'][0]['title'][:24] if p.get('items') else p.get('detail', '')[:40]}")

print()
print("=" * 60)
print("二、B站分辨率选择下载测试")
print("=" * 60)
status, raw = req("/api/parse", "POST", {"url": "https://www.bilibili.com/video/BV16Z4y1X784/"})
p = json.loads(raw)
item = p["items"][0]
fmts = item.get("formats") or []
print(f"  可用清晰度: {[(f['id'], f['label'], round(f['filesize']/1048576, 1)) for f in fmts]}")
parse_id = p.get("parse_id")

# 下载最低清晰度 (验证 format_id 生效)
low = fmts[-1]
print(f"\n  → 选择最低清晰度 [{low['id']}] {low['label']} 下载…")
status, raw = req("/api/download", "POST", {"url": "https://www.bilibili.com/video/BV16Z4y1X784/", "index": 0, "format_id": low["id"], "parse_id": parse_id})
task_id = json.loads(raw)["task_id"]
t0 = time.time()
for _ in range(120):
    time.sleep(2)
    status, raw = req(f"/api/tasks/{task_id}")
    t = json.loads(raw)
    if t["status"] in ("done", "error"):
        break
dt = time.time() - t0
if t["status"] == "done":
    size = Path(t["save_path"]).stat().st_size / 1048576
    print(f"  完成 ({dt:.1f}s) | 文件: {t['filename']}")
    print(f"  大小: {size:.2f}MB | 保存: {t['save_path']}")
    expect = low["filesize"] / 1048576
    ok = abs(size - expect) / max(expect, 0.1) < 0.15
    print(f"  与接口报告大小({expect:.1f}MB)偏差 {abs(size-expect)/expect*100:.1f}% → {'符合预期' if ok else '不符合预期!'}")
else:
    print(f"  失败: {t.get('error', '')[:200]}")

# 下载最高清晰度
high = fmts[0]
print(f"\n  → 选择最高清晰度 [{high['id']}] {high['label']} 下载…")
status, raw = req("/api/download", "POST", {"url": "https://www.bilibili.com/video/BV16Z4y1X784/", "index": 0, "format_id": high["id"], "parse_id": parse_id})
task_id = json.loads(raw)["task_id"]
t0 = time.time()
for _ in range(180):
    time.sleep(2)
    status, raw = req(f"/api/tasks/{task_id}")
    t = json.loads(raw)
    if t["status"] in ("done", "error"):
        break
dt = time.time() - t0
if t["status"] == "done":
    size = Path(t["save_path"]).stat().st_size / 1048576
    speed_mbs = size / dt if dt > 0 else 0
    print(f"  完成 ({dt:.1f}s) | 文件: {t['filename']}")
    print(f"  大小: {size:.2f}MB | 平均速度: {speed_mbs:.2f} MB/s")
    expect = high["filesize"] / 1048576
    print(f"  与接口报告大小({expect:.1f}MB)偏差 {abs(size-expect)/expect*100:.1f}%")
else:
    print(f"  失败: {t.get('error', '')[:200]}")

print()
print("=" * 60)
print("三、解析缓存命中测试 (下载启动速度)")
print("=" * 60)
status, raw = req("/api/parse", "POST", {"url": "https://h5.pipix.com/s/OI2PNF-T0Mc/"})
p = json.loads(raw)
t0 = time.time()
status, raw = req("/api/download", "POST", {"url": "https://h5.pipix.com/s/OI2PNF-T0Mc/", "index": 0, "parse_id": p.get("parse_id")})
task_id = json.loads(raw)["task_id"]
for _ in range(60):
    time.sleep(1)
    status, raw = req(f"/api/tasks/{task_id}")
    t = json.loads(raw)
    if t["status"] in ("done", "error"):
        break
print(f"  皮皮虾缓存命中下载: {t['status']} ({time.time()-t0:.1f}s) | {t.get('filename', '')[:30]}")

print()
print("=== 速度对比汇总 ===")
for label, dt in speed.items():
    print(f"  {label}: {dt:.1f}s")
