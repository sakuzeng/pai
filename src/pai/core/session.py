"""会话落盘：append-only JSONL，一次会话一个文件。格式 v1（feature 24，R4#A1）。

落点由 pai.core.paths 决定（`~/.pai/projects/<slug>/sessions/`），**不再写当前工作目录**——
pai 的立意是在别人的项目里跑，往人家仓库里拉一个 sessions/ 目录是不能接受的（feature 08）。

v1 形状是三家收敛形（K loop/session-format-three-way.md：pi/CC/dsh 完全一致）：

- 首行 header：`{type:"session", version, id, timestamp, cwd, parentSession?}`。
  身份与 cwd 一次说清，不再每条记录重复（v0 的每条 sessionId/cwd 随之取消）。
- 每条记录统一信封：`{type, id, parentId, ts, …}`。顶层判别字段只有 `type`——
  v0「消息用 role、旁账用 type」的双轨是本次要治的病。
- 消息嵌套：`type:"message"` 且 LLM 载荷整个嵌在 `message` 字段（pi/CC 同款）；
  usage / compaction 等旁账记录的字段与信封并排（pi 的 typed entry 同款）。
- `ts` 保持 epoch float（viz 的时间算术依赖数值序），header 的 `timestamp`
  用 ISO 给人读——两个口径各归其位，是对「ISO 时间戳」那条登记的刻意偏离。
- 旧格式（无 header）按拍板问 2 = B 不做读兼容：如实报错，不动不删旧文件。
"""

from __future__ import annotations

import datetime
import json
import threading
import time
import uuid
from pathlib import Path
from typing import Optional, Union

from pai.core.paths import sessions_dir

SESSION_VERSION = 1

# 词汇表外的 entry type 拒绝而非静默跳过（dsh 教训：静默跳过一个不认识的
# 必需事件可能改变日志其余部分的解读方式）。信封带 `ignorable: true` 的例外。
KNOWN_ENTRY_TYPES = ("message", "usage", "compaction")

# 信封自己的键；消息载荷嵌在 message 字段里，永不与它们同层
_ENVELOPE_KEYS = ("type", "id", "parentId", "ts")


class SessionFormatError(ValueError):
    """版本/形状不认识。与「数据损坏」是两种错误，报错要说明方向（dsh 语义）。"""


class SessionLog:
    def __init__(self, directory: Optional[Union[str, Path]] = None,
                 *, parent_session: Optional[str] = None):
        # 默认值必须在函数体里取，不能写成 `directory=sessions_dir()`——
        # 默认参数在**函数定义时**求值，测试隔离 $HOME 之后就追不回来了
        # （feature 05 补漏五刚在 history_path_for 上栽过同款）
        d = Path(directory) if directory is not None else sessions_dir()
        d.mkdir(parents=True, exist_ok=True)
        self.session_id = uuid.uuid4().hex
        # 时间戳前缀保留（`ls` 按时间排序），短 id 去碰撞（关掉 R#15：
        # 原来精确到秒，同秒建两个 SessionLog 会写同一个文件）。
        # 与 CC 不同：CC 用纯 `<sessionId>.jsonl`，可读性让位于唯一性。
        stamp = time.strftime("%Y%m%d-%H%M%S")
        self.path = d / f"{stamp}-{self.session_id[:8]}.jsonl"
        self.cwd = str(Path.cwd().absolute())
        self.parent_session = parent_session      # resume 时指向被恢复的会话 id
        self._lock = threading.Lock()
        self._last_id: Optional[str] = None
        self._header_written = False

    def append(self, record: dict, *, record_id: Optional[str] = None) -> str:
        """落一条记录，返回它的 entry id。

        `record_id` 供 resume 重录用——CC 反教材（K session-format-three-way
        第二节）：resume 路径造新身份会让转录每次恢复指数增长。
        """
        entry_id = record_id if record_id is not None else uuid.uuid4().hex
        if "role" in record:
            payload: dict = {"message": record}
            entry_type = "message"
        else:
            payload = {k: v for k, v in record.items() if k != "type"}
            entry_type = str(record.get("type", "custom"))
        entry = {"type": entry_type, "id": entry_id, "parentId": self._last_id,
                 "ts": time.time(), **payload}
        line = json.dumps(entry, ensure_ascii=False) + "\n"
        # 并发批里多个工具会同时回填结果（feature 11）。不加锁的话两条长记录可能
        # 交织成半行，而**半行 JSONL 是不可恢复的**——审计流一旦坏了，坏的是历史。
        with self._lock:
            with open(self.path, "a", encoding="utf-8") as f:
                if not self._header_written:
                    header: dict = {"type": "session", "version": SESSION_VERSION,
                                    "id": self.session_id,
                                    "timestamp": datetime.datetime.now().isoformat(
                                        timespec="seconds"),
                                    "cwd": self.cwd}
                    if self.parent_session:
                        header["parentSession"] = self.parent_session
                    f.write(json.dumps(header, ensure_ascii=False) + "\n")
                    self._header_written = True
                f.write(line)
            self._last_id = entry_id
        return entry_id


