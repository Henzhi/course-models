#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
构建脚本：模板 + 内容数据 -> 单文件 HTML，并重建总览页。

用法：
    python _src/tools/build.py             # 构建全部
    python _src/tools/build.py --only bio-7a-1.2.2-01
"""

import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TPL_DIR = os.path.join(ROOT, "_src", "tpl")
DATA_DIR = os.path.join(ROOT, "_src", "data")
CATALOG = os.path.join(ROOT, "catalog.json")

GRADE_NAME = {
    "七上": "七年级上册", "七下": "七年级下册",
    "八上": "八年级上册", "八下": "八年级下册",
    "九上": "九年级上册", "九下": "九年级下册",
    "九全": "九年级全一册",
}


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_text(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def build_model(model):
    mid = model["id"]
    subject = model["subject"]
    tpl_path = os.path.join(TPL_DIR, model["template"] + ".html")
    data_path = os.path.join(DATA_DIR, subject, mid + ".json")

    if not os.path.exists(tpl_path):
        raise SystemExit("模板不存在: " + tpl_path)
    if not os.path.exists(data_path):
        raise SystemExit("内容数据不存在: " + data_path)

    tpl = open(tpl_path, "r", encoding="utf-8").read()
    data = load_json(data_path)

    cur = model.get("curriculum", {})
    repl = {
        "PAGE_TITLE": "%s · %s · %s" % (model["title"], model["grade"], subject),
        "TITLE": model["title"],
        "GRADE": model["grade"],
        "SECTION": "%s · %s" % (model.get("unit", ""), model.get("section", "")),
        "SUBTITLE": model.get("subtitle", ""),
        "LEVEL": cur.get("level", "未标注"),
        "DURATION": model.get("duration", ""),
        "DATA": json.dumps(data, ensure_ascii=False, separators=(",", ":")),
    }
    for key, val in repl.items():
        tpl = tpl.replace("{{%s}}" % key, val)

    left = re.findall(r"\{\{[A-Z_]+\}\}", tpl)
    if left:
        raise SystemExit("模板占位符未替换: %s (%s)" % (mid, ", ".join(sorted(set(left)))))

    out = os.path.join(ROOT, model["file"])
    write_text(out, tpl)
    return out


def build_index(catalog):
    tpl = open(os.path.join(TPL_DIR, "index.html"), "r", encoding="utf-8").read()
    models = catalog["models"]

    chunks = []
    total = 0
    for subj in catalog["subjects"]:
        for grade in subj["grades"]:
            items = [m for m in models if m["subject"] == subj["key"] and m["grade"] == grade]
            total += len(items)
            rows = []
            for m in items:
                cur = m.get("curriculum", {})
                tags = "<span>%s</span>" % esc(m.get("duration", ""))
                tags += '<span class="g">%s</span>' % esc(cur.get("level", "未标注"))
                for st in m.get("stage", []):
                    tags += "<span>%s</span>" % esc(st)
                search = " ".join([
                    m.get("section", ""), m.get("topic", ""), m.get("title", ""),
                    m.get("unit", ""), " ".join(m.get("points", [])),
                    " ".join(m.get("misconceptions", [])),
                ])
                rows.append(
                    '      <a class="card" href="{href}" data-text="{search}">\n'
                    '        <div class="sec">{sec} · {tpl}</div>\n'
                    '        <h3>{title}</h3>\n'
                    '        <p>{sub}</p>\n'
                    '        <div class="meta">{tags}</div>\n'
                    '      </a>'.format(
                        href=esc(m["file"].replace(os.sep, "/")),
                        search=esc(search),
                        sec=esc(m.get("section", "")),
                        tpl=esc(m.get("template", "")),
                        title=esc(m.get("title", "")),
                        sub=esc(m.get("subtitle", "")),
                        tags=tags,
                    )
                )
            if rows:
                body = '    <div class="grid">\n' + "\n".join(rows) + "\n    </div>"
            else:
                body = ('    <div class="empty">暂无模型 —— 这一册的精选知识点开工后，会在这里出现。</div>')
            chunks.append(
                '  <section class="grade">\n'
                '    <div class="g-head"><h2>%s</h2><span class="n">%d 个模型</span></div>\n'
                '%s\n'
                '  </section>' % (esc(GRADE_NAME.get(grade, grade)), len(items), body)
            )

    html = tpl.replace("{{SECTIONS}}", "\n\n".join(chunks))
    html = html.replace("{{TEXTBOOK}}", esc(catalog.get("textbook", "")))
    html = html.replace("{{COUNT}}", "共 %d 个模型" % total)

    subjects = catalog.get("subjects", [])
    site_title = ("初中%s · 教学模型" % subjects[0]["key"]) if len(subjects) == 1 else "初中教学模型"
    html = html.replace("{{SITE_TITLE}}", esc(site_title))

    left = re.findall(r"\{\{[A-Z_]+\}\}", html)
    if left:
        raise SystemExit("总览页占位符未替换: " + ", ".join(sorted(set(left))))

    write_text(os.path.join(ROOT, "index.html"), html)
    return total


def main():
    catalog = load_json(CATALOG)
    only = None
    if "--only" in sys.argv:
        only = sys.argv[sys.argv.index("--only") + 1]

    built = []
    for m in catalog["models"]:
        if only and m["id"] != only:
            continue
        built.append(build_model(m))

    total = build_index(catalog)

    print("已构建 %d 个模型页：" % len(built))
    for p in built:
        rel = os.path.relpath(p, ROOT).replace(os.sep, "/")
        size = os.path.getsize(p)
        print("  %-58s %6.1f KB" % (rel, size / 1024.0))
    print("总览页 index.html 已重建，共登记 %d 个模型。" % total)


if __name__ == "__main__":
    main()
