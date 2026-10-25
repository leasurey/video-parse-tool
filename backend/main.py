"""
视频解析下载工具 — 统一后端服务
基于开源库 videodl (https://github.com/CharlesPikachu/videodl, PolyForm-Noncommercial-1.0.0 许可证)
提供: 链接解析 / 多平台下载 / 文件管理 HTTP API, 并托管前端页面
"""
import asyncio
import copy
import ipaddress
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import uuid
import webbrowser
from pathlib import Path
from urllib.parse import quote, urlparse

import requests
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, Response
from pydantic import BaseModel

# ============ 项目版本（唯一权威值，界面页脚与 CHANGELOG 均以此为准） ============
APP_VERSION = "1.0.1"

# ============ 基础路径 ============
BASE = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE / "config.json"
FRONTEND_FILE = BASE / "frontend" / "index.html"
BIN_DIR = BASE / "bin"

# ============ 配置 ============
DEFAULT_CONFIG = {
    # 监听地址: "127.0.0.1" = 仅本机; "0.0.0.0" = 监听全部网卡 (手机等局域网设备可访问)
    "host": "0.0.0.0",
    "port": 8000,
    # 局域网访问开关: true = 启动时打印局域网地址并允许手机访问; false = 仅本机 (忽略 host 的 0.0.0.0)
    "lan_access": True,
    "download_dir": "downloads",
    "max_concurrent_downloads": 2,
    "download_threads": 8,
    "open_browser": True,
    "cookies": {},
    # 统一输出容器: "mp4" = 下载后自动转为 MP4 (更通用); "auto" = 保留平台原始格式
    "output_format": "mp4",
    # 转为 MP4 后是否保留原始格式文件 (默认不保留, 避免重复占位)
    "keep_original_after_remux": False,
}


def load_config() -> dict:
    cfg = dict(DEFAULT_CONFIG)
    # 首次运行: config.json 不入库，从模板生成一份便于用户修改
    if not CONFIG_PATH.exists():
        example = BASE / "config.example.json"
        if example.is_file():
            try:
                shutil.copyfile(example, CONFIG_PATH)
                print("[配置] 未找到 config.json，已从 config.example.json 生成")
            except Exception as e:
                print(f"[配置] 生成 config.json 失败，使用默认配置: {e}")
    try:
        user_cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        if isinstance(user_cfg, dict):
            cfg.update(user_cfg)
    except Exception as e:
        print(f"[配置] 读取 config.json 失败，使用默认配置: {e}")
    return cfg


CONFIG = load_config()


def resolve_download_dir() -> Path:
    d = Path(CONFIG["download_dir"])
    d = d.resolve() if d.is_absolute() else (BASE / d).resolve()
    d.mkdir(parents=True, exist_ok=True)
    return d


DOWNLOAD_DIR = resolve_download_dir()

LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}

# ============ 网络地址 ============


def get_lan_ips() -> list:
    """枚举本机非回环 IPv4 地址 (用于给手机访问的地址提示)"""
    ips = set()
    try:  # 主网卡: 借 UDP  connect 拿到默认出口 IP (不发实际数据包)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("223.5.5.5", 80))
            ips.add(s.getsockname()[0])
    except Exception:
        pass
    try:  # 其余网卡
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith(("127.", "169.254.")):
                ips.add(ip)
    except Exception:
        pass
    return sorted(ips)


def lan_enabled() -> bool:
    """是否在监听全部网卡且开启了局域网访问"""
    return bool(CONFIG.get("lan_access", True)) and str(CONFIG.get("host", "127.0.0.1")) in ("0.0.0.0", "::", "")


def server_addresses() -> dict:
    port = int(CONFIG.get("port", 8000))
    lan = [f"http://{ip}:{port}" for ip in get_lan_ips()] if lan_enabled() else []
    return {
        "local": f"http://127.0.0.1:{port}",
        "lan": lan,
        "host": str(CONFIG.get("host", "127.0.0.1")),
        "port": port,
        "lan_enabled": lan_enabled(),
    }

# Windows 控制台编码保护 (库会输出中文/emoji)
for _stream in (sys.stdout, sys.stderr):
    if _stream is not None and hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

# ============ FFmpeg 配置 (HLS/DASH 合并必需) ============


def setup_ffmpeg():
    """优先使用系统 PATH 中的 ffmpeg; 否则复制 imageio-ffmpeg 静态二进制到 bin/ffmpeg.exe 并加入 PATH
    注意: 库通过 FFmpegCommandFactory(executable='ffmpeg') 按名称调用, 必须保证 PATH 能解析到 ffmpeg(.exe)"""
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg
        src = Path(imageio_ffmpeg.get_ffmpeg_exe())
        BIN_DIR.mkdir(parents=True, exist_ok=True)
        dst = BIN_DIR / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
        if not dst.exists():
            shutil.copy2(src, dst)
        os.environ["PATH"] = os.pathsep.join([str(BIN_DIR), os.environ.get("PATH", "")])
        resolved = shutil.which("ffmpeg") or ""
        if resolved.lower() != str(dst).lower():
            print(f"[FFmpeg] 警告: PATH 中 ffmpeg 解析异常 -> {resolved}")
        return str(dst)
    except Exception as e:
        print(f"[FFmpeg] 自动配置失败: {e}")
        return None


FFMPEG_PATH = setup_ffmpeg()

# ============ 输出格式 ============
OUTPUT_FORMAT = str(CONFIG.get("output_format", "mp4") or "mp4").strip().lower()
KEEP_ORIGINAL_AFTER_REMUX = bool(CONFIG.get("keep_original_after_remux", False))

# ============ 解析库导入 (PyPI: videofetch, 回退: libs/videodl) ============


def import_videodl():
    try:
        import videodl
        from videodl.videodl import VideoClient
        return VideoClient, getattr(videodl, "__version__", "unknown")
    except ImportError:
        local = BASE / "libs" / "videodl"
        if local.is_dir():
            sys.path.insert(0, str(local))
            import videodl
            from videodl.videodl import VideoClient
            return VideoClient, getattr(videodl, "__version__", "unknown")
        raise


def get_registered_client_names():
    from videodl.modules import VideoClientBuilder, CommonVideoClientBuilder
    return list(VideoClientBuilder.REGISTERED_MODULES.keys()) + list(CommonVideoClientBuilder.REGISTERED_MODULES.keys())


VideoClient = None
LIB_VERSION = None
CLIENT_NAMES = []
LIB_ERROR = None
try:
    VideoClient, LIB_VERSION = import_videodl()
    CLIENT_NAMES = get_registered_client_names()
    from enhanced_clients import patch_clients
    patch_clients()  # 注入增强客户端 (B站多清晰度) 并调整通用解析器优先级
