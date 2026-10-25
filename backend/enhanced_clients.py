"""
增强客户端模块
在不修改 videodl 库本身的前提下, 通过注册表注入增强解析器:
  1. EnhancedBilibiliVideoClient — B站 UGC 视频枚举可用清晰度(qn), 番剧暴露 DASH 格式列表, 支持下载指定格式
  2. reorder_common_clients — 将实测可用的通用解析器(GV/SnapWC)提到优先位置, 缩短抖音/小红书的兜底解析耗时
"""
import copy
import json
import os
import re
from contextlib import suppress
from urllib.parse import parse_qs, urlparse

import requests

from videodl.modules import CommonVideoClientBuilder, VideoClientBuilder
from videodl.modules.sources.base import BaseVideoClient
from videodl.modules.sources.bilibili import BilibiliVideoClient
from videodl.modules.sources.rednote import RednoteVideoClient
from videodl.modules.utils import (
    VideoInfo,
    FileTypeSniffer,
    legalizestring,
    resp2json,
    safeextractfromdict,
    taskprogress,
    yieldtimerelatedtitle,
    useparseheaderscookies,
)

# B站清晰度对照表 (qn -> 中文label), 接口未返回描述时使用
BILIBILI_QN_LABELS = {
    6: "240P 极速", 16: "360P 流畅", 32: "480P 清晰", 64: "720P 高清",
    74: "720P60 高帧率", 80: "1080P 高清", 112: "1080P+ 高码率", 116: "1080P60 高帧率",
    120: "4K 超清", 125: "HDR 真彩", 126: "杜比视界", 127: "8K 超高清", 300: "杜比全景声",
}

# 通用解析器优先级 (实测可用; 其余保持原有顺序在后兜底)
COMMON_CLIENT_PRIORITY = ["GVVideoClient", "SnapWCVideoClient"]


def _ext_from_url(url: str, default: str = "mp4") -> str:
    m = re.search(r"\.(mp4|flv|m4v|mkv|webm)(?:\?|$)", url or "", re.I)
    return m.group(1).lower() if m else default


