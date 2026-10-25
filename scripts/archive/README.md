# 归档脚本

这里的脚本**不属于当前工作流**，仅作历史留存，可能依赖已变化的后端接口或外部链接，随时可能无法运行。

| 脚本 | 说明 | 现状 |
| --- | --- | --- |
| `test_parse.py` | 通过 `parse_sync` 测四平台解析 | 被 `test_v3.py` 取代 |
| `test_v2.py` | 解析加速 + 分辨率选择 + 下载 | 被 `test_v3.py` 取代 |
| `test_final.py` | 四平台全流程（解析/清晰度/下载） | 被 `test_v3.py` 取代 |
| `test_download.py` | 后端真实代码路径的下载流程 | 被 `test_api.py` 取代 |
| `test_images.py` | 图集下载代码路径（依赖当时的临时 CDN 链接） | 被 `test_v3.py` 取代 |
| `test_enhanced.py` | 增强 B站客户端（多清晰度 / DASH） | 相关逻辑已并入正式代码与 `test_v3.py` |
| `debug_xhs2.py` | 批量检测小红书候选链接活性 | 一次性排查工具 |
| `download_lib.py` | 断点续传下载 videodl 源码包 | 一次性环境准备工具 |
| `install_vlc.py` / `verify_vlc.py` | 下载并验证 VLC（用于补齐本机 HEVC 解码） | **与本项目无关**，属另一台机器的环境配置 |

当前有效的测试脚本见上级目录，用法见根目录 `README.md` 的「开发与测试」。
