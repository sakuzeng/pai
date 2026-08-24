"""回放评测（feature 32 T4）：真实轨迹 → 派生脚本 → 真 pai 子进程重放。

全链是真的：真 HTTP（FakeProvider 回放派生脚本）→ 真 SSE → 真 pai 进程
（once 模式）→ 真工具执行。判分走外部世界（dsh 第一原则）：重读重放项目里
的文件，不对 agent 自述文本做关键词探测。
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

from fake_provider import FakeProvider

from pai.evals.replay import derive_replay

REPO = Path(__file__).resolve().parent.parent
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "20260824-greeting-file.jsonl"
PAI = str(Path(sys.executable).parent / "pai")


def test_replay_greeting_trajectory_end_to_end(tmp_path, eval_artifact_dir):
    plan = derive_replay(FIXTURE)
    proj = tmp_path / "proj"
    proj.mkdir()
    subprocess.run(["git", "init", "-q", str(proj)], check=True)

    with FakeProvider(plan.script) as provider:
        env = {**os.environ,
               "PAI_BASE_URL": provider.base_url,
               "DEEPSEEK_API_KEY": "sk-fake-eval-replay",
               "PAI_MODEL": "fake-model"}
        # 权限姿态与铸造时一致（fixtures/README）：录制回合在 bypass 下写文件，
        # 重放不还原同一姿态就会红在权限而不是行为差异上
        result = subprocess.run(
            [PAI, "--dangerously-skip-permissions", "--max-steps", "8", plan.task],
            capture_output=True, text=True, env=env, cwd=proj, timeout=120)

    assert result.returncode == 0, f"重放进程非零退出：{result.stderr[-500:]}"
    # 外部世界断言：录制回合写过的文件在重放项目里同样出现、内容逐字一致
    product = proj / "问候.txt"
    assert product.is_file(), "重放没有产出 问候.txt"
    assert product.read_text(encoding="utf-8") == "你好，评测夹具。"
    # 回放脚本应当被走完（收尾轮不是「脚本已用完」兜底）
    assert "（脚本已用完）" not in result.stdout

    # 会话快照进工件（含被评测进程的完整轨迹，事后可审计/再派生）
    home = Path(os.environ["HOME"])
    for session in home.glob(".pai/projects/*/sessions/*.jsonl"):
        shutil.copy(session, eval_artifact_dir / session.name)
