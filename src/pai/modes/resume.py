"""resume：恢复的 messages → 回放项（feature 48），以及会话切换本身（feature 49）。

回放分类照 CC 2.1.88 的 `utils/messages.ts::shouldShowUserMessage`（isMeta 的 user 消息不画）
与 `components/Messages.tsx` 的过滤。pai 的消息没有 isMeta 字段，注入消息靠它们各自的
固定头识别——都是 pai 自己造的：指令头（`loop.INSTRUCTION_HEADER`）、规则与召回块的
`<system-reminder>`、压缩摘要头（`session.SUMMARY_HEADER`）、`!命令` 回显
（`commands.shell_echo`）。所以这个模块住 modes 层：tui 不该认识 loop 与 commands
（AST 守卫），而 modes 本来就 import 它们。

切换（feature 49）照 CC 的 `switchSession` + `/resume` 命令：启动 `--resume` 与会话内 `/resume`
共用 `load_conversation` / `refresh_assembly`；`switch_conversation` 就地换 messages / ledger、
重置锚点与熔断、`SessionLog.switch_to` 接管目标文件、发 `ConversationResumed`
（进 `events.CONTEXT_REWRITING`，召回去重表与规则注入表靠它作废）。
"""

from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple, Union

from pai.core.events import AssistantMessage, ConversationResumed, ToolEnd
from pai.core.loop import INSTRUCTION_HEADER, _instruction_message, drop_instructions
from pai.core.paths import sessions_dir
from pai.core.session import (SUMMARY_HEADER, SessionFormatError, build_messages,
                              load_session, resolve_resume_target, session_cwd,
                              trim_unfinished)
from pai.core.tools import memory_tool
from pai.modes.commands import split_shell_echo
from pai.tui.history import CompactedMark, HistoryItem, ShellLine, UserLine

# 规则（core/rules.py）与召回（core/recall.py）两处注入块共用的外壳
REMINDER_OPEN = "<system-reminder>"


def history_items(messages: List[dict]) -> List[HistoryItem]:
    results: Dict[str, str] = {}
    for m in messages:
        if m.get("role") == "tool":
            results[str(m.get("tool_call_id"))] = _text(m)

    items: List[HistoryItem] = []
    for m in messages:
        role = m.get("role")
        text = _text(m)
        if role == "user":
            if text.startswith(INSTRUCTION_HEADER) or text.startswith(REMINDER_OPEN):
                continue                                   # CC 的 isMeta：框架注入不画
            if text.startswith(SUMMARY_HEADER):
                items.append(CompactedMark())
                continue
            shell = split_shell_echo(text)
            if shell is not None:
                items.append(ShellLine(command=shell[0], output=shell[1]))
                continue
            if text.strip():
                items.append(UserLine(text))
        elif role == "assistant":
            calls = m.get("tool_calls") or []
            names = tuple(str((c.get("function") or {}).get("name", "")) for c in calls)
            # 空白回答不画：模型在调工具前吐的 "\n\n"（CC filterWhitespaceOnlyAssistantMessages 同款）
            if text.strip():
                items.append(AssistantMessage(text, names))
            for c in calls:
                cid = str(c.get("id"))
                fn = c.get("function") or {}
                items.append(ToolEnd(tool_call_id=cid, name=str(fn.get("name", "")),
                                     args=_parse_args(fn.get("arguments")),
                                     result=results.get(cid, "")))
        # system 不上屏；tool 已在配对里用掉
    return items


def _text(m: dict) -> str:
    content = m.get("content")
    if content is None:
        return ""
    return content if isinstance(content, str) else str(content)


def _parse_args(raw: object) -> dict:
    """`arguments` 在线上是 JSON 串；解析不了就原样包住——回放不该因一条坏参数整个失败。
    诚实边界同 `events.ToolEnd`：is_error 一律 False，tool 消息里分不出 loop 造的错。"""
    if isinstance(raw, dict):
        return raw
    try:
        parsed = json.loads(raw if isinstance(raw, str) and raw else "{}")
    except ValueError:
        return {"raw": raw}
    return parsed if isinstance(parsed, dict) else {"raw": raw}


# ---- 切换（feature 49）-----------------------------------------------------------

def load_conversation(target: Union[str, Path]) -> Tuple[dict, List[dict], List[Optional[str]]]:
    """会话文件 → (header, messages, ledger)：重建 + 读取侧配平。错误原样上抛。"""
    header, entries = load_session(target)
    msgs, led = build_messages(entries)
    msgs, led = trim_unfinished(msgs, led)
    return header, msgs, led


def refresh_assembly(messages: List[dict], ledger: List[Optional[str]],
                     system_prompt: str, instructions_text: Optional[str] = None) -> tuple:
    """resume 后把装配层的产物换成当前环境的（照 CC：转录里不存 system prompt，每次现算）。

    system 换成现算的那份，ledger 记 None——它只在内存，不落盘（下次 resume 反正重算）。
    指令消息：与磁盘上那条内容一样就沿用原条目（不重录）；不一样才全部丢掉，
    下一轮 `_inject_instructions` 见不到旧的就会重读磁盘并追加一条。对话消息一条不动。
    """
    msgs, led = list(messages), list(ledger)
    fresh = {"role": "system", "content": system_prompt}
    if msgs and msgs[0].get("role") == "system":
        msgs[0], led[0] = fresh, None
    else:
        msgs.insert(0, fresh)
        led.insert(0, None)
    wanted = (_instruction_message(instructions_text)["content"]
              if instructions_text and instructions_text.strip() else None)
    existing = [m for m in msgs if m.get("role") == "user"
                and str(m.get("content") or "").startswith(INSTRUCTION_HEADER)]
    unchanged = wanted is not None and len(existing) == 1 and existing[0].get("content") == wanted
    if not unchanged:
        while drop_instructions(msgs, led):
            pass
    return msgs, led


