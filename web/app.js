"use strict";
const $ = (id) => document.getElementById(id);
const state = { data: null, kind: "model", visible: 24 };
const fmt = new Intl.DateTimeFormat("zh-CN", { timeZone: "Asia/Shanghai", year: "numeric", month: "2-digit", day: "2-digit" });
const date = (value) => fmt.format(new Date(value));
const stamp = (value) => new Intl.DateTimeFormat("zh-CN", { timeZone: "Asia/Shanghai", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false }).format(new Date(value));
function el(tag, cls, text) {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text !== undefined) node.textContent = text;
  return node;
}
function link(label, url, cls) {
  const node = el("a", cls, label);
  const parsed = new URL(url, location.href);
  if (parsed.protocol === "https:" || parsed.origin === location.origin) node.href = parsed.href;
  node.target = "_blank";
  node.rel = "noopener noreferrer";
  return node;
}
function card(row) {
  const node = el("article", "card");
  const top = el("div", "card-top");
  const provider = el("span", "provider");
  provider.append(el("span", "provider-mark", row.provider.slice(0, 1).toUpperCase()), document.createTextNode(row.provider));
  top.append(provider);
  const isNew = state.data.today.new_ids.includes(row.id);
  if (isNew) top.append(el("span", "badge", "本日发现"));
  const title = el("h3");
  title.append(link(row.title, row.url));
  const summary = el("p", "card-summary", row.summary);
  const features = el("div", "features");
  row.features.forEach((feature) => features.append(el("span", "feature", feature)));
  const footer = el("div", "card-footer");
  footer.append(el("span", "", row.date_label + " · " + date(row.published_at)), link(row.kind === "model" ? "模型卡" : "官方原文", row.url));
  node.append(top, title, summary, features, footer);
  node.append(el("p", "card-meta", row.kind === "model" ? "许可：" + row.license + (row.gated ? " · 需申请访问" : "") : row.summary_basis));
  return node;
}
function render() {
  if (!state.data) return;
  const term = $("search").value.trim().toLocaleLowerCase();
  const cutoff = Date.now() - Number($("period").value) * 86400000;
  const list = state.data.items.filter((row) => row.kind === state.kind &&
    (!$("provider").value || row.provider === $("provider").value) &&
    (!$("task").value || row.task === $("task").value) &&
    new Date(row.published_at).getTime() >= cutoff &&
    (!term || [row.title, row.provider, row.summary, ...row.features, ...(row.tags || [])].join(" ").toLocaleLowerCase().includes(term)));
  const fragment = document.createDocumentFragment();
  list.slice(0, state.visible).forEach((row) => fragment.append(card(row)));
  $("results").replaceChildren(fragment);
  $("result-count").textContent = "共 " + list.length + " 条 · 按来源日期由新到旧";
  $("empty").hidden = list.length !== 0;
  $("more").hidden = list.length <= state.visible;
  $("results").setAttribute("aria-labelledby", "tab-" + state.kind);
  $("kind-note").textContent = state.kind === "model"
    ? "日期为模型仓库创建时间；功能说明来自平台任务标签，详细规格与使用许可请查看官方模型卡。"
    : "根据官方标题筛选模型相关动态；包含现有模型与产品功能更新，摘要为简短原文节选。";
}
function reset() {
  $("search").value = "";
  $("provider").value = "";
  $("task").value = "";
  $("period").value = "365";
  state.visible = 24;
  render();
}
function showNotice(message) {
  $("notice").textContent = message;
  $("notice").hidden = false;
}
async function start() {
  const response = await fetch("./data/catalog.json", { cache: "no-cache" });
  if (!response.ok) throw new Error("数据请求失败（" + response.status + "）");
  const data = await response.json();
  if (!Array.isArray(data.items) || !Array.isArray(data.sources)) throw new Error("数据格式异常");
  state.data = data;
  const models = data.items.filter((r) => r.kind === "model");
  const news = data.items.filter((r) => r.kind === "announcement");
  $("stat-models").textContent = models.length;
  $("stat-news").textContent = news.length;
  $("count-model").textContent = models.length;
  $("count-announcement").textContent = news.length;
  $("stat-new").textContent = data.today.bootstrap ? data.today.imported_ids.length : data.today.new_ids.length;
  $("new-label").textContent = data.today.bootstrap ? "首次导入" : "本日新发现";
  $("brief-date").textContent = date(data.generated_at);
  $("updated").textContent = "最近更新 " + stamp(data.generated_at) + "（北京时间）";
  const healthy = data.sources.filter((s) => s.status === "ok").length;
  $("health").textContent = "来源可用 " + healthy + " / " + data.sources.length;
  const age = Date.now() - new Date(data.generated_at).getTime();
  const failed = data.sources.filter((s) => s.status !== "ok");
  if (age > 36 * 3600000 || failed.length) {
    $("health-dot").classList.add("warning");
    const messages = [];
    if (age > 36 * 3600000) messages.push("数据已超过 36 小时未更新，请查看 Actions 运行状态。");
    if (failed.length) messages.push(failed.length + " 个来源本次读取失败，相关历史记录已保留；来源状态见下方。");
    showNotice(messages.join(" "));
  }
  if (data.run_url && data.run_url.startsWith("https://github.com/lifeiXiao/ai-model-daily/actions/runs/")) $("run-link").href = data.run_url;
  const latest = news[0];
  if (latest) {
    $("spotlight").hidden = false;
    $("spotlight-title").textContent = latest.title;
    $("spotlight-meta").textContent = latest.provider + " · " + date(latest.published_at);
    $("spotlight-link").href = latest.url;
  }
  [...new Set(data.items.map((r) => r.provider))].sort((a, b) => a.localeCompare(b, "zh-CN")).forEach((name) => {
    const option = el("option", "", name); option.value = name; $("provider").append(option);
  });
  [...new Set(models.map((r) => r.task))].sort((a, b) => a.localeCompare(b, "zh-CN")).forEach((name) => {
    const option = el("option", "", name); option.value = name; $("task").append(option);
  });
  data.sources.forEach((source) => {
    const node = el("div", "source" + (source.status === "ok" ? "" : " failed"));
    node.append(link(source.name + (source.kind === "model" ? " · HF" : " · 公告"), source.url),
      el("small", "", source.status === "ok" ? "已同步" : "读取失败"));
    node.title = source.status === "ok" ? "本次检查：" + stamp(source.checked_at) : "最近成功：" + (source.last_success_at ? stamp(source.last_success_at) : "尚无") + "；" + source.error;
    $("source-list").append(node);
  });
  render();
}
document.querySelectorAll("[data-kind]").forEach((button) => {
  button.addEventListener("click", () => {
    state.kind = button.dataset.kind;
    state.visible = 24;
    $("task").value = "";
    $("task").disabled = state.kind === "announcement";
    document.querySelectorAll("[data-kind]").forEach((tab) => {
      const selected = tab === button;
      tab.setAttribute("aria-selected", String(selected));
      tab.tabIndex = selected ? 0 : -1;
    });
    render();
  });
  button.addEventListener("keydown", (event) => {
    if (["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) {
      event.preventDefault();
      const next = event.key === "Home" ? $("tab-model") : event.key === "End" ? $("tab-announcement") : document.querySelector('[data-kind]:not([aria-selected="true"])');
      next.click();
      next.focus();
    }
  });
});
["search", "provider", "task", "period"].forEach((id) => $(id).addEventListener(id === "search" ? "input" : "change", () => { state.visible = 24; render(); }));
$("reset").addEventListener("click", reset);
$("empty-reset").addEventListener("click", reset);
$("more").addEventListener("click", () => { state.visible += 24; render(); });
start().catch((error) => {
  $("updated").textContent = "本期日报暂时无法读取";
  $("health-dot").classList.add("warning");
  $("health").textContent = "读取失败";
  $("result-count").textContent = "加载失败";
  showNotice(error.message + "。请稍后刷新，或从 GitHub 仓库查看数据和运行日志。");
});
