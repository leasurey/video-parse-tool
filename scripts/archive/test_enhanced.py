"""测试: 增强 B站客户端 (UGC 多清晰度 / 番剧 DASH 格式 / 链接刷新)"""
import sys
import time
from pathlib import Path

BASE = Path(r"D:\workbuddyhuacunwenjianjjia\2026-10-24-17-18-44\video-parse-tool")
sys.path.insert(0, str(BASE / "backend"))

import main  # noqa: E402
from enhanced_clients import EnhancedBilibiliVideoClient, patch_clients  # noqa: E402

print("patch_clients:", patch_clients())
client = main.make_client()

print("\n=== 1. UGC 视频 (BV16Z4y1X784) ===")
t0 = time.time()
infos = client.parsefromurl("https://www.bilibili.com/video/BV16Z4y1X784/")
dt = time.time() - t0
for info in infos:
    fmts = info.get("formats") or []
    print(f"解析耗时 {dt:.1f}s | title={info['title'][:30]!r} | source={info['source']}")
    print(f"格式数: {len(fmts)}")
    for f in fmts:
        print(f"  - [{f['id']}] {f['label']} | {f['width']}x{f['height']} | {f['filesize']/1048576:.1f}MB | url={f['video_url'][:60]}...")
    ctx = info.get("format_ctx")
    print(f"format_ctx: {ctx}")
    if fmts:
        # 测试链接刷新
        inst = client.video_clients.get("BilibiliVideoClient")
        inst = inst if not isinstance(inst, dict) else __import__("videodl.modules", fromlist=["BuildVideoClient"]).BuildVideoClient(module_cfg=inst["cfg"])
        r = inst.refreshformat(ctx, fmts[-1]["id"])
        print(f"刷新最低格式链接: {'OK ' + r['video_url'][:60] if r and r.get('video_url') else 'FAIL'}")

print("\n=== 2. 番剧 (ep21495) ===")
t0 = time.time()
infos = client.parsefromurl("https://www.bilibili.com/bangumi/play/ep21495")
dt = time.time() - t0
for info in infos:
    fmts = info.get("formats") or []
    print(f"解析耗时 {dt:.1f}s | title={info['title'][:30]!r} | source={info['source']}")
    print(f"格式数: {len(fmts)} | audio={'有' if info.get('audio_download_url') else '无'}")
    for f in fmts[:6]:
        print(f"  - [{f['id']}] {f['label']} | {f['width']}x{f['height']} | {f['filesize']/1048576:.1f}MB | {f['codec'][:20]}")

print("\n=== 3. 多P视频 (?p=2) ===")
t0 = time.time()
infos = client.parsefromurl("https://www.bilibili.com/video/BV16Z4y1X784/?p=1")
print(f"耗时 {time.time()-t0:.1f}s | 结果数={len(infos)}")
