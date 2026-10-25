"""测试: 通过后端真实代码路径测试下载全流程 (解析->下载->落盘->ffmpeg合并)"""
import sys
import time
import uuid
from pathlib import Path

BASE = Path(r"D:\workbuddyhuacunwenjianjjia\2026-10-24-17-18-44\video-parse-tool")
sys.path.insert(0, str(BASE / "backend"))

import main  # noqa: E402

# 1) 抖音标准视频链接格式的原生解析测试
print("=== 抖音 /video/ 格式原生解析测试 ===")
try:
    r = main.parse_sync("https://www.douyin.com/video/7584665891071282432")
    for it in r.get("items", [])[:1]:
        print(f"  ok={r.get('ok')} title={it['title'][:40]!r} url={(it['download_url'] or '')[:70]!r} source={it['source']}")
    if not r.get("ok"):
        print("  detail:", r.get("detail", "")[:120])
except Exception as e:
    print("  异常:", e)

# 2) 下载全流程测试
CASES = [
    ("皮皮虾", "https://h5.pipix.com/s/OI2PNF-T0Mc/"),
    ("B站", "https://www.bilibili.com/video/BV16Z4y1X784/"),
    ("抖音", "https://www.douyin.com/jingxuan?modal_id=7584665891071282432"),
]

print("\n=== 下载全流程测试 ===")
for label, url in CASES:
    task_id = uuid.uuid4().hex[:12]
    main.tasks[task_id] = {"id": task_id, "url": url, "status": "queued", "created": time.time()}
    print(f"\n--- [{label}] {url}")
    t0 = time.time()
    main.download_sync(task_id, url, 0)
    t = main.tasks[task_id]
    dt = time.time() - t0
    if t["status"] == "done":
        p = Path(t["save_path"])
        size = p.stat().st_size if p.exists() else -1
        print(f"  下载成功 ({dt:.1f}s) status={t['status']}")
        print(f"  文件: {p}")
        print(f"  大小: {size/1048576:.2f} MB | 任务filename={t['filename']}")
        if t.get("all_paths") and len(t["all_paths"]) > 1:
            print(f"  多文件: {len(t['all_paths'])} 个")
    else:
        print(f"  下载失败 ({dt:.1f}s): {t.get('error', '')[:200]}")
