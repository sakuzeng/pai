from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from pai.evals.task_grading import TaskCase, load_case
from pai.evals.task_runner import Limits, require_llm, run_batch

REPO=Path(__file__).resolve().parents[1]
CASES=[load_case(REPO/'evals/tasks'/name) for name in ('locate','fix','tests')]


@pytest.mark.parametrize('env', [{},{'DEEPSEEK_API_KEY':'sk-fake'},
    {'PAI_RUN_LLM_TESTS':'1'},{'PAI_RUN_LLM_TESTS':'1','DEEPSEEK_API_KEY':'sk-在这里填'}])
def test_llm_gate_requires_explicit_optin_and_valid_key(env: dict[str, str]) -> None:
    with pytest.raises(ValueError):
        require_llm(env)


def test_llm_gate_freezes_endpoint_and_does_not_mutate_input() -> None:
    env={'PAI_RUN_LLM_TESTS':'1','DEEPSEEK_API_KEY':'sk-test','PAI_BASE_URL':'http://local'}
    assert require_llm(env)=={'api_key':'sk-test','base_url':'http://local'}
    assert env['DEEPSEEK_API_KEY']=='sk-test'


def test_batch_keeps_nine_trials_no_retries_and_sanitized_manifest(tmp_path: Path) -> None:
    calls=[]
    def trial(case: TaskCase, artifact: Path, **kwargs: object) -> dict:
        calls.append(case.id)
        return {'case':case.id,'execution':'completed','agentEnd':'final',
                'grade':{'status':'pass' if case.id!='fix' else 'fail'},'durationMs':10,
                'metrics':{'tokens':{'total':123},'usageCoverage':'complete'}}
    output=tmp_path/'batch'
    summary=run_batch(CASES,output,scratch_root=tmp_path/'scratch',
        credentials={'api_key':'never-save-this-key','base_url':'http://local'},run_trial=trial)
    assert calls==['locate']*3+['fix']*3+['tests']*3
    assert summary['planned']==9 and summary['completeSuccesses']==6
    assert len((output/'task-results.jsonl').read_text().splitlines())==9
    assert len((output/'runs.jsonl').read_text().splitlines())==9
    manifest=json.loads((output/'manifest.json').read_text())
    assert manifest['model']=='deepseek-flash'
    assert manifest['permissionMode']=='acceptEdits'
    assert len(manifest['codeHash'])==64
    assert len(manifest['cases'][0]['hash'])==64
    assert 'never-save-this-key' not in (output/'manifest.json').read_text()
    assert (output/'report.md').is_file()


def test_total_deadline_prevents_new_trials_and_preserves_denominator(tmp_path: Path) -> None:
    clock=[0.0]; calls=[]
    def trial(case: TaskCase,artifact: Path,**kwargs: object) -> dict:
        calls.append(case.id); clock[0]+=2
        return {'case':case.id,'execution':'timeout','agentEnd':'unknown','grade':{'status':'unavailable'}}
    s=run_batch(CASES,tmp_path/'batch',scratch_root=tmp_path/'scratch',
        credentials={'api_key':'sk-fake','base_url':'http://local'},limits=Limits(batch_seconds=1),
        run_trial=trial,now=lambda:clock[0])
    assert len(calls)==1
    assert s['planned']==9 and s['started']==1 and s['completeSuccesses']==0
    assert s['executionCounts']=={'timeout':1,'not_started':8}


def test_entry_default_never_collects_task_suite_or_fixture_tests() -> None:
    r=subprocess.run([str(REPO/'eval.sh'),'--collect-only','-q'],cwd=REPO,
        capture_output=True,text=True,env={**os.environ,'PATH':str(Path(sys.executable).parent)+os.pathsep+os.environ['PATH']},timeout=15)
    assert r.returncode==0,r.stdout+r.stderr
    assert 'task_suite.py' not in r.stdout
    assert 'test_external.py' not in r.stdout
    assert 'test_visible.py' not in r.stdout


def test_tasks_entry_has_one_offline_contract_and_explicit_real_batch() -> None:
    env={**os.environ,'PATH':str(Path(sys.executable).parent)+os.pathsep+os.environ['PATH']}
    offline=subprocess.run([str(REPO/'eval.sh'),'--tasks','--collect-only','-q'],cwd=REPO,env=env,
                           capture_output=True,text=True,timeout=15)
    assert offline.returncode==0,offline.stdout+offline.stderr
    assert 'test_catalog_contract' in offline.stdout
    assert 'test_real_task_baseline' not in offline.stdout
    live=subprocess.run([str(REPO/'eval.sh'),'--tasks','--llm','--collect-only','-q'],cwd=REPO,env=env,
                        capture_output=True,text=True,timeout=15)
    assert live.returncode==0,live.stdout+live.stderr
    assert 'test_real_task_baseline' in live.stdout


def test_batch_interrupt_records_remaining_trials_before_propagating(tmp_path: Path) -> None:
    calls=[]
    def trial(case: TaskCase,artifact: Path,**kwargs: object) -> dict:
        calls.append(case.id)
        raise KeyboardInterrupt()
    output=tmp_path/'batch'
    with pytest.raises(KeyboardInterrupt):
        run_batch(CASES,output,scratch_root=tmp_path/'scratch',
            credentials={'api_key':'sk-fake','base_url':'http://local'},run_trial=trial)
    assert calls==['locate']
    records=[json.loads(line) for line in (output/'task-results.jsonl').read_text().splitlines()]
    assert len(records)==9
    assert records[0]['execution']=='interrupted'
    assert all(r['execution']=='not_started' for r in records[1:])
