"""Collect public metadata on GitHub-hosted runners; no model inference or downloads."""
from __future__ import annotations
import hashlib
import gzip
import zlib
import html
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
UTC = timezone.utc
UA = "ai-model-daily/1.0 (+https://github.com/lifeiXiao/ai-model-daily)"
TASKS = {
    "text-generation": ("文本生成", "生成文本、续写内容；具体对话与推理能力见模型卡。"),
    "text2text-generation": ("文本转换", "完成文本到文本的转换任务，适用范围见模型卡。"),
    "image-text-to-text": ("图文理解", "根据图像与文字输入生成文本，可用于视觉问答和图片理解。"),
    "text-to-image": ("图像生成", "根据文字提示生成图像。"),
    "image-to-image": ("图像编辑", "以图像为输入生成或变换图像。"),
    "text-to-video": ("视频生成", "根据文字提示生成视频。"),
    "image-to-video": ("图生视频", "以图像为输入生成视频。"),
    "automatic-speech-recognition": ("语音识别", "将音频中的语音转写为文字。"),
    "text-to-speech": ("语音合成", "将文字转换为语音。"),
    "text-to-audio": ("音频生成", "根据文字提示生成音频。"),
    "audio-text-to-text": ("音频理解", "结合音频与文字输入生成文本。"),
    "feature-extraction": ("向量嵌入", "将输入转换为特征向量，可用于检索等任务。"),
    "sentence-similarity": ("语义匹配", "计算文本之间的语义相似程度。"),
    "text-ranking": ("重排序", "对查询与候选文本的相关性进行排序。"),
    "object-detection": ("目标检测", "检测图像中的目标及其位置。"),
    "image-classification": ("图像分类", "识别图像所属的类别。"),
    "image-segmentation": ("图像分割", "将图像划分为不同目标或区域。"),
    "document-question-answering": ("文档问答", "根据文档内容回答问题。"),
    "visual-question-answering": ("视觉问答", "根据图片内容回答问题。"),
    "any-to-any": ("多模态", "处理多种模态的输入或输出，具体支持范围见模型卡。"),
    "video-text-to-text": ("视频理解", "结合视频与文字输入生成文本。"),
}
MODEL_WORDS = re.compile(
    r"\b(model|models|gpt[\s-]?\d|gemini|claude|llama|deepseek|qwen|mistral|"
    r"gemma|sora|veo|imagen|flux|o[1-9]|reasoning|embedding|multimodal|"
    r"codex|haiku|sonnet|opus|mythos|fable)\b|模型|推理|多模态", re.I)
DATE_PATTERN = re.compile(r"\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
                          r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|"
                          r"Dec(?:ember)?) \d{1,2}, \d{4}\b", re.I)

def iso(value):
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")

def parse_date(value):
    if not value:
        return None
    try:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        try:
            result = parsedate_to_datetime(str(value))
        except (ValueError, TypeError):
            for fmt in ("%b %d, %Y", "%B %d, %Y"):
                try:
                    result = datetime.strptime(str(value), fmt)
                    break
                except ValueError:
                    pass
            else:
                return None
    return result.replace(tzinfo=UTC) if result.tzinfo is None else result.astimezone(UTC)

def plain(value):
    value = re.sub(r"<[^>]*>", " ", str(value or ""))
    return re.sub(r"\s+", " ", html.unescape(value)).strip()

def excerpt(value):
    # A short attributed extract, not a generated or translated summary.
    value = plain(value)
    return " ".join(value.split()[:45])[:300].rstrip()

def decode_body(data, encoding="", max_bytes=8_000_000):
    if encoding == "gzip" or data.startswith(b"\x1f\x8b"):
        data = gzip.decompress(data)
    elif encoding == "deflate":
        data = zlib.decompress(data)
    if len(data) > max_bytes:
        raise ValueError("Decoded response exceeds size limit")
    return data.decode("utf-8-sig", errors="replace")

def request(url, max_bytes=8_000_000):
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*", "Accept-Encoding": "identity"})
            with urllib.request.urlopen(req, timeout=25) as response:
                data = response.read(max_bytes + 1)
                if len(data) > max_bytes:
                    raise ValueError("Response exceeds size limit")
                return decode_body(data, response.headers.get("Content-Encoding", "").lower(), max_bytes)
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            if isinstance(error, urllib.error.HTTPError) and error.code not in (429, 500, 502, 503, 504):
                raise
            if attempt == 2:
                raise
            time.sleep(2 ** (attempt + 1))
    raise RuntimeError("Unreachable")

def stable_id(kind, value):
    return kind + "-" + hashlib.sha256(value.encode()).hexdigest()[:20]

def valid_url(url):
    parts = urllib.parse.urlparse(url)
    return parts.scheme == "https" and bool(parts.hostname) and not parts.username

