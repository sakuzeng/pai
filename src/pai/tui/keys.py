"""原始字节 → 按键事件。纯状态机，不碰终端。

**为什么带状态**：真终端会把一个多字节字符、一条转义序列拆成两次 read 送达
（feature 12 的 pty 反向对照里实测如此）。所以喂多少认多少，认不全的留在缓冲里。

**诚实边界**：只支持一组主流序列。未识别的转义序列**丢弃**（不塞进输入框），
但会以 `unknown` 事件留痕，`PAI_TUI_DEBUG_KEYS=1` 时可打出来看。
按键序列是长尾，装作全支持只会在别人的终端上静默出错。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

PASTE_START = b"\x1b[200~"
PASTE_END = b"\x1b[201~"


@dataclass(frozen=True)
class Key:
    """一次按键。`text` 只在 `char`（字符）/`paste`（粘贴内容）/`unknown`（原始序列）时有值。"""

    name: str
    text: str = ""


_CTRL = {
    0x01: "ctrl_a", 0x03: "ctrl_c", 0x04: "ctrl_d", 0x05: "ctrl_e",
    0x0b: "ctrl_k", 0x0c: "ctrl_l", 0x0f: "ctrl_o", 0x12: "ctrl_r", 0x15: "ctrl_u",
    0x17: "ctrl_w",
}

# CSI 终结符/参数 → 键名
_CSI_FINAL = {
    "A": "up", "B": "down", "C": "right", "D": "left",
    "H": "home", "F": "end", "Z": "shift_tab",
}
_CSI_TILDE = {"1": "home", "4": "end", "3": "delete", "7": "home", "8": "end"}
_SS3 = {"H": "home", "F": "end", "A": "up", "B": "down", "C": "right", "D": "left"}


class KeyDecoder:
    """`feed(bytes) -> list[Key]`；`flush()` 收尾（把悬着的单个 ESC 判成 esc 键）。"""

    def __init__(self) -> None:
        self._buf = b""
        self._pasting = False
        self._paste = b""

    def feed(self, data: bytes) -> List[Key]:
        self._buf += data
        out: List[Key] = []
        while self._buf:
            key, consumed = self._step()
            if consumed == 0:            # 认不全，等下一口
                break
            self._buf = self._buf[consumed:]
            if key is not None:
                out.append(key)
        return out

    def flush(self) -> List[Key]:
        """读超时/流结束时调用：单独一个 ESC 与「转义序列的开头」在字节上分不开，
        只能靠「后面没有了」来判。"""
        if self._buf == b"\x1b":
            self._buf = b""
            return [Key("esc")]
        return []

    # --- 内部 ---------------------------------------------------------

    def _step(self):
        if self._pasting:
            return self._step_paste()
        b = self._buf[0]
        if b == 0x1b:
            return self._step_escape()
        if b in (0x0d, 0x0a):
            return Key("enter"), 1
        if b in (0x7f, 0x08):
            return Key("backspace"), 1
        if b in _CTRL:
            return Key(_CTRL[b]), 1
        if b < 0x20:
            return Key("unknown", chr(b)), 1
        return self._step_char()

    def _step_char(self):
        """按 UTF-8 前导字节算出这个字符要几个字节，不够就等。"""
        b = self._buf[0]
        length = 1 if b < 0x80 else 2 if b < 0xe0 else 3 if b < 0xf0 else 4
        if len(self._buf) < length:
            return None, 0
        try:
            return Key("char", self._buf[:length].decode("utf-8")), length
        except UnicodeDecodeError:
            return Key("unknown", repr(self._buf[:length])), length

    def _step_paste(self):
        end = self._buf.find(PASTE_END)
        if end == -1:
            # 尾部可能是 PASTE_END 的前缀，留着别吞
            keep = _prefix_len(self._buf, PASTE_END)
            if keep == len(self._buf):
                return None, 0
            self._paste += self._buf[:len(self._buf) - keep]
            return None, len(self._buf) - keep
        self._paste += self._buf[:end]
        text = self._paste.decode("utf-8", "replace").replace("\r\n", "\n").replace("\r", "\n")
        self._pasting, self._paste = False, b""
        return Key("paste", text), end + len(PASTE_END)

    def _step_escape(self):
        buf = self._buf
        if self._buf.startswith(PASTE_START):
            self._pasting = True
            return None, len(PASTE_START)
        if len(buf) == 1:
            return None, 0                      # 可能是 ESC 也可能是序列开头，等
        second = buf[1:2]
        if second == b"[":
            return self._step_csi()
        if second == b"O":                      # SS3：\x1bOH 之类
            if len(buf) < 3:
                return None, 0
            name = _SS3.get(chr(buf[2]))
            raw = buf[:3].decode("latin-1")
            return Key(name) if name else Key("unknown", raw), 3
        if second == b"b":
            return Key("word_left"), 2
        if second == b"f":
            return Key("word_right"), 2
        return Key("unknown", buf[:2].decode("latin-1")), 2

    def _step_csi(self):
        buf = self._buf
        i = 2
        while i < len(buf) and (0x30 <= buf[i] <= 0x3f or 0x20 <= buf[i] <= 0x2f):
            i += 1
        if i >= len(buf):
            return None, 0                      # 参数还没收完
        final = chr(buf[i])
        params = buf[2:i].decode("latin-1")
        raw = buf[:i + 1].decode("latin-1")
        if not params and final in _CSI_FINAL:
            return Key(_CSI_FINAL[final]), i + 1
        if final == "~" and params in _CSI_TILDE:
            return Key(_CSI_TILDE[params]), i + 1
        return Key("unknown", raw), i + 1


def _prefix_len(buf: bytes, marker: bytes) -> int:
    """buf 尾部有多少字节可能是 marker 的前缀（粘贴结束标记被拆开时用）。"""
    for n in range(min(len(buf), len(marker) - 1), 0, -1):
        if marker.startswith(buf[-n:]):
            return n
    return 0
