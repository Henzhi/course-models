#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
分视图截图：把模型页切到指定步骤后再截，用于肉眼确认几何（防画歪 / 重叠 / 出画布）。

用法：
    python _src/tools/shots.py 生物/七下/4.4.3-01-心脏与血液循环.html 2 3 4
    python _src/tools/shots.py <html> --keys 2,3,4      # 一次截多张
    python _src/tools/shots.py <html>                   # 只截默认视图

说明：注入键盘事件模拟老师按键（模板都支持数字键跳步），
      --virtual-time-budget 让动画与 setTimeout 都推进完再截。
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUTDIR = os.path.join(ROOT, "_shots")
CHROME_CANDIDATES = [
    r"C:/Program Files/Google/Chrome/Application/chrome.exe",
    r"C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
]

INJECT = (
    "<script>window.addEventListener('load',function(){"
    "setTimeout(function(){document.dispatchEvent("
    "new KeyboardEvent('keydown',{key:'%s',bubbles:true}));},200);});</script>"
)


def first_existing(paths):
    for p in paths:
        if p and os.path.exists(p):
            return p
    return None


def shoot(chrome, html_path, key, name):
    html = open(html_path, "r", encoding="utf-8").read()
    if key:
        html = html.replace("</body>", INJECT % key + "\n</body>")
    fd, tmp = tempfile.mkstemp(suffix=".html")
    os.close(fd)
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(html)

    os.makedirs(OUTDIR, exist_ok=True)
    out = os.path.join(OUTDIR, name + ".png").replace("\\", "/")
    ud = tempfile.mkdtemp(prefix="chromeprof_").replace("\\", "/")
    cmd = [chrome, "--headless=new", "--disable-gpu", "--no-sandbox", "--hide-scrollbars",
           "--user-data-dir=" + ud, "--window-size=1600,1000",
           "--virtual-time-budget=3500", "--enable-logging=stderr",
           "--screenshot=" + out, "file:///" + tmp.replace("\\", "/")]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=90,
                           encoding="utf-8", errors="replace")
        logs = [l for l in (r.stderr or "").splitlines() if "CONSOLE" in l or "ERROR" in l]
        ok = os.path.exists(out)
        print(("  OK  " if ok else "  FAIL ") + out)
        for l in logs[:6]:
            print("       " + l.split("CONSOLE:")[-1][:160])
        return ok
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass
        shutil.rmtree(ud, ignore_errors=True)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    rel = sys.argv[1]
    html_path = os.path.join(ROOT, rel)
    if not os.path.exists(html_path):
        raise SystemExit("找不到页面: " + rel)

    chrome = first_existing(CHROME_CANDIDATES)
    if not chrome:
        raise SystemExit("未找到 Chrome / Edge")

    args = sys.argv[2:]
    keys = []
    if args and args[0] == "--keys":
        keys = [k.strip() for k in args[1].split(",") if k.strip()]
    elif args:
        keys = args

    base = os.path.splitext(os.path.basename(rel))[0]
    ok = shoot(chrome, html_path, None, base + "-view0")
    for k in keys:
        ok = shoot(chrome, html_path, k, base + "-key" + re.sub(r"\W", "_", k)) and ok
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