def load_session(path: Union[str, Path]) -> tuple:
    """读一个 v1 会话文件，返回 (header, entries)。

    拒绝语义分方向（dsh）：首行不是合法 header = 旧格式（拍板问 2 = B，
    不做读兼容）；version 更新 = 请升级 pai；更旧 = 本版本无升级路径
    （目前只有 v1，这个分支是给未来的自己留的路标）。
    """
    path = Path(path)
    with open(path, encoding="utf-8") as f:
        lines = [l for l in f if l.strip()]
    if not lines:
        raise SessionFormatError(f"会话文件是空的：{path}")
    try:
        header = json.loads(lines[0])
    except json.JSONDecodeError:
        header = {}
    if header.get("type") != "session" or "version" not in header:
        raise SessionFormatError(
            f"旧格式（v0，feature 24 之前）的会话，不支持恢复：{path}。"
            "文件本身原样保留，只是新格式的读取器认不得它。")
    if header["version"] > SESSION_VERSION:
        raise SessionFormatError(
            f"该会话由更新的 pai 写入（v{header['version']} > v{SESSION_VERSION}），"
            "请升级 pai 后再打开。")
    if header["version"] < SESSION_VERSION:
        raise SessionFormatError(
            f"该会话是 v{header['version']}，本版本没有它的升级路径。")
    entries = []
    for line in lines[1:]:
        entry = json.loads(line)
        if entry.get("type") not in KNOWN_ENTRY_TYPES and not entry.get("ignorable"):
            raise SessionFormatError(
                f"不认识的记录类型 {entry.get('type')!r}——静默跳过可能改变"
                "日志其余部分的解读方式（dsh 教训），拒绝读取。")
        entries.append(entry)
    return header, entries


def _summary_message(summary: str) -> dict:
    """摘要消息的包装，与 compaction.compact() 的重建逐字一致——
    两处各写一遍迟早漂，这里是唯一出处（compact 也调它）。"""
    return {"role": "user", "content": f"[早前对话的摘要，供延续任务用]\n{summary}"}


def build_messages(entries: list) -> tuple:
    """entries → (messages, ledger)。ledger 是与 messages 平行的 entry id 表。

    压缩条目按 pi `buildContextEntries`：取最后一条 compaction，输出
    [首条 system, 摘要 user（id 取 compaction 条目的 id，pi 同款——条目本身
    在上下文里就化身为摘要消息）, 自 firstKeptEntryId 起的保留段,
    compaction 之后的全部]；历史一字不删。
    指令注入消息（INSTRUCTION_HEADER 前缀）重建后放回 system 之后、只留最新
    一条——内存里 `_inject_instructions` 就是这个位置与去重语义。
    """
    from pai.core.loop import INSTRUCTION_HEADER

    last_compaction = None
    for e in entries:
        if e["type"] == "compaction":
            last_compaction = e

    messages: list = []
    ledger: list = []

    if last_compaction is None:
        for e in entries:
            if e["type"] == "message":
                messages.append(e["message"])
                ledger.append(e["id"])
    else:
        comp_idx = next(i for i, e in enumerate(entries)
                        if e is last_compaction)

        def emit(e: dict) -> None:
            # 保留段扫**全部条目**（pi buildContextEntries 同款）：压缩条目在
            # 保留段里化身为它的摘要消息——第二次压缩的切点可能恰好落在第一次
            # 的摘要上，只扫 message 条目会把保留段静默丢光（自查测试钉死）
            if e["type"] == "message":
                messages.append(e["message"])
                ledger.append(e["id"])
            elif e["type"] == "compaction":
                messages.append(_summary_message(e["summary"]))
                ledger.append(e["id"])
            # usage 等旁账不是模型可见的，跳过

        system_id = None
        for e in entries[:comp_idx]:
            if e["type"] == "message":
                if e["message"].get("role") == "system":
                    system_id = e["id"]
                    messages.append(e["message"])
                    ledger.append(e["id"])
                break
        messages.append(_summary_message(last_compaction["summary"]))
        ledger.append(last_compaction["id"])
        keeping = False
        for e in entries[:comp_idx]:
            if e["id"] == last_compaction.get("firstKeptEntryId"):
                keeping = True
            if keeping and e["id"] != system_id:
                emit(e)
        for e in entries[comp_idx + 1:]:
            emit(e)

    # 指令消息归位：内存里它永远在 system 之后且只有一条（_has_instructions 去重）
    instr = [(i, m) for i, m in enumerate(messages)
             if str(m.get("content", "")).startswith(INSTRUCTION_HEADER)]
    if instr:
        keep_i, keep_m = instr[-1]
        keep_id = ledger[keep_i]
        for i, _ in reversed(instr):
            del messages[i]
            del ledger[i]
        at = 1 if messages and messages[0].get("role") == "system" else 0
        messages.insert(at, keep_m)
        ledger.insert(at, keep_id)
    return messages, ledger