class EnhancedBilibiliVideoClient(BilibiliVideoClient):
    """B站增强: 多清晰度枚举 + 格式选择 + 下载前链接刷新"""

    source = "BilibiliVideoClient"

    # ---------- 工具 ----------
    def _playurl(self, bvid: str, cid, qn: int, request_overrides: dict = None) -> dict:
        """UGC 旧版 playurl 接口 (无需签名, qn 控制清晰度, 不可用时自动降级)"""
        resp = self.get(
            f"https://api.bilibili.com/x/player/playurl?otype=json&fnver=0&fnval=0&qn={qn}"
            f"&bvid={bvid}&cid={cid}&platform=html5",
            **(request_overrides or {}),
        )
        resp.raise_for_status()
        return resp2json(resp=resp)

    def _build_ugc_formats(self, bvid: str, cid, request_overrides: dict = None) -> tuple[list, dict, dict]:
        """枚举该视频实际可用的清晰度, 返回 (formats, 首个响应数据, 上下文)"""
        first = self._playurl(bvid, cid, 120, request_overrides)  # 请求最高清, 接口自动降级到可用最高
        # UGC playurl 响应结构: {code, message, data: {accept_quality, durl, ...}}
        payload = first.get("data") if isinstance(first.get("data"), dict) else first
        accept_quality = [q for q in (payload.get("accept_quality") or []) if isinstance(q, int)]
        if not accept_quality:
            accept_quality = [payload.get("quality") or 80]
        accept_desc = dict(zip(payload.get("accept_quality") or [], payload.get("accept_description") or []))
        formats, got = [], {}
        for qn in accept_quality:
            data = payload if payload.get("quality") == qn else (self._playurl(bvid, cid, qn, request_overrides).get("data") or {})
            durl = data.get("durl") or []
            if not durl:
                continue
            best = max(durl, key=lambda x: x.get("size", 0))
            got[qn] = best
            formats.append({
                "id": str(qn),
                "label": accept_desc.get(qn) or BILIBILI_QN_LABELS.get(qn, f"qn{qn}"),
                "width": best.get("width") or 0,
                "height": best.get("height") or 0,
                "filesize": best.get("size", 0),
                "video_url": best.get("url") or "",
                "audio_url": "",
                "codec": "",
                "fps": best.get("frame_rate") or 0,
            })
        formats.sort(key=lambda f: int(f["id"]), reverse=True)  # 高清晰度在前
        ctx = {"type": "ugc", "bvid": bvid, "cid": cid}
        return formats, first, ctx

    def _build_dash_formats(self, page_raw_data: dict) -> tuple[list, str, str]:
        """从 DASH 响应提取视频格式列表与最佳音频, 返回 (formats, audio_url, audio_ext_hint)"""
        dash = safeextractfromdict(page_raw_data, ["result", "video_info", "dash"], None) \
            or safeextractfromdict(page_raw_data, ["data", "dash"], None) or {}
        videos = dash.get("video") or []
        audios = (safeextractfromdict(dash, ["dolby", "audio"], []) or []) + (dash.get("audio") or [])
        accept_desc = dict(zip(page_raw_data.get("accept_quality") or [], page_raw_data.get("accept_description") or []))
        # 每个清晰度取一个编码 (优先 AVC 兼容性)
        by_quality = {}
        for v in videos:
            if not isinstance(v, dict) or not (v.get("baseUrl") or v.get("base_url") or v.get("url")):
                continue
            qid = v.get("id")
            codecs = v.get("codecs") or ""
            if qid not in by_quality or ("avc1" in codecs and "avc1" not in (by_quality[qid].get("codecs") or "")):
                by_quality[qid] = v
        formats = []
        for qid, v in by_quality.items():
            formats.append({
                "id": str(qid),
                "label": accept_desc.get(qid) or BILIBILI_QN_LABELS.get(qid, f"qn{qid}"),
                "width": v.get("width") or 0,
                "height": v.get("height") or 0,
                "filesize": v.get("size") or 0,
                "video_url": v.get("baseUrl") or v.get("base_url") or v.get("url"),
                "audio_url": "",
                "codec": v.get("codecs") or "",
                "fps": v.get("frameRate") or 0,
            })
        formats.sort(key=lambda f: int(f["id"]) if str(f["id"]).isdigit() else 0, reverse=True)
        audio_url = ""
        if audios:
            best_audio = max((a for a in audios if isinstance(a, dict) and (a.get("baseUrl") or a.get("base_url") or a.get("url"))),
                             key=lambda a: a.get("size") or 0, default=None)
            if best_audio:
                audio_url = best_audio.get("baseUrl") or best_audio.get("base_url") or best_audio.get("url")
        for f in formats:
            f["audio_url"] = audio_url
        return formats, audio_url, "m4a"

    # ---------- UGC 普通视频 (覆盖库实现: 枚举清晰度) ----------
    def _parsefromcommonurl(self, url: str, request_overrides: dict = None):
        if not self.belongto(url=url):
            return []
        request_overrides, video_info, null_backup_title, video_infos = request_overrides or {}, VideoInfo(source=self.source), yieldtimerelatedtitle(self.source), []
        try:
            m = re.compile(r"https?://(?:www\.)?bilibili\.com/(?:video/|festival/[^/?#]+\?(?:[^#]*&)?bvid=)(?P<prefix>[aAbB][vV])(?P<id>[^/?#&]+)").match(url)
            video_id, prefix = m.group("id", "prefix")
            part_id = int(part_id[0]) if (part_id := parse_qs(urlparse(url).query, keep_blank_values=True).get("p", None)) and isinstance(part_id, list) and str(part_id[0]).lstrip("+-").isdigit() else None
            if prefix.upper() in ["BV"]:
                (resp := self.get(f"https://api.bilibili.com/x/web-interface/view?bvid=BV{video_id}", **request_overrides)).raise_for_status()
                raw_data = resp2json(resp=resp)
            elif prefix.upper() in ["AV"]:
                (resp := self.get(f"https://api.bilibili.com/x/web-interface/view?aid={video_id}", **request_overrides)).raise_for_status()
                video_id = (raw_data := resp2json(resp=resp))["data"]["bvid"]
            bvid = raw_data["data"]["bvid"]
            pages = raw_data["data"]["pages"]
            multi_part = len(pages) > 1
            with taskprogress(description="Parsing Bilibili Video", total=len(pages)) as progress:
                for video_idx, extracted_video_item in enumerate(pages):
                    if (part_id and video_idx + 1 != part_id) or (not isinstance(extracted_video_item, dict)):
                        progress.advance(1)
                        continue
                    cid = extracted_video_item["cid"]
                    formats, first, ctx = self._build_ugc_formats(bvid, cid, request_overrides)
                    if not formats:
                        progress.advance(1)
                        continue
                    page_raw_data = dict(first)
                    page_raw_data["x/web-interface/view"] = copy.deepcopy(raw_data)
                    best = formats[0]
                    download_url = best["video_url"]
                    payload = first.get("data") if isinstance(first.get("data"), dict) else first
                    video_title = legalizestring(
                        (f"EP{video_idx+1}-{extracted_video_item.get('part')}" if multi_part else safeextractfromdict(raw_data, ["data", "title"], None))
                        or null_backup_title, replace_null_string=null_backup_title,
                    ).removesuffix(".")
                    ext = _ext_from_url(download_url, payload.get("format") if payload.get("format") in ("mp4", "flv") else "mp4")
                    (video_page_info := copy.deepcopy(video_info)).update(dict(
                        raw_data=page_raw_data,
                        download_url=download_url,
                        title=video_title,
                        save_path=os.path.join(self.work_dir, self.source, f"{video_title}.{ext}"),
                        ext=ext,
                        identifier=f"{bvid}-{cid}",
                        cover_url=safeextractfromdict(extracted_video_item, ["first_frame"], None) or safeextractfromdict(raw_data, ["data", "pic"], None),
                        formats=formats,
                        format_ctx=ctx,
                    ))
                    video_infos.append(video_page_info)
                    progress.advance(1)
        except Exception as err:
            err_msg = f"{self.source}._parsefromcommonurl >>> {url} (Error: {err})"
            video_info.update(dict(err_msg=err_msg))
            video_infos.append(video_info)
            self.logger_handle.error(err_msg, disable_print=self.disable_print)
        return video_infos

    # ---------- 番剧 ep (覆盖库实现: 暴露 DASH 格式) ----------
    def _parsefrombangumiepurl(self, url: str, request_overrides: dict = None):
        if not self.belongto(url=url):
            return []
        request_overrides, video_info, null_backup_title, video_infos = request_overrides or {}, VideoInfo(source=self.source), yieldtimerelatedtitle(self.source), []
        try:
            episode_id = str(re.compile(r"https?://(?:www\.)?bilibili\.com/bangumi/play/ep(?P<id>\d+)").match(url).group("id"))
            (resp := self.get("https://api.bilibili.com/pgc/view/web/season", params={"ep_id": episode_id}, **request_overrides)).raise_for_status()
            raw_data = resp2json(resp=resp)
            result_episodes = safeextractfromdict(raw_data, ["result", "episodes"], [])
            result_episodes += [ep for item in safeextractfromdict(raw_data, ["result", "section"], []) for ep in dict(item).get("episodes", [])]
            with taskprogress(description="Parsing Bangumi", total=len(result_episodes)) as progress:
                for _, result_episode in enumerate(result_episodes):
                    if (not isinstance(result_episode, dict)) or (str(result_episode["ep_id"]) != episode_id):
                        progress.advance(1)
                        continue
                    with suppress(Exception):
                        resp = None
                        (resp := self.get(f"https://api.bilibili.com/pgc/player/web/v2/playurl?fnval=12240&ep_id={str(result_episode['ep_id'])}", **request_overrides)).raise_for_status()
                    if not locals().get("resp") or not hasattr(locals().get("resp"), "text"):
                        progress.advance(1)
                        continue
                    (page_raw_data := resp2json(resp=resp))["pgc/view/web/season"] = copy.deepcopy(raw_data)
                    formats, audio_url, audio_ext = self._build_dash_formats(page_raw_data)
                    if not formats:
                        progress.advance(1)
                        continue
                    (video_page_info := copy.deepcopy(video_info)).update(dict(raw_data=page_raw_data))
                    download_url = formats[0]["video_url"]
                    video_title = legalizestring(result_episode.get("share_copy") or result_episode.get("show_title") or null_backup_title, replace_null_string=null_backup_title).removesuffix(".")
                    guess_video_ext_result = FileTypeSniffer.getfileextensionfromurl(url=download_url, headers=self.default_download_headers, request_overrides=request_overrides, cookies=self.default_download_cookies)
                    ext = guess_video_ext_result["ext"] if guess_video_ext_result["ext"] and guess_video_ext_result["ext"] != "NULL" else video_page_info["ext"]
                    if ext in ["m4s"]:
                        ext = "mp4"
                    video_page_info.update(dict(
                        download_url=download_url, title=video_title,
                        save_path=os.path.join(self.work_dir, self.source, f"{video_title}.{ext}"),
                        ext=ext, guess_video_ext_result=guess_video_ext_result,
                        identifier=episode_id, cover_url=safeextractfromdict(result_episode, ["cover"], None),
                        formats=formats,
                        format_ctx={"type": "dash", "ep_id": episode_id},
                    ))
                    if audio_url:
                        video_page_info.update(dict(audio_download_url=audio_url, audio_ext=audio_ext,
                                                    audio_save_path=os.path.join(self.work_dir, self.source, f"{video_title}.audio.{audio_ext}")))
                    video_infos.append(video_page_info)
                    progress.advance(1)
        except Exception as err:
            err_msg = f"{self.source}._parsefrombangumiepurl >>> {url} (Error: {err})"
            video_info.update(dict(err_msg=err_msg))
            video_infos.append(video_info)
            self.logger_handle.error(err_msg, disable_print=self.disable_print)
        return video_infos

    # ---------- 下载前刷新指定格式的新鲜链接 (B站 CDN 链接默认约2小时过期) ----------
    def refreshformat(self, format_ctx: dict, format_id: str, request_overrides: dict = None) -> dict | None:
        try:
            if (format_ctx or {}).get("type") == "ugc":
                resp = self._playurl(format_ctx["bvid"], format_ctx["cid"], int(format_id), request_overrides)
                data = resp.get("data") if isinstance(resp.get("data"), dict) else resp
                durl = data.get("durl") or []
                if not durl:
                    return None
                best = max(durl, key=lambda x: x.get("size", 0))
                return {"video_url": best.get("url"), "audio_url": "", "ext": _ext_from_url(best.get("url") or "", "mp4")}
            if (format_ctx or {}).get("type") == "dash":
                resp = self.get(f"https://api.bilibili.com/pgc/player/web/v2/playurl?fnval=12240&ep_id={format_ctx['ep_id']}", **(request_overrides or {}))
                resp.raise_for_status()
                page_raw_data = resp2json(resp=resp)
                formats, audio_url, _ = self._build_dash_formats(page_raw_data)
                for f in formats:
                    if f["id"] == str(format_id):
                        return {"video_url": f["video_url"], "audio_url": audio_url, "ext": "mp4"}
        except Exception:
            return None
        return None


