"""测试: 通过后端真实代码路径 parse_sync 测试四大平台解析"""
import json
import sys
import time
from pathlib import Path

BASE = Path(r"D:\workbuddyhuacunwenjianjjia\2026-10-24-17-18-44\video-parse-tool")
sys.path.insert(0, str(BASE / "backend"))

import main  # noqa: E402  导入即执行模块级初始化 (ffmpeg/库导入/目录创建)

print(f"库版本: {main.LIB_VERSION} | 客户端数: {len(main.CLIENT_NAMES)} | FFmpeg: {bool(main.FFMPEG_PATH)}")
if main.LIB_ERROR:
    print("库导入失败:", main.LIB_ERROR)
    sys.exit(1)

status = json.loads((BASE / "libs" / "videodl-master" / "daily_test_results" / "videodl_status.json").read_text(encoding="utf-8"))
targets = ["DouyinVideoClient", "RednoteVideoClient", "BilibiliVideoClient", "PipixVideoClient"]

test_urls = []
for c in status["clients"]:
    if c["name"] in targets:
        for t in c.get("tests", []):
            test_urls.append((c["name"], t["test_url"], t.get("ok")))

# 每个平台最多测 2 条, 控制总时长
seen = {}
selected = []
for name, url, ok in test_urls:
    if seen.get(name, 0) >= 2:
        continue
    seen[name] = seen.get(name, 0) + 1
    selected.append((name, url, ok))

print(f"\n共选择 {len(selected)} 条测试链接:\n")
results = []
for name, url, ci_ok in selected:
    print(f"--- [{name}] CI结果={'OK' if ci_ok else 'FAIL'} {url}")
    t0 = time.time()
    try:
        r = main.parse_sync(url)
        dt = time.time() - t0
        if r.get("ok"):
            items = r["items"]
            print(f"    解析成功 ({dt:.1f}s), {len(items)} 项")
            for it in items[:2]:
                imgs = f", 图片{len(it['images'])}张" if it["kind"] == "images" else ""
                print(f"      - kind={it['kind']}{imgs} title={it['title'][:40]!r} ext={it['ext']} url={(it['download_url'] or '')[:60]!r}")
            results.append((name, True))
        else:
            print(f"    解析失败 ({dt:.1f}s): {r.get('detail', '')[:150]}")
            results.append((name, False))
    except Exception as e:
        print(f"    异常: {type(e).__name__}: {e}")
        results.append((name, False))
    print()

print("=== 汇总 ===")
for name, ok in results:
    print(f"  {name}: {'OK' if ok else 'FAIL'}")
ok_count = sum(1 for _, ok in results if ok)
print(f"通过 {ok_count}/{len(results)}")