except Exception as e:
    LIB_ERROR = f"{type(e).__name__}: {e}"
    print(f"[解析库] 导入失败: {LIB_ERROR}")
    print("[解析库] 请先在项目目录运行 install.bat (或 pip install videofetch) 安装依赖")

# ============ 平台识别 ============
# 注意: 域名可能直接出现在协议头后 (//xiaohongshu.com) 或 www. 后 (.xiaohongshu.com), 需同时覆盖
PLATFORM_RULES = [
    (r"(?:^|\.|//)(douyin\.com|iesdouyin\.com)", "抖音", "#fe2c55", "douyin"),
    (r"(?:^|\.|//)(xiaohongshu\.com|xhslink\.com|xhslink\.cn|rednote\.com)", "小红书", "#ff2442", "xiaohongshu"),
    (r"(?:^|\.|//)(bilibili\.com|b23\.tv)", "B站", "#00aeec", "bilibili"),
    (r"(?:^|\.|//)(pipix\.com|pipixia)", "皮皮虾", "#ff8200", "pipix"),
    (r"(?:^|\.|//)(kuaishou\.com|chenzhongtech\.com)", "快手", "#ff4906", "kuaishou"),
    (r"(?:^|\.|//)(weibo\.com|weibo\.cn)", "微博", "#e6162d", "weibo"),
    (r"(?:^|\.|//)(youku\.com)", "优酷", "#1e88e5", "youku"),
    (r"(?:^|\.|//)(v\.qq\.com)", "腾讯视频", "#ff9d00", "tencent"),
    (r"(?:^|\.|//)(iqiyi\.com)", "爱奇艺", "#00be06", "iqiyi"),
    (r"(?:^|\.|//)(mgtv\.com)", "芒果TV", "#ff6600", "mgtv"),
    (r"(?:^|\.|//)(sohu\.com)", "搜狐视频", "#ffcc00", "sohu"),
    (r"(?:^|\.|//)(zhihu\.com)", "知乎", "#0084ff", "zhihu"),
    (r"(?:^|\.|//)(ixigua\.com)", "西瓜视频", "#f85959", "xigua"),
    (r"(?:^|\.|//)(youtube\.com|youtu\.be)", "YouTube", "#ff0000", "youtube"),
]

# 平台 -> 原生解析器类名 (用于按平台路由)
PLATFORM_NATIVE = {
    "douyin": "DouyinVideoClient",
    "xiaohongshu": "RednoteVideoClient",
    "bilibili": "BilibiliVideoClient",
    "pipix": "PipixVideoClient",
    "kuaishou": "KuaishouVideoClient",
    "weibo": "WeiboVideoClient",
}

# 平台 -> 通用解析器优先顺序 (按实测成功率/速度; 原生解析器对小红书保留第一)
# 注: 第三方解析服务速度会变化, 失败时自动走完整解析链兜底
PLATFORM_PARSER_PRIORITY = {
    "douyin": ["RayVideoClient", "BugPkVideoClient", "KedouVideoClient", "GVVideoClient", "SnapWCVideoClient"],
    "xiaohongshu": ["RayVideoClient", "GVVideoClient", "KedouVideoClient", "SnapWCVideoClient"],
}

URL_RE = re.compile(r"https?://[^\s，。；、\"'）)\]】]+", re.I)
IMAGE_URL_RE = re.compile(r"^https?://\S+?\.(?:jpg|jpeg|png|webp|gif|bmp|heic)(?:\?\S*)?$", re.I)
VIDEO_URL_RE = re.compile(r"^https?://\S+?\.(?:mp4|mov|webm|mkv|flv|m4v|m3u8)(?:\?\S*)?$", re.I)
# 常见图片 CDN 域名 (部分平台图片直链不带扩展名, 如抖音图集)
IMAGE_CDN_RE = re.compile(
    r"^https?://(?:[^/?#]+\.)?(?:xhscdn\.com|sns-img|toutiaoimg\.com|byteimg\.com|sinaimg\.cn|qpic\.cn|pstatp\.com)[^\s]*$",
    re.I,
)

# 配置 cookies 的平台键 -> 库内部客户端类名
PLATFORM_CLIENT_MAP = {
    "douyin": "DouyinVideoClient",
    "xiaohongshu": "RednoteVideoClient",
    "bilibili": "BilibiliVideoClient",
    "pipix": "PipixVideoClient",
    "pipigaoxiao": "PipigaoxiaoVideoClient",
    "kuaishou": "KuaishouVideoClient",
    "weibo": "WeiboVideoClient",
    "youku": "YoukuVideoClient",
    "tencent": "TencentVideoClient",
    "iqiyi": "IQiyiVideoClient",
    "zhihu": "ZhihuVideoClient",
    "xigua": "XiguaVideoClient",
}


def extract_url(text: str) -> str:
    m = URL_RE.search(text or "")
    return m.group(0) if m else ""


def detect_platform(url: str) -> dict:
    for pattern, label, color, _key in PLATFORM_RULES:
        if re.search(pattern, url, re.I):
            return {"label": label, "color": color}
    return {"label": "自动识别", "color": "#6c8cff"}


def detect_platform_key(url: str):
    for pattern, _label, _color, key in PLATFORM_RULES:
        if re.search(pattern, url, re.I):
            return key
    return None


def parse_cookie_string(s: str) -> dict:
    cookies = {}
    for part in re.split(r"[;,]", s or ""):
        if "=" in part:
            k, v = part.split("=", 1)
            k, v = k.strip(), v.strip()
            if k:
                cookies[k] = v
    return cookies


def build_requests_overrides() -> dict:
    overrides = {}
    cookies_cfg = CONFIG.get("cookies") or {}
    for plat, client_name in PLATFORM_CLIENT_MAP.items():
        raw = cookies_cfg.get(plat)
        if not raw:
            continue
        cookies = parse_cookie_string(raw) if isinstance(raw, str) else raw
        if cookies:
            overrides[client_name] = {"cookies": cookies}
    return overrides