# ============ 小红书增强客户端 ============
XHS_PC_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36"
XHS_MOBILE_UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"


def _ensure_https(url):
    if not url or not isinstance(url, str):
        return url
    url = url.replace("\\u002F", "/")
    return "https://" + url[7:] if url.startswith("http://") else url


def _extract_xhs_note(html: str):
    """从 window.__INITIAL_STATE__ 提取笔记数据 (兼容 PC 与移动 H5 两种结构)"""
    if not html:
        return None
    m = re.search(r"window\.__INITIAL_STATE__\s*=\s*(\{.*?\})</script>", html, re.S)
    if not m:
        m = re.search(r"window\.__INITIAL_STATE__\s*=\s*(\{.*\})", html, re.S)
    if not m:
        return None
    json_str = m.group(1)
    json_str = re.sub(r"\bundefined\b", "null", json_str)
    try:
        data = json.loads(json_str)
    except Exception:
        return None
    # PC 结构: note.noteDetailMap[firstNoteId].note
    first_id = (data.get("note") or {}).get("firstNoteId")
    if first_id:
        item = (data.get("note") or {}).get("noteDetailMap", {}).get(first_id) or {}
        note = item.get("note")
        if isinstance(note, dict) and note:
            return note
    # 移动 H5 结构: noteData.data.noteData
    note = ((data.get("noteData") or {}).get("data") or {}).get("noteData") or {}
    if note:
        return note
    return (data.get("noteData") or {}).get("note") or (data.get("note") or {}).get("note") or None


