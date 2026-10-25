"""验证 VLC 安装与 HEVC/H.264 解码能力"""
import os
import subprocess
import sys
import tempfile

VLC = r"C:\Users\k\AppData\Local\Programs\VLC\vlc.exe"
TEST_DIR = os.path.join(tempfile.gettempdir(), "hevc_test")


def run(cmd, timeout=60):
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


print("=" * 60)
print("1) VLC 版本检查")
print("=" * 60)
print(f"   路径存在: {os.path.exists(VLC)}")
if not os.path.exists(VLC):
    print("   ❌ vlc.exe 不存在")
    sys.exit(1)
code, out = run([VLC, "--version"], timeout=40)
ver_line = [ln for ln in out.splitlines() if "VLC media player" in ln]
print(f"   退出码: {code}")
for ln in ver_line[:2]:
    print(f"   {ln.strip()}")

print()
print("=" * 60)
print("2) 无界面解码测试 (dummy 输出仍执行完整解码)")
print("=" * 60)
for name, expect in [("test_hevc.mp4", "HEVC(H.265)"), ("test_h264.mp4", "H.264")]:
    path = os.path.join(TEST_DIR, name)
    if not os.path.exists(path):
        print(f"   {name}: 测试文件不存在, 跳过")
        continue
    code, out = run([VLC, "-I", "dummy", "--vout=dummy", "--aout=dummy",
                     "--play-and-exit", "--no-video-title-show", "--quiet", path], timeout=90)
    low = out.lower()
    # VLC 在 -vv 下会打印使用的解码模块; 这里用 --quiet 只看退出码与错误
    has_err = any(k in low for k in ["cannot decode", "no suitable decoder", "failed to decode", "解码失败"])
    print(f"   {name} ({expect}): 退出码={code} 解码错误标志={has_err}")

print()
print("=" * 60)
print("3) 详细解码模块检查 (HEVC, -vv)")
print("=" * 60)
path = os.path.join(TEST_DIR, "test_hevc.mp4")
if os.path.exists(path):
    code, out = run([VLC, "-I", "dummy", "--vout=dummy", "--aout=dummy", "-vv",
                     "--play-and-exit", "--no-video-title-show", path], timeout=90)
    lines = out.splitlines()
    key = [ln for ln in lines if any(k in ln.lower() for k in
           ["hevc", "decoder", "avcodec", "dxva", "d3d11", "hardware", "faile", "error"])]
    for ln in key[:12]:
        print(f"   {ln.strip()[:150]}")
    print(f"   (退出码 {code})")
