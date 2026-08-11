#!/usr/bin/env python3
"""在 iTerm2 / Terminal.app 里各开一个**新窗口**跑 probe_alt.py，并在探针自己写出的
检查点上抓屏。绝不碰当前正在跑 Claude Code 的那个会话。

抓屏时机不靠猜时间：探针在每个检查点往日志里写一行 `--- 检查点 X`，
本脚本轮询日志，看到新检查点就立刻抓一次可见屏内容。
"""
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PROBE = os.path.join(HERE, "probe_alt.py")


def osa(script: str) -> str:
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"osascript 失败: {r.stderr.strip()}\n脚本: {script}")
    return r.stdout.rstrip("\n")


class ITerm:
    name = "iTerm2"

    def open(self) -> None:
        self.wid = osa(
            'tell application "iTerm2"\n'
            "  set w to (create window with default profile)\n"
            "  return id of w\n"
            "end tell"
        )

    def run(self, cmd: str) -> None:
        esc = cmd.replace("\\", "\\\\").replace('"', '\\"')
        osa(f'tell application "iTerm2" to tell current session of window id "{self.wid}" '
            f'to write text "{esc}"')

    def snapshot(self) -> str:
        return osa(f'tell application "iTerm2" to tell current session of window id "{self.wid}" '
                   f"to get contents")

    def bounds(self):
        out = osa(f'tell application "iTerm2" to get bounds of window id "{self.wid}"')
        return [int(x.strip()) for x in out.split(",")]

    def close(self) -> None:
        try:
            osa(f'tell application "iTerm2" to close window id "{self.wid}"')
        except RuntimeError:
            pass


class TerminalApp:
    name = "Terminal.app"

    def open(self) -> None:
        # Terminal.app 冷启动时 `do script` 会 AppleEvent 超时，先唤起再等它起来
        subprocess.run(["open", "-a", "Terminal"], check=False)
        time.sleep(3)
        self.wid = osa(
            'tell application "Terminal"\n'
            "  activate\n"
            '  set t to do script ""\n'
            "  return id of (first window whose selected tab is t)\n"
            "end tell"
        )

    def run(self, cmd: str) -> None:
        esc = cmd.replace("\\", "\\\\").replace('"', '\\"')
        osa(f'tell application "Terminal" to do script "{esc}" in selected tab of window id {self.wid}')

    def snapshot(self) -> str:
        return osa(f'tell application "Terminal" to get contents of selected tab of window id {self.wid}')

    def bounds(self):
        out = osa(f'tell application "Terminal" to get bounds of window id {self.wid}')
        return [int(x.strip()) for x in out.split(",")]

    def close(self) -> None:
        try:
            osa(f'tell application "Terminal" to close window id {self.wid}')
        except RuntimeError:
            pass


def click_center(term) -> str:
    """用 System Events 在窗口中央点一下，试图产生真实鼠标事件。"""
    try:
        x1, y1, x2, y2 = term.bounds()
        cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
        osa(f'tell application "System Events" to click at {{{cx}, {cy}}}')
        return f"已在 ({cx},{cy}) 发出一次点击"
    except Exception as exc:  # noqa: BLE001
        return f"点击失败（很可能缺辅助功能授权）：{exc}"


def drive(term, outdir: str, hold: float = 4.0) -> None:
    # 必须绝对路径：命令是在新终端窗口里跑的，那边的 cwd 是 $HOME 不是这里
    outdir = os.path.abspath(outdir)
    os.makedirs(outdir, exist_ok=True)
    log = os.path.join(outdir, "probe.log")
    if os.path.exists(log):
        os.remove(log)
    term.open()
    time.sleep(1.5)
    py = sys.executable or "python3"
    term.run(f"{py} {PROBE} {log} --hold {hold}")

    seen = 0
    snaps = 0
    clicked = False
    deadline = time.time() + 120
    while time.time() < deadline:
        time.sleep(0.25)
        if not os.path.exists(log):
            continue
        lines = open(log, encoding="utf-8", errors="replace").read().splitlines()
        checkpoints = [ln for ln in lines if ln.startswith("--- 检查点")]
        if len(checkpoints) > seen:
            for cp in checkpoints[seen:]:
                time.sleep(0.6)  # 让终端把这一屏画完
                snaps += 1
                label = cp.split("检查点", 1)[1].split("@")[0].strip()
                text = term.snapshot()
                path = os.path.join(outdir, f"snap{snaps}-{label.split('(')[0].strip()}.txt")
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(f"# 检查点: {label}\n# 终端: {term.name}\n{'=' * 60}\n{text}\n")
                print(f"[{term.name}] 抓屏 {snaps}: {label} -> {os.path.basename(path)}")
                if label.startswith("D") and not clicked:
                    clicked = True
                    print(f"[{term.name}] {click_center(term)}")
            seen = len(checkpoints)
        if any("探针结束" in ln for ln in lines):
            break
    time.sleep(1.0)
    term.close()


if __name__ == "__main__":
    which = sys.argv[1]
    outdir = sys.argv[2]
    term = ITerm() if which == "iterm" else TerminalApp()
    drive(term, outdir)
