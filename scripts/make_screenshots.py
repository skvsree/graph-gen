#!/usr/bin/env python3
"""Generate the manifest screenshots (static/screenshots/*.png).

These are what Android/desktop Chrome show in the richer install sheet, so they
must look like the real app: same URL scheme, a plotted curve, both form
factors.

  * wide.png    1280x800  (form_factor "wide")
  * narrow.png   720x1280 (form_factor "narrow", portrait)

Run against the LOCAL dev server (default) or the live site:

    /usr/bin/python3 scripts/make_screenshots.py                       # 127.0.0.1:8123
    /usr/bin/python3 scripts/make_screenshots.py https://xy.selviz.in

Needs Playwright for the SYSTEM python3 (the app venv does not have it) plus its
bundled Chromium; set CHROME=/path/to/chrome to override the binary.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

CHROME = os.environ.get(
    "CHROME", "/root/.cache/ms-playwright/chromium-1223/chrome-linux64/chrome"
)
OUT = Path(__file__).resolve().parent.parent / "static" / "screenshots"
# A curve that shows off axes, grid and legend without needing a wide y range.
VIEW = "/?formula=y%3Dsin(x)%2Bcos(2x)&x_min=-10&x_max=10&x_step=0.1"


def shoot(page, path: Path, width: int, height: int, scroll_to_graph: bool) -> None:
    page.set_viewport_size({"width": width, "height": height})
    page.goto(base + VIEW, wait_until="load", timeout=45000)
    page.wait_for_timeout(2500)                      # webfont + async plot settle
    # Wide: keep the header/form/toolbar in shot (that is the app's face — the
    # install sheet shows the top of the page). Narrow: centre the canvas.
    if scroll_to_graph:
        page.evaluate("document.querySelector('#graph').scrollIntoView({block:'center'})")
    else:
        page.evaluate("window.scrollTo(0, 0)")
    page.wait_for_timeout(400)
    page.screenshot(path=str(path))                  # NOT full_page: exact size
    print(f"{path.relative_to(OUT.parent.parent)}  {width}x{height}  {path.stat().st_size} bytes")


if __name__ == "__main__":
    base = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8123").rstrip("/")
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROME, headless=True, args=["--no-sandbox"])
        ctx = browser.new_context(viewport={"width": 1280, "height": 800})
        page = ctx.new_page()
        shoot(page, OUT / "wide.png", 1280, 800, scroll_to_graph=False)
        shoot(page, OUT / "narrow.png", 720, 1280, scroll_to_graph=True)
        browser.close()
