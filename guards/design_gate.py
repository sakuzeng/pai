#!/usr/bin/env python3
"""PreToolUse 门禁：当前需求的档案没到「已拍板」，不许改 src/ 与 tests/。

「先讨论再动手」写在 AGENTS.md 是提示词层软约束，会被忽略（anna 实践与
R2#5 评审都证实了）——本脚本把它降到确定性层。机制沉淀见
knowledge/permissions/hooks-gates.md；对 anna 版的三处修正：
判定抽纯函数带 pytest（tests/test_design_gate.py）、不硬编码任务路径
（读 docs/dev/features/.active 指针）、放行是显式动作（.active 写 `!` 前缀，
理由留在文件里可查）而非默认。

诚实边界：门禁强制的是过程产物（档案的状态字段），无法从技术上证明用户
真的拍过板——把「闷头开写」变成「必须先改状态字段」，后者会留在 diff 里。
已知旁路（如实声明，R3#9）：hook 只匹配 Edit 类工具，`bash: cat > src/x.py`
可完全绕过——自律门禁不拦 Bash（误伤太大），这层靠 AGENTS.md 规矩与审查兜底。
"""
import json
import os
import re
import sys
from typing import Optional, Tuple

EDIT_TOOLS = ("Edit", "Write", "MultiEdit", "NotebookEdit")
GUARDED_PREFIXES = ("src/", "tests/")
ACTIVE_REL = "docs/dev/features/.active"
OK_STATUS = ("已拍板", "实现中", "已交付", "已验收")


def target_path(tool_input: dict) -> str:
    """Edit/Write 用 file_path，NotebookEdit 用 notebook_path——取不到目标就守不住（R3#1）。"""
    return tool_input.get("file_path") or tool_input.get("notebook_path") or ""


def decide(tool_name: str, rel_path: str, active_text: Optional[str],
           archive_text: Optional[str]) -> Tuple[str, str]:
    """纯判定函数，返回 (decision, reason)。decision: 'allow' | 'deny'。

    active_text / archive_text 传 None 表示对应文件不存在——IO 留在 main，
    这里只做判定，便于测试注入。
    """
    if tool_name not in EDIT_TOOLS:
        return "allow", ""
    if not rel_path or not rel_path.startswith(GUARDED_PREFIXES):
        return "allow", ""

    if active_text is None:
        return "deny", (
            "方案门禁：还没声明当前在做哪个需求，不能改 src/tests。\n"
            "  1) 立档案 docs/dev/features/<NN>-<名称>/（cp -r _template）\n"
            "  2) 候选方案 ≥2 个，与用户讨论，用户拍板后把状态改为「已拍板」\n"
            "  3) 把目录名写进 %s\n"
            "  小修小补：.active 写 `!<理由>`（如 `!小修:修 typo`）显式放行。\n"
            "  不要代替用户拍板。" % ACTIVE_REL
        )

    active = active_text.strip()
    if not active:
        return "deny", "方案门禁：%s 是空的，写入档案目录名（或 `!<理由>` 放行）。" % ACTIVE_REL
    if active.startswith("!"):
        return "allow", ""            # 显式放行，理由已留在 .active 里

    if archive_text is None:
        return "deny", (
            "方案门禁：.active 指向 %s，但其档案 README.md 不存在。\n"
            "  先 cp -r docs/dev/features/_template 建档案。" % active
        )

    # [^\S\n] 而非 \s：后者可跨行，「状态：」后空着会把下一行首词认作状态（R3#14）
    m = re.search(r"^状态：[^\S\n]*(\S+)", archive_text, re.M)
    if not m:
        return "deny", "方案门禁：%s 的档案缺「状态：」行，补上后再改代码。" % active
    status = m.group(1)
    if not status.startswith(OK_STATUS):
        return "deny", (
            "方案门禁：%s 当前状态是「%s」，未到「已拍板」。\n"
            "  先把候选方案（≥2 个）讲给用户、等用户选定，把选择写进档案\n"
            "  「候选方案与确认」节并将状态改为「已拍板」，再动代码。\n"
            "  不要代替用户拍板。" % (active, status)
        )
    return "allow", ""


def main() -> None:
    ev = json.loads(sys.stdin.read())
    root = os.environ.get("CLAUDE_PROJECT_DIR") or ev.get("cwd") or os.getcwd()

    target = target_path(ev.get("tool_input") or {})
    rel = ""
    if target:
        try:
            rel = os.path.relpath(os.path.abspath(target), root)
        except ValueError:
            rel = ""
        if rel.startswith(".."):
            rel = ""                  # 项目外的文件不管

    def read(p: str) -> Optional[str]:
        try:
            with open(p, encoding="utf-8") as f:
                return f.read()
        except OSError:
            return None

    active_text = read(os.path.join(root, ACTIVE_REL))
    archive_text = None
    if active_text and active_text.strip() and not active_text.strip().startswith("!"):
        archive_text = read(os.path.join(
            root, "docs", "dev", "features", active_text.strip(), "README.md"))

    decision, reason = decide(ev.get("tool_name") or "", rel, active_text, archive_text)
    if decision == "deny":
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }}, ensure_ascii=False))
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.exit(0)                   # 门禁自身异常绝不阻断工作（anna 铁律）
