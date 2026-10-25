"""后台断点续传下载 videodl tarball 并解压 (codeload 限速, 需长时间运行)"""
import os
import shutil
import tarfile
import time
import urllib.request

URL = "https://codeload.github.com/CharlesPikachu/videodl/tar.gz/refs/heads/master"
LIBS = r"D:\workbuddyhuacunwenjianjjia\2026-10-24-17-18-44\video-parse-tool\libs"
OUT = os.path.join(LIBS, "videodl.tar.gz")
TARGET = os.path.join(LIBS, "videodl")


def log(*a):
    print(*a, flush=True)


os.makedirs(LIBS, exist_ok=True)
pos = os.path.getsize(OUT) if os.path.exists(OUT) else 0
headers = {"User-Agent": "Mozilla/5.0"}
if pos:
    headers["Range"] = f"bytes={pos}-"
req = urllib.request.Request(URL, headers=headers)
resp = urllib.request.urlopen(req, timeout=300)
log("status", resp.status, "| resume from", pos, "bytes")
mode = "ab" if (pos and resp.status == 206) else "wb"
t0 = time.time()
n = pos
with open(OUT, mode) as f:
    while True:
        c = resp.read(262144)
        if not c:
            break
        f.write(c)
        n += len(c)
        if n % (4 * 1024 * 1024) < 262144:
            log(f"  {n / 1048576:.1f} MB, {time.time() - t0:.0f}s")
log("download complete:", n, "bytes in", round(time.time() - t0), "s")

if os.path.exists(TARGET):
    shutil.rmtree(TARGET)
with tarfile.open(OUT, "r:gz") as tf:
    tf.extractall(LIBS)
os.rename(os.path.join(LIBS, "videodl-master"), TARGET)
log("extracted ->", TARGET)
log("top-level:", sorted(os.listdir(TARGET)))
