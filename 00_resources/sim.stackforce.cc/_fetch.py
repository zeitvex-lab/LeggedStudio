#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Polite sequential downloader: reads URL list, saves with URL directory structure."""
import sys, os, time, urllib.parse, urllib.request, ssl, json

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = BASE
URLS_FILE = os.path.join(BASE, "_urls.txt")
LOG_FILE = os.path.join(BASE, "_dl_log.jsonl")
DELAY = 0.45
TIMEOUT = 60

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Referer": "https://sim.stackforce.cc/",
}

def path_for(url):
    p = urllib.parse.urlparse(url)
    host = p.netloc
    path = p.path
    if not path or path.endswith("/"):
        path = path + "index.html"
    rel = os.path.join(host, path.lstrip("/").replace("/", os.sep))
    full = os.path.join(OUT, rel)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    return full

def main(mode):
    urls = [l.strip() for l in open(URLS_FILE, encoding="utf-8") if l.strip() and not l.startswith("#")]
    log = open(LOG_FILE, "a", encoding="utf-8")
    done = set()
    if os.path.exists(LOG_FILE):
        for line in open(LOG_FILE, encoding="utf-8"):
            try:
                r = json.loads(line)
                if r.get("status") == 200:
                    done.add(r["url"])
            except Exception:
                pass
    for url in urls:
        if url in done:
            continue
        full = path_for(url)
        if os.path.exists(full) and os.path.getsize(full) > 0 and mode != "force":
            log.write(json.dumps({"url": url, "status": "cached", "size": os.path.getsize(full)}) + "\n")
            log.flush()
            continue
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx) as resp:
                data = resp.read()
                code = resp.status
                ctype = resp.headers.get("Content-Type", "")
            if code == 200:
                with open(full, "wb") as f:
                    f.write(data)
            log.write(json.dumps({"url": url, "status": code, "size": len(data), "ctype": ctype}) + "\n")
        except urllib.error.HTTPError as e:
            log.write(json.dumps({"url": url, "status": e.code, "error": str(e)}) + "\n")
        except Exception as e:
            log.write(json.dumps({"url": url, "status": "ERR", "error": str(e)}) + "\n")
        log.flush()
        time.sleep(DELAY)

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "")
