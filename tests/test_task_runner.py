from __future__ import annotations

from dataclasses import replace
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys

import pytest

from fake_llm import FakeClient
from fake_provider import FakeProvider, turn
from pai.evals.task_grading import TaskCase, load_case, prepare
from pai.evals.task_runner import Limits, build_env, run_one
from pai.evals.task_worker import run_worker

CASES = Path(__file__).resolve().parents[1] / "evals/tasks"


def test_worker_runs_real_once_with_fake_client_and_permission_denial(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    case=load_case(CASES/'locate')
    ws=tmp_path/'workspace'
    prepare(case,ws)
    home=tmp_path/'home'; home.mkdir()
    monkeypatch.setenv('HOME',str(home))
    monkeypatch.setenv('PYTHON_DOTENV_DISABLED','1')
    monkeypatch.chdir(ws)
    config={'prompt':case.prompt,'model':'fake-model','max_steps':4,'max_tokens':200000,
            'trace':str(tmp_path/'trace.jsonl'),'result':str(tmp_path/'worker.json')}
    client=FakeClient([
        {'tool_calls':[('bash','{"command":"echo forbidden"}')]},
        {'tool_calls':[('write_file',json.dumps({'path':'answer.json','content':'{"path":"text_rules.py","function":"slugify"}'}))]},
        {'content':'完成'}])
    assert run_worker(config,client=client) == 0
    events=[json.loads(line) for line in (tmp_path/'trace.events.jsonl').read_text().splitlines()]
    assert sum(e.get('event')=='PermissionDecided' and e.get('kind')=='deny' for e in events)==1
    assert [e['name'] for e in events if e['event']=='ToolStart']==['write_file']
    assert events[-1]['reason']=='final'
    assert (ws/'answer.json').is_file()
    assert all(r['model']=='fake-model' for r in client.requests)


@pytest.mark.parametrize('reason,max_steps,max_tokens', [('max_steps',1,200000),('budget',4,1)])
def test_worker_records_budget_and_steps_separately(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, reason: str, max_steps: int, max_tokens: int) -> None:
    ws=tmp_path/'workspace'; prepare(load_case(CASES/'locate'),ws)
    home=tmp_path/'home';home.mkdir()
    monkeypatch.setenv('HOME',str(home));monkeypatch.setenv('PYTHON_DOTENV_DISABLED','1');monkeypatch.chdir(ws)
    config={'prompt':'读取 text_rules.py','model':'fake-model','max_steps':max_steps,'max_tokens':max_tokens,
            'trace':str(tmp_path/'trace.jsonl'),'result':str(tmp_path/'worker.json')}
    client=FakeClient([{'tool_calls':[('read_file','{"path":"text_rules.py"}')],
                        'usage':{'prompt_tokens':100,'completion_tokens':10,'total_tokens':110}}])
    assert run_worker(config,client=client)==0
    events=[json.loads(line) for line in (tmp_path/'trace.events.jsonl').read_text().splitlines()]
    assert events[-1]['reason']==reason


def test_child_environment_ignores_personal_settings_and_proxy_secrets(tmp_path: Path,monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('PAI_MODEL','wrong-model');monkeypatch.setenv('OPENAI_API_KEY','secret-other')
    monkeypatch.setenv('HTTP_PROXY','http://secret-proxy');monkeypatch.setenv('PYTHONPATH','wrong-path')
    env=build_env(tmp_path/'home',tmp_path/'tmp',{'api_key':'sk-fake','base_url':'http://127.0.0.1:1'},'fixed')
    assert env['PAI_MODEL']=='fixed'
    assert env['DEEPSEEK_API_KEY']=='sk-fake'
    assert env['PYTHON_DOTENV_DISABLED']=='1'
    assert all(k not in env for k in ('HTTP_PROXY','OPENAI_API_KEY','PAI_RECALL_MODEL'))
    assert env['HOME']==str(tmp_path/'home')
    assert 'wrong-path' not in env['PYTHONPATH']


def test_real_process_fake_provider_succeeds_and_keeps_artifacts(tmp_path: Path) -> None:
    answer=json.dumps({'path':'text_rules.py','function':'slugify'})
    with FakeProvider([turn(tool_calls=[{'name':'write_file','arguments':{'path':'answer.json','content':answer}}]),
                       turn('完成')]) as provider:
        result=run_one(load_case(CASES/'locate'),tmp_path/'trial',scratch_root=tmp_path/'scratch',
            credentials={'api_key':'sk-fake','base_url':provider.base_url},model='fake-model',limits=Limits(seconds=15))
    assert result['execution']=='completed',result
    assert result['agentEnd']=='final'
    assert result['grade']['status']=='pass'
    assert result['metrics']['toolAttempts']==1
    assert result['metrics']['permissionDenials']==0
    assert list((tmp_path/'trial/sessions').glob('*.jsonl'))
    assert (tmp_path/'trial/workspace/answer.json').is_file()
    assert 'sk-fake' not in (tmp_path/'trial/input.json').read_text()
    assert not list((tmp_path/'scratch').glob('*'))


def test_deadline_stops_worker_and_separate_test_process_group(tmp_path: Path) -> None:
    root=tmp_path/'case';shutil.copytree(CASES/'fix',root)
    (root/'workspace/tests/test_visible.py').write_text(
        'import os,time\nfrom pathlib import Path\ndef test_wait():\n'
        '    Path("running.pid").write_text(str(os.getpid()))\n    time.sleep(60)\n')
    with FakeProvider([turn(tool_calls=[{'name':'run_tests','arguments':{}}])]) as provider:
        result=run_one(load_case(root),tmp_path/'trial',scratch_root=tmp_path/'scratch',
            credentials={'api_key':'sk-fake','base_url':provider.base_url},model='fake-model',limits=Limits(seconds=4))
    assert result['execution']=='timeout',result
    marker=tmp_path/'trial/workspace/running.pid'
    assert marker.is_file(), '测试须实际跑进独立进程组再验证收割'
    pid=int(marker.read_text())
    with pytest.raises(ProcessLookupError):
        os.kill(pid,0)


def test_provider_failure_is_not_a_model_task_failure(tmp_path: Path) -> None:
    result=run_one(load_case(CASES/'locate'),tmp_path/'trial',scratch_root=tmp_path/'scratch',
        credentials={'api_key':'sk-fake','base_url':'http://127.0.0.1:1'},model='fake-model',limits=Limits(seconds=8))
    assert result['execution']=='provider_error'
    assert result['grade']['status']=='unavailable'
    assert result['agentEnd']=='unknown'
    assert (tmp_path/'trial/worker.json').is_file()


def test_forced_stop_reaps_detached_child_when_worker_ignores_term(tmp_path: Path) -> None:
    import subprocess
    import time
    from pai.evals.task_runner import _stop
    marker=tmp_path/'child.pid'
    script=("import os,signal,subprocess,sys,time\nfrom pathlib import Path\n"
            "signal.signal(signal.SIGTERM,signal.SIG_IGN)\n"
            "child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)'],start_new_session=True)\n"
            f"Path({str(marker)!r}).write_text(str(child.pid))\ntime.sleep(60)\n")
    proc=subprocess.Popen([sys.executable,'-c',script],start_new_session=True)
    pid=None
    try:
        until=time.monotonic()+3
        while not marker.exists() and time.monotonic()<until:
            time.sleep(.02)
        assert marker.exists()
        pid=int(marker.read_text())
        _stop(proc)
        until=time.monotonic()+1
        alive=True
        while time.monotonic()<until:
            state=subprocess.run(['ps','-p',str(pid),'-o','stat='],capture_output=True,text=True,timeout=1).stdout.strip()
            alive=bool(state) and not state.startswith('Z')
            if not alive:
                break
            time.sleep(.02)
        assert not alive, 'worker 被强杀后，独立进程组中的工具仍在运行'
    finally:
        if pid is not None:
            try: os.killpg(pid,signal.SIGKILL)
            except ProcessLookupError: pass
        _stop(proc)


def test_interrupted_trial_preserves_workspace_before_temp_cleanup(tmp_path: Path,monkeypatch: pytest.MonkeyPatch) -> None:
    import pai.evals.task_runner as runner
    real_popen=runner.subprocess.Popen
    def start(argv: list[str],*args: object,**kwargs: object) -> subprocess.Popen:
        proc=real_popen(argv,*args,**kwargs)
        if 'pai.evals.task_worker' in argv:
            real_wait=proc.wait
            calls=[0]
            def wait(*args: object,**kwargs: object) -> int:
                calls[0]+=1
                if calls[0]==1:
                    raise KeyboardInterrupt()
                return real_wait(*args,**kwargs)
            proc.wait=wait
        return proc
    monkeypatch.setattr(runner.subprocess,'Popen',start)
    try:
        result=runner.run_one(load_case(CASES/'locate'),tmp_path/'trial',scratch_root=tmp_path/'scratch',
            credentials={'api_key':'sk-fake','base_url':'http://127.0.0.1:1'})
    except KeyboardInterrupt:
        pytest.fail('中断应先保存试验工件，由 batch 在补齐未启动记录后向外抛出')
    assert result['execution']=='interrupted'
    assert (tmp_path/'trial/workspace/text_rules.py').is_file()
    assert (tmp_path/'trial/result.json').is_file()