def _xhs_video_url(note: dict) -> str:
    """提取无水印视频直链: 优先 media.stream, 跳过带水印的 streamType 259/309"""
    video = note.get("video") or {}
    if not isinstance(video, dict):
        return ""
    # 1) mediaV2 中的 opaque 流
    media_v2 = video.get("mediaV2")
    if isinstance(media_v2, str):
        try:
            mv2 = json.loads(media_v2)
            opaque = (mv2.get("video") or {}).get("opaque1") or {}
            for key in ("hd_screencast_stream", "default_screencast_stream"):
                if opaque.get(key):
                    return _ensure_https(opaque[key])
        except Exception:
            pass
    # 2) media.stream 按编码遍历
    stream = (video.get("media") or {}).get("stream") or video.get("stream") or {}
    unwatermarked, fallback = [], []
    for codec in ("h264", "h265", "av1", "h266"):
        for item in (stream.get(codec) or []):
            if not isinstance(item, dict):
                continue
            master_url = item.get("masterUrl") or item.get("backupUrl") or ""
            if not master_url:
                continue
            clean = _ensure_https(master_url)
            if item.get("streamType") in (259, 309):
                fallback.append(clean)
            else:
                unwatermarked.append(clean)
    return (unwatermarked or fallback or [""])[0]


