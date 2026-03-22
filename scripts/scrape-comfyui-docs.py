#!/usr/bin/env python3
"""Scrape ComfyUI docs using playwright, then save as markdown."""
import asyncio
import os
import time

DOCS_BASE = "https://docs.comfy.org"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
COMBINED_MD = os.path.join(SCRIPT_DIR, "..", "docs", "comfyui-docs-scraped.md")

PAGES = [
    "/",
    "/get_started/introduction",
    "/get_started/gettingstarted",
    "/essentials/comfyui_server",
    "/essentials/custom_node_overview",
    "/essentials/custom_node_basics",
    "/essentials/custom_node_datatypes",
    "/essentials/custom_node_images_and_masks",
    "/essentials/custom_node_widgets_and_combos",
    "/essentials/custom_node_lifecycle",
    "/essentials/custom_node_lazy_evaluation",
    "/essentials/custom_node_snippets",
    "/essentials/custom_node_tensors",
    "/essentials/custom_node_ui",
    "/essentials/comms_messages",
    "/tutorials/basic/text_to_image",
    "/tutorials/basic/image_to_image",
    "/tutorials/basic/inpainting",
    "/tutorials/basic/upscaling",
    "/tutorials/basic/lora",
    "/tutorials/basic/controlnet",
    "/tutorials/api/getting_started",
    "/tutorials/api/websocket",
    "/tutorials/api/run_workflow",
]

JS_EXTRACT = """() => {
    const main = document.querySelector('main') ||
                 document.querySelector('article') ||
                 document.querySelector('.content') ||
                 document.querySelector('[role="main"]') ||
                 document.body;
    const clone = main.cloneNode(true);
    const remove = 'nav, aside, footer, .sidebar, .toc, script, style';
    clone.querySelectorAll(remove).forEach(el => el.remove());
    return clone.innerText;
}"""


async def scrape_all():
    from playwright.async_api import async_playwright

    all_content = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        for i, path in enumerate(PAGES):
            url = f"{DOCS_BASE}{path}"
            print(f"[{i+1}/{len(PAGES)}] {url}")
            try:
                await page.goto(url, wait_until="networkidle", timeout=30000)
                await page.wait_for_timeout(2000)
                content = await page.evaluate(JS_EXTRACT)
                title = await page.title()

                if content and len(content.strip()) > 100:
                    all_content.append({
                        "title": title,
                        "url": url,
                        "path": path,
                        "content": content.strip(),
                    })
                    print(f"  OK: {len(content)} chars")
                else:
                    print(f"  SKIP: too short ({len(content.strip())} chars)")
            except Exception as e:
                print(f"  ERROR: {e}")

        await browser.close()

    os.makedirs(os.path.dirname(COMBINED_MD), exist_ok=True)
    with open(COMBINED_MD, "w", encoding="utf-8") as f:
        f.write("# ComfyUI Official Documentation\n\n")
        f.write(f"Scraped on {time.strftime('%Y-%m-%d')} from {DOCS_BASE}\n\n")
        for item in all_content:
            f.write(f"## {item['title']}\n\n")
            f.write(f"**Source:** {item['url']}\n\n")
            f.write(item["content"][:5000] + "\n\n---\n\n")

    size = os.path.getsize(COMBINED_MD)
    print(f"\nSaved {len(all_content)} pages to {COMBINED_MD}")
    print(f"Total size: {size} bytes")
    return all_content


if __name__ == "__main__":
    results = asyncio.run(scrape_all())
    print(f"\nDone: {len(results)} pages scraped")
