"""Fetch public research pages and retain URL, text, links and retrieval time."""
import argparse
import concurrent.futures
import datetime
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET


class Extractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.skip = 0
        self.parts = []
        self.links = []
        self.anchor = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ("script", "style", "noscript", "svg"):
            self.skip += 1
        if not self.skip:
            if tag in ("p", "div", "article", "section", "br", "li", "h1", "h2", "h3", "tr"):
                self.parts.append("\n")
            if tag == "a":
                self.anchor = [attrs.get("href", ""), []]

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "svg"):
            self.skip = max(0, self.skip - 1)
        if tag == "a" and self.anchor:
            url, words = self.anchor
            self.links.append({"text": "".join(words).strip(), "url": url})
            self.anchor = None

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)
            if self.anchor:
                self.anchor[1].append(data)


def fetch(item):
    url = item.get("url") or "https://www.bing.com/search?" + urllib.parse.urlencode({"q": item["query"], "format": "rss"})
    result = {"id": item["id"], "url": url, "query": item.get("query"), "retrieved_utc": datetime.datetime.now(datetime.timezone.utc).isoformat()}
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36", "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7"})
        with urllib.request.urlopen(request, timeout=30) as response:
            data = response.read(5_000_000)
            result["final_url"] = response.url
            encoding = response.headers.get_content_charset()
        if not encoding:
            match = re.search(br'charset\s*=\s*["\x27]?([a-zA-Z0-9_-]+)', data[:8000])
            encoding = match.group(1).decode() if match else "utf-8"
        html = data.decode(encoding, errors="replace")
        cache = Path(__file__).parent / "sources"
        cache.mkdir(exist_ok=True)
        (cache / (item["id"] + ".html")).write_text(html, encoding="utf-8")
        if "<rss" in html[:500]:
            root = ET.fromstring(html)
            result["results"] = [{key: node.findtext(key) for key in ("title", "link", "description", "pubDate")} for node in root.findall("./channel/item")]
        else:
            parser = Extractor()
            parser.feed(html)
            result["text"] = "\n".join(line.strip() for line in re.sub(r"[ \t\r\f\v]+", " ", "".join(parser.parts)).splitlines() if line.strip())
            result["links"] = parser.links
        (cache / (item["id"] + ".json")).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as error:
        result["error"] = str(error)
        result["final_url"] = getattr(error, "url", url)
        cache = Path(__file__).parent / "sources"
        cache.mkdir(exist_ok=True)
        (cache / (item["id"] + ".json")).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("batch", type=Path)
    parser.add_argument("--limit", type=int, default=16000)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()
    items = json.loads(args.batch.read_text(encoding="utf-8"))
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        for result in pool.map(fetch, items):
            if args.quiet:
                print(json.dumps({"id": result["id"], "error": result.get("error"), "text_length": len(result.get("text", "")), "results": len(result.get("results", []))}, ensure_ascii=False), flush=True)
                continue
            if "text" in result:
                result["text"] = result["text"][:args.limit]
                result.pop("links", None)
            print(json.dumps(result, ensure_ascii=False), flush=True)
