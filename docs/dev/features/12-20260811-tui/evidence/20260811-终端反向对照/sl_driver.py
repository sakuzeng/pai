import os, sys, time
sys.path.insert(0, "/Users/sakuzeng/improve/coding/agent/projects/pai/src")
from pai.modes.statusline import StatusLinePrinter, render_tool_line, display_width
from pai.core.events import ToolStart
p = StatusLinePrinter()
LONG = {"command": "回声测试中文宽度" * 12}
print("enabled=%r width=%d" % (p.enabled, os.get_terminal_size().columns), flush=True)
p.handle(ToolStart(tool_call_id="1", name="read_file", args={"path": "a.py"}))
time.sleep(0.4)
p.handle(ToolStart(tool_call_id="2", name="bash", args=LONG))
time.sleep(0.4)
cols = os.get_terminal_size().columns
line = render_tool_line([ToolStart(tool_call_id="2", name="bash", args=LONG)], cols)
print("\n[BEFORE] cols=%d rendered_width=%d" % (cols, display_width(line)), flush=True)
time.sleep(1.5)
cols2 = os.get_terminal_size().columns
line2 = render_tool_line([ToolStart(tool_call_id="2", name="bash", args=LONG)], cols2)
print("[AFTER-RESIZE] cols=%d rendered_width=%d" % (cols2, display_width(line2)), flush=True)
p.handle(ToolStart(tool_call_id="3", name="bash", args=LONG))
time.sleep(0.3)
p.clear()
print("[DONE]", flush=True)
