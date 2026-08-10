"""量 max_tokens 阶梯：deepseek-v4-flash 是**推理模型**，reasoning_tokens 计进 max_tokens，
照抄 CC 的 256（CC 用的是不推理的 Sonnet 档）会把预算全烧在思考上，content 恒为空。
"""
import sys, pathlib, time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "src"))

from pai.config import make_client, recall_model
from pai.core.recall import SELECTOR_PROMPT

MANIFEST = """- [project] 压缩阈值.md (今天): 压缩触发点按 reserve_tokens=16384 算，当前约 983616 token
- [user] 用户偏好.md (今天): 用户偏好中文回复，喜欢先给结论再给理由
- [feedback] 构建约定.md (今天): 怎么跑测试与提交：./test.sh 跑全量，提交格式 <类型>(module): message"""

client, model = make_client(), recall_model()
query = "测试怎么跑？"
for cap in (256, 512, 1024, 2048):
    r = client.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": SELECTOR_PROMPT},
                  {"role": "user", "content": f"用户这一轮说：\n{query}\n\n可选的记忆：\n{MANIFEST}"}],
        max_tokens=cap,
        response_format={"type": "json_object"},
    )
    u = r.usage
    reasoning = (u.completion_tokens_details.reasoning_tokens
                 if u.completion_tokens_details else None)
    print(f"max_tokens={cap:5d}  completion={u.completion_tokens:4d}  reasoning={reasoning}  "
          f"content={r.choices[0].message.content!r}")
