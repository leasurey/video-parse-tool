<div align="center">

# 视频解析下载工具 · Video Parse Tool

**本地运行 · 粘贴即解析 · 统一输出 MP4**

粘贴视频链接（或抖音 / 小红书 / B站 / 皮皮虾等 App 的分享文本），自动识别平台、解析直链并下载到本地。

[![Version](https://img.shields.io/badge/version-1.0.1-4f8cff)](CHANGELOG.md)
[![License](https://img.shields.io/badge/license-MIT%20·%20非商业依赖-3fb950)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-3776ab)](requirements.txt)
[![Platform](https://img.shields.io/badge/platform-Windows%20·%20Web%20·%20手机局域网-a371f7)](#-手机--局域网访问)

[快速开始](#-快速开始) · [使用方法](#-使用方法) · [配置](#-配置说明configjson) · [常见问题](#-常见问题) · [更新日志](CHANGELOG.md)

</div>

---

基于开源库 **[videodl](https://github.com/CharlesPikachu/videodl)**（PyPI 包名 `videofetch`，v0.9.1）构建，内置 **107 个平台客户端**，并做了针对性增强（B站多清晰度、小红书图集/实况照片、按平台路由加速、DASH 合并修复、统一 MP4 输出）。

> ⚠️ videodl 采用 **PolyForm-Noncommercial-1.0.0**，**仅允许非商业用途**。本项目作为整体运行时同样仅限非商业用途，详见 [许可证](#-许可证)。

## ✨ 功能特性

- **多平台解析**：抖音、小红书、B站、皮皮虾、皮皮搞笑、快手、微博、优酷、腾讯视频、爱奇艺、芒果TV、搜狐、知乎、贴吧、西瓜视频、央视、TED、YouTube 等数十个站点；未覆盖站点走通用解析器兜底
- **批量解析**：一次粘贴多条链接（每行一条，或混合分享文本），按顺序逐条解析（最多 10 条），结果合并展示并标注来源序号；失败的条目可单独重试
- **内容自动过滤 + 视频默认**：结果按「视频 / 图集」分类，**默认只展示视频**；有图集时提示切换分类，避免混合内容干扰
- **图集分区展示**：图集清晰分为「🎬 实况视频（动态内容）」与「🖼 静态图片」两个区域，支持逐项勾选、全选/全不选，也可一键下载全部实况视频或全部图片
- **小红书实况照片（Live Photo）**：识别 `livePhoto` 项，实况视频单独列出（带封面缩略图与 ▶ 角标），下载时自动附带静态封面，得到完整的「静图 + 短视频」两部分
- **小红书双 UA 解析**：桌面 UA 优先、移动 UA 兜底，兼容 App 分享链接（`xhslink.cn` / `xhslink.com` / `rednote.com`），无需 Cookie 即可解析公开笔记
- **统一输出 MP4**：下载后自动统一为 MP4。H.264+AAC 等通用编码走**无损重封装**（秒级、画质零损失）；VP9/Opus 等不通用编码自动转码 H.264+AAC。可在 `config.json` 用 `output_format: "auto"` 关闭
- **B站多清晰度**：解析时枚举全部可用清晰度（含文件大小），下载前自由选择，所选档位体积实时显示，文件名自动附加清晰度标识
- **视频在线预览**：直链为 mp4 时结果内嵌播放器
- **解析加速**：按平台路由优先解析器 + 解析结果缓存 30 分钟（下载时无需重复解析）
- **下载管理**：任务计数、状态轮询、保存路径展示、复制路径、一键打开所在文件夹、浏览器下载、失败重试、清除已完成
- **手机 / 局域网访问**：默认监听 `0.0.0.0`，顶栏「📱 手机访问」出二维码；手机端自动隐藏仅本机可用的操作
- **自动配置 FFmpeg**：首次启动复制静态二进制到 `bin/`，支持 DASH 音视频合并与 HLS 处理（含 ffprobe 兼容补丁）
- **安全防护**：文件打开接口限制在工具目录内并拒绝非本机来源；下载接口限制在下载目录内，防路径穿越

## 🎨 界面与交互约定

单文件前端 `frontend/index.html`（无外部依赖、无构建步骤），修改时建议沿用现有令牌，避免对齐回退。

| 类别 | 约定 |
| --- | --- |
| 设计参考 | GitHub Primer 深色主题：canvas `#0d1117`、surface `#161b22`、border `#30363d`、fg `#e6edf3`、accent `#2f81f7` |
| 版心 | `--container: 960px`、`--gutter: 16px`；`header` / `main` / `footer` 共用，保证左右边缘对齐 |
| 间距 | `--sp-1…6` = 4/8/12/16/24/32；卡片外间距 16px、内边距 16px |
| 圆角 | `--r-sm 6px`（按钮/输入/缩略图）、`--r-lg 12px`（卡片/面板）、`--r-pill`（徽标） |
| 控件高度 | 常规 32px、小号 28px、徽标 22–24px，同一行内不混用 |
| 卡片布局 | `.item-head` = `grid: 140px 1fr`（封面列 + 内容列），`.album` 独立整行 |
| 动效 | 120ms `cubic-bezier(.2,.8,.2,1)`；`prefers-reduced-motion` 下自动关闭 |
| 移动端 | ≤560px 输入控件字号 16px（防 iOS 聚焦缩放），按钮触摸目标 32–36px，图集勾选框 20px |

## 🚀 快速开始

### 环境要求

- Windows 10 / 11（脚本为 `.bat`；其他系统可手动执行等效命令）
- Python 3.10 或更高版本

### 首次安装（约 1–3 分钟）

双击 **`install.bat`**：自动创建虚拟环境（`venv/`）并按 `requirements.txt` 安装依赖。

也可手动执行：

```bat
python -m venv venv
venv\Scripts\python.exe -m pip install -r requirements.txt
copy config.example.json config.json
```

### 启动使用

双击 **`start.bat`**，服务启动后自动打开浏览器进入 `http://127.0.0.1:8000`，控制台同时打印局域网地址。

> 停止服务：关闭黑色控制台窗口或按 `Ctrl+C`。

### 手机 / 局域网访问

1. 确认 `config.json` 中 `"host": "0.0.0.0"`、`"lan_access": true`（默认已是）
2. **右键 `allow_lan.bat` → 以管理员身份运行**，放行防火墙端口（只需一次；规则名 `VideoParseTool-LAN`，仅局域网网段 + 专用/域网络）
3. 手机与电脑连接**同一个 Wi-Fi**，在电脑上点顶栏 **「📱 手机访问」**，扫码或手动输入地址
4. 手机打开后即可正常解析与下载；界面会自动隐藏「打开所在文件夹」这类仅本机可用的按钮

连接不上时的排查顺序：

| 现象 | 原因与处理 |
| --- | --- |
| 手机完全打不开 | Windows 防火墙拦截（最常见）→ 以管理员身份运行 `allow_lan.bat` |
| 地址打不开，但电脑能上网 | 路由器开启了「AP 隔离 / 客户端隔离」→ 在路由器设置里关闭 |
| 地址变了 | 路由器重新分配了 IP → 以控制台打印的地址为准 |
| 只想自己用 | `config.json` 改回 `"host": "127.0.0.1"` 或 `"lan_access": false` |

撤销防火墙放行：

```bat
netsh advfirewall firewall delete rule name="VideoParseTool-LAN"
```

> 安全提示：局域网内任何人都能访问本工具的解析与下载功能，且没有登录校验；请仅在可信的家用 / 办公网络下开启。

## 📖 使用方法

1. **粘贴**：把链接贴进输入框，或直接粘贴 App 分享文本（自动提取链接）；**支持一次多行/多条**，逐条解析
2. **解析**：点「解析」或按 `Ctrl + Enter`；多条时进度面板会逐条显示成功、耗时与失败原因
3. **查看结果**：默认展示**视频**（封面、标题、平台标识、清晰度选择、预览）；若只有图集内容会自动切到「图集」
4. **图集操作**：切换到「图集」分类后，可按「🎬 实况视频」与「🖼 静态图片」两区勾选，或用「全选 / 全不选」；按钮提供 `下载全部实况视频（含封面）` / `下载全部图片` / `下载勾选内容`
5. **下载**：视频多时可用标题栏「⬇ 下载全部视频」批量入队；任务区显示进度、体积、路径，可复制路径或直接打开文件夹

下载产物位置：

```text
downloads/<平台>/<标题>/            视频：<标题> [清晰度].mp4
downloads/<平台>/<标题>/图片/        图集：IMG_001.jpg ...
downloads/<平台>/<标题>/实况视频/    LIVE_001.mp4 + LIVE_001_cover.jpg
```

## ⚙️ 配置说明（config.json）

仓库只提供 `config.example.json`；首次运行会据此生成 `config.json`（该文件可能含 Cookie，**已加入 `.gitignore`，不会入库**）。

```json
{
  "host": "0.0.0.0",
  "port": 8000,
  "lan_access": true,
  "download_dir": "downloads",
  "max_concurrent_downloads": 2,
  "download_threads": 8,
  "open_browser": true,
  "cookies": {},
  "output_format": "mp4",
  "keep_original_after_remux": false
}
```

| 字段 | 说明 |
| --- | --- |
| `host` / `port` | 监听地址与端口（端口被占用时修改）；`0.0.0.0` = 全部网卡，`127.0.0.1` = 仅本机 |
| `lan_access` | 局域网访问开关（`true` 时才提供地址提示与二维码入口） |
| `download_dir` | 下载目录，相对路径基于工具根目录 |
| `max_concurrent_downloads` | 同时下载的任务数上限 |
| `download_threads` | 单文件下载线程数（默认 8） |
| `open_browser` | 启动时是否自动打开浏览器 |
| `cookies` | 各平台登录 Cookie |
| `output_format` | 输出容器：`mp4`（默认，下载后统一转 MP4）/ `auto`（保留平台原始格式） |
| `keep_original_after_remux` | 转为 MP4 后是否保留原始格式文件（默认 `false`） |

### 配置平台 Cookie

```json
"cookies": {
  "bilibili": "SESSDATA=xxxxxx; bili_jct=xxxxxx",
  "xiaohongshu": "web_session=xxxxxx"
}
```

支持的平台键：`douyin`、`xiaohongshu`、`bilibili`、`pipix`、`pipigaoxiao`、`kuaishou`、`weibo`、`youku`、`tencent`、`iqiyi`、`zhihu`、`xigua`。

> B站配置 Cookie 后会解锁 720P / 1080P+ / 4K 等更多清晰度；小红书私密或风控笔记需要 Cookie。

## 📁 目录结构

```text
video-parse-tool/
├── install.bat              # 一键安装依赖（读取 requirements.txt）
├── start.bat                # 一键启动
├── allow_lan.bat            # 放行局域网端口（需管理员，供手机访问）
├── config.example.json      # 配置模板（复制为 config.json 后修改）
├── requirements.txt         # Python 依赖
├── backend/
│   ├── main.py              # FastAPI 后端（解析路由 / 图集分区 / 选择性下载 / MP4 转换 / 文件服务）
│   └── enhanced_clients.py  # 增强客户端（B站多清晰度 / 小红书双 UA + 实况 / ffprobe 补丁）
├── frontend/index.html      # 单文件前端（无外部依赖、无构建）
├── scripts/                 # 测试与排查脚本
│   ├── test_ui_render.js    # 前端 jsdom 冒烟测试（68 项）
│   ├── test_api.py          # HTTP API 全链路（8 项）
│   ├── test_v3.py           # 四平台 + 图集分区回归
│   ├── test_mp4.py          # 合成素材验证 MP4 转换
│   ├── test_mp4_e2e.py      # 真实下载验证输出格式
│   ├── debug_parsers.py     # 各解析器耗时排查
│   └── archive/             # 历史/一次性脚本（不属当前工作流，见其 README）
├── bin/                     # 自动放置的 ffmpeg（运行时生成，不入库）
├── downloads/               # 下载输出目录（不入库）
└── logs/                    # 服务运行日志（不入库）
```

## 🔍 工作原理

```text
浏览器前端 (index.html)
    │  POST /api/parse {url}          ← 批量时前端逐条调用，失败可单条重试
    ▼
FastAPI 后端 (backend/main.py)
    │  smart_parse() 按平台路由:
    │    ├─ B站      → EnhancedBilibiliVideoClient（枚举 qn 清晰度 + DASH 格式）
    │    ├─ 小红书   → EnhancedRednoteVideoClient（双 UA + 两种页面数据结构）
    │    ├─ 抖音     → Ray / BugPk / Kedou / GV 等第三方解析器优先
    │    └─ 全部失败 → 库完整解析链兜底
    ▼
内容分类 (视频优先):
    │  视频: download_url + formats(清晰度)
    │  图集: contents[] = [静态图...] + [实况视频(含封面)...]
    ▼
POST /api/download {parse_id, index, format_id|album_mode, album_indices}
    │  视频 → client.download() → ensure_mp4_output() → downloads/<平台>/<标题> [清晰度].mp4
    │  图集 → download_album() → downloads/<平台>/<标题>/{图片|实况视频|选中}/
    │        实况视频自动附带封面（LIVE_001.mp4 + LIVE_001_cover.jpg）
    ▼
统一 MP4 输出 (output_format=mp4):
    │  已是 MP4                    → 不动
    │  H.264/AAC 的 FLV/MKV/TS/MOV → 无损重封装（-c copy，秒级，画质零损失）
    │  VP9/Opus 等不通用编码       → 转码 H.264 + AAC
    │  纯音频 / 转换失败           → 保留原始文件并在任务中提示
```

## 🧪 开发与测试

```bat
:: 后端语法检查
venv\Scripts\python.exe -m py_compile backend\main.py

:: HTTP API 全链路（服务需已启动）
venv\Scripts\python.exe scripts\test_api.py

:: MP4 转换（合成素材，无需联网）
venv\Scripts\python.exe scripts\test_mp4.py

:: 四平台 + 图集分区回归（需联网）
venv\Scripts\python.exe scripts\test_v3.py

:: 前端 DOM 冒烟测试（需联网 + 已安装 jsdom）
set NODE_PATH=<你的 node_modules 路径>
node scripts\test_ui_render.js
```

前端测试用 jsdom 加载真实页面并转发请求到真实后端，校验初始化、批量解析、图集分区与勾选、
下载任务全流程、局域网弹窗等，当前共 **68 项**。

## 🧾 测试验证记录

### 2026-10-25 V1.0.1（批处理编码修复）

| 测试项 | 结果 |
| --- | --- |
| 三个 `.bat` 字节检查 | 非 ASCII 字节数均为 0；CRLF 换行（`start.bat` 26 处、`install.bat` 57 处、`allow_lan.bat` 50 处） |
| 批处理解析实测 | 用替换掉启动命令的副本走完 `start.bat` 全流程：分支判断、提示输出、目标命令拼接均正确，无乱码、无命令截断 |
| 原缺陷复现记录 | 修复前中文系统报 `'hon.exe' 不是内部或外部命令`（`python.exe` 被截断）与 `'氭嫙鐜' 不是内部或外部命令`（"虚拟环境"乱码） |

### 2026-10-25 V1.0.0（操作流程优化）

| 测试项 | 结果 |
| --- | --- |
| 前端 jsdom 冒烟（`scripts/test_ui_render.js`） | **68 项全部通过** |
| 批量解析（2 条链接混合分享文本） | 进度面板 2 行、结果合并 2 项、显示「来源 #1」 |
| 图集全选 / 全不选 | 勾选数与「已选 N / 总数」实时同步 |
| 任务区管理 | 计数显示、复制路径、清除已完成后卡片清空且任务区隐藏 |
| 历史单条删除 | 删除后剩余条目数与计数一致 |
| 版本号链路 | `/api/health` 返回 `app_version`，页脚显示 `v1.0.0` |
| 关键修复回归 | 复制直链走 `execCommand` 回退（http 局域网可用）；批量下载按 `_pos` 取条目 |

### 2026-10-25 V0.4.0（统一输出 MP4）

| 测试项 | 结果 |
| --- | --- |
| 合成素材重封装 | FLV / MKV / TS（H.264+AAC）→ MP4，无损重封装，时长与体积一致 |
| 合成素材转码 | WebM（VP9+Opus）→ MP4，自动转码 H.264+AAC |
| B站 360P 真实下载 | 6.90MB → `.mp4`（H.264+AAC），2.2 秒，无原始容器残留 |
| 皮皮虾真实下载 | 0.87MB → `.mp4`（H.264+AAC），0.7 秒 |

### 2026-10-25 V0.6.0（局域网 / 手机访问）

| 测试项 | 结果 |
| --- | --- |
| 监听与地址探测 | 绑定 `0.0.0.0:8000`，探测到局域网地址 `http://192.168.0.8:8000` |
| 健康接口 | `/api/health` 返回 `lan_enabled=true` 与地址列表 |
| 二维码接口 | `/api/qrcode` 返回 `image/svg+xml`；非 http 参数返回 400 |
| 权限边界 | 模拟手机 IP 调 `/api/reveal` → 403；本机 → 200 |

### 2026-10-24 V0.3.0（界面 / 过滤 / 图集分区）

| 测试项 | 结果 |
| --- | --- |
| 四平台解析 | B站 2.0s / 皮皮虾 2.7s / 抖音 3.5s / 小红书 1.1–1.4s |
| 图集解析与下载 | kind=album，静态图与实况视频分区正确；图片下载 2.0s |
| 实况分区逻辑 | 合成样本验证：2 静态 + 2 实况，封面不重复计数 |

> 说明：实况照片（Live Photo）的真实链路验证受限于找不到存活的实况图集链接。分区与配对逻辑按小红书数据结构
> （`imageList[].livePhoto` + `stream.h264[0].masterUrl`）实现，并用同结构样本验证通过；拿到真实链接后可直接复测。

## ❓ 常见问题

<details>
<summary><b>解析后看不到图集？</b></summary>

默认只展示视频。有图集时结果上方会提示「已按默认设置隐藏 N 组图集」，点击顶部「图集」分类即可查看并选择性下载。
若该链接**只有**图集，会自动切到「图集」分类。
</details>

<details>
<summary><b>图集里为什么有「实况视频」和「静态图片」两个区域？</b></summary>

小红书等平台的实况照片由「一张静态图 + 一段短视频」组成。为避免重复与混淆，实况照片只归入「实况视频」区
（封面即那张静态图，下载时自动附带），纯静态图片归入「静态图片」区。
</details>

<details>
<summary><b>实况视频下载后是什么文件？</b></summary>

每个实况照片生成两个文件：`LIVE_001.mp4`（动态片段）与 `LIVE_001_cover.jpg`（静态封面），即完整的 Live Photo 两部分。
</details>

<details>
<summary><b>解析慢或偶尔失败？</b></summary>

抖音、小红书的专用接口已被平台风控，会依次尝试多个第三方解析服务，耗时取决于对方负载；连续高频使用可能被限速。
B站、皮皮虾、小红书（原生）通常 1–4 秒。可用 `scripts\debug_parsers.py` 查看各解析器当前速度。
批量解析按顺序逐条进行，正是为了避免并发触发风控。
</details>

<details>
<summary><b>小红书链接打不开 / 解析失败？</b></summary>

分享链接必须带 `xsec_token`（App 分享自带）。从浏览器地址栏复制的裸链接可能打不开；链接过期、笔记删除或
仅自己可见也会失败。必要时在 `config.json` 配置小红书 Cookie。
</details>

<details>
<summary><b>手机上「复制直链」没反应？</b></summary>

已修复。手机通过 `http://` 局域网访问属于非安全上下文，`navigator.clipboard` 不可用，现统一回退到
`document.execCommand('copy')`。若浏览器仍拦截，长按链接手动复制即可。
</details>

<details>
<summary><b>端口被占用？</b></summary>

修改 `config.json` 中的 `port`。
</details>

<details>
<summary><b>如何更新解析库？</b></summary>

```bat
venv\Scripts\python.exe -m pip install --upgrade videofetch
```
</details>

<details>
<summary><b>FFmpeg 相关？</b></summary>

启动时自动配置（`bin/ffmpeg.exe`），内置 ffprobe 兼容补丁（用 ffmpeg 替代检测音频流）。
部分 HLS(m3u8) 平台还依赖 `N_m3u8DL-RE`（可选，需自行放置）。
</details>

## ⚠️ 已知限制（如实说明）

- **抖音 / 小红书专用接口被风控**：小红书已改为原生双 UA 解析（1–2 秒）；抖音仍依赖第三方解析服务（3–15 秒，取决于对方负载）
- **小红书图片链接时效性**：`urlDefault` 是带签名的短效 CDN 地址，易 403；本项目改用 `fileId` 构造稳定原图地址并保留回退
- **实况照片**：分区与配对逻辑按平台数据结构实现并用同结构样本验证，真实链接的完整链路仍待复测
- **本机无 ffprobe**：容器与编码探测统一解析 `ffmpeg -i` 日志；库自身的 ffprobe 调用已由补丁替代
- **平台接口随时可能变化**：解析成功率取决于各平台现状与第三方解析服务可用性，不保证长期稳定
- **无登录校验**：开启局域网时同网段任何人都可使用，请仅在可信网络下开启

## ⚖️ 法律与合规声明

- 本项目基于 **videodl** 构建，其许可证为 **PolyForm-Noncommercial-1.0.0**：**仅允许非商业用途**
- 仅供个人学习与技术研究使用。请遵守各平台服务条款，尊重版权，不得将下载内容用于传播或侵权用途
- 解析出的视频、图片、音乐等素材，著作权归原平台及权利人所有

## 📄 许可证

本项目**原创代码**采用 [MIT](LICENSE)。但运行时必需依赖 videodl（PolyForm-Noncommercial-1.0.0），
因此**本项目作为整体仅限于非商业用途**；商业使用需先取得 videodl 作者授权或替换解析实现。
第三方组件的许可证与来源见 [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md)。

## 🙏 致谢

| 来源 | 使用内容 |
| --- | --- |
| [CharlesPikachu/videodl](https://github.com/CharlesPikachu/videodl) | 核心解析库（作者：Zhenchao Jin，PolyForm-Noncommercial-1.0.0） |
| [imageio/imageio-ffmpeg](https://github.com/imageio/imageio-ffmpeg) | FFmpeg 静态二进制 |
| [fastapi/fastapi](https://github.com/fastapi/fastapi) | Web 接口框架 |
| [heuer/segno](https://github.com/heuer/segno) | 手机访问二维码生成 |

---

<div align="center">

**作者 k** · [B 站主页](https://space.bilibili.com/527557440)

如果这个项目对你有帮助，欢迎点个 ⭐

</div>
