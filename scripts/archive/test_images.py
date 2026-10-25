"""测试: 图集下载代码路径 (用真实小红书图片 CDN 链接验证 download_images)"""
import sys
import time
import uuid
from pathlib import Path

BASE = Path(r"D:\workbuddyhuacunwenjianjjia\2026-10-24-17-18-44\video-parse-tool")
sys.path.insert(0, str(BASE / "backend"))

import main  # noqa: E402
from videodl.modules.utils import VideoInfo  # noqa: E402

# 1) 先解析一条真实小红书笔记, 从 raw_data 中提取真实图片 CDN 链接
print("=== 提取真实图片链接 ===")
client = main.make_client()
infos = client.parsefromurl("http://xhslink.com/o/90PTZaZuCvC")
info = infos[0] if infos else None
images = main.collect_image_urls(main.vget(info, "raw_data") or {}) if info else []
print(f"从 raw_data 提取到 {len(images)} 个图片链接")
for u in images[:3]:
    print("  ", u[:90])
if not images:
    print("未提取到图片链接, 测试终止")
    sys.exit(1)

# 2) 构造图集 VideoInfo, 走 download_images 完整代码路径
fake_info = VideoInfo(
    source="RednoteVideoClient",
    title="测试图集-代码路径验证",
    raw_data={"imageList": [{"url_list": images}]},
)


class FakeClient:
    def parsefromurl(self, url):
        return [fake_info]


task_id = uuid.uuid4().hex[:12]
main.tasks[task_id] = {"id": task_id, "url": "https://www.xiaohongshu.com/explore/test", "status": "queued", "created": time.time()}
print("\n=== 执行图集下载 ===")
main.download_images(main.tasks[task_id], "https://www.xiaohongshu.com/explore/test", 0, FakeClient())
t = main.tasks[task_id]
print(f"status={t['status']} | message={t.get('message', '')}")
print(f"save_path={t.get('save_path')}")
print(f"all_paths={len(t.get('all_paths') or [])} 个文件")
if t.get("save_path"):
    p = Path(t["save_path"])
    print(f"文件存在: {p.exists()} | 大小: {p.stat().st_size if p.exists() else 0} bytes")
