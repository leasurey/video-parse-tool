"""HTTP API 全链路测试: health / 前端页面 / parse / download / task / file / reveal"""
import json
import time
import urllib.request
import urllib.error

BASE = "http://127.0.0.1:8000"


def req(path, method="GET", body=None, timeout=120):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, data=data, method=method,
                               headers={"Content-Type": "application/json"} if data else {})
    with urllib.request.urlopen(r, timeout=timeout) as resp:
        ctype = resp.headers.get("Content-Type", "")
        raw = resp.read()
        return resp.status, ctype, raw


print("=== 1. /api/health ===")
status, _, raw = req("/api/health")
h = json.loads(raw)
print(f"HTTP {status} | ok={h['ok']} version={h['version']} clients={h['clients']} ffmpeg={h['ffmpeg']}")
print(f"download_dir={h['download_dir']}")

print("\n=== 2. GET / (前端页面) ===")
status, ctype, raw = req("/")
html = raw.decode("utf-8", "replace")
print(f"HTTP {status} | {ctype} | {len(raw)} bytes")
print(f"包含标题: {'视频解析下载工具' in html} | 包含脚本: {'doParse' in html}")

print("\n=== 3. POST /api/parse (皮皮虾) ===")
status, _, raw = req("/api/parse", "POST", {"url": "https://h5.pipix.com/s/OI2PNF-T0Mc/"})
p = json.loads(raw)
print(f"HTTP {status} | ok={p['ok']} platform={p['platform']['label']} items={len(p['items'])}")
item = p["items"][0]
print(f"title={item['title'][:40]!r} kind={item['kind']} ext={item['ext']}")
print(f"download_url={item['download_url'][:70]!r}")

print("\n=== 4. POST /api/parse (错误输入) ===")
try:
    req("/api/parse", "POST", {"url": "这不是一个链接"})
except urllib.error.HTTPError as e:
    print(f"HTTP {e.code} (符合预期: 400) detail={json.loads(e.read()).get('detail', '')[:50]}")

print("\n=== 5. POST /api/download (皮皮虾) + 轮询任务 ===")
status, _, raw = req("/api/download", "POST", {"url": "https://h5.pipix.com/s/OI2PNF-T0Mc/", "index": 0})
d = json.loads(raw)
task_id = d["task_id"]
print(f"HTTP {status} | task_id={task_id}")
for i in range(60):
    time.sleep(2)
    status, _, raw = req(f"/api/tasks/{task_id}")
    t = json.loads(raw)
    if t["status"] in ("done", "error"):
        break
print(f"最终状态: {t['status']} | filename={t.get('filename', '')[:40]}")
print(f"save_path={t.get('save_path', '')}")
print(f"bytes={t.get('bytes')} | error={t.get('error', '')}")

print("\n=== 6. GET /api/file/{task_id} (浏览器下载) ===")
status, ctype, raw = req(f"/api/file/{task_id}")
print(f"HTTP {status} | {ctype} | {len(raw)} bytes (文件大小匹配: {t.get('bytes') == len(raw)})")

print("\n=== 7. POST /api/reveal (打开所在文件夹) ===")
try:
    status, _, raw = req("/api/reveal", "POST", {"path": t["save_path"]})
    print(f"HTTP {status} | {json.loads(raw)}")
except urllib.error.HTTPError as e:
    print(f"HTTP {e.code}: {e.read().decode()[:100]}")

print("\n=== 8. POST /api/reveal (路径穿越防护) ===")
try:
    req("/api/reveal", "POST", {"path": "C:/Windows/notepad.exe"})
    print("未拦截 (不符合预期!)")
except urllib.error.HTTPError as e:
    print(f"HTTP {e.code} (符合预期: 403) detail={json.loads(e.read()).get('detail', '')[:40]}")

print("\n全部接口测试完成")