def make_client():
    """每次操作创建新客户端 (库为惰性实例化, 创建开销小, 且天然避免并发共享状态)
    注意: 库的 VideoClient 不接受 allowed_video_sources=None (set(None) 会报错), 必须显式传列表"""
    init_cfg = {name: {"work_dir": str(DOWNLOAD_DIR)} for name in CLIENT_NAMES}
    # WebMediaGrabber 是特殊键 (直链媒体抓取器), 不设置则使用库默认的 'videodl_outputs' 目录
    init_cfg["WebMediaGrabber"] = {"work_dir": str(DOWNLOAD_DIR)}
    threads = max(1, int(CONFIG.get("download_threads", 8)))
    clients_threadings = {name: threads for name in CLIENT_NAMES}
    return VideoClient(
        allowed_video_sources=list(CLIENT_NAMES),
        init_video_clients_cfg=init_cfg,
        clients_threadings=clients_threadings,
        requests_overrides=build_requests_overrides(),
    )

# ============ VideoInfo 序列化 ============


def vget(info, key, default=None):
    try:
        val = info[key]
        if val is not None:
            return val
    except Exception:
        pass
    try:
        val = getattr(info, key, None)
        if val is not None:
            return val
    except Exception:
        pass
    return default


def _find_first_key(obj, key: str, depth: int = 0):
    """在嵌套结构中查找第一个匹配的键值"""
    if depth > 8:
        return None
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]
        for v in obj.values():
            found = _find_first_key(v, key, depth + 1)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for v in obj[:20]:
            found = _find_first_key(v, key, depth + 1)
            if found is not None:
                return found
    return None


def _ensure_https(url):
    if not url or not isinstance(url, str):
        return url
    url = url.replace("\\u002F", "/")
    return "https://" + url[7:] if url.startswith("http://") else url


