"""文档一致性校验（评审 R2#5）：把前置精读机制里机械可判的部分交给代码。

只判三件可判定的事：勾选的前置精读链接必须存在、knowledge 笔记必须登记、
笔记必须带 pai 锚点。「人是否真读了」判不了——诚实边界见 AGENTS.md「知识沉淀」。
"""
import re
import subprocess

import pytest
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


RETROSPECTIVE_RULE_DATE = "20260810"      # 「交付即复盘」立规之日（features/README 规矩 7）
DELIVERED = ("已交付", "已验收")


def test_delivered_features_have_a_retrospective():
    """交付即复盘（2026-08-10 用户裁决）：状态到「已交付」就必须有 复盘.md。

    立项日早于立规之日的档案不追溯——与「既有历史条目冻结不迁移」同一处理，
    目录名里就带着立项日，所以这条豁免是机器可判的，不靠记性。
    「复盘写得好不好」判不了，只判两件事：文件在不在、是不是还剩着模板占位。
    """
    for d in sorted(p for p in FEATURES.iterdir() if p.is_dir() and p.name != "_template"):
        date = d.name.split("-")[1]
        if date < RETROSPECTIVE_RULE_DATE:
            continue
        status = re.search(r"^状态：[^\S\n]*(\S+)", (d / "README.md").read_text(encoding="utf-8"), re.M)
        if not status or not status.group(1).startswith(DELIVERED):
            continue

        retro = d / "复盘.md"
        assert retro.is_file(), f"{d.name} 已交付却没有 复盘.md（features/README 规矩 7）"
        text = retro.read_text(encoding="utf-8")
        assert "TEMPLATE-PLACEHOLDER" not in text, f"{d.name} 的 复盘.md 还是模板占位"
        assert "## 我现在质疑什么" in text, \
            f"{d.name} 的 复盘.md 缺「我现在质疑什么」节——这一节是必答，留空视为没做"


def test_status_reports_the_current_test_count(request):
    """STATUS 的测试数字漂了三次（R#2 是「严重」级别的旧账，2026-08-10 又漂两次）。

    人肉对账靠不住：每次补完一个漏就该回头改 STATUS，而那正是最容易忘的一步。
    `testscollected` 是**选中**的用例数（不含 deselected），全绿时恰等于 passed 数。
    跑子集时这个数当然对不上，所以只在完整跑（无 -k、无显式路径）时校验。
    """
    # 只认标准入口 `./test.sh`（它带 -m "not llm"）：裸跑 pytest 时那 3 条 llm 测试是
    # **skipped**（算进 collected），带 marker 时是 **deselected**（不算），两者差 3。
    # STATUS 记的是 ./test.sh 的数字，所以对账也只在那个口径下做。
    if (request.config.option.keyword
            or request.config.args != ["tests"]
            or request.config.option.markexpr != "not llm"):
        pytest.skip("只在标准入口 ./test.sh 的口径下对账")

    text = (ROOT / "docs" / "dev" / "STATUS.md").read_text(encoding="utf-8")
    # 不认加粗：AGENTS.md 的 Markdown 规约禁掉了 `**…**`，而这条对账原先
    # 硬要求 `**N passed`——规约一改，机器校验当场失灵且报的是「找不到数字」，
    # 与真正的漂移长得一样。校验点是那个数字，不是它的字重。
    m = re.search(r"(\d+) passed", text)
    assert m, "STATUS 里应有「N passed」这样的测试数字"
    assert int(m.group(1)) == request.session.testscollected, (
        f"STATUS 写着 {m.group(1)} passed，实际选中 {request.session.testscollected} 条——"
        "补完漏别忘了回头改 STATUS"
    )


def test_feature_archives_declare_their_branches():
    """一个需求跨多条分支是常态，而事后用 git 推不出「在哪条上做的」——分支线性叠时
    `git branch --contains` 会把所有分支都列出来。所以必须当时写进档案。

    2026-08-10 的实证：05-repl 的 8 个 task 在 feat/repl、五个补漏在 feat/memory、
    conftest 回归修在 main，而档案里只写着「分支 feat/repl」——那行字是错的。
    立项日早于本规矩的档案不追溯（同复盘规矩的处理）。
    """
    for d in sorted(p for p in FEATURES.iterdir() if p.is_dir() and p.name != "_template"):
        text = (d / "README.md").read_text(encoding="utf-8")
        m = re.search(r"^分支：[^\S\n]*(\S.*)$", text, re.M)
        assert m, f"{d.name} 的档案缺「分支：」字段（features/README 规矩 2.5）"
        assert len(m.group(1).strip()) > 4, f"{d.name} 的「分支：」字段太空洞"


# 与提交类型共用一套词汇表（AGENTS.md「代码」一节）——两边分家就会出现
# 「feat 还是 feature」这种每次都要想一下的问题
BRANCH_PREFIXES = ("feat", "fix", "perf", "refactor", "docs", "test", "chore")


