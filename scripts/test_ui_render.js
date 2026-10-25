/**
 * 前端 DOM 冒烟测试（jsdom）
 * 用真实后端接口数据渲染页面，验证脚本无运行时错误、结构完整、交互可用。
 * 运行：NODE_PATH=<workspace>/node_modules node scripts/test_ui_render.js
 */
const fs = require("fs");
const path = require("path");

const { JSDOM } = require("jsdom");

const ROOT = path.resolve(__dirname, "..");
const HTML = fs.readFileSync(path.join(ROOT, "frontend", "index.html"), "utf8");
const BASE = process.env.BASE_URL || "http://127.0.0.1:8000";

const CASES = [
  { name: "B站（视频 + 清晰度）", url: "https://www.bilibili.com/video/BV16Z4y1X784/" },
  { name: "小红书（图集分区）", url: "https://xhslink.cn/o/AxnRePgIokn" },
];

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let failures = 0;

function check(label, cond, extra = "") {
  console.log(`  ${cond ? "✓" : "✗"} ${label}${extra ? " — " + extra : ""}`);
  if (!cond) failures++;
}

function makeDom(url) {
  return new JSDOM(HTML, {
    runScripts: "dangerously",
    url,
    pretendToBeVisual: true,
    beforeParse(window) {
      window.fetch = async (u, opt) => {
        const res = await fetch(BASE + u, opt);
        const text = await res.text();
        return { ok: res.ok, status: res.status, json: async () => JSON.parse(text), text: async () => text };
      };
    },
  });
}