def resume_note(header: dict, target: Union[str, Path], count: int) -> str:
    """恢复提示。恢复的只有对话：权限模式 / 模型取当前环境（24 遗留，dsh 明确警告
    「恢复到不同构图的组合是错误」），system prompt 与项目指令由 refresh_assembly 重装配。"""
    sid = str(header.get("id") or "")
    notes = [f"↩️ 已恢复会话 {sid[:8]}（{count} 条消息，来自 {Path(target).name}）",
             "   恢复的只有对话，设置不跟着回来：权限模式、模型、"
             "system prompt 都按当前环境重新装配。"]
    recorded_cwd = str(header.get("cwd") or "")
    # 目录没变就不提——每次都喊等于没喊（同「无失败一个字不提」那条反向守卫）
    if recorded_cwd and recorded_cwd != str(Path.cwd().absolute()):
        notes.append(f"   注意：该会话录制于 {recorded_cwd}，"
                     "当前目录不同——工作目录边界与项目指令都会不一样。")
    return "\n".join(notes)


def recent_sessions(exclude: Optional[Union[str, Path]] = None, limit: int = 8,
                    directory: Optional[Union[str, Path]] = None,
                    cwd: Optional[Union[str, Path]] = None) -> List[Tuple[Path, str]]:
    """选择框的候选：**当前目录**录制的最近会话（不含当前文件），每条一行
    「MM-DD HH:MM · N 条 · 首句」。只认 header.cwd = 当前目录（照 CC：选择器只看当前目录，
    跨目录只能给 id）——同一 git 仓库子目录里跑过的会话与这里同一个 sessions 目录，
    不过滤就会像用户 2026-09-11 截图那样把 pai_playground 的会话列进来。
    CC 的 LogSelector 还带 git 分支、自定义标题、全项目开关——pai 都没有，先只给最少能认出来的三样。"""
    d = Path(directory) if directory is not None else sessions_dir()
    files = sorted((f for f in d.glob("*.jsonl") if not f.name.endswith(".events.jsonl")),
                   key=lambda f: (f.stat().st_mtime_ns, f.name), reverse=True)
    current = Path(exclude).resolve() if exclude is not None else None
    here = str(Path(cwd).absolute()) if cwd is not None else str(Path.cwd().absolute())
    out: List[Tuple[Path, str]] = []
    for f in files:
        if current is not None and f.resolve() == current:
            continue
        if session_cwd(f) != here:
            continue
        try:
            header, msgs, _ = load_conversation(f)
        except (SessionFormatError, OSError, ValueError):
            continue                                   # 认不得的文件不进候选，也不炸
        first = next((i.text for i in history_items(msgs) if isinstance(i, UserLine)), "")
        first = first.replace("\n", " ").strip()[:30]
        out.append((f, f"{_stamp(header, f)} · {len(msgs)} 条 · {first}"))
        if len(out) >= limit:
            break
    return out


def _stamp(header: dict, path: Path) -> str:
    try:
        return datetime.datetime.fromisoformat(str(header.get("timestamp") or "")).strftime("%m-%d %H:%M")
    except ValueError:
        return path.name[:15]


def switch_conversation(target: Union[str, Path], *, messages: List[dict],
                        ledger: List[Optional[str]], anchors, state, session, on_event,
                        system_prompt: str, instructions_text: Optional[str] = None) -> str:
    """把当前对话换成 `target` 的（照 CC：REPL 换 messages 状态 + `switchSession`）。

    就地变更——messages / ledger 是列表对象、session 是 SessionLog 对象，装配期的闭包
    持有的都是它们本身，所以不造新对象。锚点簿与熔断状态必须从零（同启动 resume 的理由）。
    返回恢复提示。
    """
    header, msgs, led = load_conversation(target)
    count = len(msgs)
    msgs, led = refresh_assembly(msgs, led, system_prompt, instructions_text)
    messages[:] = msgs
    ledger[:] = led
    anchors.reset()
    state.failures, state.awaiting_verify, state.tripped = 0, False, False
    if session is not None:
        session.switch_to(target)
        memory_tool.set_origin_session(session.session_id)
    if on_event is not None:
        on_event(ConversationResumed(session_id=str(header.get("id") or ""), kept=len(messages)))
    return resume_note(header, target, count)


def resume_command(arg: str, *, out: Callable[[str], None], asker, session, **switch_kw) -> Optional[str]:
    """`/resume [id前缀|路径]`：带参直达，无参经 asker 弹候选。
    返回恢复提示 = 已切换；None = 没切（取消 / 找不到 / 没有可选 / 就是当前会话）。"""
    current = getattr(session, "path", None)
    if arg:
        try:
            target = resolve_resume_target(arg)
        except FileNotFoundError as e:
            out(f"❌ {e}")
            return None
    else:
        candidates = recent_sessions(exclude=current)
        if not candidates:
            out("当前目录下没有可恢复的会话（别的目录录制的不列；要恢复它们请 `/resume <id前缀|路径>`）")
            return None
        if asker is None:
            out("没有真人可选；用 `/resume <id前缀|路径>` 直接指定")
            return None
        answer = asker("恢复哪个会话？（最近的排在前面）", [label for _, label in candidates])
        target = {label: path for path, label in candidates}.get(answer)
        if target is None:
            out("已取消，仍在当前对话")
            return None
    if current is not None and Path(target).resolve() == Path(current).resolve():
        out("这就是当前会话")
        return None
    try:
        return switch_conversation(target, session=session, **switch_kw)
    except SessionFormatError as e:
        out(f"❌ {e}")
        return None