class EnhancedRednoteVideoClient(RednoteVideoClient):
    """小红书增强: 双 UA 兼容 App 分享链接 / 完整图集(含实况照片)数据 / 无水印视频流"""

    source = "RednoteVideoClient"

    @staticmethod
    def belongto(url: str, valid_domains=None):
        valid_domains = set(valid_domains or []) | {"xiaohongshu.com", "xhslink.com", "xhslink.cn", "rednote.com"}
        return BaseVideoClient.belongto(url, valid_domains)

    @useparseheaderscookies
    def parsefromurl(self, url: str, request_overrides: dict = None):
        request_overrides = request_overrides or {}
        video_info, null_backup_title = VideoInfo(source=self.source), yieldtimerelatedtitle(self.source)
        note = None
        last_err = ""
        # 双 UA: PC 优先 (无水印高清), App 分享链接可能被重定向到时回退移动 UA
        for ua in (XHS_PC_UA, XHS_MOBILE_UA):
            try:
                with requests.Session() as session:
                    session.headers.update({"User-Agent": ua, "Referer": "https://www.xiaohongshu.com/"})
                    resp = session.get(url, timeout=20, allow_redirects=True, **request_overrides)
                    resp.raise_for_status()
                    final_url = str(getattr(resp, "url", "") or "")
                    if "xiaohongshu.com/404" in final_url or "login" in final_url:
                        last_err = "笔记不存在或需要登录"
                        continue
                    note = _extract_xhs_note(resp.text)
                    if note:
                        break
                    last_err = "页面中未找到笔记数据"
            except Exception as e:
                last_err = str(e)[:120]
        if not note:
            video_info.update(dict(err_msg=f"{self.source}.parsefromurl >>> {url} (Error: {last_err or '未获取到笔记数据'})"))
            self.logger_handle.error(video_info["err_msg"], disable_print=self.disable_print)
            return [video_info]
        # 标题
        title = (note.get("title") or "").strip() or (note.get("desc") or "").strip() or null_backup_title
        title = legalizestring(title, replace_null_string=null_backup_title).removesuffix(".")[:80]
        # 视频直链 (视频笔记)
        download_url = _xhs_video_url(note)
        # 封面: imageList 首图
        cover_url = ""
        image_list = note.get("imageList") or []
        if image_list and isinstance(image_list[0], dict):
            cover_url = _ensure_https(image_list[0].get("urlDefault") or image_list[0].get("url") or "")
        video_info.update(dict(raw_data=note, title=title, cover_url=cover_url))
        if download_url:
            guess = {}
            with suppress(Exception):
                guess = FileTypeSniffer.getfileextensionfromurl(url=download_url, headers=self.default_download_headers, request_overrides=request_overrides, cookies=self.default_download_cookies) or {}
            ext = guess.get("ext") if guess.get("ext") and guess.get("ext") != "NULL" else "mp4"
            video_info.update(dict(
                download_url=download_url, ext=ext, guess_video_ext_result=guess,
                save_path=os.path.join(self.work_dir, self.source, f"{title}.{ext}"),
                identifier=str(note.get("noteId") or ""),
            ))
        else:
            # 图集笔记: download_url 留空, 后端从 raw_data 提取图片与实况视频
            video_info.update(dict(identifier=str(note.get("noteId") or "")))
        return [video_info]


