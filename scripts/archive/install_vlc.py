"""下载并校验官方 VLC 便携版
- 文件来源: VideoLAN 官方镜像 (TUNA / USTC / NJU, 来自 get.videolan.org 的官方镜像列表)
- 完整性: 从两个独立镜像获取 .sha256 并交叉比对, 再校验文件哈希
- 安装: 解压到用户目录, 无需管理员权限, 不修改系统
"""
import hashlib
import os
import sys
import time
import urllib.request
import zipfile

ZIP_NAME = "vlc-3.0.24-win64.zip"
MIRRORS = [
    "https://download.videolan.org/pub/videolan/vlc/3.0.24/win64",
    "https://get.videolan.org/vlc/3.0.24/win64",
]
TMP_DIR = os.environ.get("TEMP", r"C:\Users\k\AppData\Local\Temp")
ZIP_PATH = os.path.join(TMP_DIR, ZIP_NAME)
DEST = r"C:\Users\k\AppData\Local\Programs\VLC"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36"}


def log(*a):
    print(*a, flush=True)


def fetch_text(url, timeout=30, ua=None):
    hdrs = {"User-Agent": ua or UA["User-Agent"]}
    return urllib.request.urlopen(urllib.request.Request(url, headers=hdrs), timeout=timeout).read().decode("utf-8", "replace").strip()


def download(url, dst, max_retries=10):
    part = dst + ".part"
    t0 = time.time()
    for attempt in range(1, max_retries + 1):
        pos = os.path.getsize(part) if os.path.exists(part) else 0
        headers = dict(UA)
        if pos:
            headers["Range"] = f"bytes={pos}-"
        try:
            hdrs = dict(headers)
            if "get.videolan.org" in url:
                hdrs["User-Agent"] = "Wget/1.21.4"
            resp = urllib.request.urlopen(urllib.request.Request(url, headers=hdrs), timeout=30)
            total = int(resp.headers.get("Content-Length") or 0) + pos
            ctype = resp.headers.get("Content-Type", "")
            if "text/html" in ctype:
                raise RuntimeError(f"返回了 HTML 而非文件: {ctype}")
            mode = "ab" if (pos and resp.status == 206) else "wb"
            if mode == "wb":
                pos = 0
            with open(part, mode) as f:
                while True:
                    chunk = resp.read(262144)
                    if not chunk:
                        break
                    f.write(chunk)
                    pos += len(chunk)
                    if pos % (10 * 1024 * 1024) < 262144:
                        log(f"    {pos/1048576:.1f}MB" + (f" / {total/1048576:.1f}MB" if total else "") + f"  ({pos/max(time.time()-t0,0.1)/1048576:.1f}MB/s)")
            got = os.path.getsize(part)
            if total and got < total:
                log(f"  第 {attempt} 次未完成 ({got}/{total}), 续传…")
                continue
            os.replace(part, dst)
            log(f"  完成: {got} 字节, 用时 {time.time()-t0:.1f}s")
            return
        except Exception as e:
            got = os.path.getsize(part) if os.path.exists(part) else 0
            log(f"  第 {attempt} 次中断 ({type(e).__name__}: {str(e)[:60]}), 已下载 {got/1048576:.1f}MB, 续传…")
            time.sleep(min(2 * attempt, 10))
    raise RuntimeError("下载多次重试后仍失败")


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


log("1) 从两个独立官方镜像获取 SHA-256 并交叉比对")
hashes = {}
for i, m in enumerate(MIRRORS[:2]):
    try:
        # get.videolan.org 对浏览器 UA 返回镜像选择页, 需用 wget UA 获取文件
        txt = fetch_text(f"{m}/{ZIP_NAME}.sha256", ua=("Wget/1.21.4" if i == 1 else None))
        h = txt.split()[0].lower()
        hashes[m] = h
        log(f"  {m.split('/')[2]}: {h}")
    except Exception as e:
        log(f"  {m.split('/')[2]} 获取失败: {str(e)[:60]}")
if not hashes:
    log("  ❌ 无法获得官方哈希, 停止")
    sys.exit(1)
if len(set(hashes.values())) > 1:
    log("  ❌ 不同来源哈希不一致, 停止 (可能存在篡改)")
    sys.exit(1)
official_hash = next(iter(hashes.values()))
log(f"  ✅ 官方哈希: {official_hash}" + (f" (来自 {len(hashes)} 个独立源)" if len(hashes) > 1 else ""))

log("2) 下载安装包 (按镜像顺序尝试)")
if os.path.exists(ZIP_PATH):
    os.remove(ZIP_PATH)
last_err = None
for m in MIRRORS:
    try:
        log(f"  使用镜像: {m.split('/')[2]}")
        download(f"{m}/{ZIP_NAME}", ZIP_PATH)
        break
    except Exception as e:
        last_err = e
        log(f"  镜像失败: {str(e)[:80]}")
else:
    log(f"  ❌ 所有镜像均失败: {last_err}")
    sys.exit(1)

log("3) 校验文件 SHA-256")
actual = sha256_of(ZIP_PATH)
log(f"  实际: {actual}")
if actual != official_hash:
    log("  ❌ 校验失败! 文件损坏或被篡改, 已删除")
    os.remove(ZIP_PATH)
    sys.exit(1)
log("  ✅ 校验通过")

log("4) 解压到用户目录 (无需管理员)")
os.makedirs(DEST, exist_ok=True)
with zipfile.ZipFile(ZIP_PATH) as zf:
    names = zf.namelist()
    top = names[0].split("/")[0] if names else ""
    for member in zf.infolist():
        rel = member.filename
        if rel.startswith(top + "/"):
            rel = rel[len(top) + 1:]
        if not rel:
            continue
        target = os.path.join(DEST, rel.replace("/", os.sep))
        if member.is_dir():
            os.makedirs(target, exist_ok=True)
        else:
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with zf.open(member) as src, open(target, "wb") as out:
                out.write(src.read())

exe = os.path.join(DEST, "vlc.exe")
if os.path.exists(exe):
    log(f"5) ✅ vlc.exe 就绪: {exe} ({os.path.getsize(exe)/1048576:.1f}MB), 目录共 {len(os.listdir(DEST))} 项")
else:
    log("5) ❌ vlc.exe 未找到")
    sys.exit(1)
