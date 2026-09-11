# -*- coding: utf-8 -*-
import urllib.request

try:
    with urllib.request.urlopen("http://127.0.0.1:8765/api/health", timeout=5) as r:
        print("health:", r.status, r.read(120))
except Exception as exc:
    print("server not ready:", exc)
