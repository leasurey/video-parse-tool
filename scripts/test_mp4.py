"""验证「统一输出 MP4」逻辑: 用 ffmpeg 造出 flv/webm/mkv/ts 素材, 检查转换后是否为真 MP4 容器"""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE / "backend"))

FFMPEG = BASE / "bin" / "ffmpeg.exe"
if not FFMPEG.is_file():
    FFMPEG = Path(shutil.which("ffmpeg") or "")
if not FFMPEG:
    raise SystemExit("未找到 ffmpeg, 无法测试")

import main as backend  # noqa: E402  (加载后端模块, 复用 ensure_mp4_output)


def gen(path: Path, container_args: list):
    cmd = [
        str(FFMPEG), "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "testsrc=size=320x240:rate=15",
        "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100",
        "-t", "3", "-shortest", *container_args, str(path),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore")
    return r.returncode == 0 and path.is_file()


def is_mp4(path: Path) -> bool:
    with open(path, "rb") as fp:
        head = fp.read(12)
    return len(head) >= 8 and head[4:8] == b"ftyp"


def duration(path: Path) -> str:
    r = subprocess.run([str(FFMPEG), "-hide_banner", "-i", str(path)], capture_output=True, text=True,
                       encoding="utf-8", errors="ignore")
    m = __import__("re").search(r"Duration:\s*([^,]+)", r.stderr or "")
    return m.group(1).strip() if m else "?"


CASES = [
    ("flv", ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-f", "flv"]),
    ("webm", ["-c:v", "libvpx-vp9", "-b:v", "0", "-crf", "40", "-c:a", "libopus", "-f", "webm"]),
    ("mkv", ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-f", "matroska"]),
    ("ts", ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-f", "mpegts"]),
    ("mp4", ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-f", "mp4", "-movflags", "+faststart"]),
]


def main():
    tmp = Path(tempfile.mkdtemp(prefix="mp4test_"))
    print(f"临时目录: {tmp}\n")
    ok_all = True
    for name, args in CASES:
        src = tmp / f"sample.{name}"
        if not gen(src, args):
            print(f"[{name}] 素材生成失败 -> 跳过")
            continue
        probe = backend.probe_media(src)
        task: dict = {}
        out = backend.ensure_mp4_output(src, task)
        passed = out.suffix.lower() == ".mp4" and is_mp4(out)
        orig_left = src.is_file()
        size_in = src.stat().st_size if orig_left else 0
        print(f"[{name:>4}] 探测={probe['format'] or '?':<24} 视频流={probe['has_video']} "
              f"-> {out.name} ({out.stat().st_size / 1024:.0f} KB) "
              f"MP4容器={'是' if is_mp4(out) else '否'} 时长={duration(out)} "
              f"原文件{'保留' if orig_left else '已删除'} msg={task.get('message', '')}")
        print(f"        结果: {'通过' if passed else '失败'}")
        ok_all = ok_all and passed
    shutil.rmtree(tmp, ignore_errors=True)
    print("\n总体:", "全部通过" if ok_all else "存在失败项")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
