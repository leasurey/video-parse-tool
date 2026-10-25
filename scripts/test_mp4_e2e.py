"""端到端验证: 真实下载后是否统一输出为 MP4 (并确认原始容器文件已清理)"""
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE / "backend"))

BILI = "https://www.bilibili.com/video/BV16Z4y1X784/"
PIPIX = "https://h5.pipix.com/s/OI2PNF-T0Mc/"


def is_mp4(p: Path) -> bool:
    try:
        with open(p, "rb") as fp:
            head = fp.read(12)
    except Exception:
        return False
    return len(head) >= 8 and head[4:8] == b"ftyp"


def run(tid: str, url: str, index: int = 0, format_id=None, parse_id=None):
    backend.tasks[tid] = {"id": tid, "url": url, "status": "queued", "created": time.time()}
    t0 = time.time()
    backend.download_sync(tid, url, index, format_id, parse_id)
    return backend.tasks[tid], time.time() - t0


def report(name: str, t: dict, dt: float):
    if t.get("status") != "done":
        print(f"[{name}] 失败 ({dt:.1f}s): {t.get('error') or t.get('message') or ''}")
        return False
    p = Path(t["save_path"])
    probe = backend.probe_media(p)
    size_mb = p.stat().st_size / 1048576 if p.is_file() else 0
    print(f"[{name}] {dt:5.1f}s | {p.name}")
    print(f"        后缀={p.suffix} MP4容器={'是' if is_mp4(p) else '否'} "
          f"视频={probe['video_codec'] or '-'} 音频={probe['audio_codec'] or '-'} 大小={size_mb:.2f}MB")
    print(f"        提示={t.get('message') or '-'}")
    parent = p.parent
    others = [f.name for f in parent.iterdir() if f.is_file() and f.suffix.lower() != ".mp4"]
    print(f"        同目录非 MP4 残留: {others or '无'}")
    return p.suffix.lower() == ".mp4" and is_mp4(p)


print("加载后端模块 ...")
import main as backend  # noqa: E402

ok_all = True

print("\n=== 1) B站 低清 (FLV 流 -> 需重封装) ===")
p = backend.parse_sync(BILI)
fmts = (p["items"][0].get("formats") or []) if p.get("items") else []
print("  可选清晰度:", [(f["id"], f["label"]) for f in fmts])
low = min(fmts, key=lambda f: f.get("filesize") or 0) if fmts else None
t, dt = run("t_bili", BILI, 0, low["id"] if low else None, p.get("parse_id"))
ok_all = report("B站", t, dt) and ok_all

print("\n=== 2) 皮皮虾 (直链, 平台原始容器) ===")
p2 = backend.parse_sync(PIPIX)
t2, dt2 = run("t_pipix", PIPIX, 0, None, p2.get("parse_id"))
ok_all = report("皮皮虾", t2, dt2) and ok_all

print("\n总体:", "全部输出为 MP4" if ok_all else "存在非 MP4 输出")
sys.exit(0 if ok_all else 1)