def replay_messages(path: Union[str, Path]) -> list:
    """会话文件 → 发给模型的 messages（feature 23 引入，feature 24 升级走 v1
    读取器——压缩会话不再拒收，按 compaction 条目重建）。"""
    _, entries = load_session(path)
    messages, _ = build_messages(entries)
    return messages


def trim_unfinished(messages: list, ledger: list) -> tuple:
    """resume 配平（CC 三道过滤的 pai 版，K session-format-three-way 第二节）：

    - assistant 声明的 tool_calls 缺任何一条结果 → 该 assistant 整块删
      （半截回合发回 provider 就是 400）；
    - tool 结果找不到幸存的宿主 assistant → 孤儿，删。
    修复只发生在读取侧（dsh：「内存配平中断轮次，物理尾部保持撕裂原样」），
    磁盘上的文件一字不动。返回 (messages, ledger) 的新列表。
    """
    result_ids = {m.get("tool_call_id") for m in messages if m.get("role") == "tool"}
    surviving_calls: set = set()
    keep_msg: list = []
    keep_led: list = []
    for m, lid in zip(messages, ledger):
        if m.get("role") == "assistant" and m.get("tool_calls"):
            ids = [tc.get("id") for tc in m["tool_calls"]]
            if any(i not in result_ids for i in ids):
                continue
            surviving_calls.update(ids)
        keep_msg.append(m)
        keep_led.append(lid)
    out_msg: list = []
    out_led: list = []
    for m, lid in zip(keep_msg, keep_led):
        if m.get("role") == "tool" and m.get("tool_call_id") not in surviving_calls:
            continue
        out_msg.append(m)
        out_led.append(lid)
    return out_msg, out_led


def resolve_resume_target(target: Optional[str],
                          directory: Optional[Union[str, Path]] = None) -> Path:
    """`--resume` 的目标解析：None/空串 = 本项目最近一次；否则先当路径、
    再当会话 id 前缀（比对 header 里的完整 id 与文件名里的短 id）。
    找不到就 FileNotFoundError 说清找过哪里——静默兜底成「新会话」比报错更糟。"""
    d = Path(directory) if directory is not None else sessions_dir()
    if target:
        p = Path(target)
        if p.is_file():
            return p
    candidates = sorted(
        (f for f in d.glob("*.jsonl") if not f.name.endswith(".events.jsonl")),
        key=lambda f: f.stat().st_mtime, reverse=True)
    if not target:
        if not candidates:
            raise FileNotFoundError(f"{d} 下没有任何会话可恢复")
        return candidates[0]
    for f in candidates:
        if target in f.name:
            return f
        try:
            header, _ = load_session(f)
        except SessionFormatError:
            continue
        if str(header.get("id", "")).startswith(target):
            return f
    raise FileNotFoundError(f"{d} 下没有匹配 {target!r} 的会话（也不是现存文件路径）")
