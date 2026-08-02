"""把 DeepSeek API 文档（中文版）抓成本地 markdown 知识库。

站点是 Docusaurus，没有 llms.txt，源仓库也不公开，所以走 sitemap → HTML → pandoc。
"""

import re
import subprocess
import time
import urllib.request
from pathlib import Path

BASE = "https://api-docs.deepseek.com"
OUT = Path("/Users/sakuzeng/improve/coding/agent/projects/pai/refs/deepseek-api")
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120 Safari/537.36"


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", errors="replace")


def clean(md: str) -> str:
    # base64 内联图标：纯噪音，一个能有好几 KB
    md = re.sub(r"data:image/[^\s\"')]+", "", md)
    md = re.sub(r"!\[\]\(\s*\)", "", md)
    # pandoc 从 HTML 带出来的裸 div/span 标签
    md = re.sub(r"^\s*</?(?:div|span|img|a|button)[^>]*>\s*$", "", md, flags=re.M)
    lines = md.split("\n")
    # 面包屑 + 移动端 TOC 都在正文标题之前，从第一个 h1 起才是内容
    for i, ln in enumerate(lines):
        if ln.startswith("# "):
            lines = lines[i:]
            break
    md = "\n".join(lines)
    # 页脚的上一页/下一页导航
    md = re.split(r"^#+\s*(?:上一页|下一页)\s*$", md, flags=re.M)[0]
    md = re.sub(r"\n{3,}", "\n\n", md)
    return md.strip() + "\n"


def main() -> None:
    sitemap = fetch(f"{BASE}/sitemap.xml")
    paths = [
        u.replace(BASE, "").strip("/")
        for u in re.findall(r"<loc>(.*?)</loc>", sitemap)
    ]
    paths = sorted(p for p in paths if p)
    print(f"sitemap 共 {len(paths)} 页")

    ok, failed = [], []
    for i, path in enumerate(paths, 1):
        url = f"{BASE}/zh-cn/{path}"
        dest = OUT / f"{path}.md"
        try:
            html = fetch(url)
            m = re.search(r"<article[^>]*>(.*?)</article>", html, re.S)
            if not m:
                failed.append((path, "无 <article>"))
                print(f"[{i:2d}/{len(paths)}] ✗ {path} — 无 <article>")
                continue
            proc = subprocess.run(
                ["pandoc", "-f", "html", "-t", "gfm", "--wrap=none"],
                input=m.group(1), capture_output=True, text=True, check=True,
            )
            md = clean(proc.stdout)
            title = next((l[2:].strip() for l in md.split("\n") if l.startswith("# ")), path)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(f"<!-- 来源: {url} -->\n\n{md}", encoding="utf-8")
            ok.append((path, title, len(md)))
            print(f"[{i:2d}/{len(paths)}] ✓ {path} — {title} ({len(md)} 字符)")
        except Exception as e:  # 单页失败不中断整批
            failed.append((path, str(e)[:80]))
            print(f"[{i:2d}/{len(paths)}] ✗ {path} — {e}")
        time.sleep(0.3)

    index = ["# DeepSeek API 文档（本地快照）", "", f"来源：{BASE}/zh-cn/ ，共 {len(ok)} 页。", ""]
    group = ""
    for path, title, size in ok:
        g = path.split("/")[0] if "/" in path else "（顶层）"
        if g != group:
            group = g
            index += ["", f"## {g}", ""]
        index.append(f"- [{title}]({path}.md) — {size} 字符")
    if failed:
        index += ["", "## 抓取失败", ""] + [f"- {p} — {e}" for p, e in failed]
    (OUT / "INDEX.md").write_text("\n".join(index) + "\n", encoding="utf-8")

    total = sum(s for _, _, s in ok)
    print(f"\n完成：成功 {len(ok)} / 失败 {len(failed)}，合计 {total} 字符 ≈ {total // 4} token")


if __name__ == "__main__":
    main()
