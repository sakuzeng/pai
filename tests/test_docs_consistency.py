"""文档一致性校验（评审 R2#5）：把前置精读机制里机械可判的部分交给代码。

只判三件可判定的事：勾选的前置精读链接必须存在、knowledge 笔记必须登记、
笔记必须带 pai 锚点。「人是否真读了」判不了——诚实边界见 AGENTS.md「知识沉淀」。
"""
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ROADMAP = ROOT / "docs" / "dev" / "roadmap.md"
KNOWLEDGE = ROOT / "knowledge"


def _gitignored(path):
    """刻意不入库的文件（如 knowledge/anna/，R2#1 裁决）在新克隆里不存在，不算断链。"""
    return subprocess.run(
        ["git", "check-ignore", "-q", str(path.relative_to(ROOT))],
        cwd=ROOT, capture_output=True,
    ).returncode == 0


def _notes():
    return [p for p in KNOWLEDGE.rglob("*.md") if p.name != "README.md"]


def test_roadmap_checked_reading_links_exist():
    text = ROADMAP.read_text(encoding="utf-8")
    links = re.findall(r"- \[x\] \[[^\]]+\]\(([^)]+)\)", text)
    assert links, "roadmap 里应存在已勾选的前置精读链接（一个都没有说明格式变了，先修本测试的正则）"
    for link in links:
        target = (ROADMAP.parent / link.split("#")[0]).resolve()
        assert target.is_file() or _gitignored(target), \
            f"roadmap 勾选的前置精读文件不存在且非刻意不入库: {link}"


def test_knowledge_notes_are_registered():
    readme = (KNOWLEDGE / "README.md").read_text(encoding="utf-8")
    notes = _notes()
    assert notes, "knowledge/ 下应存在至少一篇笔记"
    for note in notes:
        rel = note.relative_to(KNOWLEDGE).as_posix()
        assert rel in readme, f"knowledge 笔记未登记进 README 登记表: {rel}"


def test_knowledge_notes_have_pai_anchor():
    for note in _notes():
        head = "\n".join(note.read_text(encoding="utf-8").splitlines()[:10])
        assert "pai 锚点" in head, f"笔记头部缺少「pai 锚点」字段: {note.relative_to(KNOWLEDGE)}"


FEATURES = ROOT / "docs" / "dev" / "features"


def test_feature_dirs_follow_naming_and_archive_rules():
    """功能目录规矩的机器可判部分：命名含立项日期、档案齐、确认节在（讨论质量判不了）。"""
    dirs = [p for p in FEATURES.iterdir() if p.is_dir() and p.name != "_template"]
    assert dirs, "features/ 下应有功能目录"
    for d in dirs:
        assert re.match(r"^\d{2}-\d{8}-.+", d.name), \
            f"功能目录名需为 NN-YYYYMMDD-名称（日期=立项日）: {d.name}"
        readme = d / "README.md"
        assert readme.is_file(), f"功能目录缺档案 README.md: {d.name}"
        text = readme.read_text(encoding="utf-8")
        assert re.search(r"^状态：[^\S\n]*\S", text, re.M), f"档案缺有效状态行: {d.name}"
        assert "候选方案与确认" in text, f"档案缺「候选方案与确认」节: {d.name}"


def test_no_empty_dirs_under_features():
    """禁止空目录占位（含按需创建的 evidence/）。"""
    for d in FEATURES.rglob("*"):
        if d.is_dir():
            assert any(d.iterdir()), f"空目录占位: {d}"


def test_decisions_index_matches_entries():
    """decisions 头部索引与正文条目一一对应——索引是同一事实的第二个家，必须机器钉住。"""
    text = (ROOT / "docs" / "dev" / "decisions.md").read_text(encoding="utf-8")
    body = sorted({int(n) for n in re.findall(r"^(\d+)\. ", text, re.M)})
    index = sorted({int(n) for n in re.findall(r"^\| (\d+) \| ", text, re.M)})
    assert index, "decisions.md 缺头部索引表（| n | 标题 |）"
    assert index == body, f"索引与正文条目漂移：索引 {len(index)} 条 vs 正文 {len(body)} 条"


def test_devlog_milestone_section_is_one_liners():
    """全局 devlog 的唯一合法追加区是「## 里程碑」，一行一条——细节住 features/<NN>/devlog.md。

    背景：里程碑模式 2026-08-09 宣布当天就被违反（长 bullet 继续进全局 devlog），
    证明没有机器校验的格式规矩活不过一天。「一句话写得好不好」判不了，只判单行格式。
    """
    text = (ROOT / "docs" / "dev" / "devlog.md").read_text(encoding="utf-8")
    marker = "\n## 里程碑"          # 认行首标题，不认正文里对它的引用
    assert marker in text, "devlog 缺「## 里程碑」区（2026-08-09 起的唯一合法追加区）"
    for line in text.split(marker, 1)[1].splitlines()[1:]:
        if not line.strip():
            continue
        assert re.match(r"^- \d{4}-\d{2}-\d{2} ", line), \
            f"里程碑区只许「- YYYY-MM-DD 主题——一句话 → 链接」单行条目，违例: {line[:60]}"
