"""方案门禁的判定测试——门禁必须带测试（anna 教训第一条，knowledge/anna 短板节）。

注入已知错误（状态未拍板、无 .active、档案缺失）断言真会拦，且合法路径不误拦。
"""
import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "design_gate", Path(__file__).resolve().parent.parent / "guards" / "design_gate.py")
design_gate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(design_gate)
decide = design_gate.decide

ARCHIVE_OK = "# 03-x\n状态：已拍板\n"
ARCHIVE_DRAFT = "# 03-x\n状态：讨论中\n"


def test_non_edit_tools_pass():
    assert decide("Bash", "src/pai/loop.py", None, None) == ("allow", "")
    assert decide("Read", "src/pai/loop.py", None, None) == ("allow", "")


def test_unguarded_paths_pass():
    d, _ = decide("Edit", "docs/dev/TODO.md", None, None)
    assert d == "allow"
    d, _ = decide("Write", "knowledge/inbox.md", None, None)
    assert d == "allow"
    assert decide("Edit", "", None, None)[0] == "allow"  # 项目外/无路径不管


def test_no_active_denies_src_edit():
    d, reason = decide("Edit", "src/pai/core/loop.py", None, None)
    assert d == "deny" and ".active" in reason


def test_empty_active_denies():
    assert decide("Write", "tests/test_x.py", "  \n", None)[0] == "deny"


def test_bang_prefix_allows_with_trace():
    assert decide("Edit", "src/pai/cli.py", "!小修:修 typo\n", None) == ("allow", "")


def test_missing_archive_denies():
    d, reason = decide("Edit", "src/pai/cli.py", "03-x\n", None)
    assert d == "deny" and "README.md 不存在" in reason


def test_unapproved_status_denies():
    d, reason = decide("Edit", "src/pai/cli.py", "03-x\n", ARCHIVE_DRAFT)
    assert d == "deny" and "讨论中" in reason and "不要代替用户拍板" in reason


def test_missing_status_line_denies():
    assert decide("Edit", "src/pai/cli.py", "03-x\n", "# 没有状态行\n")[0] == "deny"


def test_approved_and_later_statuses_allow():
    for status in ("已拍板", "实现中", "已交付", "已验收"):
        text = "# 03-x\n状态：%s（备注）\n" % status
        assert decide("Edit", "src/pai/cli.py", "03-x\n", text) == ("allow", "")


def test_real_active_pointer_is_consistent():
    """真实 .active 指向的档案必须存在且带有效状态行——防指针烂掉。"""
    import re

    root = Path(__file__).resolve().parent.parent
    active = (root / "docs" / "dev" / "features" / ".active").read_text(encoding="utf-8").strip()
    if active.startswith("!"):
        return                        # 显式放行状态，无档案可校验
    archive = root / "docs" / "dev" / "features" / active / "README.md"
    assert archive.is_file(), f".active 指向不存在的档案: {active}"
    text = archive.read_text(encoding="utf-8")
    assert re.search(r"^状态：[^\S\n]*\S", text, re.M), f"{active} 档案缺有效状态行"


def test_notebook_edit_target_is_extracted():
    """NotebookEdit 的入参字段是 notebook_path——取不到目标就恒放行，门禁形同虚设（R3#1）。"""
    assert design_gate.target_path({"file_path": "/a/b.py"}) == "/a/b.py"
    assert design_gate.target_path({"notebook_path": "/a/nb.ipynb"}) == "/a/nb.ipynb"
    assert design_gate.target_path({}) == ""


def test_status_regex_does_not_cross_lines():
    """「状态：」后空着时，不能把下一行首词认作状态（R3#14）。"""
    d, reason = decide("Edit", "src/pai/x.py", "02-x\n", "# 02-x\n状态：\n已拍板\n")
    assert d == "deny" and "状态" in reason


def test_design_gate_stays_fail_open():
    """**开发期自律门禁保持 fail-open**，与运行期权限 hook 的 fail-closed 相反。

    feature 09 Task 7 复议 D#50 时明确分了场景：
    - 运行期权限 hook 挡的是「agent 动用户的机器」，失败的代价是**安全事故** → fail-closed；
    - `design_gate.py` 挡的是「AI 改自己源码时没走流程」，失败的代价是**流程没走到**
      → fail-open（门禁自己崩了不该让开发整个停摆）。

    这条测试是防「统一一下失败语义」的误改——两处相反是刻意的，不是遗漏。
    """
    gate = Path(__file__).resolve().parent.parent / "guards" / "design_gate.py"
    source = gate.read_text(encoding="utf-8")

    assert "sys.exit(0)" in source
    assert "门禁自身异常绝不阻断工作" in source