def collect_image_urls(obj, acc=None, depth=0):
    """通用图片 URL 收集 (非标准结构的兜底)"""
    if acc is None:
        acc = []
    if depth > 6 or len(acc) >= 100:
        return acc
    if isinstance(obj, str):
        if obj in acc or VIDEO_URL_RE.match(obj):
            return acc
        try:
            host = urlparse(obj).netloc.lower()
            path = urlparse(obj).path.lower()
        except Exception:
            host, path = "", ""
        if "video" in host or "/stream/" in path or "/pre_post/" in path:
            return acc
        if IMAGE_URL_RE.match(obj) or IMAGE_CDN_RE.match(obj):
            acc.append(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            collect_image_urls(v, acc, depth + 1)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            collect_image_urls(v, acc, depth + 1)
    return acc


def _xhs_image_candidates(entry: dict) -> list:
    """小红书图片候选地址: 优先 fileId 构造的稳定原图, 备选签名地址 (sns-webpic 有时效/限流)"""
    urls = []
    file_id = entry.get("fileId") or ""
    if file_id:
        urls.append(f"https://sns-img-qc.xhscdn.com/{file_id}?imageView2/2/w/1920/format/jpg")
    for key in ("urlDefault", "url"):
        u = _ensure_https(entry.get(key) or "")
        if u and u not in urls:
            urls.append(u)
    info_list = entry.get("infoList") or []
    for it in reversed(info_list):
        if isinstance(it, dict):
            u = _ensure_https(it.get("url") or "")
            if u and u not in urls:
                urls.append(u)
    if file_id:
        u = f"https://sns-img-hw.xhscdn.com/{file_id}"
        if u not in urls:
            urls.append(u)
    return urls


def extract_album_contents(raw_data, cover_url: str = "") -> list:
    """从 raw_data 提取图集内容, 静态图片与实况视频分区:
    [{"type": "image"|"live_video", "url": ..., "fallback_urls": [...], "thumbnail": ...}, ...]
    实况照片 (小红书): imageList[].livePhoto == true, 视频在 stream.{h264,h265,av1,h266}[0].masterUrl
    实况照片的静态封面不作为独立静态图 (避免重复), 仅作为实况视频的缩略图, 下载时随视频一并保存"""
    contents = []
    image_list = _find_first_key(raw_data, "imageList")
    if isinstance(image_list, list) and image_list:
        for entry in image_list:
            if not isinstance(entry, dict):
                continue
            candidates = _xhs_image_candidates(entry)
            img_url = candidates[0] if candidates else ""
            live_url = ""
            if entry.get("livePhoto"):
                stream = entry.get("stream") or {}
                for codec in ("h264", "h265", "av1", "h266"):
                    arr = stream.get(codec) or []
                    if arr and isinstance(arr[0], dict) and (arr[0].get("masterUrl") or arr[0].get("backupUrl")):
                        live_url = _ensure_https(arr[0].get("masterUrl") or arr[0].get("backupUrl"))
                        break
                if not live_url:
                    for k in ("videoUrl", "livePhotoUrl", "streamUrl"):
                        if entry.get(k):
                            live_url = _ensure_https(entry[k])
                            break
            if live_url:
                # 实况照片: 归入实况视频区, 封面仅作缩略图 (下载时随视频保存)
                contents.append({"type": "live_video", "url": live_url, "fallback_urls": [], "thumbnail": img_url or cover_url, "cover_url": img_url, "cover_fallbacks": candidates[1:]})
            elif img_url:
                contents.append({"type": "image", "url": img_url, "fallback_urls": candidates[1:], "thumbnail": img_url})
    # 兜底: 非标准结构, 用通用收集
    if not contents:
        for u in collect_image_urls(raw_data):
            if u != cover_url:
                contents.append({"type": "image", "url": u, "fallback_urls": [], "thumbnail": u})
    return contents


def extract_meta(raw) -> dict:
    meta = {}
    if not isinstance(raw, dict):
        return meta
    for key in ("nickname", "author_name", "user_name"):
        v = raw.get(key)
        if isinstance(v, str) and v.strip():
            meta["作者"] = v.strip()[:30]
            break
    else:
        u = raw.get("author") or raw.get("user")
        if isinstance(u, dict):
            for key in ("nickname", "name"):
                v = u.get(key)
                if isinstance(v, str) and v.strip():
                    meta["作者"] = v.strip()[:30]
                    break
    for key in ("duration", "video_duration"):
        v = raw.get(key)
        if isinstance(v, (int, float)) and v > 0:
            meta["时长"] = f"{int(v // 60)}:{int(v % 60):02d}"
            break
        if isinstance(v, str) and v.strip().isdigit() and int(v) > 0:
            t = int(v)
            meta["时长"] = f"{t // 60}:{t % 60:02d}"
            break
    return meta


def serialize_info(info) -> dict:
    download_url = vget(info, "download_url") or ""
    audio_url = vget(info, "audio_download_url") or ""
    cover = vget(info, "cover_url") or ""
    raw = vget(info, "raw_data") or {}
    ext = (vget(info, "ext") or "").lower()
    kind, images, live_videos, contents = "video", [], [], []
    if download_url or audio_url:
        # 有视频直链 → 视频类型 (视频为默认下载类型, 优先于图集)
        kind = "video"
    else:
        # 图集: 静态图片与实况视频分区
        contents = extract_album_contents(raw, cover)
        images = [c["url"] for c in contents if c["type"] == "image"]
        live_videos = [c["url"] for c in contents if c["type"] == "live_video"]
        if contents:
            kind = "album"
    return {
        "title": (vget(info, "title") or "").strip() or "(无标题)",
        "cover_url": cover,
        "download_url": download_url,
        "audio_download_url": audio_url,
        "ext": ext,
        "identifier": vget(info, "identifier") or "",
        "source": vget(info, "source") or "",
        "kind": kind,
        "images": images,
        "live_videos": live_videos,
        "contents": contents,
        "meta": extract_meta(raw if isinstance(raw, dict) else {}),
        "formats": [dict(f) for f in (vget(info, "formats") or []) if isinstance(f, dict) and f.get("video_url")],
    }

# ============ 按平台路由的智能解析 (缩短抖音/小红书解析耗时) ============


def _client_cfg(name: str) -> dict:
    cfg = {"type": name, "work_dir": str(DOWNLOAD_DIR)}
    ov = build_requests_overrides().get(name) or {}
    if ov.get("cookies"):
        cfg["default_parse_cookies"] = ov["cookies"]
        cfg["default_download_cookies"] = ov["cookies"]
        cfg["default_search_cookies"] = ov["cookies"]
    return cfg


def _infos_valid(infos) -> bool:
    for info in (infos or []):
        s = serialize_info(info)
        if s["download_url"] or s["audio_download_url"] or s["images"] or s["live_videos"]:
            return True
    return False


def smart_parse(client, url: str):
    """按平台优先级尝试解析器, 全部失败再走库的完整解析链兜底"""
    key = detect_platform_key(url)
    priority = PLATFORM_PARSER_PRIORITY.get(key)
    if not priority:
        return client.parsefromurl(url)
    from videodl.modules import BuildCommonVideoClient, BuildVideoClient, VideoClientBuilder
    native = PLATFORM_NATIVE.get(key)
    order = ([native] if native else []) + list(priority)
    overrides = build_requests_overrides()
    for name in order:
        try:
            if name in VideoClientBuilder.REGISTERED_MODULES:
                inst = BuildVideoClient(_client_cfg(name))
            else:
                inst = BuildCommonVideoClient(_client_cfg(name))
            infos = inst.parsefromurl(url, request_overrides=overrides.get(name) or {})
        except Exception:
            continue
        if _infos_valid(infos):
            return infos
    # 优先解析器全部失败, 走完整链兜底 (覆盖其他平台与未知站点)
    return client.parsefromurl(url)


# ============ 解析结果缓存 (避免下载时重复解析, 加快下载启动) ============
parse_cache: dict = {}
PARSE_CACHE_TTL = 1800  # 30 分钟
parse_cache_lock = threading.Lock()


def cache_parse(url: str, infos: list) -> str:
    parse_id = uuid.uuid4().hex[:12]
    with parse_cache_lock:
        # 清理过期缓存
        now = time.time()
        for pid in [p for p, v in parse_cache.items() if now - v["time"] > PARSE_CACHE_TTL]:
            parse_cache.pop(pid, None)
        parse_cache[parse_id] = {"url": url, "infos": infos, "time": now}
    return parse_id


def get_cached_parse(parse_id, url: str):
    if not parse_id:
        return None
    with parse_cache_lock:
        cached = parse_cache.get(parse_id)
    if cached and cached["url"] == url and time.time() - cached["time"] <= PARSE_CACHE_TTL:
        return cached["infos"]
    return None


def apply_format(client, info, format_id: str):
    """按用户选择的清晰度构造下载用的 VideoInfo (B站等平台会刷新新鲜链接)"""
    fmts = vget(info, "formats") or []
    fmt = next((f for f in fmts if str(f.get("id")) == str(format_id)), None)
    if not fmt:
        return info
    new_info = copy.deepcopy(info)
    # 尝试刷新新鲜链接 (B站 CDN 链接默认约2小时过期)
    ctx = vget(info, "format_ctx")
    refreshed = None
    if ctx:
        bili = None
        for name, c in (getattr(client, "video_clients", None) or {}).items():
            if name == "BilibiliVideoClient":
                if isinstance(c, dict):
                    from videodl.modules import BuildVideoClient
                    c = BuildVideoClient(module_cfg=c["cfg"])
                bili = c
        if bili is not None and hasattr(bili, "refreshformat"):
            refreshed = bili.refreshformat(ctx, str(format_id))
    video_url = (refreshed or {}).get("video_url") or fmt.get("video_url") or ""
    audio_url = (refreshed or {}).get("audio_url") or fmt.get("audio_url") or ""
    if not video_url:
        return info
    title = (vget(info, "title") or "video").strip()
    label = str(fmt.get("label") or fmt.get("id") or "").strip()
    new_title = f"{title} [{label}]" if label else title
    ext = (refreshed or {}).get("ext") or vget(info, "ext") or "mp4"
    source = vget(info, "source") or "Video"
    new_info["download_url"] = video_url
    new_info["ext"] = ext
    new_info["title"] = new_title
    new_info["save_path"] = os.path.join(DOWNLOAD_DIR, source, f"{new_title}.{ext}")
    if audio_url:
        new_info["audio_download_url"] = audio_url
        audio_ext = vget(info, "audio_ext") or "m4a"
        new_info["audio_ext"] = audio_ext
        new_info["audio_save_path"] = os.path.join(DOWNLOAD_DIR, source, f"{new_title}.audio.{audio_ext}")
    else:
        new_info["audio_download_url"] = ""
        new_info["audio_save_path"] = ""
    return new_info


# ============ 图集下载 (库本身仅支持视频, 图片笔记由后端自行下载) ============
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".heic", ".bmp")


def sanitize_filename(name: str, fallback: str = "未命名") -> str:
    name = re.sub(r'[\\/:*?"<>|\r\n\t]+', "_", str(name)).strip().strip(".")
    return (name or fallback)[:80]


