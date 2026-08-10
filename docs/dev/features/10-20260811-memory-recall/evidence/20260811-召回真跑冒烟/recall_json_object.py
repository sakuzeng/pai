"""feature 10 遗留 1 的冒烟：真实 provider 是否接受 response_format=json_object，
以及召回选择器在真模型下是否稳定吐可解析的 JSON。

会花钱（一次很短的侧查询）。手工跑：python3 pai_playground/smoke/recall_json_object.py
"""
import sys, pathlib, tempfile, json
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "src"))

from pai.config import make_client, recall_model
from pai.core.memory import scan_memories
from pai.core.recall import RecallState, build_manifest, select_memories

MEMS = [
    ("构建约定", "feedback", "怎么跑测试与提交：./test.sh 跑全量，提交格式 <类型>(module): message"),
    ("用户偏好", "user", "用户偏好中文回复，喜欢先给结论再给理由"),
    ("压缩阈值", "project", "压缩触发点按 reserve_tokens=16384 算，当前约 983616 token"),
]

d = pathlib.Path(tempfile.mkdtemp(prefix="pai-recall-smoke-"))
for name, kind, desc in MEMS:
    (d / f"{name}.md").write_text(
        f"---\nname: {name}\ndescription: {desc}\nmetadata:\n  type: {kind}\n---\n\n正文占位\n",
        encoding="utf-8")

client, model = make_client(), recall_model()
headers = scan_memories(d)
print(f"模型：{model}\n目录：{d}\nmanifest:\n{build_manifest(headers, __import__('time').time())}\n")

QUERIES = ["测试怎么跑？", "帮我看看 loop.py 有没有 bug", "压缩什么时候触发"]

# 1) 先裸打一次，看 provider 到底接不接受 response_format 这个参数
try:
    raw = client.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": '只输出 JSON：{"ok": true}'},
                  {"role": "user", "content": "确认一下"}],
        max_tokens=64,
        response_format={"type": "json_object"},
    )
    print("① response_format=json_object 被接受，原样回复：", repr(raw.choices[0].message.content))
except Exception as e:
    print("① response_format=json_object 被拒绝：", type(e).__name__, e)

# 2) 再走真正的 select_memories，三个 query 各一次
for q in QUERIES:
    state = RecallState()
    picked, usage = select_memories(q, headers, client=client, model=model, state=state)
    print(f"② query={q!r}\n   选中={[h.name for h in picked]}  失败计数={state.failures}  usage={usage}")