def patch_clients():
    """在创建 VideoClient 之前调用: 注入增强客户端并调整通用解析器顺序"""
    VideoClientBuilder.REGISTERED_MODULES["BilibiliVideoClient"] = EnhancedBilibiliVideoClient
    VideoClientBuilder.REGISTERED_MODULES["RednoteVideoClient"] = EnhancedRednoteVideoClient
    # 通用解析器重排: 实测可用的提到最前 (原地重排, 保持同一个 OrderedDict 对象)
    reg = CommonVideoClientBuilder.REGISTERED_MODULES
    names = list(reg.keys())
    ordered = [n for n in COMMON_CLIENT_PRIORITY if n in reg] + [n for n in names if n not in COMMON_CLIENT_PRIORITY]
    items = [(n, reg[n]) for n in ordered]
    reg.clear()
    reg.update(items)
    _patch_ffprobe_dependency()
    return True


def _patch_ffprobe_dependency():
    """库在音视频合并后调用 ffprobe 校验音频流, 但本工具仅提供 ffmpeg 静态二进制。
    用 ffmpeg 替代检测 (读取 0.1 秒音频流即可判定), 避免 FileNotFoundError 导致下载任务假失败。"""
    import subprocess as _sp

    from videodl.modules.utils.cmd import (
        MergeVideoAudioAudioTranscodeFFmpegCommand,
        MergeVideoAudioCopyFFmpegCommand,
        MergeVideoAudioFullTranscodeFFmpegCommand,
    )

    def hasaudiostream_via_ffmpeg(file_path) -> bool:
        try:
            result = _sp.run(
                ["ffmpeg", "-v", "error", "-i", str(file_path), "-map", "0:a", "-t", "0.1", "-f", "null", "-"],
                capture_output=True, text=True, timeout=120,
            )
            return result.returncode == 0
        except Exception:
            return True  # 检测异常时假定正常, 不阻塞下载流程

    for cls in (MergeVideoAudioAudioTranscodeFFmpegCommand, MergeVideoAudioFullTranscodeFFmpegCommand, MergeVideoAudioCopyFFmpegCommand):
        cls.hasaudiostream = staticmethod(hasaudiostream_via_ffmpeg)