def model_record(model, source):
    model_id = model.get("id") or model.get("modelId") or ""
    if model_id.split("/")[0].lower() != source["org"].lower():
        return None
    created = parse_date(model.get("createdAt"))
    if not created:
        return None  # Never substitute lastModified for the repository creation date.
    task = model.get("pipeline_tag") or ""
    label, summary = TASKS.get(task, ("其他任务", "官方尚未提供可识别的任务标签，请查看模型卡了解具体功能。"))
    tags = model.get("tags") or []
    card = model.get("cardData") or {}
    if not isinstance(card, dict):
        card = {}
    license_name = card.get("license") or next((x[8:] for x in tags if x.startswith("license:")), "未标注")
    if isinstance(license_name, list):
        license_name = ", ".join(str(x) for x in license_name)
    features = [label]
    for tag, name in (("conversational", "对话"), ("code", "代码"), ("tool-calling", "工具调用")):
        if tag in tags:
            features.append(name)
    return {
        "id": stable_id("model", model_id), "kind": "model", "title": model_id.split("/", 1)[-1],
        "provider": source["name"], "source_id": "hf-" + source["org"],
        "url": "https://huggingface.co/" + urllib.parse.quote(model_id, safe="/"),
        "published_at": iso(created), "date_label": "仓库创建", "task": label,
        "summary": summary, "summary_basis": "Hugging Face 任务标签的中文说明",
        "features": features, "license": str(license_name), "model_id": model_id,
        "downloads": int(model.get("downloads") or 0), "likes": int(model.get("likes") or 0),
        "gated": bool(model.get("gated")), "tags": [str(x) for x in tags[:30]],
    }

def collect_hf(source, limit):
    query = urllib.parse.urlencode({
        "author": source["org"], "sort": "createdAt", "direction": -1,
        "limit": limit, "full": "true", "cardData": "true"
    })
    data = json.loads(request("https://huggingface.co/api/models?" + query))
    if not isinstance(data, list) or not data:
        raise ValueError("Empty or invalid model list")
    records = [r for m in data if (r := model_record(m, source))]
    if not records:
        raise ValueError("No models with valid creation dates")
    return records

def announcement(title, url, date, description, source):
    published = parse_date(date)
    title = plain(title)
    if not title or not published or not valid_url(url) or not MODEL_WORDS.search(title):
        return None
    return {
        "id": stable_id("news", url.rstrip("/")), "kind": "announcement",
        "title": title, "provider": source["name"], "source_id": source["id"],
        "url": url, "published_at": iso(published), "date_label": "公告发布",
        "task": "官方动态", "summary": excerpt(description) or "查看官方原文，了解本次模型或产品更新。",
        "summary_basis": "官方原文节选" if excerpt(description) else "官方公告链接",
        "features": ["官方动态"],
    }

def parse_rss(text, source):
    try:
        root = ET.fromstring(text)
    except ET.ParseError as error:
        raise ValueError(f"Invalid feed content: {text[:80]!r}") from error
    records = []
    nodes = root.findall(".//item")
    atom = "{http://www.w3.org/2005/Atom}"
    if not nodes:
        nodes = root.findall(".//" + atom + "entry")
    for node in nodes:
        def get(name):
            return node.findtext(name) or node.findtext(atom + name) or ""
        link = get("link").strip()
        if not link:
            for anchor in node.findall(atom + "link"):
                if anchor.get("rel", "alternate") == "alternate":
                    link = anchor.get("href", "")
                    break
        result = announcement(get("title"), link, get("pubDate") or get("published") or get("updated"),
                              get("description") or get("summary"), source)
        if result:
            records.append(result)
    if not nodes:
        raise ValueError("RSS/Atom format not recognized")
    return records

class Node:
    def __init__(self, tag="", attrs=None):
        self.tag, self.attrs, self.children = tag, dict(attrs or []), []
    def text(self):
        return " ".join(c if isinstance(c, str) else c.text() for c in self.children)
    def walk(self, tag):
        if self.tag == tag:
            yield self
        for child in self.children:
            if isinstance(child, Node):
                yield from child.walk(tag)

class NewsParser(HTMLParser):
    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
    def __init__(self):
        super().__init__()
        self.root = Node()
        self.stack = [self.root]
    def handle_starttag(self, tag, attrs):
        node = Node(tag, attrs)
        self.stack[-1].children.append(node)
        if tag not in self.VOID:
            self.stack.append(node)
    def handle_startendtag(self, tag, attrs):
        self.stack[-1].children.append(Node(tag, attrs))
    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                break
    def handle_data(self, data):
        self.stack[-1].children.append(data)

def parse_anthropic(text, source):
    parser = NewsParser()
    parser.feed(text)
    records = {}
    # Date and heading are siblings of the link on some layouts.
    for node in parser.root.walk("li"):
        date_match = DATE_PATTERN.search(plain(node.text()))
        if not date_match:
            continue
        anchors = [a for a in node.walk("a") if re.match(r"^/news/[^/?#]+/?$", a.attrs.get("href", ""))]
        for anchor in anchors[:1]:
            title = plain(anchor.text())
            headings = list(anchor.walk("h3")) + list(anchor.walk("h2"))
            if headings:
                title = plain(headings[0].text())
            title = DATE_PATTERN.sub("", title).strip()
            result = announcement(title, urllib.parse.urljoin(source["url"], anchor.attrs["href"]),
                                  date_match.group(), "", source)
            if result:
                records[result["id"]] = result
    if not records:
        raise ValueError("No dated model announcements; HTML layout may have changed")
    return list(records.values())

