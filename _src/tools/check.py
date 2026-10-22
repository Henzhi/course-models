#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
交付门禁：对 catalog.json 登记的每个模型页做静态与渲染校验。

用法：
    python _src/tools/check.py           # 静态检查（快）
    python _src/tools/check.py --shot    # 追加无头 Chrome 截图（慢，但能证明真的渲染）
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CATALOG = os.path.join(ROOT, "catalog.json")
MAX_KB = 300
LEVELS = {"了解", "理解", "应用"}
REQUIRED = ["id", "subject", "grade", "unit", "section", "title", "file", "template", "duration"]

NODE_CANDIDATES = [
    r"C:/Users/MaHuhu/.workbuddy/binaries/node/versions/22.22.2-6/node.exe",
    shutil.which("node"),
]
CHROME_CANDIDATES = [
    r"C:/Program Files/Google/Chrome/Application/chrome.exe",
    r"C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
]


def first_existing(paths):
    for p in paths:
        if p and os.path.exists(p):
            return p
    return None


def read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def js_syntax_errors(html, node):
    if not node:
        return ["未找到 node，跳过 JS 语法校验"]
    blocks = re.findall(r"<script(?:\s[^>]*)?>(.*?)</script>", html, re.S)
    code = "\n;\n".join(blocks)
    if not code.strip():
        return ["页面内没有脚本"]
    fd, tmp = tempfile.mkstemp(suffix=".js")
    os.close(fd)
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(code)
        r = subprocess.run([node, "--check", tmp], capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        if r.returncode != 0:
            msg = (r.stderr or "").strip().splitlines()
            return ["JS 语法错误: " + (msg[0] if msg else "unknown")]
        return []
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


def check_model(m, node):
    errs = []
    path = os.path.join(ROOT, m["file"])
    if not os.path.exists(path):
        return ["文件不存在: " + m["file"]], path

    html = read(path)
    kb = os.path.getsize(path) / 1024.0

    for key in REQUIRED:
        if not str(m.get(key, "")).strip():
            errs.append("元数据缺少字段: " + key)
    level = m.get("curriculum", {}).get("level")
    if level not in LEVELS:
        errs.append("课标层次不在三档内: %r" % level)

    if kb > MAX_KB:
        errs.append("体积超标: %.1f KB > %d KB" % (kb, MAX_KB))

    if re.search(r"<link[^>]+href=[\"']https?://", html, re.I):
        errs.append("存在外链 <link>")
    if re.search(r"<script[^>]+src=", html, re.I):
        errs.append("存在外链 <script src>")
    if re.search(r"<img[^>]+src=[\"']https?://", html, re.I):
        errs.append("存在外链图片")
    if re.search(r"url\(\s*[\"']?https?://", html, re.I):
        errs.append("CSS 中引用外链资源")
    if "@import" in html:
        errs.append("CSS 使用 @import")

    if "{{" in html:
        errs.append("模板占位符残留")
    if "window.__APP__" not in html:
        errs.append("缺少 window.__APP__ 数据注入")
    if "__SELFTEST__" not in html:
        errs.append("缺少内置自检 __SELFTEST__")

    ids = set(re.findall(r'id="([^"]+)"', html))
    refs = set(re.findall(r'getElementById\("([^"]+)"\)', html))
    for miss in sorted(refs - ids):
        errs.append("getElementById 引用了不存在的 id: " + miss)

    errs.extend(js_syntax_errors(html, node))
    return errs, path


def check_catalog(catalog):
    errs = []
    seen_ids, seen_files = set(), set()
    for m in catalog.get("models", []):
        if m.get("id") in seen_ids:
            errs.append("重复 id: " + m.get("id", "?"))
        seen_ids.add(m.get("id"))
        fp = m.get("file", "").replace("\\", "/")
        if fp in seen_files:
            errs.append("重复 file: " + fp)
        seen_files.add(fp)

    for subj in catalog.get("subjects", []):
        base = os.path.join(ROOT, subj["dir"])
        if not os.path.isdir(base):
            errs.append("学科目录不存在: " + subj["dir"])
            continue
        for dirpath, _, files in os.walk(base):
            for f in files:
                if not f.lower().endswith(".html"):
                    continue
                rel = os.path.relpath(os.path.join(dirpath, f), ROOT).replace(os.sep, "/")
                if rel not in seen_files:
                    errs.append("有文件未在 catalog 登记: " + rel)
    return errs


def shot(path, chrome, outdir):
    if not chrome:
        return "未找到 Chrome/Edge，跳过截图"
    name = os.path.splitext(os.path.basename(path))[0] + ".png"
    out = os.path.join(outdir, name).replace("\\", "/")
    url = "file:///" + path.replace("\\", "/")
    ud = tempfile.mkdtemp(prefix="chromeprof_").replace("\\", "/")
    cmd = [chrome, "--headless=new", "--disable-gpu", "--no-sandbox",
           "--hide-scrollbars", "--user-data-dir=" + ud,
           "--window-size=1600,1000", "--virtual-time-budget=3000",
           "--screenshot=" + out, url]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
    if not os.path.exists(out):
        return "截图失败: " + (r.stderr or "").strip()[:120]
    return "截图 -> " + out


def main():
    catalog = json.loads(read(CATALOG))
    node = first_existing(NODE_CANDIDATES)
    chrome = first_existing(CHROME_CANDIDATES) if "--shot" in sys.argv else None
    outdir = os.path.join(ROOT, "_shots")
    if chrome:
        os.makedirs(outdir, exist_ok=True)

    print("Node:  ", node or "未找到")
    print("Chrome:", chrome or "未找到")
    print("")

    total_errs = 0
    cat_errs = check_catalog(catalog)
    if cat_errs:
        total_errs += len(cat_errs)
        print("[catalog] FAIL")
        for e in cat_errs:
            print("    x " + e)
    else:
        print("[catalog] PASS")

    for m in catalog.get("models", []):
        errs, path = check_model(m, node)
        label = "%s  (%s)" % (m["id"], m["file"])
        if errs:
            total_errs += len(errs)
            print("[model] FAIL  " + label)
            for e in errs:
                print("    x " + e)
        else:
            print("[model] PASS  " + label)
        if chrome and os.path.exists(path):
            msg = shot(path, chrome, outdir)
            print("        " + msg)

    print("")
    if total_errs:
        print("结果：%d 项未通过" % total_errs)
        sys.exit(1)
    print("结果：全部通过")


if __name__ == "__main__":
    main()
