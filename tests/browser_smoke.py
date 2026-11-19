"""UI checks executed only on a GitHub-hosted runner."""
import copy
import functools
import http.server
import json
import threading
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
data = json.loads((ROOT / "dist/data/catalog.json").read_text(encoding="utf-8"))
handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT / "dist"))
server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
url = f"http://127.0.0.1:{server.server_port}/"
out = ROOT / "test-results"
out.mkdir(exist_ok=True)
try:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1100}, device_scale_factor=1)
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(url)
        expect(page.locator(".card").first).to_be_visible()
        expect(page.locator("#stat-models")).not_to_have_text("—")
        assert int(page.locator("#stat-models").inner_text()) > 0
        assert int(page.locator("#stat-news").inner_text()) > 0
        title = page.locator(".card h3").first.inner_text()
        page.locator("#search").fill(title)
        expect(page.locator(".card h3").first).to_have_text(title)
        page.locator("#search").fill("__no_match_7a783bf1__")
        expect(page.locator("#empty")).to_be_visible()
        page.locator("#empty-reset").click()
        expect(page.locator(".card").first).to_be_visible()
        provider = next(row["provider"] for row in data["items"] if row["kind"] == "model")
        page.select_option("#provider", provider)
        for node in page.locator(".card .provider").all():
            assert provider in node.inner_text()
        page.locator("#reset").click()
        page.locator("#tab-announcement").click()
        expect(page.locator("#task")).to_be_disabled()
        expect(page.locator(".card").first).to_be_visible()
        expect(page.locator("#kind-note")).to_contain_text("官方标题")
        page.locator("#tab-model").click()
        page.locator("#period").select_option("90")
        page.evaluate("window.scrollTo({top: 0, behavior: 'instant'})")
        page.screenshot(path=str(out / "desktop.png"))
        page.set_viewport_size({"width": 390, "height": 844})
        page.evaluate("window.scrollTo({top: 0, behavior: 'instant'})")
        page.screenshot(path=str(out / "mobile.png"))
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        hostile = copy.deepcopy(data)
        first = next(row for row in hostile["items"] if row["kind"] == "model")
        first["title"] = '<img src=x onerror="window.__injected=1">'
        first["published_at"] = data["generated_at"]
        page.route("**/data/catalog.json", lambda route: route.fulfill(
            status=200, content_type="application/json", body=json.dumps(hostile)))
        page.reload()
        page.locator("#search").fill("onerror")
        expect(page.locator(".card h3").first).to_contain_text("<img")
        assert page.locator("#results img").count() == 0
        assert page.evaluate("window.__injected") is None
        assert not errors, errors
        browser.close()
        print("Passed: real data, search, filters, tabs, empty state, mobile overflow, XSS safety.")
finally:
    server.shutdown()