def test_declared_branches_follow_the_naming_convention():
    """分支前缀**复用提交类型**（AGENTS.md「代码」一节），不另立一套词汇表。

    只校验形状（前缀在允许集合内、全小写连字符），不校验 `<NN>` 编号——
    走 `!小修` 通道的改动没有档案，编号无从谈起。`main` 显式放行。
    """
    for d in sorted(p for p in FEATURES.iterdir() if p.is_dir() and p.name != "_template"):
        text = (d / "README.md").read_text(encoding="utf-8")
        line = re.search(r"^分支：[^\S\n]*(.*)$", text, re.M).group(1)
        for name in re.findall(r"`([^`]+)`", line):
            if name == "main":
                continue
            assert re.match(r"^(%s)/[a-z0-9][a-z0-9-]*$" % "|".join(BRANCH_PREFIXES), name), (
                f"{d.name} 声明的分支 {name!r} 不合规约：应为 <类型>/<描述>，"
                f"类型取 {list(BRANCH_PREFIXES)}，描述全小写连字符"
            )


PROCESS_RULE_DATE = "20260811"      # 「档案头部必有流程字段」立规之日（features/README 规矩 9）


def test_feature_archives_declare_their_process():
    """spec/plan 只在走全链路时才有，中等改动可以省——**但省了要说是省的**。

    起因：2026-08-11 用户问「15 这个没有 plan 吗」。按规矩它不算违规，
    可档案里没写「为什么没有」，于是「选了中等改动通道」与「漏了」看起来一模一样。
    机器判不了「这条流程选得对不对」，只判「有没有把选择写下来」。
    """
    for d in sorted(p for p in FEATURES.iterdir() if p.is_dir() and p.name != "_template"):
        if d.name.split("-")[1] < PROCESS_RULE_DATE:
            continue
        text = (d / "README.md").read_text(encoding="utf-8")
        m = re.search(r"^流程：[^\S\n]*(\S.*)$", text, re.M)
        assert m, f"{d.name} 的档案缺「流程：」字段（features/README 规矩 9）"
        assert len(m.group(1).strip()) > 6, f"{d.name} 的「流程：」字段太空洞"


def test_full_chain_archives_actually_have_a_spec_and_plan():
    """声明走了全链路就得拿得出 spec 与 plan——否则这个字段也成了自说自话。"""
    for d in sorted(p for p in FEATURES.iterdir() if p.is_dir() and p.name != "_template"):
        if d.name.split("-")[1] < PROCESS_RULE_DATE:
            continue
        line = re.search(r"^流程：[^\S\n]*(.*)$", (d / "README.md").read_text(encoding="utf-8"), re.M)
        if "全链路" not in line.group(1) or "待定" in line.group(1):
            continue
        for required in ("spec.md", "plan.md"):
            assert (d / required).is_file(), \
                f"{d.name} 声明走了全链路，却没有 {required}"


# ---- e2e 分层：快循环要跑得起来（15 遗留）----


def test_e2e_files_are_recognized_by_the_marking_rule():
    """规则是机械的（文件名以 test_e2e_ 开头），不靠每个文件自觉挂标记——
    自觉的那种漏一个不会红，而漏掉的后果是快循环里混进一条 pty e2e。"""
    from conftest import is_e2e_path

    assert is_e2e_path("/repo/tests/test_e2e_tui.py")
    assert is_e2e_path("tests/test_e2e_mouse.py")
    assert not is_e2e_path("tests/test_loop.py")
    assert not is_e2e_path("tests/test_tui_app.py")     # 组件测试不是 e2e


def test_every_collected_e2e_test_carries_the_marker(request):
    """真的落到 item 上了没有。只在收集范围里含 e2e 文件时才有内容
    （`-k` 子集跑时这条是空转，如实声明）。"""
    from conftest import is_e2e_path

    missing = [item.nodeid for item in request.session.items
               if is_e2e_path(str(item.fspath)) and "e2e" not in item.keywords]
    assert missing == [], f"这些 e2e 没拿到标记：{missing}"


# ---- 依赖方向：tui 不许反向依赖 modes（12 T1）----


def test_tui_modules_do_not_depend_on_modes_except_the_known_residue():
    """宽度原语此前住在 `modes/statusline.py`，而 `pai/tui/` 九个模块都要用它——
    tui → modes 的反向依赖（无环，但方向反了：宽度是 TUI 的地基，不是状态行的私产）。
    搬进 `tui/width.py` 之后这条方向该是干净的。

    唯一允许的残余是 `_preview`（工具参数预览）：statusline 与 dock 共用，
    它不是宽度原语，搬进 width.py 是错的家——单独登记在 TODO 里。
    """
    import ast
    from pathlib import Path

    tui_dir = Path(__file__).resolve().parent.parent / "src" / "pai" / "tui"
    offenders = []
    for path in sorted(tui_dir.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("pai.modes"):
                names = {a.name for a in node.names}
                if names - {"_preview"}:
                    offenders.append(f"{path.name}: {node.module} → {sorted(names)}")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("pai.modes"):
                        offenders.append(f"{path.name}: import {alias.name}")
    assert offenders == [], "tui 不该反向依赖 modes：\n" + "\n".join(offenders)