def download_album(task: dict, url: str, index: int, infos: list, mode: str = "images", indices=None) -> None:
    """下载图集内容: mode=images 仅静态图 / live_videos 仅实况视频 / selected 按 contents 下标"""
    valid = [i for i in infos if serialize_info(i)["images"] or serialize_info(i)["live_videos"] or vget(i, "download_url")]
    if not valid:
        raise RuntimeError("未解析到图集内容")
    target = valid[index] if 0 <= index < len(valid) else valid[0]
    s = serialize_info(target)
    contents = s["contents"]
    if not contents:
        raise RuntimeError("未找到图集内容")
    if mode == "images":
        selected = [c for c in contents if c["type"] == "image"]
        subdir, prefix, ext_default = "图片", "IMG", ".jpg"
    elif mode == "live_videos":
        selected = [c for c in contents if c["type"] == "live_video"]
        subdir, prefix, ext_default = "实况视频", "LIVE", ".mp4"
    elif mode == "selected" and indices:
        selected = [contents[i] for i in indices if 0 <= i < len(contents)]
        subdir, prefix, ext_default = "选中", "SEL", None
    else:
        selected = list(contents)
        subdir, prefix, ext_default = "全部", "ALL", None
    if not selected:
        raise RuntimeError(f"没有可下载的{'实况视频' if mode == 'live_videos' else '图片'}")
    title = sanitize_filename(s["title"])
    save_dir = DOWNLOAD_DIR / (s["source"] or "Album") / title / subdir
    save_dir.mkdir(parents=True, exist_ok=True)
    parsed = urlparse(url)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36",
        "Referer": f"{parsed.scheme}://{parsed.netloc}/",
    }
    saved, failed = [], []
    total = len(selected)

    def fetch_to_file(urls, dst, timeout=60):
        """依次尝试候选 URL 下载到目标文件, 成功返回 True"""
        for u in urls:
            if not u:
                continue
            try:
                with requests.get(u, headers=headers, timeout=timeout, stream=True) as r:
                    r.raise_for_status()
                    with open(dst, "wb") as fp:
                        for chunk in r.iter_content(chunk_size=256 * 1024):
                            if chunk:
                                fp.write(chunk)
                return True
            except Exception:
                continue
        return False

    for i, item in enumerate(selected):
        item_url = item.get("url") or ""
        if not item_url:
            continue
        ext = os.path.splitext(urlparse(item_url).path)[1].lower()
        if ext not in IMAGE_EXTS and ext != ".mp4":
            ext = ext_default or (".mp4" if item.get("type") == "live_video" else ".jpg")
        dst = save_dir / f"{prefix}_{i + 1:03d}{ext}"
        urls = [item_url] + [u for u in (item.get("fallback_urls") or []) if u]
        ok = False
        for attempt in range(2):
            if fetch_to_file(urls, dst):
                ok = True
                break
            time.sleep(1.2 * (attempt + 1))
        if ok and item.get("type") == "live_video":
            dst = ensure_mp4_output(dst, task)  # 实况视频同样统一为 MP4
            task["message"] = f"{subdir}下载中 {i + 1}/{total}"
        (saved if ok else failed).append(str(dst))
        # 实况视频: 随附保存静态封面 (Live Photo 的完整两部分)
        cover = item.get("cover_url") or ""
        if ok and cover:
            cext = os.path.splitext(urlparse(cover).path)[1].lower()
            if cext not in IMAGE_EXTS:
                cext = ".jpg"
            cdst = save_dir / f"{prefix}_{i + 1:03d}_cover{cext}"
            if fetch_to_file([cover] + [u for u in (item.get("cover_fallbacks") or []) if u], cdst):
                saved.append(str(cdst))
        task["message"] = f"{subdir}下载中 {i + 1}/{total}"
        time.sleep(0.3)  # 轻微间隔, 避免 CDN 限流
    if not saved:
        raise RuntimeError(f"下载失败: {len(selected)} 个文件全部失败")
    task["save_path"] = saved[0]
    task["all_paths"] = saved
    task["filename"] = Path(saved[0]).name
    try:
        task["bytes"] = Path(saved[0]).stat().st_size
    except Exception:
        task["bytes"] = 0
    task["status"] = "done"
    task["finished"] = time.time()
    if failed:
        task["message"] = f"完成 {len(saved)} 个, 失败 {len(failed)} 个"


# ============ 统一输出 MP4 (MP4 兼容性最好: 播放器/剪辑/手机/微信 均可直接打开) ============
MP4_CONTAINER_TAGS = {"mp4", "mov", "m4a", "3gp", "3g2", "mj2"}
# MP4 中被广泛支持的编码 (Windows/手机/剪辑软件通用); 其余编码需转码才能真正"通用"
MP4_SAFE_VIDEO_CODECS = {"h264", "hevc", "h265", "mpeg4", "mpeg1video", "mpeg2video", "mjpeg"}
MP4_SAFE_AUDIO_CODECS = {"aac", "mp3", "mp2", "ac3", "eac3", "alac"}


def safe_remove(path) -> None:
    try:
        Path(path).unlink()
    except Exception:
        pass


def probe_media(path) -> dict:
    """探测容器类型与是否含视频流
    说明: 工具只提供 ffmpeg 静态二进制 (无 ffprobe), 故解析 `ffmpeg -i` 的日志输出"""
    result = {"format": "", "has_video": False, "video_codec": "", "audio_codec": ""}
    if not FFMPEG_PATH or not Path(path).is_file():
        return result
    try:
        proc = subprocess.run(
            [FFMPEG_PATH, "-hide_banner", "-i", str(path)],
            capture_output=True, text=True, encoding="utf-8", errors="ignore", timeout=90,
        )
        err = proc.stderr or ""
    except Exception:
        return result
    m = re.search(r"Input #0,\s*([^,]+(?:,[^,]+)*?),\s*from", err)
    if m:
        result["format"] = m.group(1).strip().lower()
    result["has_video"] = bool(re.search(r"Stream #\d+:\d+[^:]*:\s*Video:", err))
    mv = re.search(r"Stream #\d+:\d+[^:]*:\s*Video:\s*([a-z0-9_]+)", err)
    if mv:
        result["video_codec"] = mv.group(1).strip().lower()
    ma = re.search(r"Stream #\d+:\d+[^:]*:\s*Audio:\s*([a-z0-9_]+)", err)
    if ma:
        result["audio_codec"] = ma.group(1).strip().lower()
    return result


def is_mp4_container(path) -> bool:
    """先按文件头快速判断 (MP4/MOV 第 5~8 字节为 ftyp), 再退回 ffmpeg 探测"""
    try:
        with open(path, "rb") as fp:
            head = fp.read(12)
    except Exception:
        return False
    if len(head) >= 8 and head[4:8] == b"ftyp":
        return True
    fmt = probe_media(path)["format"]
    return bool(fmt) and bool(set(fmt.split(",")) & MP4_CONTAINER_TAGS)


