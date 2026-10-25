"""调试6: 各通用解析器对抖音/小红书的耗时与成功率"""
import sys
import time
from pathlib import Path

BASE = Path(r"D:\workbuddyhuacunwenjianjjia\2026-10-24-17-18-44\video-parse-tool")
sys.path.insert(0, str(BASE / "backend"))
import main  # noqa: E402
from videodl.modules import BuildCommonVideoClient  # noqa: E402

CANDIDATES = ["GVVideoClient", "SnapWCVideoClient", "VgetVideoClient", "KedouVideoClient", "MiZhiVideoClient", "APICXVideoClient", "RayVideoClient", "BugPkVideoClient"]
URLS = {
    "抖音": "https://www.douyin.com/jingxuan?modal_id=7584665891071282432",
    "小红书": "http://xhslink.com/o/90PTZaZuCvC",
}

for label, url in URLS.items():
    print(f"\n=== {label} {url} ===")
    for name in CANDIDATES:
        try:
            inst = BuildCommonVideoClient(main._client_cfg(name))
            t0 = time.time()
            infos = inst.parsefromurl(url)
            dt = time.time() - t0
            ok = main._infos_valid(infos)
            src = infos[0]["source"] if infos else "-"
            print(f"  {name:24s} {dt:6.1f}s {'成功' if ok else '失败'} ({src})", flush=True)
        except Exception as e:
            print(f"  {name:24s} 异常: {str(e)[:60]}", flush=True)