def merge(previous, incoming, now, days=365):
    cutoff = now - timedelta(days=days)
    result = {}
    for row in previous:
        date = parse_date(row.get("published_at"))
        if date and cutoff <= date <= now + timedelta(days=1):
            result[row["id"]] = row
    for row in incoming:
        date = parse_date(row.get("published_at"))
        if not date or not cutoff <= date <= now + timedelta(days=1):
            continue
        old = result.get(row["id"])
        row = dict(row)
        row["first_seen_at"] = old.get("first_seen_at", iso(now)) if old else iso(now)
        row["last_seen_at"] = iso(now)
        result[row["id"]] = row
    return sorted(result.values(), key=lambda r: (r["published_at"], r["id"]), reverse=True)

def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)

def main():
    now = datetime.now(UTC)
    config = json.loads((ROOT / "config/sources.json").read_text(encoding="utf-8"))
    path = ROOT / "data/catalog.json"
    previous = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"items": [], "sources": []}
    old_sources = {s["id"]: s for s in previous.get("sources", [])}
    pending = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        for source in config["huggingface"]:
            sid = "hf-" + source["org"]
            pending.append((pool.submit(collect_hf, source, config["models_per_source"]),
                            sid, source["name"], "model", "https://huggingface.co/" + source["org"]))
        for source in config["announcements"]:
            def collect(source=source):
                content = request(source["url"])
                return parse_rss(content, source) if source["kind"] == "rss" else parse_anthropic(content, source)
            pending.append((pool.submit(collect), source["id"], source["name"], "announcement", source["url"]))
        incoming, statuses = [], []
        for future, sid, name, kind, url in pending:
            state = {"id": sid, "name": name, "kind": kind, "url": url, "checked_at": iso(now)}
            try:
                rows = future.result()
                incoming.extend(rows)
                state.update(status="ok", count=len(rows), last_success_at=iso(now))
                print(f"OK {sid}: {len(rows)} records")
            except Exception as error:
                state.update(status="error", count=0,
                             last_success_at=old_sources.get(sid, {}).get("last_success_at"),
                             error=f"{type(error).__name__}: {str(error)[:180]}")
                print(f"::warning title=Source unavailable::{sid}: {state['error']}")
            statuses.append(state)
    # A completely broken source family must not look like a successful refresh.
    for family in ("model", "announcement"):
        if not any(s["kind"] == family and s["status"] == "ok" for s in statuses):
            raise RuntimeError(f"All {family} sources failed; previous published data is preserved")
    if not previous.get("items"):
        cutoff = now - timedelta(days=config["initial_window_days"])
        incoming = [r for r in incoming if parse_date(r["published_at"]) >= cutoff]
    items = merge(previous.get("items", []), incoming, now, config["retention_days"])
    if not items:
        raise RuntimeError("No valid records; refusing to replace the catalog")
    day = now.astimezone(ZoneInfo(config["timezone"])).date().isoformat()
    old_ids = {r["id"] for r in previous.get("items", [])}
    newly_seen = [r["id"] for r in items if r["id"] not in old_ids]
    snapshot_path = ROOT / "daily" / f"{day}.json"
    old_snapshot = json.loads(snapshot_path.read_text(encoding="utf-8")) if snapshot_path.exists() else {}
    # Bootstrap import is recorded separately from later newly discovered items.
    bootstrap = not previous.get("items")
    snapshot = {
        "date": day, "updated_at": iso(now), "bootstrap": old_snapshot.get("bootstrap", bootstrap),
        "new_ids": sorted(set(old_snapshot.get("new_ids", [])) | (set(newly_seen) if not bootstrap else set())),
        "imported_ids": old_snapshot.get("imported_ids", newly_seen if bootstrap else []),
        "total": len(items), "healthy_sources": sum(s["status"] == "ok" for s in statuses),
        "source_count": len(statuses),
    }
    data = {
        "schema_version": 1, "generated_at": iso(now), "timezone": config["timezone"],
        "run_url": os.getenv("RUN_URL", ""), "items": items, "sources": statuses,
        "today": snapshot,
        "coverage": "指定官方账号的最新模型仓库与三家厂商的相关公告；不是全网模型全集。",
    }
    write_json(path, data)
    write_json(snapshot_path, snapshot)
    summary = os.getenv("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as handle:
            handle.write(f"## AI 模型日报 · {day}\n\n"
                         f"- 记录：{len(items)}\n- 新发现：{len(snapshot['new_ids'])}\n"
                         f"- 数据源成功：{snapshot['healthy_sources']}/{len(statuses)}\n"
                         f"- 首次导入：{'是' if bootstrap else '否'}\n")
    print(f"Saved {len(items)} records for {day}")

if __name__ == "__main__":
    main()
