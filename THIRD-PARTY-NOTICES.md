# 第三方组件说明

本项目自身代码采用 MIT 许可证（见 `LICENSE`），但依赖了以下第三方组件。使用时请一并遵守其许可证。

## 核心解析库（运行时必需）

| 组件 | 来源 | 许可证 | 用途 |
| --- | --- | --- | --- |
| videofetch（PyPI 包名）/ videodl | [CharlesPikachu/videodl](https://github.com/CharlesPikachu/videodl) | **PolyForm-Noncommercial-1.0.0** | 107 个平台的视频/图集解析与下载核心能力 |

> ⚠️ **PolyForm-Noncommercial-1.0.0 仅允许非商业用途**。这是本项目运行时不可或缺的依赖，
> 因此本项目作为整体也仅限于非商业用途。详见 `LICENSE` 末尾的「附加说明」。

## 其他运行时依赖

| 组件 | 来源 | 许可证 | 用途 |
| --- | --- | --- | --- |
| FastAPI | [fastapi.tiangolo.com](https://fastapi.tiangolo.com/) | MIT | HTTP 接口框架 |
| Uvicorn | [github.com/encode/uvicorn](https://github.com/encode/uvicorn) | BSD-3-Clause | ASGI 服务器 |
| Requests | [github.com/psf/requests](https://github.com/psf/requests) | Apache-2.0 | HTTP 请求 |
| imageio-ffmpeg | [github.com/imageio/imageio-ffmpeg](https://github.com/imageio/imageio-ffmpeg) | BSD-2-Clause | 提供 FFmpeg 静态二进制（DASH/HLS 合并、MP4 转换） |
| segno | [github.com/heuer/segno](https://github.com/heuer/segno) | BSD-3-Clause | 生成手机访问用的二维码（纯 Python，无外部依赖） |

FFmpeg 本体由 `imageio-ffmpeg` 提供，其许可证与组件说明随该包分发（通常为 LGPL/GPL 构建，
仅以二进制形式调用、未修改、未重新分发源码）。

## 开发/测试期依赖（不随运行分发）

| 组件 | 来源 | 许可证 | 用途 |
| --- | --- | --- | --- |
| jsdom | [github.com/jsdom/jsdom](https://github.com/jsdom/jsdom) | MIT | 前端 DOM 冒烟测试（`scripts/test_ui_render.js`） |
| httpx | [github.com/encode/httpx](https://github.com/encode/httpx) | BSD-3-Clause | FastAPI TestClient 依赖 |

## 可选的外部工具

| 工具 | 来源 | 说明 |
| --- | --- | --- |
| N_m3u8DL-RE | [nilaoda/N_m3u8DL-RE](https://github.com/nilaoda/N_m3u8DL-RE) | 部分 HLS(m3u8) 平台的可选下载器，未内置，需自行放置 |

## 参考源码（不参与构建）

`libs/` 目录曾用于存放 videodl 源码以便排查，已被 `.gitignore` 排除、不入库。
需要参考时请以官方仓库为准。