TRANSCODE_VIDEO_ARGS = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p"]
TRANSCODE_AUDIO_ARGS = ["-c:a", "aac", "-b:a", "192k"]


def convert_to_mp4(src: Path, task: dict | None = None, video_codec: str = "", audio_codec: str = "") -> Path | None:
    """转为 MP4:
    - 编码已被 MP4 广泛支持 -> 无损重封装 (秒级完成, 画质零损失)
    - 编码不通用 (如 VP9/Opus/Theora) -> 转码为 H.264 + AAC (兼容播放器/剪辑软件/手机)"""
    if not FFMPEG_PATH:
        return None
    dst = src.with_suffix(".mp4")
    if dst.resolve() == src.resolve():
        dst = src.with_name(f"{src.stem}_mp4.mp4")
    v_ok = (not video_codec) or video_codec in MP4_SAFE_VIDEO_CODECS
    a_ok = (not audio_codec) or audio_codec in MP4_SAFE_AUDIO_CODECS
    attempts: list[tuple[str, list]] = []
    if v_ok and a_ok:
        attempts.append(("重封装", ["-c", "copy"]))
        attempts.append(("重封装+音频修正", ["-c", "copy", "-bsf:a", "aac_adtstoasc"]))
    label = "兼容转码" + ("" if v_ok else "+H.264") + ("" if a_ok else "+AAC")
    attempts.append((label, (["-c:v", "copy"] if v_ok else list(TRANSCODE_VIDEO_ARGS))
                     + (["-c:a", "copy"] if a_ok else list(TRANSCODE_AUDIO_ARGS))))
    attempts.append(("强制转码", list(TRANSCODE_VIDEO_ARGS) + list(TRANSCODE_AUDIO_ARGS)))
    for lbl, extra in attempts:
        if task is not None:
            task["message"] = f"转为 MP4（{lbl}）"
        safe_remove(dst)
        cmd = [FFMPEG_PATH, "-y", "-hide_banner", "-loglevel", "error", "-i", str(src),
               "-map", "0:v:0?", "-map", "0:a:0?", *extra, "-movflags", "+faststart", str(dst)]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore", timeout=7200)
        except Exception:
            continue
        if proc.returncode == 0 and dst.is_file() and dst.stat().st_size > 0:
            return dst
    safe_remove(dst)
    return None


def ensure_mp4_output(path, task: dict | None = None) -> Path:
    """确保最终产物是 MP4; 已是 MP4 / 纯音频 / 转换失败时保持原文件不动"""
    path = Path(path)
    if OUTPUT_FORMAT != "mp4" or not path.is_file():
        return path
    if path.suffix.lower() == ".mp4" and is_mp4_container(path):
        return path
    if not FFMPEG_PATH:
        if task is not None:
            task["message"] = "未找到 FFmpeg，保留平台原始格式"
        return path
    probe = probe_media(path)
    if not probe["has_video"]:
        return path  # 纯音频文件不强行改容器
    dst = convert_to_mp4(path, task, probe["video_codec"], probe["audio_codec"])
    if dst is None:
        if task is not None:
            task["message"] = "MP4 转换失败，保留平台原始格式"
        return path
    try:
        src_size = path.stat().st_size
        if src_size > 0 and dst.stat().st_size < src_size * 0.05:
            raise ValueError("输出体积异常")
    except Exception:
        safe_remove(dst)
        if task is not None:
            task["message"] = "MP4 转换异常，保留平台原始格式"
        return path
    if not KEEP_ORIGINAL_AFTER_REMUX:
        safe_remove(path)
    return dst


def locate_downloaded_file(info, title_hint: str = "") -> Path | None:
    """定位库实际落盘的文件 (库可能对重名文件追加 (1) 之类的后缀)"""
    p = Path(vget(info, "save_path") or "")
    if p.is_file():
        return p
    stem = sanitize_filename(title_hint or vget(info, "title") or "")
    parent = p.parent
    if not stem or not parent.is_dir():
        return None
    prefix = stem[:30]
    cands = [f for f in parent.iterdir() if f.is_file() and f.stem[:len(prefix)] == prefix]
    return max(cands, key=lambda f: f.stat().st_mtime) if cands else None


# ============ FastAPI 应用 ============
app = FastAPI(title="视频解析下载工具", docs_url=None, redoc_url=None)

download_sem = asyncio.Semaphore(max(1, int(CONFIG.get("max_concurrent_downloads", 2))))
tasks: dict = {}
tasks_lock = threading.Lock()


class ParseRequest(BaseModel):
    url: str


class DownloadRequest(BaseModel):
    url: str
    index: int = 0
    format_id: str | None = None
    parse_id: str | None = None
    album_mode: str | None = None      # images / live_videos / selected
    album_indices: list | None = None  # selected 模式下的 contents 下标


class RevealRequest(BaseModel):
    path: str


def _require_lib():
    if LIB_ERROR or VideoClient is None:
        raise HTTPException(status_code=503, detail=f"解析库未就绪: {LIB_ERROR or '未知错误'}")


@app.get("/", response_class=HTMLResponse)
async def api_index():
    if not FRONTEND_FILE.is_file():
        return HTMLResponse("<h1>前端文件缺失: frontend/index.html</h1>", status_code=500)
    return FRONTEND_FILE.read_text(encoding="utf-8")


@app.get("/api/health")
async def api_health():
    return {
        "ok": LIB_ERROR is None,
        "app_version": APP_VERSION,
        "version": LIB_VERSION,
        "ffmpeg": bool(FFMPEG_PATH),
        "ffmpeg_path": FFMPEG_PATH or "",
        "download_dir": str(DOWNLOAD_DIR),
        "clients": len(CLIENT_NAMES),
        "output_format": OUTPUT_FORMAT,
        "error": LIB_ERROR,
        "addresses": server_addresses(),
    }


# ============ 缩略图代理 ============
# 图床（小红书 / 抖音 / B站 等）会校验 Referer 与 UA，浏览器直接 <img src> 常被 403，
# 表现就是卡片一片黑。这里由后端带同样的头部取图再回传，前端只连本机。
THUMB_TIMEOUT = 15
THUMB_MAX_BYTES = 8 * 1024 * 1024
THUMB_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36")

