# -*- coding: utf-8 -*-
"""Extract human-readable UI strings from obfuscated JS chunks (single-quote escaped style)."""
import re, io, os

os.makedirs('_analysis', exist_ok=True)
files = {
    'page': 'sim.stackforce.cc/_next/static/chunks/app/page-436aa2d611eaef8a.js',
    'chunk813': 'sim.stackforce.cc/_next/static/chunks/813.a483af6207812705.js',
    'chunk595': 'sim.stackforce.cc/_next/static/chunks/595.37abfba7757430ff.js',
    'chunk117': 'sim.stackforce.cc/_next/static/chunks/117-2ee3bdcd70c3e40c.js',
    'chunk520': 'sim.stackforce.cc/_next/static/chunks/520-eb9aebf56d2f93f7.js',
    'chunk862': 'sim.stackforce.cc/_next/static/chunks/862-cd6ccb43afd19fbd.js',
    'layout': 'sim.stackforce.cc/_next/static/chunks/app/layout-998e3b0ec6d3e0a1.js',
}

SQ = re.compile(r"'((?:[^'\\]|\\.)*)'")
DQ = re.compile(r'"((?:[^"\\]|\\.)*)"')
CJK = re.compile(r'[\u4e00-\u9fff]')
LATIN_TEXT = re.compile(r"^[A-Za-z][A-Za-z0-9 ,.:;!?()/'\-\u00b7]+$")


def decode(s):
    if ('\\x' not in s) and ('\\u' not in s):
        return s
    try:
        t = s.encode('latin-1', 'backslashreplace').decode('unicode_escape')
        return t.encode('latin-1', 'backslashreplace').decode('utf-8', 'ignore')
    except Exception:
        return s


def extract(path):
    if not os.path.exists(path):
        return []
    src = open(path, encoding='utf-8', errors='ignore').read()
    raw = SQ.findall(src) + DQ.findall(src)
    out, seen = [], set()
    for s in raw:
        t = decode(s).strip()
        if len(t) < 2 or len(t) > 150:
            continue
        if CJK.search(t) or (LATIN_TEXT.match(t) and ' ' in t):
            if t not in seen:
                seen.add(t)
                out.append(t)
    return out


total = 0
for tag, path in files.items():
    out = extract(path)
    with io.open('_analysis/ui_strings_%s.txt' % tag, 'w', encoding='utf-8') as f:
        f.write('\n'.join(out))
    total += len(out)
    print(tag, '->', len(out))
print('total', total)
