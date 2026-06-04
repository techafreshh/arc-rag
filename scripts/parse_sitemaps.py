import argparse
import json
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import httpx

SITEMAP_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
(PROJECT_DIR / "data").mkdir(exist_ok=True)


SOURCES = {
    "arcpro": {
        "sitemap_entry": "https://doc.esri.com/sitemap.xml",
        "guide_filters": ["/arcgis-pro/", "/en/arcgis-pro/"],
        "output": str(PROJECT_DIR / "data/arcpro_urls.json"),
        "checkpoint": str(PROJECT_DIR / "data/.checkpoint_arcpro_urls.json"),
        "path_filter": "/en/arcgis-pro/",
        "exclude_filters": ["/sdk/"],
        "delay": 0.5,
    },
    "arcmap": {
        "sitemap_entry": "http://desktop.arcgis.com/sitemap_index.xml",
        "guide_filters": ["/en/arcmap/latest/"],
        "output": str(PROJECT_DIR / "data/arcmap_urls.json"),
        "checkpoint": str(PROJECT_DIR / "data/.checkpoint_arcmap_urls.json"),
        "path_filter": "/en/arcmap/latest/",
        "exclude_filters": [],
        "delay": 1.0,
    },
}

def fetch_xml(url: str, timeout: float = 15.0, retries: int = 2) -> str | None:
    last_error = None
    for attempt in range(retries + 1):
        try:
            resp = httpx.get(url, follow_redirects=True, timeout=timeout)
            resp.raise_for_status()
            return resp.text
        except Exception as e:
            last_error = e
            if attempt < retries:
                time.sleep(2)
    print(f" FAILED: {last_error}")
    return None


def should_include(url: str, path_filter: str, exclude_filters: list[str]) -> bool:
    if path_filter not in url:
        return False
    for exclude in exclude_filters:
        if exclude in url:
            return False
    return True


def load_checkpoint(path: str) -> tuple[set[str], set[str]]:
    checkpoint_file = Path(path)
    if checkpoint_file.exists():
        data = json.loads(checkpoint_file.read_text())
        if isinstance(data, dict):
            return set(data.get("urls", [])), set(data.get("done_sitemaps", []))
        return set(data), set()
    return set(), set()


def save_checkpoint(path: str, urls: set[str], done_sitemaps: set[str]):
    Path(path).write_text(json.dumps({
        "urls": sorted(urls),
        "done_sitemaps": sorted(done_sitemaps),
    }, indent=2))


def parse(source: str):
    config = SOURCES[source]
    path_filter = config["path_filter"]
    exclude_filters = config["exclude_filters"]
    guide_filters = config["guide_filters"]
    delay = config["delay"]

    all_urls, done_sitemaps = load_checkpoint(config["checkpoint"])
    if all_urls:
        print(f"[{source}] Resuming from checkpoint: {len(all_urls)} URLs, {len(done_sitemaps)} sitemaps done")

    to_visit: list[tuple[str, int]] = [(config["sitemap_entry"], 0)]
    visited: set[str] = set()

    leaf_count = 0

    while to_visit:
        url, depth = to_visit.pop(0)
        if url in visited:
            continue
        visited.add(url)

        indent = "  " * (depth + 1)
        short = url.split("/")[-1] if "/" in url else url

        if depth > 0 and url in done_sitemaps:
            print(f"[{source}] [{depth}] {indent}{short} -> already processed, skipping")
            continue

        print(f"[{source}] [{depth}] {indent}{short}", end="", flush=True)

        xml_text = fetch_xml(url)
        if xml_text is None:
            continue

        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as e:
            import re
            cleaned = re.sub(r'&(?!amp;|lt;|gt;|quot;|apos;|#\d+;|#x[0-9a-fA-F]+;)\S+?;', '&amp;', xml_text)
            try:
                root = ET.fromstring(cleaned)
            except ET.ParseError:
                print(f" -> XML parse error (unrecoverable): {e}")
                continue

        sub_sitemaps: list[str] = []
        page_urls: list[str] = []

        for el in root:
            loc_el = el.find(f"{{{SITEMAP_NS}}}loc")
            if loc_el is None or not loc_el.text:
                continue
            target = loc_el.text.strip()
            if el.tag == f"{{{SITEMAP_NS}}}sitemap":
                sub_sitemaps.append(target)
            elif el.tag == f"{{{SITEMAP_NS}}}url":
                page_urls.append(target)

        if page_urls:
            before = len(all_urls)
            for pu in page_urls:
                if should_include(pu, path_filter, exclude_filters):
                    all_urls.add(pu)
            added = len(all_urls) - before
            done_sitemaps.add(url)
            leaf_count += 1
            print(f" -> {added} new URLs (filtered from {len(page_urls)}), total: {len(all_urls)}")
            time.sleep(delay)
        elif sub_sitemaps:
            matching = [s for s in sub_sitemaps if any(f in s for f in guide_filters)]
            if matching:
                print(f" -> {len(matching)} matching sub-sitemaps")
                for s in matching:
                    if s not in visited:
                        to_visit.append((s, depth + 1))
            else:
                print(f" -> no matching sub-sitemaps ({len(sub_sitemaps)} total), skipping")
        else:
            print(" -> empty sitemap, skipping")

        if leaf_count > 0 and leaf_count % 5 == 0:
            save_checkpoint(config["checkpoint"], all_urls, done_sitemaps)
            print(f"[{source}] Checkpoint saved: {len(all_urls)} URLs, {len(done_sitemaps)} sitemaps done")

    save_checkpoint(config["checkpoint"], all_urls, done_sitemaps)

    output_path = Path(config["output"])
    output_path.write_text(json.dumps(sorted(all_urls), indent=2))
    print(f"[{source}] Done. {len(all_urls)} URLs from {leaf_count} leaf sitemaps -> {config['output']}")


def main():
    parser = argparse.ArgumentParser(description="Parse ArcGIS documentation sitemaps")
    parser.add_argument(
        "--source",
        required=True,
        choices=["arcpro", "arcmap"],
        help="Which documentation source to parse",
    )
    args = parser.parse_args()
    parse(args.source)


if __name__ == "__main__":
    main()