# 图床 Referer 映射: 必须填「站点来源」, 绝不能填图床自身域名。
# 实测小红书 sns-img-qc.xhscdn.com: Referer=自身域名 → 403; Referer=www.xiaohongshu.com 或不带 → 正常。
THUMB_REFERERS = (
    ("xhscdn.com", "https://www.xiaohongshu.com/"),
    ("xiaohongshu.com", "https://www.xiaohongshu.com/"),
    ("douyinpic.com", "https://www.douyin.com/"),
    ("douyin.com", "https://www.douyin.com/"),
    ("byteimg.com", "https://www.douyin.com/"),
    ("toutiaoimg.com", "https://www.toutiao.com/"),
    ("pstatp.com", "https://www.toutiao.com/"),
    ("hdslb.com", "https://www.bilibili.com/"),
    ("bilibili.com", "https://www.bilibili.com/"),
    ("sinaimg.cn", "https://weibo.com/"),
    ("qpic.cn", "https://mp.weixin.qq.com/"),
    ("pipix.com", "https://www.pipix.com/"),
    ("kuaishou.com", "https://www.kuaishou.com/"),
)


def thumb_referer(url: str) -> str:
    """按图床域名挑站点 Referer; 未收录的域名返回空串 (宁可不带, 也不自引用)。"""
    host = (urlparse(url).hostname or "").lower()
    for suffix, ref in THUMB_REFERERS:
        if host == suffix or host.endswith("." + suffix):
            return ref
    return ""


def thumb_url_allowed(url: str) -> bool:
    """只放行公网 http/https 地址: 解析域名后逐个校验 IP, 挡掉本机与内网 (防 SSRF)。"""
    try:
        p = urlparse(url)
    except Exception:
        return False
    if p.scheme not in ("http", "https") or not p.hostname:
        return False
    host = p.hostname.lower()
    if host in ("localhost", "localhost.localdomain") or host.endswith((".local", ".internal")):
        return False
    try:
        infos = socket.getaddrinfo(host, None)
    except Exception:
        return False
    for info in infos:
        try:
            addr = ipaddress.ip_address(info[4][0])
        except ValueError:
            return False
        if (addr.is_private or addr.is_loopback or addr.is_link_local
                or addr.is_reserved or addr.is_multicast or addr.is_unspecified):
            return False
    return True


@app.get("/api/thumb")
async def api_thumb(url: str = ""):
    """缩略图代理: 带 Referer/UA 抓取外链图片, 规避图床防盗链。"""
    u = (url or "").strip()
    if not u:
        raise HTTPException(status_code=400, detail="缺少 url 参数")
    if not thumb_url_allowed(u):
        raise HTTPException(status_code=400, detail="不允许获取该地址（仅支持公网 http/https 图片）")

    def fetch():
        base = {
            "User-Agent": THUMB_UA,
            "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }

        def load(headers):
            with requests.get(u, headers=headers, timeout=THUMB_TIMEOUT, stream=True) as r:
                r.raise_for_status()
                ctype = (r.headers.get("Content-Type") or "").split(";")[0].strip().lower()
                if not ctype.startswith("image/"):
                    raise ValueError(f"响应不是图片: {ctype or '未知类型'}")
                buf = bytearray()
                for chunk in r.iter_content(chunk_size=64 * 1024):
                    if chunk:
                        buf.extend(chunk)
                        if len(buf) > THUMB_MAX_BYTES:
                            raise ValueError("图片超出 8MB 上限")
                return bytes(buf), ctype

        # 先按站点来源带 Referer, 再退到不带 Referer; 任一成功即可
        ref = thumb_referer(u)
        attempts = [{**base, "Referer": ref}] if ref else []
        attempts.append(dict(base))
        last = None
        for hdr in attempts:
            try:
                return load(hdr)
            except Exception as e:  # noqa: BLE001 - 逐个候选头部重试, 保留最后一个错误
                last = e
        raise last if last else RuntimeError("缩略图获取失败")

    try:
        data, ctype = await asyncio.to_thread(fetch)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"缩略图获取失败: {type(e).__name__}: {e}")
    return Response(
        content=data,
        media_type=ctype,
        headers={"Cache-Control": "public, max-age=86400"},
    )


@app.post("/api/parse")
async def api_parse(req: ParseRequest):
    _require_lib()
    url = extract_url(req.url) or (req.url or "").strip()
    if not url.lower().startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="请提供有效的视频链接（需以 http/https 开头）")
    try:
        return await asyncio.to_thread(parse_sync, url)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"解析出错: {type(e).__name__}: {e}")


def parse_sync(url: str) -> dict:
    client = make_client()
    infos = smart_parse(client, url) or []
    items, errors = [], []
    for info in infos:
        s = serialize_info(info)
        if s["download_url"] or s["audio_download_url"] or s["images"] or s["live_videos"]:
            items.append(s)
        else:
            err = vget(info, "err_msg")
            if err:
                errors.append(str(err)[:120])
    if not items:
        detail = "未解析到可下载的视频地址（链接无效或平台接口已变化）"
        if errors:
            detail += "：" + "; ".join(errors[:3])
        return {"ok": False, "detail": detail, "platform": detect_platform(url), "items": []}
    # 缓存原始 VideoInfo, 供下载时直接使用 (避免重复解析)
    valid_infos = [i for i in infos if serialize_info(i)["download_url"] or serialize_info(i)["audio_download_url"] or serialize_info(i)["images"] or serialize_info(i)["live_videos"]]
    parse_id = cache_parse(url, valid_infos)
    return {"ok": True, "platform": detect_platform(url), "items": items, "parse_id": parse_id}


@app.post("/api/download")
async def api_download(req: DownloadRequest):
    _require_lib()
    url = extract_url(req.url) or (req.url or "").strip()
    if not url.lower().startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="请提供有效的视频链接")
    task_id = uuid.uuid4().hex[:12]
    with tasks_lock:
        tasks[task_id] = {
            "id": task_id, "url": url, "status": "queued",
            "created": time.time(), "finished": None,
        }
    asyncio.create_task(download_worker(task_id, url, max(req.index, 0), req.format_id, req.parse_id, req.album_mode, req.album_indices))
    return {"ok": True, "task_id": task_id}


async def download_worker(task_id: str, url: str, index: int, format_id: str | None = None, parse_id: str | None = None,
                          album_mode: str | None = None, album_indices: list | None = None):
    async with download_sem:
        await asyncio.to_thread(download_sync, task_id, url, index, format_id, parse_id, album_mode, album_indices)