async function main() {
  const dom = makeDom(BASE + "/");
  const w = dom.window;
  const d = w.document;
  w.addEventListener("error", (e) => { console.log("  ✗ 运行时错误:", e.message); failures++; });

  console.log("== 初始化 ==");
  await sleep(1200);
  check("顶栏状态徽标已填充", d.getElementById("pillVersion").textContent.includes("解析库"));
  check("输出格式徽标显示统一 MP4", d.getElementById("pillFormat").textContent.includes("统一 MP4"),
    d.getElementById("pillFormat").textContent.trim());
  check("平台列表已渲染", d.getElementById("platformGrid").children.length > 10,
    d.getElementById("platformGrid").children.length + " 个");

  console.log("\n== 历史链接（折叠 / 清空） ==");
  const hWrap = d.getElementById("historyWrap");
  check("无历史时整块隐藏", hWrap.classList.contains("hidden"));
  w.pushHistory("https://www.bilibili.com/video/BV16Z4y1X784/");
  w.pushHistory("https://xhslink.cn/o/AxnRePgIokn");
  await sleep(120);
  check("有历史时显示", !hWrap.classList.contains("hidden"));
  check("计数正确", d.getElementById("historyCount").textContent === "2",
    d.getElementById("historyCount").textContent);
  check("渲染历史条目", d.querySelectorAll("#historyBox .hchip").length === 2);

  const hToggle = d.getElementById("historyToggle");
  check("默认展开", !hWrap.classList.contains("collapsed") && hToggle.getAttribute("aria-expanded") === "true");
  hToggle.onclick();
  await sleep(80);
  check("点击后折叠", hWrap.classList.contains("collapsed") && hToggle.getAttribute("aria-expanded") === "false");
  hToggle.onclick();
  await sleep(80);
  check("再次点击展开", !hWrap.classList.contains("collapsed"));

  d.querySelector("#historyBox .hchip .txt").onclick();
  check("点击历史回填输入框", /^https?:\/\//.test(d.getElementById("urlInput").value),
    d.getElementById("urlInput").value.slice(0, 40));

  // 历史条目支持单条删除
  w.pushHistory("https://www.bilibili.com/video/BV16Z4y1X784/");
  w.pushHistory("https://xhslink.cn/o/AxnRePgIokn");
  await sleep(120);
  check("历史条目含删除按钮", d.querySelectorAll("#historyBox .hchip .del").length === 2);
  d.querySelector("#historyBox .hchip .del").onclick();
  await sleep(120);
  check("单条删除后剩 1 条", d.querySelectorAll("#historyBox .hchip").length === 1,
    d.getElementById("historyCount").textContent);

  d.getElementById("historyClear").onclick();
  await sleep(120);
  check("清空后历史隐藏", hWrap.classList.contains("hidden"));
  check("清空同时清空输入框", d.getElementById("urlInput").value === "");
  check("清空后计数归零", d.getElementById("historyCount").textContent === "0");
  d.getElementById("urlInput").value = "";
  w.onInput();

  for (const c of CASES) {
    console.log(`\n== ${c.name} ==`);
    d.getElementById("urlInput").value = c.url;
    w.onInput();
    check("链接识别徽标", d.getElementById("detectBadge").style.display === "inline-flex",
      d.getElementById("detectBadge").textContent);

    await w.doParse();
    await sleep(300);

    // 只有图集时应自动切到图集分类
    const activeFilter = d.querySelector("#filterBarWrap .segmented button.active").dataset.filter;
    const isVideoOnly = [...d.querySelectorAll("#results .item")].length > 0;
    check("分类自适应（视频/图集）", isVideoOnly || activeFilter === "album", `当前：${activeFilter}`);

    const items = d.querySelectorAll("#results .item");
    check("结果卡片渲染", items.length > 0, `${items.length} 张`);
    check("过滤栏（分段控件）", d.querySelectorAll("#filterBarWrap .segmented button").length === 3);
    check("结果计数", /\d+ 项/.test(d.getElementById("resultCounter").textContent),
      d.getElementById("resultCounter").textContent);

    const first = items[0];
    check("卡片结构 item-head", !!first.querySelector(".item-head"));
    check("标题与标签", !!first.querySelector(".item-title") && !!first.querySelector(".chips .chip"));

    const sel = first.querySelector("select");
    if (sel) check("清晰度下拉", sel.options.length > 1, `${sel.options.length} 项`);

    // 切到图集分类
    const albumBtn = [...d.querySelectorAll("#filterBarWrap .segmented button")]
      .find((b) => b.dataset.filter === "album");
    albumBtn.onclick();
    await sleep(150);
    const albumCards = d.querySelectorAll("#results .item");
    if (albumCards.length) {
      const card = albumCards[0];
      const groups = card.querySelectorAll(".album .album-group");
      const cells = card.querySelectorAll(".album .cell");
      check("图集分区（整行容器）", !!card.querySelector(".album"));
      check("分区数量", groups.length >= 1, `${groups.length} 个分区 / ${cells.length} 个格子`);
      check("格子默认勾选", [...cells].every((x) => x.classList.contains("checked")));
      check("格子含复选框与序号", !!card.querySelector(".cell input[data-content]") && !!card.querySelector(".cell .idx-badge"));
      check("封面列与分区对齐（同属 .item）", !!card.querySelector(".item-head .thumb") && !!card.querySelector(".album"));

      // 全选 / 全不选（新增）
      const noneBtn = card.querySelector("button[data-album-none]");
      if (noneBtn) {
        noneBtn.onclick();
        await sleep(80);
        check("全不选后无勾选", card.querySelectorAll("input[data-content]:checked").length === 0);
        card.querySelector("button[data-album-all]").onclick();
        await sleep(80);
        check("全选后全部勾选",
          card.querySelectorAll("input[data-content]:checked").length ===
          card.querySelectorAll("input[data-content]").length);
        const selText = card.querySelector(".album-tools .sel").textContent;
        check("已选计数同步", /已选\s*\d+/.test(selText), selText.trim());
        card.querySelector("button[data-album-all]").onclick();
      }
    } else {
      console.log("  · 该链接无图集内容，跳过图集结构检查");
    }
  }

  console.log("\n== 下载任务 ==");
  // 用最后一个可用链接发起一次图片下载（小红书图集）
  d.getElementById("urlInput").value = CASES[1].url;
  w.onInput();
  await w.doParse();
  await sleep(300);
  const albumBtn = [...d.querySelectorAll("#filterBarWrap .segmented button")]
    .find((b) => b.dataset.filter === "album");
  if (albumBtn) albumBtn.onclick();
  await sleep(150);
  const imgBtn = d.querySelector("#results button[data-album-img]");
  if (imgBtn) {
    imgBtn.onclick();
    await sleep(600);
    const task = d.querySelector("#tasks .task");
    check("任务卡片出现", !!task);
    check("运行中显示进度条", !!d.querySelector("#tasks .progress"));
    check("状态徽标", !!d.querySelector("#tasks .status"));
    for (let i = 0; i < 60; i++) {
      await sleep(500);
      const st = d.querySelector("#tasks .status");
      if (st && /已完成|失败/.test(st.textContent)) break;
    }
    const st = d.querySelector("#tasks .status");
    check("任务完成", st && st.textContent.includes("已完成"), st ? st.textContent : "");
    check("完成后展示路径", /downloads/.test(d.querySelector("#tasks .task-detail").textContent));
    check("完成后有操作按钮", d.querySelectorAll("#tasks .task-actions button").length >= 1);
  } else {
    console.log("  · 未找到图集下载按钮，跳过");
  }

  console.log("\n== 批量解析（多行链接） ==");
  d.getElementById("urlInput").value =
    CASES[0].url + "\n这是分享文本 复制此条信息 " + CASES[1].url + " 打开抖音看看";
  w.onInput();
  check("多行识别到 2 条链接", d.getElementById("detectBadge").textContent.includes("2 条"),
    d.getElementById("detectBadge").textContent);
  await w.doParse();
  await sleep(400);
  check("首屏引导在解析后隐藏", d.getElementById("steps").classList.contains("hidden"));
  const batchRows = d.querySelectorAll("#batchWrap .batch-row");
  check("批量进度面板出现", batchRows.length === 2, `${batchRows.length} 行`);
  check("批量结果合并", d.querySelectorAll("#results .item").length >= 1,
    d.getElementById("resultCounter").textContent);
  const srcChips = [...d.querySelectorAll("#results .chip-src")];
  check("批量时显示来源序号", srcChips.length >= 1, srcChips.map((c) => c.textContent).join(" "));

  console.log("\n== 解析结果清空 ==");
  check("解析后有结果", !d.getElementById("resultsWrap").classList.contains("hidden"));
  d.getElementById("clearResultsBtn").onclick();
  await sleep(120);
  check("清空后结果区隐藏", d.getElementById("resultsWrap").classList.contains("hidden"));
  check("清空后无残留卡片", d.querySelectorAll("#results .item").length === 0);
  check("清空后计数为空", d.getElementById("resultCounter").textContent === "");
  check("清空后过滤栏移除", d.getElementById("filterBarWrap").innerHTML === "");
  check("下载任务保留", d.querySelectorAll("#tasks .task").length >= 1);

  console.log("\n== 任务区管理（复制路径 / 清除已完成） ==");
  check("完成后有复制路径按钮", !!d.querySelector("#tasks button[data-path]"));
  check("任务计数已显示", /\d/.test(d.getElementById("taskCounter").textContent),
    d.getElementById("taskCounter").textContent);
  const clearDone = d.getElementById("clearDoneTasks");
  check("有已完成任务时显示「清除已完成」", !clearDone.classList.contains("hidden"));
  clearDone.onclick();
  await sleep(150);
  check("清除后无任务卡片", d.querySelectorAll("#tasks .task").length === 0);
  check("清除后任务区隐藏", d.getElementById("tasksWrap").classList.contains("hidden"));

  console.log("\n== 局域网访问入口 ==");
  const lanPill = d.getElementById("pillLan");
  check("本机访问时显示「手机访问」入口", !lanPill.classList.contains("hidden"));
  lanPill.onclick();
  await sleep(800);
  const modal = d.getElementById("lanModal");
  check("弹窗已打开", !!modal);
  if (modal) {
    check("二维码渲染为 SVG", !!modal.querySelector(".qr-box svg"));
    const urls = [...modal.querySelectorAll(".lan-url code")].map((c) => c.textContent);
    check("列出局域网地址", urls.length >= 1 && urls.every((u) => /^http:\/\/\d+\.\d+\.\d+\.\d+:\d+$/.test(u)),
      urls.join(" "));
    check("提供复制按钮", modal.querySelectorAll("button[data-copy]").length === urls.length);
    modal.querySelector("#lanClose").onclick();
    await sleep(100);
    check("关闭后移除弹窗", !d.getElementById("lanModal"));
  }

  // 用局域网地址打开页面时，不应再给手机自己显示扫码入口
  const lanDom = makeDom((process.env.LAN_URL || "http://192.168.0.8:8000") + "/");
  const ld = lanDom.window.document;
  await sleep(1200);
  check("手机端不显示「手机访问」入口", ld.getElementById("pillLan").classList.contains("hidden"));
  lanDom.window.close();

  console.log(`\n结果: ${failures === 0 ? "全部通过" : failures + " 项失败"}`);
  dom.window.close();
  process.exit(failures === 0 ? 0 : 1);
}

main().catch((e) => { console.error("测试异常:", e); process.exit(1); });
