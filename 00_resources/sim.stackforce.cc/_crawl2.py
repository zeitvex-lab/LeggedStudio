#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Recursive polite downloader for sim.stackforce.cc public assets.

Seeds: 25 robot example main files (URDF/USD) + lazy chunks + announcement image.
Parses URDF <mesh filename="..."> and DAE initiative/texture refs to enqueue deps.
Saves under out/sim.stackforce.cc preserving URL path structure. Logs JSONL.
"""
import os, re, sys, time, json, ssl, posixpath
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "sim.stackforce.cc")
LOG = os.path.join(HERE, "_dl_log2.jsonl")
DELAY = 0.4
TIMEOUT = 90

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

HDRS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Referer": "https://sim.stackforce.cc/",
}

# folder -> (subdir, urdf filename); subdir None means probe both urdf/ and root
ROBOTS = {
    "宇树A1": ("urdf", "a1.urdf"),
    "go2_description": ("urdf", "go2_description.urdf"),
    "go1_description": ("urdf", "go1.urdf"),
    "aliengo_description": ("urdf", "aliengo.urdf"),
    "b2_description": ("urdf", "b2_description.urdf"),
    "g1_description": ("urdf", "g1_29dof.urdf"),
    "xbot_l": ("urdf", "XBot-L.urdf"),
    "robotamer_qmini": ("urdf", "q1.urdf"),
    "gr1": ("urdf", "gr1t1.urdf"),
    "anymal_b": ("urdf", "anymal_b.urdf"),
    "anymal_c": ("urdf", "anymal_c.urdf"),
    "逐际带脚底板双足": ("urdf", "robot.urdf"),
    "逐际点足": ("urdf", "robot.urdf"),
    "逐际轮足": ("urdf", "robot.urdf"),
    "lite3": ("urdf", "Lite3.urdf"),
    "x30": ("urdf", "X30.urdf"),
    "solo12": ("urdf", "solo12.urdf"),
    "12自由度菠萝狗": ("urdf", "pypydog_6.urdf"),
    "菠萝狗": ("urdf", "Pyapple_urdf.urdf"),
    "SF双足带脚底板": ("urdf", "SF_sole.urdf"),
    "SF双足点足": ("urdf", "SF_bipedal_6.urdf"),
    "SF大轮足": ("urdf", "SF_big_bipedal_wheel.urdf"),
    "SF小轮足": ("urdf", "SF_wheel_bipedal.urdf"),
    "SF舵机四轮足": ("urdf", "sf_robot.urdf"),
}
CLOSED_CHAIN = {
    "anymal-softfoot-q": ["anymal_c_softfoot_q.usd", "anymal_c_softfoot_q_meshes.usd"],
    "simplified-quadruped": ["quadruped_in_world.usd", "quadruped_simplified_meshes.usd"],
}
SEED_URLS = [
    "https://sim.stackforce.cc/_next/static/chunks/726.4e3ad189194e715e.js",
    "https://sim.stackforce.cc/_next/static/chunks/595.37abfba7757430ff.js",
    "https://sim.stackforce.cc/_next/static/chunks/813.a483af6207812705.js",
    "https://sim.stackforce.cc/announcements/simready-mjlab-update-hero-v3.png",
]

def log(obj):
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")

def local_path(url):
    p = urllib.parse.urlparse(url)
    path = urllib.parse.unquote(p.path)
    if not path or path.endswith("/"):
        path += "index.html"
    return os.path.join(OUT, p.netloc, *path.lstrip("/").split("/"))

def fetch(url, method="GET"):
    req = urllib.request.Request(url, headers=HDRS, method=method)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx) as r:
            data = r.read()
            return r.status, data, r.headers.get("Content-Type", "")
    except urllib.error.HTTPError as e:
        return e.code, b"", ""
    except Exception as e:
        return None, b"", str(e)

def download(url):
    dest = local_path(url)
    dest = os.path.normpath(dest)
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        log({"url": url, "status": "cached"})
        return open(dest, "rb").read()
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    code, data, ctype = fetch(url)
    if code == 200:
        with open(dest, "wb") as f:
            f.write(data)
    log({"url": url, "status": code, "size": len(data), "ctype": ctype})
    print(f"[{code}] {len(data):>9}B  {url}")
    time.sleep(DELAY)
    return data if code == 200 else b""

MESH_RE = re.compile(r'filename\s*[:=]\s*["\']([^"\']+)["\']')
TEXTURE_RE = re.compile(r'<init_from>([^<]+)</init_from>')

def crawl_urdf_deps(url, depth=0, folder_prefix=None):
    """Download url; if textual asset file, parse relative refs and enqueue."""
    if depth > 4:
        return
    data = download(url)
    if not data:
        return
    try:
        text = data.decode("utf-8", errors="replace")
    except Exception:
        return
    refs = []
    if url.lower().endswith((".urdf", ".xml")):
        # only mesh/texture refs; skip gazebo plugin <so> refs
        refs = [r for r in MESH_RE.findall(text)
                if re.search(r'\.(dae|stl|obj|glb|gltf|png|jpg|jpeg|mtl|bin)(\?|$)', r, re.I)]
    elif url.lower().endswith(".dae"):
        refs = TEXTURE_RE.findall(text)
    else:
        return
    for ref in refs:
        ref = ref.strip()
        if ref.startswith("package://"):
            # package://pkg_name/meshes/x.dae -> resolve against urdf dir's parent later;
            # the site rewrites package refs to 'meshes/x.dae' relative to robot folder root
            rest = ref[len("package://"):]
            ref = rest.split("/", 1)[1] if "/" in rest else rest
            # package refs: relative to robot folder root -> go through urdf/ dir collapse
            ref = "../" + ref
        elif ref.startswith(("http://", "https://")):
            continue
        # resolve relative to the URDF file's directory (browser URL semantics)
        base_dir = urllib.parse.unquote(urllib.parse.urlparse(url).path.rsplit("/", 1)[0])
        rel = base_dir + "/" + ref
        parts = []
        for seg in rel.replace("\\", "/").split("/"):
            if seg == "..":
                if parts:
                    parts.pop()
            elif seg in (".", ""):
                continue
            else:
                parts.append(seg)
        path = urllib.parse.quote("/".join(parts))
        full = "https://sim.stackforce.cc" + "/" + path
        crawl_urdf_deps(full, depth + 1, folder_prefix=folder_prefix)

def main():
    for u in SEED_URLS:
        download(u)
    for folder, (sub, fn) in ROBOTS.items():
        prefix = urllib.parse.unquote(urllib.parse.quote(folder))
        folder_prefix = f"examples/robots/{folder}"
        url = f"https://sim.stackforce.cc/examples/robots/{urllib.parse.quote(folder)}/{sub}/{urllib.parse.quote(fn)}"
        crawl_urdf_deps(url, folder_prefix=folder_prefix)
    for folder, files in CLOSED_CHAIN.items():
        for fn in files:
            url = f"https://sim.stackforce.cc/examples/closed-chain/{urllib.parse.quote(folder)}/{urllib.parse.quote(fn)}"
            download(url)
    print("DONE")

if __name__ == "__main__":
    main()