def download_sync(task_id: str, url: str, index: int, format_id: str | None = None, parse_id: str | None = None,
                  album_mode: str | None = None, album_indices: list | None = None):
    task = tasks.get(task_id)
    if not task:
        return
    try:
        task["status"] = "parsing"
        client = make_client()
        # 优先使用解析缓存, 避免重复解析 (加快下载启动)
        infos = get_cached_parse(parse_id, url)
        if infos is None:
            infos = smart_parse(client, url) or []
        valid = []
        for info in infos:
            s = serialize_info(info)
            if s["download_url"] or s["audio_download_url"] or s["images"] or s["live_videos"]:
                valid.append((info, s))
        if not valid:
            raise RuntimeError("未解析到可下载的媒体地址（平台接口可能已变化或链接无效）")
        # 图集: 库不支持图片下载, 走后端自带逻辑 (支持按类型/下标选择)
        if 0 <= index < len(valid) and valid[index][1]["kind"] == "album":
            task["status"] = "downloading"
            task["filename"] = valid[index][1]["title"]
            download_album(task, url, index, [i for i, _ in valid], album_mode or "images", album_indices)
            return
        # 视频只下载指定分集
        if 0 <= index < len(valid):
            selected = [valid[index][0]]
        else:
            selected = [i for i, _ in valid]
        # 应用用户选择的清晰度 (B站等平台会刷新新鲜链接)
        if format_id:
            selected = [apply_format(client, i, format_id) for i in selected]
        task["status"] = "downloading"
        task["filename"] = vget(selected[0], "title") or url
        client.download(selected)
        saved = []
        for info in selected:
            p = locate_downloaded_file(info, vget(selected[0], "title") or "")
            if p:
                saved.append(p)
        if not saved:
            raise RuntimeError("下载流程结束，但未在输出目录找到文件")
        # 统一输出为 MP4 (FLV/MKV/WebM/TS 等容器统一重封装, 不兼容时再转码)
        final_paths = []
        converted = False
        for p in saved:
            new_p = ensure_mp4_output(p, task)
            if new_p != p:
                converted = True
            final_paths.append(str(new_p))
        saved = final_paths
        if converted:
            task["message"] = "已统一输出为 MP4"
        task["save_path"] = saved[0]
        task["all_paths"] = saved
        task["filename"] = Path(saved[0]).name
        try:
            task["bytes"] = Path(saved[0]).stat().st_size
        except Exception:
            task["bytes"] = 0
        task["status"] = "done"
        task["finished"] = time.time()
    except Exception as e:
        task["status"] = "error"
        task["error"] = f"{type(e).__name__}: {e}"
        task["finished"] = time.time()


@app.get("/api/tasks/{task_id}")
async def api_task(task_id: str):
    task = tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在或已过期")
    keys = ("id", "status", "filename", "save_path", "all_paths", "bytes", "error", "message", "created", "finished")
    return {k: task.get(k) for k in keys}


@app.get("/api/file/{task_id}")
async def api_file(task_id: str):
    task = tasks.get(task_id)
    if not task or task.get("status") != "done":
        raise HTTPException(status_code=404, detail="文件不存在或任务未完成")
    path = Path(task.get("save_path") or "")
    if not path.is_file():
        raise HTTPException(status_code=404, detail="文件已被移动或删除")
    resp = FileResponse(path, media_type="application/octet-stream", filename=path.name)
    # 中文文件名在 iOS Safari / 部分安卓浏览器上需要 RFC 5987 编码, 否则会显示成乱码
    ascii_name = path.name.encode("ascii", "ignore").decode("ascii") or "download"
    resp.headers["Content-Disposition"] = f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(path.name)}"
    resp.headers["Cache-Control"] = "no-cache"
    return resp


@app.get("/api/qrcode")
async def api_qrcode(text: str = ""):
    """生成二维码 SVG (手机扫码访问用), 需要 segno; 未安装时返回 404 由前端降级为文本提示"""
    if not text or not text.lower().startswith("http"):
        raise HTTPException(status_code=400, detail="需要 http(s) 链接")
    try:
        import io
        import segno
    except ImportError:
        raise HTTPException(status_code=404, detail="未安装二维码库 (pip install segno)")
    # 注意: segno 的 SVG writer 即使传入文本流也写 bytes, 故用 BytesIO 再解码
    buf = io.BytesIO()
    segno.make(text, error="m").save(buf, kind="svg", scale=6, border=2, dark="#0d1117", light="#ffffff")
    return Response(content=buf.getvalue().decode("utf-8"), media_type="image/svg+xml")


@app.post("/api/reveal")
async def api_reveal(req: RevealRequest, request: Request):
    # 在资源管理器里定位文件只对本机有意义, 手机等局域网设备请求时直接拒绝
    client_host = (request.client.host if request.client else "") or ""
    if client_host and client_host not in LOOPBACK_HOSTS:
        raise HTTPException(status_code=403, detail="「打开文件夹」仅在本机可用")
    p = Path(req.path or "").resolve()
    if not str(p).startswith(str(BASE.resolve())):
        raise HTTPException(status_code=403, detail="为安全起见，仅允许打开工具目录内的文件")
    if not p.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    try:
        if os.name == "nt":
            subprocess.Popen(["explorer", "/select,", str(p)])
        else:
            subprocess.Popen(["xdg-open", str(p.parent)])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"打开文件夹失败: {e}")
    return {"ok": True}

# ============ 启动 ============


def main():
    host = str(CONFIG.get("host", "127.0.0.1"))
    port = int(CONFIG.get("port", 8000))
    addrs = server_addresses()
    print("=" * 60)
    print("  视频解析下载工具 (基于开源库 videodl)")
    print("=" * 60)
    print(f"  解析库版本 : {LIB_VERSION or '未就绪'} ({len(CLIENT_NAMES)} 个平台客户端)")
    print(f"  FFmpeg     : {FFMPEG_PATH or '未找到 (HLS/DASH 下载可能失败)'}")
    print(f"  下载目录   : {DOWNLOAD_DIR}")
    print(f"  本机访问   : {addrs['local']}")
    if addrs["lan_enabled"]:
        if addrs["lan"]:
            print("  局域网访问  : (手机与电脑需连接同一个 Wi-Fi)")
            for u in addrs["lan"]:
                print(f"      {u}")
        else:
            print("  局域网访问  : 已开启，但未探测到局域网 IP")
        print("  提示       : 若手机打不开，多半是 Windows 防火墙拦截，")
        print("               右键以管理员身份运行 allow_lan.bat 放行端口")
    else:
        print("  局域网访问  : 已关闭 (config.json 的 lan_access / host)")
    print("  停止服务   : 关闭本窗口或按 Ctrl+C")
    print("=" * 60)
    if CONFIG.get("open_browser", True):
        # 0.0.0.0 不能直接用于浏览器地址栏, 统一用回环地址打开
        open_url = addrs["local"]
        threading.Timer(1.5, lambda: webbrowser.open(open_url)).start()
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
