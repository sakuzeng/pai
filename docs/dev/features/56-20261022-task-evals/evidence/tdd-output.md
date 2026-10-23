# Feature 56 · 实际 TDD 输出

## t1-red

```text

==================================== ERRORS ====================================
_________________ ERROR collecting tests/test_task_grading.py __________________
ImportError while importing test module '/Users/sakuzeng/improve/coding/agent/projects/pai/tests/test_task_grading.py'.
Hint: make sure your test modules/packages have valid Python names.
Traceback:
/Library/Developer/CommandLineTools/Library/Frameworks/Python3.framework/Versions/3.9/lib/python3.9/importlib/__init__.py:127: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
tests/test_task_grading.py:7: in <module>
    from pai.evals.task_grading import load_case, prepare, grade
E   ModuleNotFoundError: No module named 'pai.evals.task_grading'
=========================== short test summary info ============================
ERROR tests/test_task_grading.py
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
1 error in 0.07s
```

## t1-green

```text
..F.....                                                                 [100%]
=================================== FAILURES ===================================
__________ test_added_tests_must_pass_correct_and_reject_every_mutant __________

tmp_path = PosixPath('/private/tmp/pai56-t1-green/test_added_tests_must_pass_cor0')

    def test_added_tests_must_pass_correct_and_reject_every_mutant(tmp_path):
        case, ws, before = setup_case(tmp_path, "tests")
        assert check(tmp_path, case, ws, before).status == "fail"
        (ws / "tests" / "test_clip.py").write_text("def test_empty():\n    assert True\n")
        assert check(tmp_path, case, ws, before).status == "fail"
        shutil.copyfile(case.root / "reference" / "test_clip.py", ws / "tests" / "test_clip.py")
        result = check(tmp_path, case, ws, before)
>       assert result.status == "pass", result.details
E       AssertionError: [{'assertionFailures': 0, 'check': 'correct', 'collected': 7, 'errors': 0, ...}, {'assertionFailures': 0, 'check': 'ab...ow', 'collected': 7, 'errors': 0, ...}, {'assertionFailures': 1, 'check': 'invalid', 'collected': 7, 'errors': 0, ...}]
E       assert 'fail' == 'pass'
E         
E         - pass
E         + fail

tests/test_task_grading.py:48: AssertionError
=========================== short test summary info ============================
FAILED tests/test_task_grading.py::test_added_tests_must_pass_correct_and_reject_every_mutant
1 failed, 7 passed in 10.01s
```

## t1-behavior-red

```text
..F.....F                                                                [100%]
=================================== FAILURES ===================================
__________ test_added_tests_must_pass_correct_and_reject_every_mutant __________

tmp_path = PosixPath('/private/tmp/pai56-t1-behavior-red/test_added_tests_must_pass_cor0')

    def test_added_tests_must_pass_correct_and_reject_every_mutant(tmp_path):
        case, ws, before = setup_case(tmp_path, "tests")
        assert check(tmp_path, case, ws, before).status == "fail"
        (ws / "tests" / "test_clip.py").write_text("def test_empty():\n    assert True\n")
        assert check(tmp_path, case, ws, before).status == "fail"
        shutil.copyfile(case.root / "reference" / "test_clip.py", ws / "tests" / "test_clip.py")
        result = check(tmp_path, case, ws, before)
>       assert result.status == "pass", result.details
E       AssertionError: [{'assertionFailures': 0, 'check': 'correct', 'collected': 7, 'errors': 0, ...}, {'assertionFailures': 0, 'check': 'ab...ow', 'collected': 7, 'errors': 0, ...}, {'assertionFailures': 1, 'check': 'invalid', 'collected': 7, 'errors': 0, ...}]
E       assert 'fail' == 'pass'
E         
E         - pass
E         + fail

tests/test_task_grading.py:48: AssertionError
_____________ test_fix_cannot_pass_by_skipping_external_assertions _____________

tmp_path = PosixPath('/private/tmp/pai56-t1-behavior-red/test_fix_cannot_pass_by_skippi0')

    def test_fix_cannot_pass_by_skipping_external_assertions(tmp_path):
        case, ws, before = setup_case(tmp_path, "fix")
        (ws / "pagination.py").write_text(
            "from unittest import SkipTest\ndef page_count(total, size):\n    raise SkipTest('skip')\n")
>       assert check(tmp_path, case, ws, before).status == "fail"
E       AssertionError: assert 'pass' == 'fail'
E         
E         - fail
E         + pass

tests/test_task_grading.py:81: AssertionError
=========================== short test summary info ============================
FAILED tests/test_task_grading.py::test_added_tests_must_pass_correct_and_reject_every_mutant
FAILED tests/test_task_grading.py::test_fix_cannot_pass_by_skipping_external_assertions
2 failed, 7 passed in 10.72s
```

## t1-fixed

```text
.........                                                                [100%]
9 passed in 10.31s
```

## t2-red

```text

==================================== ERRORS ====================================
_________________ ERROR collecting tests/test_task_metrics.py __________________
ImportError while importing test module '/Users/sakuzeng/improve/coding/agent/projects/pai/tests/test_task_metrics.py'.
Hint: make sure your test modules/packages have valid Python names.
Traceback:
/Library/Developer/CommandLineTools/Library/Frameworks/Python3.framework/Versions/3.9/lib/python3.9/importlib/__init__.py:127: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
tests/test_task_metrics.py:6: in <module>
    from pai.evals.task_metrics import measure, summarize
E   ModuleNotFoundError: No module named 'pai.evals.task_metrics'
=========================== short test summary info ============================
ERROR tests/test_task_metrics.py
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
1 error in 0.07s
```

## t2-green

```text
.........                                                                [100%]
9 passed in 0.63s
```

## t3-red

```text

==================================== ERRORS ====================================
__________________ ERROR collecting tests/test_task_runner.py __________________
ImportError while importing test module '/Users/sakuzeng/improve/coding/agent/projects/pai/tests/test_task_runner.py'.
Hint: make sure your test modules/packages have valid Python names.
Traceback:
/Library/Developer/CommandLineTools/Library/Frameworks/Python3.framework/Versions/3.9/lib/python3.9/importlib/__init__.py:127: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
tests/test_task_runner.py:14: in <module>
    from pai.evals.task_runner import Limits, build_env, run_one
E   ModuleNotFoundError: No module named 'pai.evals.task_runner'
=========================== short test summary info ============================
ERROR tests/test_task_runner.py
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
1 error in 0.10s
```

## t3-green

```text
FFF.FF.                                                                  [100%]
=================================== FAILURES ===================================
______ test_worker_runs_real_once_with_fake_client_and_permission_denial _______

tmp_path = PosixPath('/private/tmp/pai56-t3-green/test_worker_runs_real_once_wit0')
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10a0caaf0>

    def test_worker_runs_real_once_with_fake_client_and_permission_denial(tmp_path, monkeypatch):
        case=load_case(CASES/'locate')
        ws=tmp_path/'workspace'
        prepare(case,ws)
        home=tmp_path/'home'; home.mkdir()
        monkeypatch.setenv('HOME',str(home))
        monkeypatch.setenv('PYTHON_DOTENV_DISABLED','1')
        monkeypatch.chdir(ws)
        config={'prompt':case.prompt,'model':'fake-model','max_steps':4,'max_tokens':200000,
                'events':str(tmp_path/'events.jsonl'),'result':str(tmp_path/'worker.json')}
        client=FakeClient([
            {'tool_calls':[('bash','{"command":"echo forbidden"}')]},
            {'tool_calls':[('write_file',json.dumps({'path':'answer.json','content':'{"path":"text_rules.py","function":"slugify"}'}))]},
            {'content':'完成'}])
        assert run_worker(config,client=client) == 0
>       events=[json.loads(line) for line in (tmp_path/'events.jsonl').read_text().splitlines()]

/Users/sakuzeng/improve/coding/agent/projects/pai/tests/test_task_runner.py:35: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
/Library/Developer/CommandLineTools/Library/Frameworks/Python3.framework/Versions/3.9/lib/python3.9/pathlib.py:1256: in read_text
    with self.open(mode='r', encoding=encoding, errors=errors) as f:
/Library/Developer/CommandLineTools/Library/Frameworks/Python3.framework/Versions/3.9/lib/python3.9/pathlib.py:1242: in open
    return io.open(self, mode, buffering, encoding, errors, newline,
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = PosixPath('/private/tmp/pai56-t3-green/test_worker_runs_real_once_wit0/events.jsonl')
name = '/private/tmp/pai56-t3-green/test_worker_runs_real_once_wit0/events.jsonl'
flags = 16777216, mode = 438

    def _opener(self, name, flags, mode=0o666):
        # A stub for the opener argument to built-in open()
>       return self._accessor.open(self, flags, mode)
E       FileNotFoundError: [Errno 2] No such file or directory: '/private/tmp/pai56-t3-green/test_worker_runs_real_once_wit0/events.jsonl'

/Library/Developer/CommandLineTools/Library/Frameworks/Python3.framework/Versions/3.9/lib/python3.9/pathlib.py:1110: FileNotFoundError
----------------------------- Captured stdout call -----------------------------
完成
_____ test_worker_records_budget_and_steps_separately[max_steps-1-200000] ______

tmp_path = PosixPath('/private/tmp/pai56-t3-green/test_worker_records_budget_and0')
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10a157910>
reason = 'max_steps', max_steps = 1, max_tokens = 200000

    @pytest.mark.parametrize('reason,max_steps,max_tokens', [('max_steps',1,200000),('budget',4,1)])
    def test_worker_records_budget_and_steps_separately(tmp_path, monkeypatch, reason, max_steps, max_tokens):
        ws=tmp_path/'workspace'; prepare(load_case(CASES/'locate'),ws)
        home=tmp_path/'home';home.mkdir()
        monkeypatch.setenv('HOME',str(home));monkeypatch.setenv('PYTHON_DOTENV_DISABLED','1');monkeypatch.chdir(ws)
        config={'prompt':'读取 text_rules.py','model':'fake-model','max_steps':max_steps,'max_tokens':max_tokens,
                'events':str(tmp_path/'events.jsonl'),'result':str(tmp_path/'worker.json')}
        client=FakeClient([{'tool_calls':[('read_file','{"path":"text_rules.py"}')],
                            'usage':{'prompt_tokens':100,'completion_tokens':10,'total_tokens':110}}])
        assert run_worker(config,client=client)==0
>       events=[json.loads(line) for line in (tmp_path/'events.jsonl').read_text().splitlines()]

/Users/sakuzeng/improve/coding/agent/projects/pai/tests/test_task_runner.py:53: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
/Library/Developer/CommandLineTools/Library/Frameworks/Python3.framework/Versions/3.9/lib/python3.9/pathlib.py:1256: in read_text
    with self.open(mode='r', encoding=encoding, errors=errors) as f:
/Library/Developer/CommandLineTools/Library/Frameworks/Python3.framework/Versions/3.9/lib/python3.9/pathlib.py:1242: in open
    return io.open(self, mode, buffering, encoding, errors, newline,
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = PosixPath('/private/tmp/pai56-t3-green/test_worker_records_budget_and0/events.jsonl')
name = '/private/tmp/pai56-t3-green/test_worker_records_budget_and0/events.jsonl'
flags = 16777216, mode = 438

    def _opener(self, name, flags, mode=0o666):
        # A stub for the opener argument to built-in open()
>       return self._accessor.open(self, flags, mode)
E       FileNotFoundError: [Errno 2] No such file or directory: '/private/tmp/pai56-t3-green/test_worker_records_budget_and0/events.jsonl'

/Library/Developer/CommandLineTools/Library/Frameworks/Python3.framework/Versions/3.9/lib/python3.9/pathlib.py:1110: FileNotFoundError
----------------------------- Captured stdout call -----------------------------
达到最大步数（1），任务可能未完成。
_________ test_worker_records_budget_and_steps_separately[budget-4-1] __________

tmp_path = PosixPath('/private/tmp/pai56-t3-green/test_worker_records_budget_and1')
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10a1a0340>
reason = 'budget', max_steps = 4, max_tokens = 1

    @pytest.mark.parametrize('reason,max_steps,max_tokens', [('max_steps',1,200000),('budget',4,1)])
    def test_worker_records_budget_and_steps_separately(tmp_path, monkeypatch, reason, max_steps, max_tokens):
        ws=tmp_path/'workspace'; prepare(load_case(CASES/'locate'),ws)
        home=tmp_path/'home';home.mkdir()
        monkeypatch.setenv('HOME',str(home));monkeypatch.setenv('PYTHON_DOTENV_DISABLED','1');monkeypatch.chdir(ws)
        config={'prompt':'读取 text_rules.py','model':'fake-model','max_steps':max_steps,'max_tokens':max_tokens,
                'events':str(tmp_path/'events.jsonl'),'result':str(tmp_path/'worker.json')}
        client=FakeClient([{'tool_calls':[('read_file','{"path":"text_rules.py"}')],
                            'usage':{'prompt_tokens':100,'completion_tokens':10,'total_tokens':110}}])
        assert run_worker(config,client=client)==0
>       events=[json.loads(line) for line in (tmp_path/'events.jsonl').read_text().splitlines()]

/Users/sakuzeng/improve/coding/agent/projects/pai/tests/test_task_runner.py:53: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
/Library/Developer/CommandLineTools/Library/Frameworks/Python3.framework/Versions/3.9/lib/python3.9/pathlib.py:1256: in read_text
    with self.open(mode='r', encoding=encoding, errors=errors) as f:
/Library/Developer/CommandLineTools/Library/Frameworks/Python3.framework/Versions/3.9/lib/python3.9/pathlib.py:1242: in open
    return io.open(self, mode, buffering, encoding, errors, newline,
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = PosixPath('/private/tmp/pai56-t3-green/test_worker_records_budget_and1/events.jsonl')
name = '/private/tmp/pai56-t3-green/test_worker_records_budget_and1/events.jsonl'
flags = 16777216, mode = 438

    def _opener(self, name, flags, mode=0o666):
        # A stub for the opener argument to built-in open()
>       return self._accessor.open(self, flags, mode)
E       FileNotFoundError: [Errno 2] No such file or directory: '/private/tmp/pai56-t3-green/test_worker_records_budget_and1/events.jsonl'

/Library/Developer/CommandLineTools/Library/Frameworks/Python3.framework/Versions/3.9/lib/python3.9/pathlib.py:1110: FileNotFoundError
----------------------------- Captured stdout call -----------------------------
已达用量预算：累计 110 token 超过上限 1，在第 2 步发出请求前停止。任务可能未完成。要放宽用 --max-tokens（0 = 不限）。
_________ test_real_process_fake_provider_succeeds_and_keeps_artifacts _________

tmp_path = PosixPath('/private/tmp/pai56-t3-green/test_real_process_fake_provide0')

    def test_real_process_fake_provider_succeeds_and_keeps_artifacts(tmp_path):
        answer=json.dumps({'path':'text_rules.py','function':'slugify'})
>       with FakeProvider([turn(tool_calls=[{'name':'write_file','arguments':{'path':'answer.json','content':answer}}]),
                           turn('完成')]) as provider:

tests/test_task_runner.py:71: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
tests/fake_provider.py:230: in __enter__
    return self.start()
tests/fake_provider.py:213: in start
    self._server = Quiet(("127.0.0.1", 0), Handler)
/Library/Developer/CommandLineTools/Library/Frameworks/Python3.framework/Versions/3.9/lib/python3.9/socketserver.py:452: in __init__
    self.server_bind()
/Library/Developer/CommandLineTools/Library/Frameworks/Python3.framework/Versions/3.9/lib/python3.9/http/server.py:138: in server_bind
    socketserver.TCPServer.server_bind(self)
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <fake_provider.FakeProvider.start.<locals>.Quiet object at 0x10a1ddee0>

    def server_bind(self):
        """Called by constructor to bind the socket.
    
        May be overridden.
    
        """
        if self.allow_reuse_address:
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
>       self.socket.bind(self.server_address)
E       PermissionError: [Errno 1] Operation not permitted

/Library/Developer/CommandLineTools/Library/Frameworks/Python3.framework/Versions/3.9/lib/python3.9/socketserver.py:466: PermissionError
__________ test_deadline_stops_worker_and_separate_test_process_group __________

tmp_path = PosixPath('/private/tmp/pai56-t3-green/test_deadline_stops_worker_and0')

    def test_deadline_stops_worker_and_separate_test_process_group(tmp_path):
        root=tmp_path/'case';shutil.copytree(CASES/'fix',root)
        (root/'workspace/tests/test_visible.py').write_text(
            'import os,time\nfrom pathlib import Path\ndef test_wait():\n'
            '    Path("running.pid").write_text(str(os.getpid()))\n    time.sleep(60)\n')
>       with FakeProvider([turn(tool_calls=[{'name':'run_tests','arguments':{}}])]) as provider:

tests/test_task_runner.py:91: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
tests/fake_provider.py:230: in __enter__
    return self.start()
tests/fake_provider.py:213: in start
    self._server = Quiet(("127.0.0.1", 0), Handler)
/Library/Developer/CommandLineTools/Library/Frameworks/Python3.framework/Versions/3.9/lib/python3.9/socketserver.py:452: in __init__
    self.server_bind()
/Library/Developer/CommandLineTools/Library/Frameworks/Python3.framework/Versions/3.9/lib/python3.9/http/server.py:138: in server_bind
    socketserver.TCPServer.server_bind(self)
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <fake_provider.FakeProvider.start.<locals>.Quiet object at 0x10a327040>

    def server_bind(self):
        """Called by constructor to bind the socket.
    
        May be overridden.
    
        """
        if self.allow_reuse_address:
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
>       self.socket.bind(self.server_address)
E       PermissionError: [Errno 1] Operation not permitted

/Library/Developer/CommandLineTools/Library/Frameworks/Python3.framework/Versions/3.9/lib/python3.9/socketserver.py:466: PermissionError
=========================== short test summary info ============================
FAILED tests/test_task_runner.py::test_worker_runs_real_once_with_fake_client_and_permission_denial
FAILED tests/test_task_runner.py::test_worker_records_budget_and_steps_separately[max_steps-1-200000]
FAILED tests/test_task_runner.py::test_worker_records_budget_and_steps_separately[budget-4-1]
FAILED tests/test_task_runner.py::test_real_process_fake_provider_succeeds_and_keeps_artifacts
FAILED tests/test_task_runner.py::test_deadline_stops_worker_and_separate_test_process_group
5 failed, 2 passed in 1.98s
```

## t3-outside

```text
.......                                                                  [100%]
7 passed in 8.05s
```

## t4-red

```text

==================================== ERRORS ====================================
__________________ ERROR collecting tests/test_task_entry.py ___________________
ImportError while importing test module '/Users/sakuzeng/improve/coding/agent/projects/pai/tests/test_task_entry.py'.
Hint: make sure your test modules/packages have valid Python names.
Traceback:
/Library/Developer/CommandLineTools/Library/Frameworks/Python3.framework/Versions/3.9/lib/python3.9/importlib/__init__.py:127: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
tests/test_task_entry.py:10: in <module>
    from pai.evals.task_runner import Limits, require_llm, run_batch
E   ImportError: cannot import name 'require_llm' from 'pai.evals.task_runner' (/Users/sakuzeng/improve/coding/agent/projects/pai/src/pai/evals/task_runner.py)
=========================== short test summary info ============================
ERROR tests/test_task_entry.py
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
1 error in 0.08s
```

## t4-green

```text
.........                                                                [100%]
9 passed in 3.21s
```

## grader-isolation-red

```text
F                                                                        [100%]
=================================== FAILURES ===================================
__________ test_external_grader_never_loads_source_checkout_conftest ___________

tmp_path = PosixPath('/private/tmp/pai56-grader-isolation-red/test_external_grader_never_loa0')

    def test_external_grader_never_loads_source_checkout_conftest(tmp_path):
        source=tmp_path/'source'
        root=source/'case'
        shutil.copytree(CASES/'fix',root)
        (source/'conftest.py').write_text("raise RuntimeError('source conftest must not execute')\n")
        case=load_case(root)
        ws=tmp_path/'workspace'
        before=prepare(case,ws)
        shutil.copyfile(root/'reference/pagination.py',ws/'pagination.py')
        result=check(tmp_path,case,ws,before)
>       assert result.status=='pass',result.details
E       AssertionError: [{'assertionFailures': 0, 'check': 'external_tests', 'collected': 0, 'errors': 1, ...}]
E       assert 'fail' == 'pass'
E         
E         - pass
E         + fail

tests/test_task_grading.py:94: AssertionError
=========================== short test summary info ============================
FAILED tests/test_task_grading.py::test_external_grader_never_loads_source_checkout_conftest
1 failed, 9 deselected in 0.96s
```

## new-tests（隔离修复后组合验证）

```text
...................................                                      [100%]
35 passed in 20.32s
```

## full-first

```text
........................................................................ [  3%]
........................................................................ [  7%]
F....................................................................... [ 11%]
........................................................................ [ 14%]
........................................................................ [ 18%]
........................................................................ [ 22%]
........................................................................ [ 25%]
........................................................................ [ 29%]
........................................................................ [ 33%]
........................................................................ [ 36%]
........................................................................ [ 40%]
........................................................................ [ 44%]
........................................................................ [ 47%]
........................................................................ [ 51%]
........................................................................ [ 55%]
........................................................................ [ 58%]
........................................................................ [ 62%]
........................................................................ [ 66%]
........................................................................ [ 69%]
........................................................................ [ 73%]
........................................................................ [ 77%]
........................................................................ [ 80%]
........................................................................ [ 84%]
........................................................................ [ 88%]
........................................................................ [ 91%]
........................................................................ [ 95%]
........................................................................ [ 99%]
..................                                                       [100%]
=================================== FAILURES ===================================
__________________ test_status_reports_the_current_test_count __________________

request = <FixtureRequest for <Function test_status_reports_the_current_test_count>>

    def test_status_reports_the_current_test_count(request: pytest.FixtureRequest) -> None:
        """STATUS 的测试数字漂了三次（R#2 是「严重」级别的旧账，2026-08-10 又漂两次）。
    
        人肉对账靠不住：每次补完一个漏就该回头改 STATUS，而那正是最容易忘的一步。
        `testscollected` 是**选中**的用例数（不含 deselected），全绿时恰等于 passed 数。
        跑子集时这个数当然对不上，所以只在完整跑（无 -k、无显式路径）时校验。
        """
        # 只认标准入口 `./test.sh`（它带 -m "not llm"）：裸跑 pytest 时那 3 条 llm 测试是
        # **skipped**（算进 collected），带 marker 时是 **deselected**（不算），两者差 3。
        # STATUS 记的是 ./test.sh 的数字，所以对账也只在那个口径下做。
        if (request.config.option.keyword
                or request.config.args != ["tests"]
                or request.config.option.markexpr != "not llm"):
            pytest.skip("只在标准入口 ./test.sh 的口径下对账")
    
        text = (ROOT / "docs" / "dev" / "STATUS.md").read_text(encoding="utf-8")
        reported = _status_passed_count(text)
>       assert reported == request.session.testscollected, (
            f"STATUS 写着 {reported} passed，实际选中 {request.session.testscollected} 条——"
            "补完漏别忘了回头改 STATUS"
        )
E       AssertionError: STATUS 写着 1927 passed，实际选中 1962 条——补完漏别忘了回头改 STATUS
E       assert 1927 == 1962
E        +  where 1962 = <Session  exitstatus=<ExitCode.OK: 0> testsfailed=0 testscollected=1962>.testscollected
E        +    where <Session  exitstatus=<ExitCode.OK: 0> testsfailed=0 testscollected=1962> = <FixtureRequest for <Function test_status_reports_the_current_test_count>>.session

tests/test_docs_consistency.py:226: AssertionError
=========================== short test summary info ============================
FAILED tests/test_docs_consistency.py::test_status_reports_the_current_test_count
1 failed, 1961 passed, 8 deselected in 213.83s (0:03:33)
```

## lifecycle-red

```text
FFF                                                                      [100%]
=================================== FAILURES ===================================
________ test_forced_stop_reaps_detached_child_when_worker_ignores_term ________

tmp_path = PosixPath('/private/tmp/pai56-lifecycle-red/test_forced_stop_reaps_detache0')

    def test_forced_stop_reaps_detached_child_when_worker_ignores_term(tmp_path):
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
>               state=subprocess.run(['ps','-p',str(pid),'-o','stat='],capture_output=True,text=True,timeout=1).stdout.strip()

tests/test_task_runner.py:132: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
/Library/Developer/CommandLineTools/Library/Frameworks/Python3.framework/Versions/3.9/lib/python3.9/subprocess.py:505: in run
    with Popen(*popenargs, **kwargs) as process:
/Library/Developer/CommandLineTools/Library/Frameworks/Python3.framework/Versions/3.9/lib/python3.9/subprocess.py:951: in __init__
    self._execute_child(args, executable, preexec_fn, close_fds,
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <Popen: returncode: 255 args: ['ps', '-p', '92576', '-o', 'stat=']>
args = ['ps', '-p', '92576', '-o', 'stat='], executable = b'ps'
preexec_fn = None, close_fds = True, pass_fds = (), cwd = None, env = None
startupinfo = None, creationflags = 0, shell = False, p2cread = -1
p2cwrite = -1, c2pread = 12, c2pwrite = 13, errread = 14, errwrite = 15
restore_signals = True, gid = None, gids = None, uid = None, umask = -1
start_new_session = False

    def _execute_child(self, args, executable, preexec_fn, close_fds,
                       pass_fds, cwd, env,
                       startupinfo, creationflags, shell,
                       p2cread, p2cwrite,
                       c2pread, c2pwrite,
                       errread, errwrite,
                       restore_signals,
                       gid, gids, uid, umask,
                       start_new_session):
        """Execute program (POSIX version)"""
    
        if isinstance(args, (str, bytes)):
            args = [args]
        elif isinstance(args, os.PathLike):
            if shell:
                raise TypeError('path-like args is not allowed when '
                                'shell is true')
            args = [args]
        else:
            args = list(args)
    
        if shell:
            # On Android the default shell is at '/system/bin/sh'.
            unix_shell = ('/system/bin/sh' if
                      hasattr(sys, 'getandroidapilevel') else '/bin/sh')
            args = [unix_shell, "-c"] + args
            if executable:
                args[0] = executable
    
        if executable is None:
            executable = args[0]
    
        sys.audit("subprocess.Popen", executable, args, cwd, env)
    
        if (_USE_POSIX_SPAWN
                and os.path.dirname(executable)
                and preexec_fn is None
                and not close_fds
                and not pass_fds
                and cwd is None
                and (p2cread == -1 or p2cread > 2)
                and (c2pwrite == -1 or c2pwrite > 2)
                and (errwrite == -1 or errwrite > 2)
                and not start_new_session
                and gid is None
                and gids is None
                and uid is None
                and umask < 0):
            self._posix_spawn(args, executable, env, restore_signals,
                              p2cread, p2cwrite,
                              c2pread, c2pwrite,
                              errread, errwrite)
            return
    
        orig_executable = executable
    
        # For transferring possible exec failure from child to parent.
        # Data format: "exception name:hex errno:description"
        # Pickle is not used; it is complex and involves memory allocation.
        errpipe_read, errpipe_write = os.pipe()
        # errpipe_write must not be in the standard io 0, 1, or 2 fd range.
        low_fds_to_close = []
        while errpipe_write < 3:
            low_fds_to_close.append(errpipe_write)
            errpipe_write = os.dup(errpipe_write)
        for low_fd in low_fds_to_close:
            os.close(low_fd)
        try:
            try:
                # We must avoid complex work that could involve
                # malloc or free in the child process to avoid
                # potential deadlocks, thus we do all this here.
                # and pass it to fork_exec()
    
                if env is not None:
                    env_list = []
                    for k, v in env.items():
                        k = os.fsencode(k)
                        if b'=' in k:
                            raise ValueError("illegal environment variable name")
                        env_list.append(k + b'=' + os.fsencode(v))
                else:
                    env_list = None  # Use execv instead of execve.
                executable = os.fsencode(executable)
                if os.path.dirname(executable):
                    executable_list = (executable,)
                else:
                    # This matches the behavior of os._execvpe().
                    executable_list = tuple(
                        os.path.join(os.fsencode(dir), executable)
                        for dir in os.get_exec_path(env))
                fds_to_keep = set(pass_fds)
                fds_to_keep.add(errpipe_write)
                self.pid = _posixsubprocess.fork_exec(
                        args, executable_list,
                        close_fds, tuple(sorted(map(int, fds_to_keep))),
                        cwd, env_list,
                        p2cread, p2cwrite, c2pread, c2pwrite,
                        errread, errwrite,
                        errpipe_read, errpipe_write,
                        restore_signals, start_new_session,
                        gid, gids, uid, umask,
                        preexec_fn)
                self._child_created = True
            finally:
                # be sure the FD is closed no matter what
                os.close(errpipe_write)
    
            self._close_pipe_fds(p2cread, p2cwrite,
                                 c2pread, c2pwrite,
                                 errread, errwrite)
    
            # Wait for exec to fail or succeed; possibly raising an
            # exception (limited in size)
            errpipe_data = bytearray()
            while True:
                part = os.read(errpipe_read, 50000)
                errpipe_data += part
                if not part or len(errpipe_data) > 50000:
                    break
        finally:
            # be sure the FD is closed no matter what
            os.close(errpipe_read)
    
        if errpipe_data:
            try:
                pid, sts = os.waitpid(self.pid, 0)
                if pid == self.pid:
                    self._handle_exitstatus(sts)
                else:
                    self.returncode = sys.maxsize
            except ChildProcessError:
                pass
    
            try:
                exception_name, hex_errno, err_msg = (
                        errpipe_data.split(b':', 2))
                # The encoding here should match the encoding
                # written in by the subprocess implementations
                # like _posixsubprocess
                err_msg = err_msg.decode()
            except ValueError:
                exception_name = b'SubprocessError'
                hex_errno = b'0'
                err_msg = 'Bad exception data from child: {!r}'.format(
                              bytes(errpipe_data))
            child_exception_type = getattr(
                    builtins, exception_name.decode('ascii'),
                    SubprocessError)
            if issubclass(child_exception_type, OSError) and hex_errno:
                errno_num = int(hex_errno, 16)
                child_exec_never_called = (err_msg == "noexec")
                if child_exec_never_called:
                    err_msg = ""
                    # The error must be from chdir(cwd).
                    err_filename = cwd
                else:
                    err_filename = orig_executable
                if errno_num != 0:
                    err_msg = os.strerror(errno_num)
>               raise child_exception_type(errno_num, err_msg, err_filename)
E               PermissionError: [Errno 1] Operation not permitted: 'ps'

/Library/Developer/CommandLineTools/Library/Frameworks/Python3.framework/Versions/3.9/lib/python3.9/subprocess.py:1821: PermissionError
________ test_interrupted_trial_preserves_workspace_before_temp_cleanup ________

tmp_path = PosixPath('/private/tmp/pai56-lifecycle-red/test_interrupted_trial_preserv0')
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10846be50>

    def test_interrupted_trial_preserves_workspace_before_temp_cleanup(tmp_path,monkeypatch):
        import pai.evals.task_runner as runner
        real_popen=runner.subprocess.Popen
        def start(argv,*args,**kwargs):
            proc=real_popen(argv,*args,**kwargs)
            if 'pai.evals.task_worker' in argv:
                real_wait=proc.wait
                calls=[0]
                def wait(*args,**kwargs):
                    calls[0]+=1
                    if calls[0]==1:
                        raise KeyboardInterrupt()
                    return real_wait(*args,**kwargs)
                proc.wait=wait
            return proc
        monkeypatch.setattr(runner.subprocess,'Popen',start)
        try:
>           result=runner.run_one(load_case(CASES/'locate'),tmp_path/'trial',scratch_root=tmp_path/'scratch',
                credentials={'api_key':'sk-fake','base_url':'http://127.0.0.1:1'})

tests/test_task_runner.py:162: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
src/pai/evals/task_runner.py:101: in run_one
    proc.wait(timeout=max(0.001, deadline - time.monotonic()))
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

args = (), kwargs = {'timeout': 179.976587541}

    def wait(*args,**kwargs):
        calls[0]+=1
        if calls[0]==1:
>           raise KeyboardInterrupt()
E           KeyboardInterrupt

tests/test_task_runner.py:156: KeyboardInterrupt

During handling of the above exception, another exception occurred:

tmp_path = PosixPath('/private/tmp/pai56-lifecycle-red/test_interrupted_trial_preserv0')
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10846be50>

    def test_interrupted_trial_preserves_workspace_before_temp_cleanup(tmp_path,monkeypatch):
        import pai.evals.task_runner as runner
        real_popen=runner.subprocess.Popen
        def start(argv,*args,**kwargs):
            proc=real_popen(argv,*args,**kwargs)
            if 'pai.evals.task_worker' in argv:
                real_wait=proc.wait
                calls=[0]
                def wait(*args,**kwargs):
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
>           pytest.fail('中断应先保存试验工件，由 batch 在补齐未启动记录后向外抛出')
E           Failed: 中断应先保存试验工件，由 batch 在补齐未启动记录后向外抛出

tests/test_task_runner.py:165: Failed
_______ test_batch_interrupt_records_remaining_trials_before_propagating _______

tmp_path = PosixPath('/private/tmp/pai56-lifecycle-red/test_batch_interrupt_records_r0')

    def test_batch_interrupt_records_remaining_trials_before_propagating(tmp_path):
        calls=[]
        def trial(case,artifact,**kwargs):
            calls.append(case.id)
            raise KeyboardInterrupt()
        output=tmp_path/'batch'
        with pytest.raises(KeyboardInterrupt):
            run_batch(CASES,output,scratch_root=tmp_path/'scratch',
                credentials={'api_key':'sk-fake','base_url':'http://local'},run_trial=trial)
        assert calls==['locate']
>       records=[json.loads(line) for line in (output/'task-results.jsonl').read_text().splitlines()]

tests/test_task_entry.py:97: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
/Library/Developer/CommandLineTools/Library/Frameworks/Python3.framework/Versions/3.9/lib/python3.9/pathlib.py:1256: in read_text
    with self.open(mode='r', encoding=encoding, errors=errors) as f:
/Library/Developer/CommandLineTools/Library/Frameworks/Python3.framework/Versions/3.9/lib/python3.9/pathlib.py:1242: in open
    return io.open(self, mode, buffering, encoding, errors, newline,
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = PosixPath('/private/tmp/pai56-lifecycle-red/test_batch_interrupt_records_r0/batch/task-results.jsonl')
name = '/private/tmp/pai56-lifecycle-red/test_batch_interrupt_records_r0/batch/task-results.jsonl'
flags = 16777216, mode = 438

    def _opener(self, name, flags, mode=0o666):
        # A stub for the opener argument to built-in open()
>       return self._accessor.open(self, flags, mode)
E       FileNotFoundError: [Errno 2] No such file or directory: '/private/tmp/pai56-lifecycle-red/test_batch_interrupt_records_r0/batch/task-results.jsonl'

/Library/Developer/CommandLineTools/Library/Frameworks/Python3.framework/Versions/3.9/lib/python3.9/pathlib.py:1110: FileNotFoundError
=========================== short test summary info ============================
FAILED tests/test_task_runner.py::test_forced_stop_reaps_detached_child_when_worker_ignores_term
FAILED tests/test_task_runner.py::test_interrupted_trial_preserves_workspace_before_temp_cleanup
FAILED tests/test_task_entry.py::test_batch_interrupt_records_remaining_trials_before_propagating
3 failed, 16 deselected in 1.90s
```

## lifecycle-green

```text
FF.                                                                      [100%]
=================================== FAILURES ===================================
________ test_forced_stop_reaps_detached_child_when_worker_ignores_term ________

tmp_path = PosixPath('/private/tmp/pai56-lifecycle-green/test_forced_stop_reaps_detache0')

    def test_forced_stop_reaps_detached_child_when_worker_ignores_term(tmp_path):
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
>               state=subprocess.run(['ps','-p',str(pid),'-o','stat='],capture_output=True,text=True,timeout=1).stdout.strip()

tests/test_task_runner.py:132: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
/Library/Developer/CommandLineTools/Library/Frameworks/Python3.framework/Versions/3.9/lib/python3.9/subprocess.py:505: in run
    with Popen(*popenargs, **kwargs) as process:
/Library/Developer/CommandLineTools/Library/Frameworks/Python3.framework/Versions/3.9/lib/python3.9/subprocess.py:951: in __init__
    self._execute_child(args, executable, preexec_fn, close_fds,
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <Popen: returncode: 255 args: ['ps', '-p', '92659', '-o', 'stat=']>
args = ['ps', '-p', '92659', '-o', 'stat='], executable = b'ps'
preexec_fn = None, close_fds = True, pass_fds = (), cwd = None, env = None
startupinfo = None, creationflags = 0, shell = False, p2cread = -1
p2cwrite = -1, c2pread = 12, c2pwrite = 13, errread = 14, errwrite = 15
restore_signals = True, gid = None, gids = None, uid = None, umask = -1
start_new_session = False

    def _execute_child(self, args, executable, preexec_fn, close_fds,
                       pass_fds, cwd, env,
                       startupinfo, creationflags, shell,
                       p2cread, p2cwrite,
                       c2pread, c2pwrite,
                       errread, errwrite,
                       restore_signals,
                       gid, gids, uid, umask,
                       start_new_session):
        """Execute program (POSIX version)"""
    
        if isinstance(args, (str, bytes)):
            args = [args]
        elif isinstance(args, os.PathLike):
            if shell:
                raise TypeError('path-like args is not allowed when '
                                'shell is true')
            args = [args]
        else:
            args = list(args)
    
        if shell:
            # On Android the default shell is at '/system/bin/sh'.
            unix_shell = ('/system/bin/sh' if
                      hasattr(sys, 'getandroidapilevel') else '/bin/sh')
            args = [unix_shell, "-c"] + args
            if executable:
                args[0] = executable
    
        if executable is None:
            executable = args[0]
    
        sys.audit("subprocess.Popen", executable, args, cwd, env)
    
        if (_USE_POSIX_SPAWN
                and os.path.dirname(executable)
                and preexec_fn is None
                and not close_fds
                and not pass_fds
                and cwd is None
                and (p2cread == -1 or p2cread > 2)
                and (c2pwrite == -1 or c2pwrite > 2)
                and (errwrite == -1 or errwrite > 2)
                and not start_new_session
                and gid is None
                and gids is None
                and uid is None
                and umask < 0):
            self._posix_spawn(args, executable, env, restore_signals,
                              p2cread, p2cwrite,
                              c2pread, c2pwrite,
                              errread, errwrite)
            return
    
        orig_executable = executable
    
        # For transferring possible exec failure from child to parent.
        # Data format: "exception name:hex errno:description"
        # Pickle is not used; it is complex and involves memory allocation.
        errpipe_read, errpipe_write = os.pipe()
        # errpipe_write must not be in the standard io 0, 1, or 2 fd range.
        low_fds_to_close = []
        while errpipe_write < 3:
            low_fds_to_close.append(errpipe_write)
            errpipe_write = os.dup(errpipe_write)
        for low_fd in low_fds_to_close:
            os.close(low_fd)
        try:
            try:
                # We must avoid complex work that could involve
                # malloc or free in the child process to avoid
                # potential deadlocks, thus we do all this here.
                # and pass it to fork_exec()
    
                if env is not None:
                    env_list = []
                    for k, v in env.items():
                        k = os.fsencode(k)
                        if b'=' in k:
                            raise ValueError("illegal environment variable name")
                        env_list.append(k + b'=' + os.fsencode(v))
                else:
                    env_list = None  # Use execv instead of execve.
                executable = os.fsencode(executable)
                if os.path.dirname(executable):
                    executable_list = (executable,)
                else:
                    # This matches the behavior of os._execvpe().
                    executable_list = tuple(
                        os.path.join(os.fsencode(dir), executable)
                        for dir in os.get_exec_path(env))
                fds_to_keep = set(pass_fds)
                fds_to_keep.add(errpipe_write)
                self.pid = _posixsubprocess.fork_exec(
                        args, executable_list,
                        close_fds, tuple(sorted(map(int, fds_to_keep))),
                        cwd, env_list,
                        p2cread, p2cwrite, c2pread, c2pwrite,
                        errread, errwrite,
                        errpipe_read, errpipe_write,
                        restore_signals, start_new_session,
                        gid, gids, uid, umask,
                        preexec_fn)
                self._child_created = True
            finally:
                # be sure the FD is closed no matter what
                os.close(errpipe_write)
    
            self._close_pipe_fds(p2cread, p2cwrite,
                                 c2pread, c2pwrite,
                                 errread, errwrite)
    
            # Wait for exec to fail or succeed; possibly raising an
            # exception (limited in size)
            errpipe_data = bytearray()
            while True:
                part = os.read(errpipe_read, 50000)
                errpipe_data += part
                if not part or len(errpipe_data) > 50000:
                    break
        finally:
            # be sure the FD is closed no matter what
            os.close(errpipe_read)
    
        if errpipe_data:
            try:
                pid, sts = os.waitpid(self.pid, 0)
                if pid == self.pid:
                    self._handle_exitstatus(sts)
                else:
                    self.returncode = sys.maxsize
            except ChildProcessError:
                pass
    
            try:
                exception_name, hex_errno, err_msg = (
                        errpipe_data.split(b':', 2))
                # The encoding here should match the encoding
                # written in by the subprocess implementations
                # like _posixsubprocess
                err_msg = err_msg.decode()
            except ValueError:
                exception_name = b'SubprocessError'
                hex_errno = b'0'
                err_msg = 'Bad exception data from child: {!r}'.format(
                              bytes(errpipe_data))
            child_exception_type = getattr(
                    builtins, exception_name.decode('ascii'),
                    SubprocessError)
            if issubclass(child_exception_type, OSError) and hex_errno:
                errno_num = int(hex_errno, 16)
                child_exec_never_called = (err_msg == "noexec")
                if child_exec_never_called:
                    err_msg = ""
                    # The error must be from chdir(cwd).
                    err_filename = cwd
                else:
                    err_filename = orig_executable
                if errno_num != 0:
                    err_msg = os.strerror(errno_num)
>               raise child_exception_type(errno_num, err_msg, err_filename)
E               PermissionError: [Errno 1] Operation not permitted: 'ps'

/Library/Developer/CommandLineTools/Library/Frameworks/Python3.framework/Versions/3.9/lib/python3.9/subprocess.py:1821: PermissionError
________ test_interrupted_trial_preserves_workspace_before_temp_cleanup ________

tmp_path = PosixPath('/private/tmp/pai56-lifecycle-green/test_interrupted_trial_preserv0')
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x108647820>

    def test_interrupted_trial_preserves_workspace_before_temp_cleanup(tmp_path,monkeypatch):
        import pai.evals.task_runner as runner
        real_popen=runner.subprocess.Popen
        def start(argv,*args,**kwargs):
            proc=real_popen(argv,*args,**kwargs)
            if 'pai.evals.task_worker' in argv:
                real_wait=proc.wait
                calls=[0]
                def wait(*args,**kwargs):
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
>       assert result['execution']=='interrupted'
E       AssertionError: assert 'harness_error' == 'interrupted'
E         
E         - interrupted
E         + harness_error

tests/test_task_runner.py:166: AssertionError
=========================== short test summary info ============================
FAILED tests/test_task_runner.py::test_forced_stop_reaps_detached_child_when_worker_ignores_term
FAILED tests/test_task_runner.py::test_interrupted_trial_preserves_workspace_before_temp_cleanup
2 failed, 1 passed, 16 deselected in 1.88s
```

## lifecycle-outside

```text
...                                                                      [100%]
3 passed, 16 deselected in 1.86s
```

## rates-red

```text
F                                                                        [100%]
=================================== FAILURES ===================================
_______ test_summary_keeps_budget_failures_and_unstarted_in_denominator ________

    def test_summary_keeps_budget_failures_and_unstarted_in_denominator():
        rows=[
          {"case":"fix","execution":"completed","agentEnd":"final","grade":{"status":"pass"},"durationMs":100,"metrics":{"tokens":{"total":12},"usageCoverage":"complete"}},
          {"case":"fix","execution":"completed","agentEnd":"budget","grade":{"status":"pass"},"durationMs":300,"metrics":{"tokens":{"total":24},"usageCoverage":"complete"}},
          {"case":"fix","execution":"not_started","agentEnd":"unknown","grade":{"status":"unavailable"}}]
        s=summarize(rows)
        assert (s['planned'],s['started'],s['completeSuccesses'],s['productPasses']) == (3,2,1,2)
        assert s['byCase']['fix']['durationMs'] == {'n':2,'median':200,'min':100,'max':300}
        assert s['byCase']['fix']['totalTokens']['median'] == 18
>       assert s['completeSuccessRate'] == pytest.approx(1/3)
E       KeyError: 'completeSuccessRate'

tests/test_task_metrics.py:97: KeyError
=========================== short test summary info ============================
FAILED tests/test_task_metrics.py::test_summary_keeps_budget_failures_and_unstarted_in_denominator
1 failed, 8 deselected in 0.61s
```

## new-final

```text
......................................                                   [100%]
38 passed in 20.29s
```

## stop-fault

```text
F                                                                        [100%]
=================================== FAILURES ===================================
________ test_forced_stop_reaps_detached_child_when_worker_ignores_term ________

tmp_path = PosixPath('/private/tmp/pai56-stop-fault/test_forced_stop_reaps_detache0')

    def test_forced_stop_reaps_detached_child_when_worker_ignores_term(tmp_path):
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
>           assert not alive, 'worker 被强杀后，独立进程组中的工具仍在运行'
E           AssertionError: worker 被强杀后，独立进程组中的工具仍在运行
E           assert not True

tests/test_task_runner.py:137: AssertionError
=========================== short test summary info ============================
FAILED tests/test_task_runner.py::test_forced_stop_reaps_detached_child_when_worker_ignores_term
1 failed, 8 deselected in 2.73s
```

## collected

```text
tests/test_assembly.py::test_repl_closes_mcp_sessions_before_returning
tests/test_assembly.py::test_repl_closes_mcp_sessions_when_loop_raises
tests/test_assembly.py::test_assemble_applies_bash_timeout_from_settings
tests/test_assembly.py::test_assemble_applies_tests_settings
tests/test_assembly.py::test_assemble_wires_additional_directories_into_boundary
tests/test_assembly.py::test_memory_and_recall_events_follow_the_swapped_sink
tests/test_assembly.py::test_rewriting_the_context_lets_a_recalled_memory_be_picked_again
tests/test_assembly.py::test_assembly_wires_the_rule_pipeline
tests/test_assembly.py::test_rewriting_the_context_lets_a_rule_be_injected_again
tests/test_assembly.py::test_no_rules_directory_costs_nothing
tests/test_assembly.py::test_repl_passes_the_rule_callback_to_run_agent
tests/test_assembly.py::test_once_passes_the_rule_callback_to_run_agent
tests/test_assembly.py::test_a_real_turn_pulls_the_rule_in_after_reading_a_matching_file
tests/test_assembly.py::test_the_listener_ignores_events_that_did_not_rewrite_anything
tests/test_assembly.py::test_clearing_the_conversation_really_lets_recall_come_back
tests/test_boundary.py::test_path_inside_cwd_is_in_boundary
tests/test_boundary.py::test_parent_directory_is_outside
tests/test_boundary.py::test_sibling_directory_is_outside
tests/test_boundary.py::test_prefix_is_not_enough
tests/test_boundary.py::test_additional_directories_extend_the_boundary
tests/test_boundary.py::test_boundary_uses_startup_cwd_not_current_cwd
tests/test_boundary.py::test_relative_paths_resolve_against_current_cwd_not_the_boundary
tests/test_boundary.py::test_all_paths_must_be_inside
tests/test_boundary.py::test_empty_path_is_not_inside
tests/test_boundary.py::test_dotdot_traversal_is_normalized
tests/test_boundary.py::test_paths_for_permission_check_returns_both
tests/test_boundary.py::test_paths_for_permission_check_dedups_when_not_a_symlink
tests/test_boundary.py::test_symlink_out_of_boundary_is_outside
tests/test_boundary.py::test_working_dirs_are_resolved_the_same_way
tests/test_boundary.py::test_broken_symlink_does_not_crash
tests/test_boundary.py::test_shell_configs_are_dangerous
tests/test_boundary.py::test_git_hooks_are_protected
tests/test_boundary.py::test_ssh_dir_is_protected
tests/test_boundary.py::test_pai_settings_is_protected
tests/test_boundary.py::test_ordinary_paths_are_not_dangerous
tests/test_boundary.py::test_exec_participates_in_the_boundary
tests/test_boundary.py::test_exec_inside_the_working_dir_is_allowed
tests/test_boundary.py::test_exec_outside_the_working_dir_still_asks
tests/test_boundary.py::test_accept_edits_does_not_let_exec_sneak_in
tests/test_boundary.py::test_dangerous_write_check_still_only_looks_at_writes
tests/test_boundary.py::test_path_access_for_accepts_exec_and_still_rejects_garbage
tests/test_compaction.py::test_user_message_token_estimate
tests/test_compaction.py::test_system_and_tool_messages_counted_like_text
tests/test_compaction.py::test_chinese_costs_twice_as_much_as_english
tests/test_compaction.py::test_mixed_content_counted_per_character
tests/test_compaction.py::test_cjk_punctuation_counted_as_chinese
tests/test_compaction.py::test_partial_token_rounds_up
tests/test_compaction.py::test_assistant_with_tool_calls_is_bigger
tests/test_compaction.py::test_assistant_with_null_content_does_not_crash
tests/test_compaction.py::test_unknown_role_is_still_weighed
tests/test_compaction.py::test_unknown_role_still_counts_its_tool_calls
tests/test_compaction.py::test_should_compact_threshold_is_strictly_greater
tests/test_compaction.py::test_should_compact_respects_disabled_flag
tests/test_compaction.py::test_should_compact_default_settings
tests/test_compaction.py::test_reserve_is_absolute_not_proportional
tests/test_compaction.py::test_window_smaller_than_reserve_always_triggers
tests/test_compaction.py::test_serialize_keeps_roles_and_tool_calls
tests/test_compaction.py::test_serialize_skips_unknown_role
tests/test_compaction.py::test_serialize_truncates_long_content
tests/test_compaction.py::test_serialize_truncation_limit_is_configurable
tests/test_compaction.py::test_serialize_truncates_long_tool_call_arguments
tests/test_compaction.py::test_real_trajectory_estimate_between_pure_english_and_pure_chinese
tests/test_compaction.py::test_real_trajectory_chinese_correction_is_material
tests/test_compaction.py::test_real_trajectory_every_message_counted
tests/test_compaction.py::test_real_trajectory_serialize_is_lossless_enough
tests/test_compaction.py::test_real_trajectory_serialize_shorter_than_raw_json
tests/test_compaction.py::test_request_tokens_without_tools_equals_message_tokens
tests/test_compaction.py::test_request_tokens_include_tool_schemas
tests/test_compaction.py::test_request_tokens_real_tool_schemas_are_not_negligible
tests/test_compaction.py::test_context_tokens_without_anchor_falls_back_to_pure_estimate
tests/test_compaction.py::test_context_tokens_ignores_everything_before_the_anchor
tests/test_compaction.py::test_context_tokens_adds_only_the_tail_estimate
tests/test_compaction.py::test_anchored_estimate_beats_pure_estimate_on_real_usage
tests/test_compaction.py::TestFindCutPoint::test_cuts_at_anchor_keeping_recent_budget
tests/test_compaction.py::TestFindCutPoint::test_never_starts_kept_segment_with_tool_result
tests/test_compaction.py::TestFindCutPoint::test_returns_1_when_nothing_can_be_cut
tests/test_compaction.py::TestAnchorBook::test_records_and_latest
tests/test_compaction.py::TestAnchorBook::test_anchor_fields_are_named_and_ordered_like_entries
tests/test_compaction.py::TestAnchorBook::test_empty_book_latest_is_also_named
tests/test_compaction.py::TestAnchorBook::test_turn_cost_is_adjacent_difference
tests/test_compaction.py::TestAnchorBook::test_no_anchor_is_index_none_not_tokens_zero
tests/test_compaction.py::TestAnchorBook::test_reset_clears_everything
tests/test_compaction.py::TestSummarize::test_flat_style_feeds_serialized_text_without_system
tests/test_compaction.py::TestSummarize::test_raw_style_sends_original_messages
tests/test_compaction.py::TestSummarize::test_instructions_override_default
tests/test_compaction.py::TestCompactAndBreaker::test_compact_rebuilds_with_summary_as_user
tests/test_compaction.py::TestCompactAndBreaker::test_verify_counts_failure_only_on_real_usage_still_over
tests/test_compaction.py::TestCompactAndBreaker::test_breaker_trips_after_three_consecutive_failures
tests/test_compaction.py::TestCompactAndBreaker::test_tripped_is_one_way
tests/test_compaction.py::test_shortfall_says_how_much_history_is_still_missing
tests/test_compaction.py::test_shortfall_of_a_single_anchor_is_the_whole_threshold
tests/test_config.py::test_model_name_loads_dotenv_first
tests/test_config.py::test_user_level_env_is_used_when_project_has_none
tests/test_config.py::test_project_env_wins_over_user_env
tests/test_config.py::test_real_environment_variable_wins_over_both
tests/test_config.py::test_project_env_is_found_from_cwd_not_from_the_package_location
tests/test_config.py::test_user_dir_constant_does_not_drift_from_memory_module
tests/test_config.py::test_recall_model_falls_back_to_the_main_model
tests/test_config.py::test_recall_model_env_overrides
tests/test_config.py::test_context_window_rejects_non_numeric_with_a_clear_message
tests/test_config.py::test_context_window_rejects_non_positive
tests/test_config.py::test_context_window_accepts_valid_values
tests/test_config.py::test_keep_recent_tokens_defaults_to_the_settings_default
tests/test_config.py::test_keep_recent_tokens_reads_the_env
tests/test_config.py::test_keep_recent_tokens_rejects_bad_values
tests/test_design_gate.py::test_non_edit_tools_pass
tests/test_design_gate.py::test_unguarded_paths_pass
tests/test_design_gate.py::test_no_active_denies_src_edit
tests/test_design_gate.py::test_empty_active_denies
tests/test_design_gate.py::test_bang_prefix_allows_with_trace
tests/test_design_gate.py::test_missing_archive_denies
tests/test_design_gate.py::test_unapproved_status_denies
tests/test_design_gate.py::test_missing_status_line_denies
tests/test_design_gate.py::test_approved_and_later_statuses_allow
tests/test_design_gate.py::test_real_active_pointer_is_consistent
tests/test_design_gate.py::test_notebook_edit_target_is_extracted
tests/test_design_gate.py::test_status_regex_does_not_cross_lines
tests/test_design_gate.py::test_design_gate_stays_fail_open
tests/test_dialog_wait.py::test_a_suppressed_dialog_does_not_end_the_wait
tests/test_dialog_wait.py::test_interrupting_the_wait_leaves_no_zombie_dialog
tests/test_dialog_wait.py::test_an_abandoned_dialog_cannot_answer_the_next_question
tests/test_dialog_wait.py::test_the_caller_still_sees_commands_typed_during_a_question
tests/test_dialog_wait.py::test_a_quit_command_during_a_question_ends_the_wait_without_a_zombie
tests/test_docs_consistency.py::test_roadmap_checked_reading_links_exist
tests/test_docs_consistency.py::test_knowledge_notes_are_registered
tests/test_docs_consistency.py::test_knowledge_notes_have_pai_anchor
tests/test_docs_consistency.py::test_feature_dirs_follow_naming_and_archive_rules
tests/test_docs_consistency.py::test_no_empty_dirs_under_features
tests/test_docs_consistency.py::test_decision_numbers_support_both_record_formats[1. \u5386\u53f2\u683c\u5f0f\n-expected0]
tests/test_docs_consistency.py::test_decision_numbers_support_both_record_formats[## 70. \u65b0\u683c\u5f0f\n-expected1]
tests/test_docs_consistency.py::test_decision_numbers_support_both_record_formats[69. \u5386\u53f2\u5c3e\u90e8\n## 70. \u540e\u7eed\u51b3\u7b56\n-expected2]
tests/test_docs_consistency.py::test_decisions_index_matches_entries
tests/test_docs_consistency.py::test_feature_index_rejects_missing_stale_and_duplicate_entries[entries0-archives0-\u7f3a\u9879]
tests/test_docs_consistency.py::test_feature_index_rejects_missing_stale_and_duplicate_entries[entries1-archives1-\u5931\u6548\u9879]
tests/test_docs_consistency.py::test_feature_index_rejects_missing_stale_and_duplicate_entries[entries2-archives2-\u91cd\u590d]
tests/test_docs_consistency.py::test_feature_index_covers_every_archive
tests/test_docs_consistency.py::test_feature_index_status_matches_archives
tests/test_docs_consistency.py::test_status_rejects_missing_or_multiple_current_counts[\u6ca1\u6709\u6d4b\u8bd5\u6570\u5b57]
tests/test_docs_consistency.py::test_status_rejects_missing_or_multiple_current_counts[3 passed\n4 passed]
tests/test_docs_consistency.py::test_status_rejects_missing_or_multiple_current_counts[3 passed\n3 passed]
tests/test_docs_consistency.py::test_status_accepts_one_current_count
tests/test_docs_consistency.py::test_status_has_one_current_result
tests/test_docs_consistency.py::test_devlog_milestone_section_is_one_liners
tests/test_docs_consistency.py::test_delivered_features_have_a_retrospective
tests/test_docs_consistency.py::test_status_reports_the_current_test_count
tests/test_docs_consistency.py::test_feature_archives_declare_their_branches
tests/test_docs_consistency.py::test_declared_branches_follow_the_naming_convention
tests/test_docs_consistency.py::test_feature_archives_declare_their_process
tests/test_docs_consistency.py::test_full_chain_archives_actually_have_a_spec_and_plan
tests/test_docs_consistency.py::test_e2e_files_are_recognized_by_the_marking_rule
tests/test_docs_consistency.py::test_every_collected_e2e_test_carries_the_marker
tests/test_docs_consistency.py::test_tui_modules_do_not_depend_on_modes_except_the_known_residue
tests/test_e2e_alt_screen.py::test_a_full_turn_renders_with_the_dock_pinned_to_the_bottom
tests/test_e2e_alt_screen.py::test_alt_screen_is_entered_exactly_once
tests/test_e2e_alt_screen.py::test_paging_up_moves_the_transcript_but_not_the_dock
tests/test_e2e_alt_screen.py::test_leaving_restores_the_shell_screen_and_leaves_a_session_hint
tests/test_e2e_alt_screen.py::test_the_answer_is_wrapped_not_truncated
tests/test_e2e_mouse.py::test_mouse_tracking_is_enabled_exactly_once_and_disabled_on_exit
tests/test_e2e_mouse.py::test_a_burst_of_wheel_events_scrolls_the_transcript
tests/test_e2e_mouse.py::test_dragging_highlights_and_copies
tests/test_e2e_mouse.py::test_a_fast_drag_is_batched_into_a_handful_of_frames
tests/test_e2e_steering.py::test_typing_during_a_tool_call_is_injected_in_the_same_run
tests/test_e2e_steering.py::test_a_slash_command_typed_while_busy_never_reaches_the_model
tests/test_e2e_steering.py::test_steering_survives_a_turn_with_no_tool_calls
tests/test_e2e_steering.py::test_the_injection_is_visible_on_screen
tests/test_e2e_steering.py::test_commands_typed_while_busy_run_after_the_turn[/]
tests/test_e2e_steering.py::test_commands_typed_while_busy_run_after_the_turn[!]
tests/test_e2e_tui.py::test_the_model_answer_reaches_the_screen
tests/test_e2e_tui.py::test_a_permission_dialog_appears_and_can_be_answered
tests/test_e2e_tui.py::test_multiline_content_does_not_stair_step
tests/test_e2e_tui.py::test_the_request_carries_the_tool_schemas
tests/test_e2e_tui.py::test_typing_while_busy_lands_in_the_queue
tests/test_e2e_tui.py::test_idle_ctrl_c_actually_clears_the_input
tests/test_e2e_tui.py::test_tui_shell_command_lands_in_history
tests/test_e2e_tui.py::test_main_screen_exit_leaves_no_dock_residue
tests/test_e2e_tui.py::test_mode_cycle_works_during_dialogs_and_busy
tests/test_e2e_tui.py::test_overwide_input_tail_is_visible_in_alt_screen
tests/test_e2e_tui.py::test_overwide_input_does_not_break_the_main_screen_dock
tests/test_e2e_tui.py::test_resume_carries_the_conversation_into_a_new_process
tests/test_e2e_tui.py::test_slash_resume_switches_the_screen_to_the_other_conversation
tests/test_e2e_tui.py::test_a_project_skill_loads_and_reaches_the_model
tests/test_e2e_tui.py::test_mcp_tool_reaches_model_through_real_process
tests/test_e2e_tui.py::test_project_skills_trust_dialog_gates_then_persists
tests/test_e2e_tui.py::test_automatic_compaction_really_happens_in_a_real_process
tests/test_e2e_tui.py::test_ctrl_c_mid_stream_stops_the_answer_and_keeps_the_repl_alive
tests/test_e2e_tui.py::test_typing_during_a_long_command_shows_up_on_screen
tests/test_e2e_tui.py::test_ctrl_c_can_stop_a_shell_command_in_the_tui
tests/test_e2e_tui.py::test_tool_calls_collapse_into_one_summary_line_after_the_turn
tests/test_evals_artifacts.py::test_new_run_dir_creates_timestamped_dir
tests/test_evals_artifacts.py::test_build_and_append_run_records_round_trip
tests/test_evals_artifacts.py::test_build_run_record_rejects_unknown_status
tests/test_evals_replay.py::test_derive_replay_from_real_trajectory
tests/test_evals_replay.py::test_derive_replay_rejects_v0
tests/test_evals_replay.py::test_derive_replay_rejects_compacted_session
tests/test_evals_replay.py::test_derive_replay_rejects_session_without_user_message
tests/test_evals_replay.py::test_instruction_and_recall_messages_are_not_mistaken_for_the_task
tests/test_evals_replay.py::test_a_session_with_only_framework_messages_has_no_task
tests/test_events.py::test_render_text_matches_legacy_strings
tests/test_events.py::test_render_text_returns_none_for_silent_events
tests/test_events.py::test_tool_end_truncates_long_result
tests/test_events.py::test_interrupted_has_its_own_line
tests/test_events.py::test_interrupted_in_stream_does_not_claim_the_request_was_never_sent
tests/test_events.py::test_events_are_frozen_dataclasses
tests/test_events.py::test_recall_failed_renders_reason_and_says_when_it_stops_trying
tests/test_events.py::test_recall_injected_names_the_memories
tests/test_events.py::test_recall_injected_is_frozen
tests/test_events.py::test_steering_injected_says_what_went_in
tests/test_events.py::test_steering_injected_truncates_long_text
tests/test_events.py::test_steering_injected_is_frozen
tests/test_events.py::test_context_rewriting_names_the_events_that_invalidate_cross_turn_state
tests/test_events.py::test_context_rewriting_does_not_include_merely_related_events
tests/test_events.py::test_every_context_rewriting_event_is_a_real_event
tests/test_fake_provider.py::test_streaming_yields_content_character_by_character
tests/test_fake_provider.py::test_usage_is_on_the_last_chunk_with_non_empty_choices
tests/test_fake_provider.py::test_tool_calls_are_merged_by_index_with_id_only_on_the_first_chunk
tests/test_fake_provider.py::test_non_streaming_path_also_works
tests/test_fake_provider.py::test_script_is_consumed_in_order
tests/test_fake_provider.py::test_exhausted_script_falls_back_instead_of_erroring
tests/test_fake_provider.py::test_requests_are_recorded_for_assertions
tests/test_fake_provider.py::test_prompt_tokens_grow_across_requests
tests/test_fake_provider.py::test_a_turn_can_pin_its_own_usage
tests/test_fake_provider.py::test_the_non_streaming_path_reports_usage_the_same_way
tests/test_four_frictions.py::test_default_budget_is_half_a_million
tests/test_four_frictions.py::test_hitting_the_budget_says_how_to_continue
tests/test_four_frictions.py::test_once_mode_does_not_promise_a_next_turn
tests/test_four_frictions.py::test_waiting_for_a_human_does_not_count_as_working_time
tests/test_four_frictions.py::test_the_clock_is_not_paused_twice_by_nested_asks
tests/test_four_frictions.py::test_resume_without_pause_is_a_no_op
tests/test_four_frictions.py::test_the_asker_pauses_the_clock_end_to_end
tests/test_four_frictions.py::test_a_long_cwd_keeps_the_model_and_context_visible
tests/test_four_frictions.py::test_the_shortened_path_keeps_the_last_segment
tests/test_four_frictions.py::test_a_short_cwd_is_not_shortened
tests/test_four_frictions.py::test_bash_asks_in_plain_words
tests/test_four_frictions.py::test_reading_outside_the_workdir_says_where_and_how_to_allow
tests/test_four_frictions.py::test_writing_says_what_changes_and_how_to_stop_being_asked
tests/test_four_frictions.py::test_a_dangerous_write_says_it_cannot_be_turned_off
tests/test_four_frictions.py::test_permissions_command_shows_the_same_words
tests/test_gate.py::test_bash_permission_question_shows_the_command_verbatim
tests/test_gate.py::test_long_argument_values_are_truncated_not_dumped
tests/test_git_tool.py::test_argv_never_goes_through_a_shell_and_disables_the_pager
tests/test_git_tool.py::test_diff_family_disables_external_diff_drivers
tests/test_git_tool.py::test_a_write_subcommand_is_refused_and_says_where_to_go
tests/test_git_tool.py::test_dangerous_global_flags_are_refused
tests/test_git_tool.py::test_an_unlisted_flag_is_refused_and_the_message_lists_what_is_allowed
tests/test_git_tool.py::test_unbalanced_quotes_are_reported_not_raised
tests/test_git_tool.py::test_status_and_log_actually_run
tests/test_git_tool.py::test_a_semicolon_cannot_smuggle_a_second_command
tests/test_git_tool.py::test_the_exit_code_is_reported
tests/test_git_tool.py::test_the_tool_is_registered_and_its_schema_is_generated
tests/test_git_tool.py::test_it_declares_exec_like_run_tests
tests/test_git_tool.py::test_concurrency_safety_depends_on_the_subcommand
tests/test_git_tool.py::test_two_log_reads_batch_but_status_does_not
tests/test_git_tool.py::test_reading_git_inside_the_working_dir_is_allowed_without_asking
tests/test_git_tool.py::test_a_deny_rule_can_still_turn_it_off
tests/test_hang_becomes_red.py::test_a_hanging_test_fails_instead_of_hanging_forever
tests/test_hang_becomes_red.py::test_a_normal_test_is_untouched
tests/test_hang_becomes_red.py::test_the_repo_suite_arms_the_net_by_default
tests/test_heartbeat.py::test_default_heartbeat_is_a_no_op
tests/test_heartbeat.py::test_beat_calls_the_injected_callback
tests/test_heartbeat.py::test_a_crashing_heartbeat_does_not_take_the_tool_down
tests/test_heartbeat.py::test_a_long_command_beats_while_it_waits
tests/test_heartbeat.py::test_a_fast_command_does_not_need_a_beat
tests/test_hooks.py::test_exit_zero_json_decision_is_honored
tests/test_hooks.py::test_exit_two_blocks_with_stderr_as_reason
tests/test_hooks.py::test_other_exit_codes_are_non_blocking
tests/test_hooks.py::test_multiple_hooks_deny_beats_ask_beats_allow
tests/test_hooks.py::test_hook_allow_cannot_override_deny_rule
tests/test_hooks.py::test_hook_block_beats_allow_rule
tests/test_hooks.py::test_hook_timeout_blocks
tests/test_hooks.py::test_hook_cannot_be_started_blocks
tests/test_hooks.py::test_nonzero_exit_is_still_non_blocking_and_this_differs_from_pi
tests/test_hooks.py::test_exit_zero_without_a_decision_is_still_no_opinion
tests/test_hooks.py::test_matcher_filters_by_tool_name
tests/test_hooks.py::test_hook_receives_the_event_on_stdin
tests/test_hooks.py::test_no_hooks_means_no_opinion
tests/test_hooks.py::test_loads_hooks_from_both_layers
tests/test_hooks.py::test_malformed_hook_entries_are_skipped_not_fatal
tests/test_hooks.py::test_configured_hook_actually_blocks_a_tool_call
tests/test_interactive.py::test_slash_exit_ends_loop_without_calling_model
tests/test_interactive.py::test_ctrl_d_ends_loop
tests/test_interactive.py::test_conversation_persists_across_turns
tests/test_interactive.py::test_slash_clear_keeps_system_and_drops_history
tests/test_interactive.py::test_slash_status_reports_context_and_breaker
tests/test_interactive.py::test_slash_help_lists_commands
tests/test_interactive.py::test_unknown_slash_command_does_not_call_model
tests/test_interactive.py::test_bang_runs_shell_without_calling_model
tests/test_interactive.py::test_backslash_continues_multiline_input
tests/test_interactive.py::test_first_ctrl_c_hints_second_exits
tests/test_interactive.py::test_input_between_two_ctrl_c_resets_the_counter
tests/test_interactive.py::test_slash_compact_compacts_and_resets_anchors
tests/test_interactive.py::test_slash_compact_without_anchors_explains_why
tests/test_interactive.py::test_ask_user_question_is_wired_to_thescripted_reader
tests/test_interactive.py::test_history_dedupes_consecutive_duplicates
tests/test_interactive.py::test_history_path_is_per_working_directory
tests/test_interactive.py::test_slash_commands_do_not_enter_history
tests/test_interactive.py::test_blank_input_is_ignored[]
tests/test_interactive.py::test_blank_input_is_ignored[   ]
tests/test_interactive.py::test_cli_dispatches_to_repl_without_task_and_to_once_with_task
tests/test_interactive.py::test_model_error_does_not_kill_the_repl
tests/test_interactive.py::test_repl_assembles_layered_instructions
tests/test_interactive.py::test_repl_shows_memory_writes
tests/test_interactive.py::test_slash_memory_lists_loaded_files
tests/test_interactive.py::test_slash_memory_shows_memory_dir
tests/test_interactive.py::test_slash_memory_says_so_when_nothing_loaded
tests/test_interactive.py::test_slash_memory_is_listed_in_help
tests/test_interactive.py::test_history_is_not_bound_to_readline_for_injected_readers
tests/test_interactive.py::test_history_is_loaded_when_input_is_a_real_terminal
tests/test_interactive.py::test_real_terminal_input_requires_both_real_input_and_tty
tests/test_interactive.py::test_read_history_into_readline_survives_a_missing_file
tests/test_interactive.py::test_ctrl_c_during_shell_mode_does_not_kill_the_repl
tests/test_interactive.py::test_shell_mode_runs_under_the_interrupt_flag
tests/test_interactive.py::test_cli_reaps_background_process_groups_on_exit
tests/test_interactive.py::test_tests_can_never_touch_the_real_home
tests/test_interactive.py::test_slash_memory_shows_both_memory_and_session_dirs
tests/test_interactive.py::test_slash_memory_shows_the_readable_slug
tests/test_interactive.py::test_asker_offers_a_way_to_skip
tests/test_interactive.py::test_asker_does_not_swallow_slash_commands
tests/test_interactive.py::test_asker_lets_the_user_exit
tests/test_interactive.py::test_slash_permissions_lists_rules_with_source
tests/test_interactive.py::test_slash_permissions_says_so_when_empty
tests/test_interactive.py::test_repl_holds_recall_state_across_turns
tests/test_interactive.py::test_manual_compact_survives_a_network_error
tests/test_interactive.py::test_slash_permissions_tells_the_whole_truth
tests/test_interactive.py::test_repl_wires_keep_recent_tokens_from_the_env
tests/test_interactive.py::test_manual_compact_says_how_far_short_the_history_is
tests/test_interactive.py::test_manual_compact_without_anchors_does_not_pretend_to_know_the_gap
tests/test_interactive.py::test_clear_emits_a_context_rewriting_event
tests/test_interactive.py::test_other_commands_rewrite_nothing
tests/test_interactive.py::test_manual_compact_emits_a_context_rewriting_event
tests/test_interactive.py::test_a_failed_manual_compact_rewrites_nothing
tests/test_interactive.py::test_memory_reload_makes_a_changed_instruction_file_take_effect
tests/test_interactive.py::test_memory_reload_says_what_it_did
tests/test_interactive.py::test_plain_memory_still_lists_files
tests/test_interactive.py::test_resume_says_that_settings_are_not_restored
tests/test_interactive.py::test_resume_points_out_a_different_working_directory
tests/test_interactive.py::test_resume_in_the_same_directory_says_nothing_about_cwd
tests/test_interactive.py::test_memory_lists_path_scoped_rules
tests/test_interactive.py::test_memory_marks_which_rules_are_already_injected
tests/test_interactive.py::test_memory_without_rules_says_nothing_about_them
tests/test_interactive_steering.py::TestInjectionPredicate::test_plain_text_goes_to_the_model
tests/test_interactive_steering.py::TestInjectionPredicate::test_slash_command_does_not
tests/test_interactive_steering.py::TestInjectionPredicate::test_bang_command_does_not
tests/test_interactive_steering.py::TestInjectionPredicate::test_leading_whitespace_does_not_smuggle_a_command_through
tests/test_interactive_steering.py::TestInjectionPredicate::test_slash_inside_the_sentence_is_just_text
tests/test_interactive_steering.py::TestInjectionPredicate::test_missing_or_empty_content_is_not_a_command
tests/test_interactive_steering.py::TestQueueWiring::test_injection_takes_messages_and_leaves_commands
tests/test_interactive_steering.py::TestQueueWiring::test_the_queue_is_all_mode
tests/test_interactive_steering.py::TestDockCountFollowsTheDrain::test_reported_count_is_the_real_remainder_not_a_stale_snapshot
tests/test_interactive_steering.py::TestDockCountFollowsTheDrain::test_reports_zero_when_the_queue_empties
tests/test_interactive_steering.py::TestDockCountFollowsTheDrain::test_reports_even_when_nothing_was_drained
tests/test_interactive_steering.py::TestDockCountFollowsTheDrain::test_works_without_a_callback
tests/test_interactive_steering.py::TestAfterTurnProcessing::test_hitting_round_cap_notifies_user_with_remaining_count
tests/test_interactive_steering.py::TestAfterTurnProcessing::test_no_notify_when_queue_drains_within_cap
tests/test_interactive_steering.py::TestAfterTurnProcessing::test_leftover_command_is_executed_not_sent_to_the_model
tests/test_interactive_steering.py::TestAfterTurnProcessing::test_leftover_message_starts_a_new_turn
tests/test_interactive_steering.py::TestAfterTurnProcessing::test_mixed_items_keep_the_order_the_user_typed_them
tests/test_interactive_steering.py::TestAfterTurnProcessing::test_empty_queue_does_nothing
tests/test_interactive_steering.py::TestAfterTurnProcessing::test_the_round_bound_stops_a_runaway_and_leaves_the_rest_in_the_queue
tests/test_interactive_steering.py::TestAfterTurnProcessing::test_the_default_bound_is_a_real_number
tests/test_interactive_steering.py::TestAfterTurnProcessing::test_a_command_that_asks_to_exit_stops_the_processing
tests/test_interactive_steering.py::TestFollowUpIsGone::test_no_follow_up_symbol_left_in_the_module
tests/test_interactive_steering.py::TestFollowUpIsGone::test_run_agent_no_longer_accepts_it
tests/test_interrupt.py::test_flag_set_is_set_clear_roundtrip
tests/test_interrupt.py::test_current_is_process_singleton
tests/test_interrupt.py::test_current_defaults_to_unset_flag
tests/test_interrupt.py::test_set_current_none_restores_a_usable_default
tests/test_listing.py::test_the_tree_shows_directories_and_files
tests/test_listing.py::test_noise_directories_are_skipped
tests/test_listing.py::test_depth_limits_how_deep_it_goes
tests/test_listing.py::test_too_many_entries_are_capped_and_it_says_so
tests/test_listing.py::test_entries_are_sorted_and_stable
tests/test_listing.py::test_directories_come_before_files
tests/test_listing.py::test_list_dir_runs
tests/test_listing.py::test_list_dir_defaults_to_cwd
tests/test_listing.py::test_list_dir_reports_a_missing_path
tests/test_listing.py::test_list_dir_rejects_a_negative_depth
tests/test_listing.py::test_list_dir_on_a_file_says_so
tests/test_listing.py::test_it_is_registered_with_a_generated_schema
tests/test_listing.py::test_it_declares_read_and_uses_the_shared_root_helpers
tests/test_listing.py::test_listing_inside_the_working_dir_is_allowed_without_asking
tests/test_listing.py::test_listing_outside_the_working_dir_still_asks
tests/test_loop.py::test_loop_tool_then_answer
tests/test_loop.py::test_loop_unknown_tool_feeds_error_back
tests/test_loop.py::test_loop_bad_json_arguments_feeds_error_back
tests/test_loop.py::test_loop_max_steps_bailout
tests/test_loop.py::test_usage_is_logged_once_per_model_call
tests/test_loop.py::test_usage_record_carries_deepseek_cache_fields
tests/test_loop.py::test_usage_never_leaks_into_messages_sent_to_api
tests/test_loop.py::test_missing_usage_does_not_break_loop
tests/test_loop.py::test_non_object_arguments_feed_error_back_instead_of_crashing
tests/test_loop.py::test_non_object_arguments_still_pair_tool_call_id
tests/test_loop.py::test_budget_stops_loop_before_next_request
tests/test_loop.py::test_budget_not_exceeded_runs_to_completion
tests/test_loop.py::test_budget_none_means_unlimited
tests/test_loop.py::test_budget_survives_provider_without_usage
tests/test_loop.py::test_budget_stop_is_reported_with_numbers
tests/test_loop.py::test_anchor_bookkeeping_is_exact
tests/test_loop.py::test_anchor_does_not_double_count_the_assistant_message
tests/test_loop.py::test_parallel_tool_calls_each_get_a_reply
tests/test_loop.py::test_parallel_tool_calls_mixed_known_and_unknown
tests/test_loop.py::test_truncated_tool_calls_are_failed_not_executed
tests/test_loop.py::test_truncated_batch_backfills_every_call_in_order
tests/test_loop.py::test_loop_compacts_when_over_threshold
tests/test_loop.py::test_loop_warns_not_compacts_when_no_cut_available
tests/test_loop.py::test_breaker_stops_auto_compaction
tests/test_loop.py::test_loop_compaction_usage_counts_toward_budget
tests/test_loop.py::test_loop_warns_when_truly_uncompactable
tests/test_loop.py::test_events_cover_the_whole_lifecycle
tests/test_loop.py::test_tool_end_marks_loop_generated_errors
tests/test_loop.py::test_steering_injected_after_all_tool_results
tests/test_loop.py::test_steering_is_polled_when_model_gives_final_answer
tests/test_loop.py::test_steering_keeps_loop_running_when_model_stops
tests/test_loop.py::test_steering_has_two_outlets_in_one_run
tests/test_loop.py::test_steering_injection_emits_an_event_at_both_outlets
tests/test_loop.py::test_no_steering_no_event
tests/test_loop.py::test_steering_event_comes_after_the_messages_are_in
tests/test_loop.py::test_follow_up_parameter_is_gone
tests/test_loop.py::test_no_queues_preserves_old_request_sequence
tests/test_loop.py::test_interrupt_backfills_remaining_tool_calls
tests/test_loop.py::test_interrupt_emits_interrupted_and_agent_end
tests/test_loop.py::test_interrupt_before_step_stops_without_calling_model
tests/test_loop.py::test_interrupted_conversation_is_preserved_for_next_turn
tests/test_loop.py::test_messages_param_continues_existing_conversation
tests/test_loop.py::test_anchor_book_can_be_shared_across_runs
tests/test_loop.py::test_compaction_state_can_be_shared_across_runs
tests/test_loop.py::test_compaction_state_updates_propagate_to_caller
tests/test_loop.py::test_instructions_become_the_first_user_message
tests/test_loop.py::test_no_instructions_preserves_old_message_shape
tests/test_loop.py::test_empty_instructions_do_not_add_a_message
tests/test_loop.py::test_instructions_are_loaded_once_per_run
tests/test_loop.py::test_instructions_not_duplicated_when_conversation_continues
tests/test_loop.py::test_instructions_survive_compaction
tests/test_loop.py::test_reinjected_instructions_are_re_read_from_disk
tests/test_loop.py::test_no_reinjection_when_instructions_not_provided
tests/test_loop.py::test_denied_tool_is_not_executed_but_result_is_backfilled
tests/test_loop.py::test_deny_reason_reaches_the_model
tests/test_loop.py::test_permission_decided_event_is_emitted
tests/test_loop.py::test_allow_decision_runs_the_tool_normally
tests/test_loop.py::test_no_before_tool_call_preserves_old_behavior
tests/test_loop.py::test_recall_text_is_appended_after_the_task_message
tests/test_loop.py::test_recall_is_called_once_with_the_task_as_query
tests/test_loop.py::test_empty_recall_text_inserts_no_message
tests/test_loop.py::test_recall_usage_counts_toward_the_budget
tests/test_loop.py::test_recall_failure_does_not_break_the_turn
tests/test_loop.py::test_recall_crash_is_reported_not_swallowed
tests/test_loop.py::test_request_actually_asks_for_streaming
tests/test_loop.py::test_streaming_keeps_messages_and_session_records_identical
tests/test_loop.py::test_message_delta_events_are_emitted_in_order
tests/test_loop.py::test_interrupt_mid_stream_stops_the_turn
tests/test_loop.py::test_interrupted_stream_is_unmetered_and_leaves_a_trace
tests/test_loop.py::test_side_queries_stay_non_streaming
tests/test_loop.py::test_pairing_survives_parallel_execution
tests/test_loop.py::test_pairing_survives_parallel_plus_interrupt
tests/test_loop.py::test_pairing_survives_parallel_plus_partial_denial
tests/test_loop.py::test_permissions_for_a_batch_are_decided_before_any_of_it_runs
tests/test_loop.py::test_batches_are_still_sequential_between_each_other
tests/test_loop.py::test_serial_only_turn_behaves_exactly_as_before
tests/test_loop.py::test_session_append_is_thread_safe
tests/test_loop.py::test_a_self_argument_is_rejected_at_the_door_not_left_to_explode
tests/test_loop.py::test_every_declared_tool_call_gets_a_result_even_when_something_explodes
tests/test_loop.py::test_the_backfilled_result_says_why_it_is_there
tests/test_loop.py::test_a_self_argument_does_not_break_the_conversation
tests/test_loop.py::test_an_unknown_tool_is_reported_as_unknown_not_as_denied
tests/test_loop.py::test_a_known_tool_still_goes_through_the_gate
tests/test_loop.py::test_a_failing_summary_request_does_not_blow_up_the_turn
tests/test_loop.py::test_repeated_summary_failures_trip_the_breaker
tests/test_loop.py::test_build_system_prompt_follows_the_actual_toolset
tests/test_loop.py::test_build_system_prompt_is_stable_for_the_same_toolset
tests/test_loop.py::test_run_agent_uses_the_injected_system_prompt
tests/test_loop.py::test_run_agent_without_injection_keeps_the_constant_verbatim
tests/test_loop.py::test_replay_messages_rebuilds_the_conversation_from_a_real_trajectory
tests/test_loop.py::test_replay_now_rebuilds_compacted_sessions
tests/test_loop.py::test_session_replay_equals_the_model_visible_messages
tests/test_loop.py::test_auto_compaction_records_first_kept_entry_and_replay_still_matches
tests/test_loop.py::test_fake_client_satisfies_the_chat_client_protocol
tests/test_loop.py::test_something_without_chat_is_not_a_chat_client
tests/test_loop.py::test_a_successful_compaction_emits_a_context_rewriting_event
tests/test_loop.py::test_nothing_to_compact_emits_no_rewriting_event
tests/test_loop.py::test_drop_instructions_removes_the_message_and_keeps_the_ledger_aligned
tests/test_loop.py::test_drop_instructions_is_a_no_op_when_there_is_none
tests/test_loop.py::test_loop_reports_the_paths_a_step_touched
tests/test_loop.py::test_an_empty_result_inserts_no_message
tests/test_loop.py::test_a_denied_call_touched_nothing
tests/test_loop.py::test_bash_does_not_count_as_touching_a_file
tests/test_loop.py::test_dirty_args_do_not_break_the_collection
tests/test_markdown_wordwrap.py::test_ascii_words_are_never_split[24]
tests/test_markdown_wordwrap.py::test_ascii_words_are_never_split[25]
tests/test_markdown_wordwrap.py::test_ascii_words_are_never_split[26]
tests/test_markdown_wordwrap.py::test_ascii_words_are_never_split[27]
tests/test_markdown_wordwrap.py::test_ascii_words_are_never_split[28]
tests/test_markdown_wordwrap.py::test_ascii_words_are_never_split[29]
tests/test_markdown_wordwrap.py::test_ascii_words_are_never_split[30]
tests/test_markdown_wordwrap.py::test_ascii_words_are_never_split[31]
tests/test_markdown_wordwrap.py::test_ascii_words_are_never_split[32]
tests/test_markdown_wordwrap.py::test_ascii_words_are_never_split[33]
tests/test_markdown_wordwrap.py::test_ascii_words_are_never_split[34]
tests/test_markdown_wordwrap.py::test_ascii_words_are_never_split[35]
tests/test_markdown_wordwrap.py::test_ascii_words_are_never_split[36]
tests/test_markdown_wordwrap.py::test_ascii_words_are_never_split[37]
tests/test_markdown_wordwrap.py::test_ascii_words_are_never_split[38]
tests/test_markdown_wordwrap.py::test_ascii_words_are_never_split[39]
tests/test_markdown_wordwrap.py::test_ascii_words_are_never_split[40]
tests/test_markdown_wordwrap.py::test_ascii_words_are_never_split[41]
tests/test_markdown_wordwrap.py::test_ascii_words_are_never_split[42]
tests/test_markdown_wordwrap.py::test_ascii_words_are_never_split[43]
tests/test_markdown_wordwrap.py::test_ascii_words_are_never_split[44]
tests/test_markdown_wordwrap.py::test_ascii_words_are_never_split[45]
tests/test_markdown_wordwrap.py::test_ascii_words_are_never_split[46]
tests/test_markdown_wordwrap.py::test_ascii_words_are_never_split[47]
tests/test_markdown_wordwrap.py::test_ascii_words_are_never_split[48]
tests/test_markdown_wordwrap.py::test_ascii_words_are_never_split[49]
tests/test_markdown_wordwrap.py::test_ascii_words_are_never_split[50]
tests/test_markdown_wordwrap.py::test_ascii_words_are_never_split[51]
tests/test_markdown_wordwrap.py::test_ascii_words_are_never_split[52]
tests/test_markdown_wordwrap.py::test_ascii_words_are_never_split[53]
tests/test_markdown_wordwrap.py::test_ascii_words_are_never_split[54]
tests/test_markdown_wordwrap.py::test_ascii_words_are_never_split[55]
tests/test_markdown_wordwrap.py::test_ascii_words_are_never_split[56]
tests/test_markdown_wordwrap.py::test_ascii_words_are_never_split[57]
tests/test_markdown_wordwrap.py::test_ascii_words_are_never_split[58]
tests/test_markdown_wordwrap.py::test_ascii_words_are_never_split[59]
tests/test_markdown_wordwrap.py::test_ascii_words_are_never_split[60]
tests/test_markdown_wordwrap.py::test_ascii_words_are_never_split[61]
tests/test_markdown_wordwrap.py::test_ascii_words_are_never_split[62]
tests/test_markdown_wordwrap.py::test_ascii_words_are_never_split[63]
tests/test_markdown_wordwrap.py::test_ascii_words_are_never_split[64]
tests/test_markdown_wordwrap.py::test_ascii_words_are_never_split[65]
tests/test_markdown_wordwrap.py::test_ascii_words_are_never_split[66]
tests/test_markdown_wordwrap.py::test_ascii_words_are_never_split[67]
tests/test_markdown_wordwrap.py::test_ascii_words_are_never_split[68]
tests/test_markdown_wordwrap.py::test_ascii_words_are_never_split[69]
tests/test_markdown_wordwrap.py::test_ascii_words_are_never_split[70]
tests/test_markdown_wordwrap.py::test_ascii_words_are_never_split[71]
tests/test_markdown_wordwrap.py::test_ascii_words_are_never_split[72]
tests/test_markdown_wordwrap.py::test_ascii_words_are_never_split[73]
tests/test_markdown_wordwrap.py::test_ascii_words_are_never_split[74]
tests/test_markdown_wordwrap.py::test_ascii_words_are_never_split[75]
tests/test_markdown_wordwrap.py::test_ascii_words_are_never_split[76]
tests/test_markdown_wordwrap.py::test_ascii_words_are_never_split[77]
tests/test_markdown_wordwrap.py::test_ascii_words_are_never_split[78]
tests/test_markdown_wordwrap.py::test_ascii_words_are_never_split[79]
tests/test_markdown_wordwrap.py::test_ascii_words_are_never_split[80]
tests/test_markdown_wordwrap.py::test_nothing_is_lost_or_duplicated[24]
tests/test_markdown_wordwrap.py::test_nothing_is_lost_or_duplicated[25]
tests/test_markdown_wordwrap.py::test_nothing_is_lost_or_duplicated[26]
tests/test_markdown_wordwrap.py::test_nothing_is_lost_or_duplicated[27]
tests/test_markdown_wordwrap.py::test_nothing_is_lost_or_duplicated[28]
tests/test_markdown_wordwrap.py::test_nothing_is_lost_or_duplicated[29]
tests/test_markdown_wordwrap.py::test_nothing_is_lost_or_duplicated[30]
tests/test_markdown_wordwrap.py::test_nothing_is_lost_or_duplicated[31]
tests/test_markdown_wordwrap.py::test_nothing_is_lost_or_duplicated[32]
tests/test_markdown_wordwrap.py::test_nothing_is_lost_or_duplicated[33]
tests/test_markdown_wordwrap.py::test_nothing_is_lost_or_duplicated[34]
tests/test_markdown_wordwrap.py::test_nothing_is_lost_or_duplicated[35]
tests/test_markdown_wordwrap.py::test_nothing_is_lost_or_duplicated[36]
tests/test_markdown_wordwrap.py::test_nothing_is_lost_or_duplicated[37]
tests/test_markdown_wordwrap.py::test_nothing_is_lost_or_duplicated[38]
tests/test_markdown_wordwrap.py::test_nothing_is_lost_or_duplicated[39]
tests/test_markdown_wordwrap.py::test_nothing_is_lost_or_duplicated[40]
tests/test_markdown_wordwrap.py::test_nothing_is_lost_or_duplicated[41]
tests/test_markdown_wordwrap.py::test_nothing_is_lost_or_duplicated[42]
tests/test_markdown_wordwrap.py::test_nothing_is_lost_or_duplicated[43]
tests/test_markdown_wordwrap.py::test_nothing_is_lost_or_duplicated[44]
tests/test_markdown_wordwrap.py::test_nothing_is_lost_or_duplicated[45]
tests/test_markdown_wordwrap.py::test_nothing_is_lost_or_duplicated[46]
tests/test_markdown_wordwrap.py::test_nothing_is_lost_or_duplicated[47]
tests/test_markdown_wordwrap.py::test_nothing_is_lost_or_duplicated[48]
tests/test_markdown_wordwrap.py::test_nothing_is_lost_or_duplicated[49]
tests/test_markdown_wordwrap.py::test_nothing_is_lost_or_duplicated[50]
tests/test_markdown_wordwrap.py::test_nothing_is_lost_or_duplicated[51]
tests/test_markdown_wordwrap.py::test_nothing_is_lost_or_duplicated[52]
tests/test_markdown_wordwrap.py::test_nothing_is_lost_or_duplicated[53]
tests/test_markdown_wordwrap.py::test_nothing_is_lost_or_duplicated[54]
tests/test_markdown_wordwrap.py::test_nothing_is_lost_or_duplicated[55]
tests/test_markdown_wordwrap.py::test_nothing_is_lost_or_duplicated[56]
tests/test_markdown_wordwrap.py::test_nothing_is_lost_or_duplicated[57]
tests/test_markdown_wordwrap.py::test_nothing_is_lost_or_duplicated[58]
tests/test_markdown_wordwrap.py::test_nothing_is_lost_or_duplicated[59]
tests/test_markdown_wordwrap.py::test_nothing_is_lost_or_duplicated[60]
tests/test_markdown_wordwrap.py::test_nothing_is_lost_or_duplicated[61]
tests/test_markdown_wordwrap.py::test_nothing_is_lost_or_duplicated[62]
tests/test_markdown_wordwrap.py::test_nothing_is_lost_or_duplicated[63]
tests/test_markdown_wordwrap.py::test_nothing_is_lost_or_duplicated[64]
tests/test_markdown_wordwrap.py::test_nothing_is_lost_or_duplicated[65]
tests/test_markdown_wordwrap.py::test_nothing_is_lost_or_duplicated[66]
tests/test_markdown_wordwrap.py::test_nothing_is_lost_or_duplicated[67]
tests/test_markdown_wordwrap.py::test_nothing_is_lost_or_duplicated[68]
tests/test_markdown_wordwrap.py::test_nothing_is_lost_or_duplicated[69]
tests/test_markdown_wordwrap.py::test_nothing_is_lost_or_duplicated[70]
tests/test_markdown_wordwrap.py::test_nothing_is_lost_or_duplicated[71]
tests/test_markdown_wordwrap.py::test_nothing_is_lost_or_duplicated[72]
tests/test_markdown_wordwrap.py::test_nothing_is_lost_or_duplicated[73]
tests/test_markdown_wordwrap.py::test_nothing_is_lost_or_duplicated[74]
tests/test_markdown_wordwrap.py::test_nothing_is_lost_or_duplicated[75]
tests/test_markdown_wordwrap.py::test_nothing_is_lost_or_duplicated[76]
tests/test_markdown_wordwrap.py::test_nothing_is_lost_or_duplicated[77]
tests/test_markdown_wordwrap.py::test_nothing_is_lost_or_duplicated[78]
tests/test_markdown_wordwrap.py::test_nothing_is_lost_or_duplicated[79]
tests/test_markdown_wordwrap.py::test_nothing_is_lost_or_duplicated[80]
tests/test_markdown_wordwrap.py::test_a_word_longer_than_the_line_still_renders[8]
tests/test_markdown_wordwrap.py::test_a_word_longer_than_the_line_still_renders[12]
tests/test_markdown_wordwrap.py::test_a_word_longer_than_the_line_still_renders[16]
tests/test_markdown_wordwrap.py::test_a_very_long_token_does_not_hang
tests/test_markdown_wordwrap.py::test_chinese_still_fills_the_line[20]
tests/test_markdown_wordwrap.py::test_chinese_still_fills_the_line[21]
tests/test_markdown_wordwrap.py::test_chinese_still_fills_the_line[22]
tests/test_markdown_wordwrap.py::test_chinese_still_fills_the_line[23]
tests/test_markdown_wordwrap.py::test_chinese_still_fills_the_line[24]
tests/test_markdown_wordwrap.py::test_chinese_still_fills_the_line[25]
tests/test_markdown_wordwrap.py::test_chinese_still_fills_the_line[26]
tests/test_markdown_wordwrap.py::test_chinese_still_fills_the_line[27]
tests/test_markdown_wordwrap.py::test_chinese_still_fills_the_line[28]
tests/test_markdown_wordwrap.py::test_chinese_still_fills_the_line[29]
tests/test_markdown_wordwrap.py::test_chinese_still_fills_the_line[30]
tests/test_markdown_wordwrap.py::test_chinese_still_fills_the_line[31]
tests/test_markdown_wordwrap.py::test_chinese_still_fills_the_line[32]
tests/test_markdown_wordwrap.py::test_chinese_still_fills_the_line[33]
tests/test_markdown_wordwrap.py::test_chinese_still_fills_the_line[34]
tests/test_markdown_wordwrap.py::test_chinese_still_fills_the_line[35]
tests/test_markdown_wordwrap.py::test_chinese_still_fills_the_line[36]
tests/test_markdown_wordwrap.py::test_chinese_still_fills_the_line[37]
tests/test_markdown_wordwrap.py::test_chinese_still_fills_the_line[38]
tests/test_markdown_wordwrap.py::test_chinese_still_fills_the_line[39]
tests/test_markdown_wordwrap.py::test_chinese_still_fills_the_line[40]
tests/test_markdown_wordwrap.py::test_chinese_still_fills_the_line[41]
tests/test_markdown_wordwrap.py::test_chinese_still_fills_the_line[42]
tests/test_markdown_wordwrap.py::test_chinese_still_fills_the_line[43]
tests/test_markdown_wordwrap.py::test_chinese_still_fills_the_line[44]
tests/test_markdown_wordwrap.py::test_chinese_still_fills_the_line[45]
tests/test_markdown_wordwrap.py::test_chinese_still_fills_the_line[46]
tests/test_markdown_wordwrap.py::test_chinese_still_fills_the_line[47]
tests/test_markdown_wordwrap.py::test_chinese_still_fills_the_line[48]
tests/test_markdown_wordwrap.py::test_chinese_still_fills_the_line[49]
tests/test_markdown_wordwrap.py::test_chinese_still_fills_the_line[50]
tests/test_markdown_wordwrap.py::test_chinese_still_fills_the_line[51]
tests/test_markdown_wordwrap.py::test_chinese_still_fills_the_line[52]
tests/test_markdown_wordwrap.py::test_chinese_still_fills_the_line[53]
tests/test_markdown_wordwrap.py::test_chinese_still_fills_the_line[54]
tests/test_markdown_wordwrap.py::test_chinese_still_fills_the_line[55]
tests/test_markdown_wordwrap.py::test_chinese_still_fills_the_line[56]
tests/test_markdown_wordwrap.py::test_chinese_still_fills_the_line[57]
tests/test_markdown_wordwrap.py::test_chinese_still_fills_the_line[58]
tests/test_markdown_wordwrap.py::test_chinese_still_fills_the_line[59]
tests/test_markdown_wordwrap.py::test_chinese_still_fills_the_line[60]
tests/test_markdown_wordwrap.py::test_a_space_left_behind_by_the_move_is_stripped
tests/test_mcp.py::test_handshake_and_discovery
tests/test_mcp.py::test_discovery_drains_pagination
tests/test_mcp.py::test_call_tool_returns_raw_result
tests/test_mcp.py::test_call_tool_iserror_raises_with_detail
tests/test_mcp.py::test_call_tool_protocol_error_raises
tests/test_mcp.py::test_call_tool_timeout
tests/test_mcp.py::test_server_death_fails_calls_and_marks_state
tests/test_mcp.py::test_death_during_discovery_fails_start
tests/test_mcp.py::test_dirty_stdout_flood_warns_once
tests/test_mcp.py::test_dirty_stdout_lines_are_tolerated
tests/test_mcp.py::test_bad_command_fails_loud_not_crash
tests/test_mcp.py::test_close_is_idempotent_and_kills_process
tests/test_mcp.py::test_public_name_normalizes_and_lowercases
tests/test_mcp.py::test_public_name_overlong_gets_deterministic_hash
tests/test_mcp.py::test_public_name_all_non_ascii_gets_hash_not_collision
tests/test_mcp.py::test_bridge_produces_pai_tools
tests/test_mcp.py::test_bridged_tool_joins_text_and_placeholders_nontext
tests/test_mcp.py::test_bridged_tool_iserror_becomes_error_string
tests/test_mcp.py::test_description_sanitized_and_truncated
tests/test_mcp.py::test_output_char_budget_truncates_with_note
tests/test_mcp.py::test_load_mcp_servers_two_layers_project_wins
tests/test_mcp.py::test_load_mcp_servers_skips_bad_entries_with_warn
tests/test_mcp.py::test_load_mcp_servers_bad_json_warns_layer_skipped
tests/test_mcp.py::test_mcp_trust_once_drops_project_servers_and_warns
tests/test_mcp.py::test_mcp_trust_dialog_yes_persists_no_skips
tests/test_mcp.py::test_bridge_skips_public_name_collision_with_warn
tests/test_mcp.py::test_decide_mcp_tool_defaults_to_ask
tests/test_mcp.py::test_allow_rule_server_glob_passes
tests/test_mcp.py::test_once_wires_mcp_tools_end_to_end
tests/test_mcp.py::test_once_mcp_denied_by_default_in_dontask
tests/test_mcp.py::test_once_untrusted_project_mcp_skipped
tests/test_mcp.py::test_repl_wires_mcp_tools
tests/test_mcp.py::test_loop_with_real_trajectory_and_mcp_tool
tests/test_mcp.py::test_reader_survives_unhashable_id
tests/test_mcp.py::test_connect_helper_closes_sessions_on_unexpected_error
tests/test_mcp.py::test_repl_mcp_trust_dialog_loads_and_persists
tests/test_mcp.py::test_once_broken_server_warns_and_continues
tests/test_mcp.py::test_connect_returns_failed_server_names
tests/test_mcp.py::test_once_tells_model_about_failed_servers
tests/test_mcp.py::test_once_no_failure_note_when_no_server_configured
tests/test_mcp.py::test_once_config_timeout_reaches_call
tests/test_mcp.py::test_bridge_skips_non_object_root_schema_with_warn
tests/test_mcp.py::test_a_slow_call_beats_while_it_waits
tests/test_mcp.py::test_an_interrupted_call_stops_waiting_and_says_what_it_could_not_stop
tests/test_mcp.py::test_a_normal_call_is_not_affected_by_a_stale_flag
tests/test_memory.py::test_discovers_up_the_tree_root_first
tests/test_memory.py::test_local_comes_after_plain_in_same_dir
tests/test_memory.py::test_user_level_comes_first
tests/test_memory.py::test_subdirectory_files_are_not_loaded
tests/test_memory.py::test_missing_files_are_skipped_silently
tests/test_memory.py::test_agents_md_is_read
tests/test_memory.py::test_pai_md_comes_after_agents_md_in_the_same_dir
tests/test_memory.py::test_other_agents_entry_files_are_still_not_read
tests/test_memory.py::test_user_level_agents_md_is_read_too
tests/test_memory.py::test_import_is_relative_to_the_importing_file
tests/test_memory.py::test_import_recurses_up_to_four_hops
tests/test_memory.py::test_import_cycle_terminates
tests/test_memory.py::test_inline_code_and_fenced_blocks_are_not_imports
tests/test_memory.py::test_missing_import_leaves_a_note_not_an_exception
tests/test_memory.py::test_home_and_absolute_import_paths_work
tests/test_memory.py::test_load_joins_files_in_discovery_order
tests/test_memory.py::test_project_key_comes_from_git_root
tests/test_memory.py::test_project_key_falls_back_to_project_root_outside_git
tests/test_memory.py::test_memory_index_is_truncated_at_200_lines
tests/test_memory.py::test_memory_index_is_truncated_at_25kb
tests/test_memory.py::test_short_index_is_returned_whole_without_note
tests/test_memory.py::test_memory_bodies_are_not_loaded_at_startup
tests/test_memory.py::test_missing_memory_index_returns_empty
tests/test_memory.py::test_an_email_address_is_not_an_import
tests/test_memory.py::test_a_decorator_is_not_an_import
tests/test_memory.py::test_a_path_shaped_target_is_still_an_import
tests/test_memory.py::test_a_path_shaped_but_missing_target_still_reports
tests/test_memory_index.py::test_memory_age_says_today
tests/test_memory_index.py::test_memory_age_uses_calendar_days_not_elapsed_seconds
tests/test_memory_index.py::test_memory_age_counts_days
tests/test_memory_index.py::test_freshness_note_is_empty_within_one_day
tests/test_memory_index.py::test_freshness_note_warns_that_file_line_refs_may_be_stale
tests/test_memory_index.py::test_render_index_without_now_has_no_relative_time
tests/test_memory_index.py::test_render_index_with_now_includes_relative_time
tests/test_memory_index.py::test_index_header_declares_it_is_generated
tests/test_memory_index.py::test_render_index_of_empty_directory_is_empty
tests/test_memory_index.py::test_index_is_derived_from_files_not_from_the_disk_index
tests/test_memory_index.py::test_truncation_notice_points_at_recall_not_read_file
tests/test_memory_scan.py::test_parses_our_own_frontmatter
tests/test_memory_scan.py::test_strips_quotes_from_values
tests/test_memory_scan.py::test_ignores_unknown_keys_instead_of_failing
tests/test_memory_scan.py::test_no_frontmatter_parses_to_empty
tests/test_memory_scan.py::test_scan_excludes_the_index_file
tests/test_memory_scan.py::test_scan_sorts_by_mtime_newest_first
tests/test_memory_scan.py::test_scan_caps_at_max_scanned_keeping_the_newest
tests/test_memory_scan.py::test_scan_reads_only_the_first_lines
tests/test_memory_scan.py::test_legacy_file_without_frontmatter_degrades
tests/test_memory_scan.py::test_unreadable_file_is_skipped_not_fatal
tests/test_memory_scan.py::test_missing_directory_scans_to_empty
tests/test_modes.py::test_run_once_wires_client_and_returns_answer
tests/test_modes.py::test_run_once_passes_budget_through
tests/test_modes.py::test_run_once_no_session_skips_disk
tests/test_modes.py::test_cli_rejects_negative_max_tokens
tests/test_modes.py::test_run_once_respects_max_steps
tests/test_modes.py::test_once_event_output_is_byte_identical
tests/test_modes.py::test_once_default_event_handler_prints_rendered_text
tests/test_modes.py::test_once_assembles_layered_instructions
tests/test_modes.py::test_ask_without_a_human_degrades_to_deny
tests/test_modes.py::test_ask_with_a_human_asks_and_honors_the_answer
tests/test_modes.py::test_run_once_wires_the_permission_gate
tests/test_modes.py::test_run_once_wires_recall_when_memories_exist
tests/test_modes.py::test_run_once_without_memories_costs_no_extra_request
tests/test_modes.py::test_stream_echo_writes_deltas_with_one_robot_prefix
tests/test_modes.py::test_stream_echo_does_not_print_the_final_answer_twice
tests/test_modes.py::test_stream_echo_still_prints_synthesized_endings
tests/test_modes.py::test_stream_echo_closes_the_line_when_interrupted_mid_stream
tests/test_modes.py::test_stream_echo_falls_back_for_other_events
tests/test_modes.py::test_status_line_shows_multiple_running_tools
tests/test_modes.py::test_no_emoji_in_tui_authored_lines
tests/test_modes.py::test_mode_command_shows_the_current_mode_and_the_cycle
tests/test_modes.py::test_mode_command_switches
tests/test_modes.py::test_mode_command_rejects_unknown_and_keeps_the_old_mode
tests/test_modes.py::test_permissions_command_shows_the_current_mode
tests/test_modes.py::test_repl_survives_an_unexpected_exception_in_a_turn
tests/test_modes.py::test_ctrl_d_still_exits_and_is_not_swallowed
tests/test_modes.py::test_gate_asker_can_be_swapped_after_assembly
tests/test_modes.py::test_asker_ref_reports_whether_a_human_is_available
tests/test_modes.py::test_once_sends_a_prompt_built_from_its_actual_tools
tests/test_modes.py::test_interactive_sends_a_prompt_that_admits_ask_user_question
tests/test_modes.py::test_manual_compact_records_the_entry_and_replay_rebuilds
tests/test_modes.py::test_slash_clear_trims_the_ledger_with_the_messages
tests/test_modes.py::test_resume_continues_the_previous_conversation
tests/test_modes.py::test_resume_trims_a_torn_tail_before_continuing
tests/test_modes.py::test_cli_resume_flag_reaches_run_interactive
tests/test_modes.py::test_cli_resume_conflicts_with_a_task
tests/test_modes.py::test_cli_turns_resume_errors_into_plain_words
tests/test_modes.py::test_once_warns_when_configured_default_mode_cannot_apply
tests/test_modes.py::test_once_stays_silent_when_no_default_mode_configured
tests/test_modes.py::test_once_wires_keep_recent_tokens_from_the_env
tests/test_paths.py::test_slug_is_the_dashed_absolute_path
tests/test_paths.py::test_slug_uses_the_git_root
tests/test_paths.py::test_slug_falls_back_to_cwd_outside_git
tests/test_paths.py::test_slug_keeps_chinese_path_as_is
tests/test_paths.py::test_known_slug_collision_is_documented
tests/test_paths.py::test_project_dir_layout
tests/test_paths.py::test_memory_dir_now_lives_under_the_readable_slug
tests/test_paths.py::test_session_defaults_to_the_project_sessions_dir
tests/test_paths.py::test_session_directory_param_still_works
tests/test_paths.py::test_the_header_carries_session_id_and_cwd
tests/test_paths.py::test_same_second_sessions_do_not_collide
tests/test_paths.py::test_filename_keeps_the_timestamp_prefix
tests/test_permission_mode_switching.py::test_cycle_order
tests/test_permission_mode_switching.py::test_bypass_is_skipped_when_unavailable
tests/test_permission_mode_switching.py::test_dont_ask_is_not_in_the_cycle
tests/test_permission_mode_switching.py::test_cycle_is_data_not_an_if_chain
tests/test_permission_mode_switching.py::test_unknown_mode_falls_back_to_default
tests/test_permission_mode_switching.py::test_state_reports_and_cycles
tests/test_permission_mode_switching.py::test_state_set_rejects_unknown_mode
tests/test_permission_mode_switching.py::test_gate_sees_the_new_mode_on_the_very_next_decision
tests/test_permission_mode_switching.py::test_gate_still_accepts_a_plain_string_mode
tests/test_permission_mode_switching.py::test_gate_accepts_none_as_before
tests/test_permission_modes.py::test_default_mode_is_the_baseline
tests/test_permission_modes.py::test_accept_edits_allows_writes_inside_boundary
tests/test_permission_modes.py::test_accept_edits_still_respects_boundary
tests/test_permission_modes.py::test_accept_edits_still_respects_dangerous_paths
tests/test_permission_modes.py::test_accept_edits_does_not_touch_bash
tests/test_permission_modes.py::test_bypass_allows_fallback_ask
tests/test_permission_modes.py::test_bypass_is_immune_to_deny_rules
tests/test_permission_modes.py::test_bypass_is_immune_to_explicit_ask_rules
tests/test_permission_modes.py::test_bypass_is_immune_to_dangerous_paths
tests/test_permission_modes.py::test_dont_ask_turns_ask_into_deny_without_asking
tests/test_permission_modes.py::test_no_human_is_equivalent_to_dont_ask
tests/test_permission_modes.py::test_mode_from_settings
tests/test_permission_modes.py::test_invalid_mode_in_settings_falls_back_with_warning
tests/test_permission_modes.py::test_unknown_mode_is_rejected_at_the_api
tests/test_permissions.py::test_parses_bare_tool_and_specifier
tests/test_permissions.py::test_deny_beats_more_specific_allow
tests/test_permissions.py::test_ask_beats_allow
tests/test_permissions.py::test_first_match_in_order_wins_not_most_specific
tests/test_permissions.py::test_no_match_falls_back_to_default_decision
tests/test_permissions.py::test_tool_name_glob_matches_whole_name
tests/test_permissions.py::test_decision_carries_reason_and_rule
tests/test_permissions.py::test_default_matcher_globs_first_argument
tests/test_permissions.py::test_matcher_for_attaches_to_registered_tool
tests/test_permissions.py::test_permission_layer_never_branches_on_tool_name
tests/test_permissions.py::test_require_all_flag_is_passed_through
tests/test_permissions.py::test_compound_command_requires_every_subcommand_to_match
tests/test_permissions.py::test_any_subcommand_matching_deny_blocks
tests/test_permissions.py::test_all_separators_split
tests/test_permissions.py::test_process_wrappers_are_stripped
tests/test_permissions.py::test_env_runners_are_not_stripped_and_this_is_a_known_hole
tests/test_permissions.py::test_word_boundary_before_star
tests/test_permissions.py::test_colon_star_suffix_equals_trailing_space_star
tests/test_permissions.py::test_double_slash_is_filesystem_absolute
tests/test_permissions.py::test_tilde_is_home_relative
tests/test_permissions.py::test_single_slash_anchors_to_the_settings_source
tests/test_permissions.py::test_bare_filename_matches_at_any_depth
tests/test_permissions.py::test_relative_pattern_anchors_to_cwd
tests/test_permissions.py::test_symlink_cannot_bypass_deny
tests/test_permissions.py::test_symlink_allow_requires_both_paths_clean
tests/test_permissions.py::test_loads_user_then_project_settings
tests/test_permissions.py::test_deny_in_either_layer_beats_allow_in_the_other
tests/test_permissions.py::test_malformed_settings_does_not_crash
tests/test_permissions.py::test_bare_name_deny_removes_tool_from_schema
tests/test_permissions.py::test_scoped_deny_keeps_tool_visible
tests/test_permissions.py::test_fs_tools_declare_path_and_access
tests/test_permissions.py::test_bash_declares_neither
tests/test_permissions.py::test_tool_without_declaration_does_not_participate
tests/test_permissions.py::test_get_path_reads_the_declared_argument
tests/test_permissions.py::test_path_access_for_rejects_unregistered_tool
tests/test_permissions.py::test_default_is_now_workingdir
tests/test_permissions.py::test_read_inside_cwd_allows
tests/test_permissions.py::test_read_outside_cwd_asks
tests/test_permissions.py::test_write_always_asks_even_inside
tests/test_permissions.py::test_bash_falls_back_to_ask
tests/test_permissions.py::test_bash_ignores_the_boundary_and_this_is_the_known_hole
tests/test_permissions.py::test_explicit_allow_preserves_feature_07_behavior
tests/test_permissions.py::test_deny_and_ask_rules_still_win
tests/test_permissions.py::test_once_degrades_boundary_ask_to_deny
tests/test_permissions.py::test_dangerous_write_is_blocked_even_with_allow_rule
tests/test_permissions.py::test_dangerous_read_is_not_blocked
tests/test_permissions.py::test_deny_rule_still_takes_precedence_over_dangerous_check
tests/test_permissions.py::test_dangerous_write_reason_names_the_path
tests/test_permissions.py::test_rule_matching_does_not_depend_on_argument_order
tests/test_permissions.py::test_edit_file_rule_survives_a_path_last_ordering
tests/test_pty_reaping.py::test_reaping_cleans_up_a_child_that_is_busy_writing
tests/test_pty_reaping.py::test_reaping_is_bounded_even_when_the_child_never_appears
tests/test_queue.py::test_drain_all_takes_everything_and_empties
tests/test_queue.py::test_drain_single_takes_one_in_fifo_order
tests/test_queue.py::test_drain_empty_returns_empty_list
tests/test_queue.py::test_clear_discards_pending
tests/test_queue.py::test_has_items_reflects_state
tests/test_queue.py::test_drain_result_is_a_copy_not_the_internal_list
tests/test_queue.py::test_unknown_mode_is_rejected_at_construction
tests/test_queue.py::test_drain_all_with_predicate_leaves_unmatched_in_place
tests/test_queue.py::test_drain_all_with_predicate_matching_nothing_keeps_queue_intact
tests/test_queue.py::test_drain_single_with_predicate_takes_first_match_not_first_item
tests/test_queue.py::test_drain_empty_with_predicate_returns_empty_list
tests/test_queue.py::test_drain_without_predicate_is_unchanged
tests/test_queue.py::test_take_first_is_fifo_regardless_of_mode_or_kind
tests/test_queue.py::test_take_first_on_empty_returns_none_not_raises
tests/test_queue.py::test_drain_with_predicate_result_is_a_copy
tests/test_queue.py::test_queue_reports_its_own_length
tests/test_queue.py::test_len_tracks_partial_drain_and_take_first
tests/test_recall.py::test_manifest_line_carries_type_age_and_description
tests/test_recall.py::test_empty_directory_short_circuits_without_a_request
tests/test_recall.py::test_already_surfaced_files_are_filtered_before_the_request
tests/test_recall.py::test_everything_already_surfaced_means_no_request
tests/test_recall.py::test_whitelist_rejects_hallucinated_filenames
tests/test_recall.py::test_caps_at_max_recall_files
tests/test_recall.py::test_defensive_json_parsing_survives_fenced_output
tests/test_recall.py::test_unparseable_reply_degrades_to_empty
tests/test_recall.py::test_client_exception_degrades_to_empty_without_raising
tests/test_recall.py::test_disables_after_consecutive_failures
tests/test_recall.py::test_success_resets_the_failure_count
tests/test_recall.py::test_returns_usage_so_the_budget_can_count_it
tests/test_recall.py::test_selected_files_are_recorded_as_surfaced
tests/test_recall.py::test_prompt_carries_the_two_denoising_rules
tests/test_recall.py::test_block_is_wrapped_in_a_system_reminder
tests/test_recall.py::test_block_declares_it_is_background_not_an_instruction
tests/test_recall.py::test_block_warns_about_stale_memories
tests/test_recall.py::test_block_does_not_warn_about_fresh_memories
tests/test_recall.py::test_block_is_empty_when_nothing_was_selected
tests/test_recall.py::test_make_recall_returns_block_and_usage
tests/test_recall.py::test_make_recall_on_empty_directory_costs_nothing
tests/test_recall.py::test_real_trajectory_query_flows_through_recall_and_compaction
tests/test_recall.py::test_max_tokens_leaves_room_for_reasoning_tokens
tests/test_recall.py::test_selection_tolerates_manifest_line_decoration
tests/test_recall.py::test_whitelist_still_rejects_decorated_hallucinations
tests/test_recall.py::test_longest_match_wins_when_one_filename_contains_another
tests/test_recall.py::test_unparseable_reply_counts_as_a_failure
tests/test_recall.py::test_explicit_empty_selection_is_not_a_failure
tests/test_recall.py::test_failures_notify_the_assembly_layer
tests/test_recall.py::test_prompt_tells_the_model_to_return_bare_filenames
tests/test_recall.py::test_successful_recall_reports_which_memories_were_injected
tests/test_recall.py::test_no_event_when_nothing_is_selected
tests/test_recall.py::test_no_event_when_the_side_query_fails
tests/test_recall.py::test_a_huge_memory_is_truncated_before_it_reaches_the_context
tests/test_recall.py::test_a_normal_memory_is_not_touched
tests/test_resume_replay.py::test_history_items_from_a_real_session
tests/test_resume_replay.py::test_framework_injections_are_not_replayed_as_user_lines
tests/test_resume_replay.py::test_tool_rounds_pair_calls_with_results
tests/test_resume_replay.py::test_replay_puts_the_conversation_on_the_alt_screen
tests/test_resume_replay.py::test_replay_does_not_touch_the_dock
tests/test_resume_replay.py::test_replayed_tool_outputs_are_reachable_with_ctrl_o
tests/test_resume_replay.py::test_compacted_mark_shell_and_answer_render
tests/test_resume_replay.py::test_resume_rebuilds_system_prompt_and_instructions_from_the_current_environment
tests/test_resume_switch.py::test_open_existing_adopts_the_id_and_continues_the_physical_tail
tests/test_resume_switch.py::test_open_existing_rejects_a_v0_file
tests/test_resume_switch.py::test_event_trace_follows_the_session_when_it_switches
tests/test_resume_switch.py::test_cli_resume_appends_to_the_same_file
tests/test_resume_switch.py::test_resume_without_typing_leaves_the_file_byte_for_byte
tests/test_resume_switch.py::test_refreshed_system_stays_in_memory_and_unchanged_instructions_are_not_rerecorded
tests/test_resume_switch.py::test_changed_instructions_are_rerecorded_after_resume
tests/test_resume_switch.py::test_fork_session_writes_a_new_file_with_parent_session
tests/test_resume_switch.py::test_cli_fork_session_flag_requires_resume
tests/test_resume_switch.py::test_slash_resume_switches_to_the_target_conversation
tests/test_resume_switch.py::test_slash_resume_lets_recall_come_back
tests/test_resume_switch.py::test_slash_resume_without_argument_offers_recent_sessions
tests/test_resume_switch.py::test_cancelling_the_picker_keeps_the_current_conversation
tests/test_resume_switch.py::test_slash_resume_with_an_unknown_id_says_so
tests/test_resume_switch.py::test_slash_resume_with_nothing_to_resume_says_so
tests/test_resume_switch.py::test_picker_only_lists_sessions_recorded_in_the_current_directory
tests/test_resume_switch.py::test_resume_latest_skips_sessions_recorded_elsewhere
tests/test_resume_switch.py::test_explicit_id_still_reaches_a_session_recorded_elsewhere
tests/test_rules.py::test_scans_project_and_user_rules
tests/test_rules.py::test_scans_recursively
tests/test_rules.py::test_both_paths_spellings_parse_the_same
tests/test_rules.py::test_a_rule_without_paths_is_skipped_with_a_warning
tests/test_rules.py::test_broken_files_do_not_explode
tests/test_rules.py::test_no_rules_directory_is_not_an_error
tests/test_rules.py::test_double_star_crosses_directories
tests/test_rules.py::test_single_star_does_not_cross_a_slash
tests/test_rules.py::test_a_directory_pattern_matches_everything_under_it
tests/test_rules.py::test_question_mark_matches_one_char_not_a_slash
tests/test_rules.py::test_special_regex_chars_are_literal
tests/test_rules.py::test_double_star_translation_is_load_bearing
tests/test_rules.py::test_a_touched_path_pulls_in_its_rule
tests/test_rules.py::test_an_untouched_rule_never_shows_up
tests/test_rules.py::test_a_rule_is_not_injected_twice
tests/test_rules.py::test_clearing_the_state_lets_it_come_back
tests/test_rules.py::test_paths_outside_the_project_never_match
tests/test_rules.py::test_a_huge_rule_is_truncated
tests/test_rules.py::test_too_many_rules_in_one_step_says_so
tests/test_rules.py::test_relative_paths_resolve_against_cwd_not_the_project_root
tests/test_run_tests_tool.py::test_the_configured_command_wins
tests/test_run_tests_tool.py::test_autodetect_prefers_the_projects_own_test_script
tests/test_run_tests_tool.py::test_autodetect_falls_back_to_pytest_for_a_python_project
tests/test_run_tests_tool.py::test_autodetect_knows_a_few_other_ecosystems
tests/test_run_tests_tool.py::test_filter_and_path_are_passed_through
tests/test_run_tests_tool.py::test_the_running_command_is_reported
tests/test_run_tests_tool.py::test_a_failing_run_reports_the_exit_code
tests/test_run_tests_tool.py::test_long_output_keeps_the_verdict_at_the_end
tests/test_run_tests_tool.py::test_an_undetectable_project_says_which_setting_to_configure
tests/test_run_tests_tool.py::test_a_missing_path_is_reported
tests/test_run_tests_tool.py::test_a_bogus_configured_timeout_falls_back_loudly
tests/test_run_tests_tool.py::test_the_tool_is_registered_and_its_schema_is_generated
tests/test_run_tests_tool.py::test_it_declares_exec_so_the_boundary_can_see_it
tests/test_run_tests_tool.py::test_the_declared_path_resolves_the_default_root
tests/test_run_tests_tool.py::test_it_is_declared_not_concurrency_safe_on_purpose
tests/test_run_tests_tool.py::test_two_test_runs_never_batch_in_parallel
tests/test_run_tests_tool.py::test_running_tests_inside_the_working_dir_is_allowed_without_asking
tests/test_run_tests_tool.py::test_running_tests_outside_the_working_dir_still_asks
tests/test_run_tests_tool.py::test_a_deny_rule_can_target_the_test_root
tests/test_scheduler.py::test_consecutive_safe_tools_merge_into_one_batch
tests/test_scheduler.py::test_a_serial_tool_splits_the_batch_and_order_is_preserved
tests/test_scheduler.py::test_only_read_only_and_concurrency_safe_tools_go_parallel
tests/test_scheduler.py::test_unknown_tool_is_never_parallel
tests/test_scheduler.py::test_bad_json_arguments_is_never_parallel
tests/test_scheduler.py::test_results_are_returned_in_input_order_not_completion_order
tests/test_scheduler.py::test_batch_really_runs_in_parallel
tests/test_scheduler.py::test_serial_batch_runs_one_by_one
tests/test_scheduler.py::test_single_call_batch_does_not_spawn_a_thread
tests/test_scheduler.py::test_real_builtin_tools_partition_as_expected
tests/test_scheduler.py::test_exception_in_one_parallel_task_does_not_swallow_the_others
tests/test_search_tool.py::test_finds_matches_and_reports_file_and_line
tests/test_search_tool.py::test_glob_filters_which_files_are_searched
tests/test_search_tool.py::test_noise_directories_are_skipped
tests/test_search_tool.py::test_an_empty_pattern_lists_the_files_matching_the_glob
tests/test_search_tool.py::test_binary_files_are_skipped_not_crashed_on
tests/test_search_tool.py::test_max_results_caps_the_output_and_says_so
tests/test_search_tool.py::test_a_file_that_decodes_but_holds_nul_bytes_is_also_skipped
tests/test_search_tool.py::test_many_matches_inside_one_file_still_respect_max_results
tests/test_search_tool.py::test_no_match_says_so_instead_of_returning_nothing
tests/test_search_tool.py::test_symlinks_pointing_outside_the_search_root_are_skipped
tests/test_search_tool.py::test_a_single_file_can_be_the_search_root
tests/test_search_tool.py::test_searching_a_single_file_finds_nothing_gracefully
tests/test_search_tool.py::test_a_single_file_root_still_respects_the_glob
tests/test_search_tool.py::test_directory_behaviour_is_byte_for_byte_unchanged
tests/test_search_tool.py::test_a_bad_regex_is_reported_not_raised
tests/test_search_tool.py::test_a_missing_search_root_is_reported
tests/test_search_tool.py::test_a_negative_max_results_is_reported_not_silently_ignored
tests/test_search_tool.py::test_the_tool_is_registered_in_the_default_set
tests/test_search_tool.py::test_the_schema_is_generated_from_the_signature
tests/test_search_tool.py::test_it_declares_path_semantics_so_the_boundary_can_see_it
tests/test_search_tool.py::test_the_declared_path_resolves_the_default_root
tests/test_search_tool.py::test_it_declares_capabilities_so_the_scheduler_can_batch_it
tests/test_search_tool.py::test_it_batches_in_parallel_next_to_read_file
tests/test_search_tool.py::test_searching_inside_the_working_dir_is_allowed_without_asking
tests/test_search_tool.py::test_searching_outside_the_working_dir_still_asks
tests/test_search_tool.py::test_a_deny_rule_can_target_the_search_root
tests/test_session_format.py::test_first_line_is_a_header_with_version_and_identity
tests/test_session_format.py::test_messages_are_wrapped_in_an_envelope_with_nested_payload
tests/test_session_format.py::test_type_records_keep_their_fields_beside_the_envelope
tests/test_session_format.py::test_parent_id_chains_entries_in_file_order
tests/test_session_format.py::test_append_can_preserve_an_explicit_id_for_resume
tests/test_session_format.py::test_v0_files_are_refused_with_an_honest_message
tests/test_session_format.py::test_newer_versions_are_refused_with_the_upgrade_direction
tests/test_session_format.py::test_unknown_entry_types_are_refused_unless_ignorable
tests/test_session_format.py::test_build_messages_rebuilds_a_real_trajectory
tests/test_session_format.py::test_build_messages_reconstructs_a_compacted_session
tests/test_session_format.py::test_build_messages_relocates_the_instruction_after_system
tests/test_session_format.py::test_replay_messages_now_goes_through_the_v1_loader
tests/test_session_format.py::test_trim_unfinished_drops_the_torn_tail
tests/test_session_format.py::test_trim_unfinished_drops_orphan_tool_results
tests/test_session_format.py::test_resolve_resume_target_picks_the_latest_session
tests/test_session_format.py::test_resolve_resume_target_breaks_mtime_ties_deterministically
tests/test_session_format.py::test_resolve_resume_target_by_id_prefix_and_by_path
tests/test_session_format.py::test_resolve_resume_target_errors_honestly_when_nothing_matches
tests/test_session_format.py::test_second_compaction_can_keep_the_first_summary
tests/test_settings.py::test_read_settings_layers_returns_both_layers_with_paths
tests/test_settings.py::test_read_settings_layers_missing_files_are_empty
tests/test_settings.py::test_read_settings_layers_bad_json_warns_only_that_layer
tests/test_settings.py::test_trust_marker_roundtrip_and_isolation
tests/test_settings.py::test_gate_unattended_drops_project_items_with_note
tests/test_settings.py::test_gate_trust_persists_and_refuse_does_not
tests/test_settings.py::test_bash_timeout_seconds_reads_valid_value
tests/test_settings.py::test_bash_timeout_seconds_missing_returns_none
tests/test_settings.py::test_bash_timeout_seconds_invalid_warns_and_falls_back[300]
tests/test_settings.py::test_bash_timeout_seconds_invalid_warns_and_falls_back[0]
tests/test_settings.py::test_bash_timeout_seconds_invalid_warns_and_falls_back[-5]
tests/test_settings.py::test_bash_timeout_seconds_invalid_warns_and_falls_back[601]
tests/test_settings.py::test_bash_timeout_seconds_invalid_warns_and_falls_back[True]
tests/test_settings.py::test_additional_directories_parses_and_expands_home
tests/test_settings.py::test_additional_directories_missing_is_empty
tests/test_settings.py::test_additional_directories_invalid_warns_and_ignores
tests/test_skills.py::test_skills_paths_live_in_paths_module
tests/test_skills.py::test_project_skills_dir_without_git_uses_cwd
tests/test_skills.py::test_scan_finds_directory_bundle_skill
tests/test_skills.py::test_scan_finds_flat_markdown_skill
tests/test_skills.py::test_scan_project_beats_user_on_same_name
tests/test_skills.py::test_scan_directory_bundle_beats_flat_file_in_same_root
tests/test_skills.py::test_scan_skips_missing_description_and_warns
tests/test_skills.py::test_scan_skips_broken_frontmatter_and_warns
tests/test_skills.py::test_scan_reads_disable_model_invocation
tests/test_skills.py::test_scan_warns_on_non_kebab_name_but_still_loads
tests/test_skills.py::test_scan_ignores_deeper_nesting_and_hidden_entries
tests/test_skills.py::test_scan_missing_roots_yield_empty
tests/test_skills.py::test_scan_frontmatter_name_is_ignored
tests/test_skills.py::test_catalog_lists_name_and_description_sorted
tests/test_skills.py::test_catalog_has_no_file_paths
tests/test_skills.py::test_catalog_escapes_xml
tests/test_skills.py::test_catalog_excludes_disable_model_invocation
tests/test_skills.py::test_catalog_empty_returns_empty_string
tests/test_skills.py::test_catalog_caps_each_description
tests/test_skills.py::test_catalog_total_budget_truncates_with_hint
tests/test_skills.py::test_prompt_without_catalog_is_byte_identical
tests/test_skills.py::test_prompt_appends_catalog_when_skill_tool_present
tests/test_skills.py::test_prompt_ignores_catalog_when_skill_tool_absent
tests/test_skills.py::test_prompt_ignores_empty_catalog
tests/test_skills.py::test_skill_tool_returns_body_with_base_dir_note
tests/test_skills.py::test_skill_tool_rereads_disk_each_call
tests/test_skills.py::test_skill_tool_unknown_name_lists_available
tests/test_skills.py::test_skill_tool_hides_disable_model_invocation
tests/test_skills.py::test_skill_tool_records_into_tracker
tests/test_skills.py::test_skill_tool_without_catalog_says_no_skills
tests/test_skills.py::test_skill_tool_capabilities_and_boundary_declarations
tests/test_skills.py::test_dangerous_write_guards_skills_dirs
tests/test_skills.py::test_accept_edits_does_not_silently_write_skills
tests/test_skills.py::test_trust_once_drops_untrusted_project_skills_and_warns
tests/test_skills.py::test_trust_marker_lets_project_skills_through
tests/test_skills.py::test_trust_dialog_yes_persists_and_loads
tests/test_skills.py::test_trust_dialog_no_skips_without_persisting
tests/test_skills.py::test_once_untrusted_project_skill_stays_out_of_prompt
tests/test_skills.py::test_user_skill_link_roots_resolves_only_user_level
tests/test_skills.py::test_once_reads_attachment_of_symlinked_user_skill
tests/test_skills.py::test_decide_allows_skill_tool_via_boundary_exemption
tests/test_skills.py::test_decide_skill_exemption_yields_to_deny_and_ask_rules
tests/test_skills.py::test_decide_skill_attachments_still_walk_the_boundary
tests/test_skills.py::test_once_loads_user_level_skill_in_dontask_mode
tests/test_skills.py::test_once_loads_project_skill_from_repo_subdir
tests/test_skills.py::test_once_system_prompt_carries_catalog
tests/test_skills.py::test_once_without_skills_hides_skill_tool
tests/test_skills.py::test_once_all_disabled_also_hides_skill_tool
tests/test_skills.py::test_reattach_renders_recent_first_and_rereads_disk
tests/test_skills.py::test_reattach_truncates_head_and_drops_over_total_budget
tests/test_skills.py::test_reattach_skips_deleted_files_and_empty_is_empty
tests/test_skills.py::test_loaded_skills_record_is_thread_safe
tests/test_skills.py::test_make_instructions_composes_base_and_loaded
tests/test_skills.py::test_compaction_reinjects_loaded_skill_body
tests/test_skills.py::test_help_mentions_skill_command
tests/test_skills.py::test_repl_skill_command_expands_and_runs_turn
tests/test_skills.py::test_repl_bare_skill_lists_without_model_call
tests/test_skills.py::test_repl_skill_unknown_name_no_model_call
tests/test_skills.py::test_repl_system_prompt_carries_catalog_and_tool
tests/test_skills.py::test_repl_without_skills_hides_tool_and_catalog
tests/test_skills.py::test_repl_all_disabled_hides_tool_but_keeps_user_channel
tests/test_skills.py::test_repl_skill_can_invoke_disable_model_invocation
tests/test_skills.py::test_repl_skill_command_records_into_tracker_for_reattach
tests/test_statusline.py::test_completed_tools_fold_by_name_with_count
tests/test_statusline.py::test_single_call_has_no_count_suffix
tests/test_statusline.py::test_running_tool_comes_first_with_arg_preview
tests/test_statusline.py::test_finished_tool_is_no_longer_running
tests/test_statusline.py::test_error_tool_gets_cross_mark
tests/test_statusline.py::test_truncates_by_terminal_columns_not_characters
tests/test_statusline.py::test_display_width_counts_east_asian_wide_as_two
tests/test_statusline.py::test_combining_marks_take_zero_columns
tests/test_statusline.py::test_zwj_emoji_sequences_are_still_wrong_and_we_say_so
tests/test_statusline.py::test_empty_events_render_empty_string
tests/test_statusline.py::test_no_color_unless_asked
tests/test_statusline.py::test_other_events_are_ignored
tests/test_statusline.py::test_colored_line_is_also_width_limited
tests/test_statusline.py::test_parts_beyond_width_are_dropped_not_cut_mid_escape
tests/test_statusline.py::test_default_handler_falls_back_to_scrolling_lines_off_tty
tests/test_statusline.py::test_default_handler_uses_inplace_statusline_on_tty
tests/test_statusline.py::test_statusline_is_cleared_when_the_turn_ends
tests/test_statusline.py::test_display_width_ignores_escape_sequences
tests/test_statusline.py::test_display_width_of_plain_text_is_unchanged_by_escape_stripping
tests/test_statusline.py::test_preview_shows_the_command_even_when_another_argument_comes_first
tests/test_streaming.py::test_assembles_parallel_tool_calls_from_real_fragments
tests/test_streaming.py::test_tool_calls_are_merged_by_index_not_by_id
tests/test_streaming.py::test_interleaved_fragments_are_still_merged_correctly
tests/test_streaming.py::test_usage_is_found_on_deepseek_shape_last_chunk
tests/test_streaming.py::test_usage_is_found_on_openai_shape_separate_chunk
tests/test_streaming.py::test_usage_keeps_provider_specific_fields
tests/test_streaming.py::test_content_deltas_are_streamed_out_in_order
tests/test_streaming.py::test_reasoning_content_does_not_leak_into_content
tests/test_streaming.py::test_pure_text_answer_has_no_tool_calls
tests/test_streaming.py::test_interrupt_stops_consuming_and_reports_no_usage
tests/test_streaming.py::test_no_flag_means_never_interrupted
tests/test_streaming.py::test_fake_client_streaming_round_trips_through_the_assembler
tests/test_streaming.py::test_fake_client_streaming_can_emit_tool_calls
tests/test_streaming.py::test_fake_client_can_emit_the_openai_usage_shape
tests/test_streaming.py::test_empty_tool_call_ids_are_synthesized_unique
tests/test_streaming.py::test_duplicate_tool_call_ids_are_made_unique
tests/test_streaming.py::test_normal_unique_ids_are_left_untouched
tests/test_task_entry.py::test_llm_gate_requires_explicit_optin_and_valid_key[env0]
tests/test_task_entry.py::test_llm_gate_requires_explicit_optin_and_valid_key[env1]
tests/test_task_entry.py::test_llm_gate_requires_explicit_optin_and_valid_key[env2]
tests/test_task_entry.py::test_llm_gate_requires_explicit_optin_and_valid_key[env3]
tests/test_task_entry.py::test_llm_gate_freezes_endpoint_and_does_not_mutate_input
tests/test_task_entry.py::test_batch_keeps_nine_trials_no_retries_and_sanitized_manifest
tests/test_task_entry.py::test_total_deadline_prevents_new_trials_and_preserves_denominator
tests/test_task_entry.py::test_entry_default_never_collects_task_suite_or_fixture_tests
tests/test_task_entry.py::test_tasks_entry_has_one_offline_contract_and_explicit_real_batch
tests/test_task_entry.py::test_batch_interrupt_records_remaining_trials_before_propagating
tests/test_task_grading.py::test_locate_requires_exact_target_and_no_protected_change
tests/test_task_grading.py::test_fix_fixture_red_and_reference_green
tests/test_task_grading.py::test_added_tests_must_pass_correct_and_reject_every_mutant
tests/test_task_grading.py::test_bad_added_tests_cannot_count_as_mutant_detection[???]
tests/test_task_grading.py::test_bad_added_tests_cannot_count_as_mutant_detection[import missing_package]
tests/test_task_grading.py::test_bad_added_tests_cannot_count_as_mutant_detection[def test_bad():\n    assert False\n]
tests/test_task_grading.py::test_added_tests_must_detect_invalid_bounds_mutant
tests/test_task_grading.py::test_symlink_and_extra_files_are_rejected
tests/test_task_grading.py::test_fix_cannot_pass_by_skipping_external_assertions
tests/test_task_grading.py::test_external_grader_never_loads_source_checkout_conftest
tests/test_task_metrics.py::test_metrics_from_committed_real_chinese_trajectory
tests/test_task_metrics.py::test_missing_usage_and_event_stream_are_unknown
tests/test_task_metrics.py::test_denied_parallel_call_counts_as_attempt_not_execution
tests/test_task_metrics.py::test_metrics_reject_broken_session_instead_of_reporting_zero[rows0]
tests/test_task_metrics.py::test_metrics_reject_broken_session_instead_of_reporting_zero[rows1]
tests/test_task_metrics.py::test_metrics_reject_broken_session_instead_of_reporting_zero[rows2]
tests/test_task_metrics.py::test_invalid_json_is_not_silently_dropped
tests/test_task_metrics.py::test_partial_usage_optional_fields_and_side_requests
tests/test_task_metrics.py::test_summary_keeps_budget_failures_and_unstarted_in_denominator
tests/test_task_runner.py::test_worker_runs_real_once_with_fake_client_and_permission_denial
tests/test_task_runner.py::test_worker_records_budget_and_steps_separately[max_steps-1-200000]
tests/test_task_runner.py::test_worker_records_budget_and_steps_separately[budget-4-1]
tests/test_task_runner.py::test_child_environment_ignores_personal_settings_and_proxy_secrets
tests/test_task_runner.py::test_real_process_fake_provider_succeeds_and_keeps_artifacts
tests/test_task_runner.py::test_deadline_stops_worker_and_separate_test_process_group
tests/test_task_runner.py::test_provider_failure_is_not_a_model_task_failure
tests/test_task_runner.py::test_forced_stop_reaps_detached_child_when_worker_ignores_term
tests/test_task_runner.py::test_interrupted_trial_preserves_workspace_before_temp_cleanup
tests/test_tool_choice_scoring.py::test_score_counts_hits_and_misses
tests/test_tool_choice_scoring.py::test_a_partial_hit_is_a_fraction_not_a_boolean
tests/test_tool_choice_scoring.py::test_negatives_are_counted_separately_but_weighted_the_same
tests/test_tool_choice_scoring.py::test_a_miss_records_what_was_picked_instead
tests/test_tool_choice_scoring.py::test_no_tool_call_is_a_result_not_a_crash
tests/test_tool_choice_scoring.py::test_first_tool_name_survives_junk
tests/test_tool_choice_scoring.py::test_run_cases_uses_the_injected_asker
tests/test_tool_choice_scoring.py::test_samples_controls_how_many_times_each_case_is_asked
tests/test_tool_choice_scoring.py::test_the_case_set_is_the_shape_the_archive_pre_registered
tests/test_tool_choice_scoring.py::test_every_case_expects_a_real_tool_and_explains_itself
tests/test_tool_choice_scoring.py::test_the_baseline_prompt_is_frozen_text_not_regenerated
tests/test_tool_diffs.py::test_a_small_change_shows_a_unified_diff
tests/test_tool_diffs.py::test_the_empty_file_headers_are_stripped
tests/test_tool_diffs.py::test_a_content_line_starting_with_dashes_survives
tests/test_tool_diffs.py::test_an_unchanged_write_says_so_instead_of_showing_nothing
tests/test_tool_diffs.py::test_a_new_file_reports_lines_instead_of_pasting_the_body_twice
tests/test_tool_diffs.py::test_a_huge_change_reports_stats_and_points_somewhere
tests/test_tool_diffs.py::test_the_stats_count_added_and_removed_separately
tests/test_tool_diffs.py::test_binary_or_undecodable_before_is_not_a_crash
tests/test_tool_diffs.py::test_edit_file_returns_a_diff
tests/test_tool_diffs.py::test_write_file_returns_a_diff_when_overwriting
tests/test_tool_diffs.py::test_write_file_on_a_new_file_does_not_paste_the_body_twice
tests/test_tool_diffs.py::test_an_overwrite_with_identical_content_says_no_change
tests/test_tool_diffs.py::test_write_file_over_a_binary_file_still_writes
tests/test_tool_diffs.py::test_the_diff_is_a_multiline_result_so_the_tui_can_fold_it
tests/test_tool_roots.py::test_the_extracted_getter_matches_the_old_ones_verbatim[args0]
tests/test_tool_roots.py::test_the_extracted_getter_matches_the_old_ones_verbatim[args1]
tests/test_tool_roots.py::test_the_extracted_getter_matches_the_old_ones_verbatim[args2]
tests/test_tool_roots.py::test_the_extracted_getter_matches_the_old_ones_verbatim[args3]
tests/test_tool_roots.py::test_the_extracted_getter_matches_the_old_ones_verbatim[args4]
tests/test_tool_roots.py::test_the_extracted_getter_matches_the_old_ones_verbatim[args5]
tests/test_tool_roots.py::test_the_extracted_getter_matches_the_old_ones_verbatim[args6]
tests/test_tool_roots.py::test_the_extracted_getter_matches_the_old_ones_verbatim[args7]
tests/test_tool_roots.py::test_the_extracted_getter_matches_the_old_ones_verbatim[args8]
tests/test_tool_roots.py::test_the_extracted_getter_matches_the_old_ones_verbatim[args9]
tests/test_tool_roots.py::test_git_read_still_ignores_args_entirely[args0]
tests/test_tool_roots.py::test_git_read_still_ignores_args_entirely[args1]
tests/test_tool_roots.py::test_git_read_still_ignores_args_entirely[args2]
tests/test_tool_roots.py::test_git_read_still_ignores_args_entirely[args3]
tests/test_tool_roots.py::test_git_read_still_ignores_args_entirely[args4]
tests/test_tool_roots.py::test_git_read_still_ignores_args_entirely[args5]
tests/test_tool_roots.py::test_git_read_still_ignores_args_entirely[args6]
tests/test_tool_roots.py::test_git_read_still_ignores_args_entirely[args7]
tests/test_tool_roots.py::test_git_read_still_ignores_args_entirely[args8]
tests/test_tool_roots.py::test_git_read_still_ignores_args_entirely[args9]
tests/test_tool_roots.py::test_the_extracted_matcher_matches_the_old_wrapping_verbatim[args0]
tests/test_tool_roots.py::test_the_extracted_matcher_matches_the_old_wrapping_verbatim[args1]
tests/test_tool_roots.py::test_the_extracted_matcher_matches_the_old_wrapping_verbatim[args2]
tests/test_tool_roots.py::test_the_extracted_matcher_matches_the_old_wrapping_verbatim[args3]
tests/test_tool_roots.py::test_the_extracted_matcher_matches_the_old_wrapping_verbatim[args4]
tests/test_tool_roots.py::test_the_extracted_matcher_matches_the_old_wrapping_verbatim[args5]
tests/test_tool_roots.py::test_the_extracted_matcher_matches_the_old_wrapping_verbatim[args6]
tests/test_tool_roots.py::test_the_extracted_matcher_matches_the_old_wrapping_verbatim[args7]
tests/test_tool_roots.py::test_the_extracted_matcher_matches_the_old_wrapping_verbatim[args8]
tests/test_tool_roots.py::test_the_extracted_matcher_matches_the_old_wrapping_verbatim[args9]
tests/test_tool_roots.py::test_a_tool_without_a_path_parameter_ignores_stray_args
tests/test_tool_steering.py::test_every_specialised_tool_gets_a_steering_line
tests/test_tool_steering.py::test_steering_lines_are_conditional_on_the_tool_being_present
tests/test_tool_steering.py::test_bash_description_points_at_the_specialised_tools
tests/test_tool_steering.py::test_the_project_overview_is_injected
tests/test_tool_steering.py::test_without_a_project_root_the_prompt_is_byte_for_byte_unchanged
tests/test_tool_steering.py::test_the_prompt_is_stable_across_calls
tests/test_tool_steering.py::test_a_broken_project_root_does_not_break_the_prompt
tests/test_tool_steering.py::test_once_passes_the_working_directory_into_the_prompt
tests/test_tools.py::test_schema_generated_from_signature
tests/test_tools.py::test_get_tools_subset
tests/test_tools.py::test_edit_file_unique_match
tests/test_tools.py::test_edit_file_rejects_missing_and_ambiguous
tests/test_tools.py::test_tool_run_converts_exception_to_message
tests/test_tools.py::test_tool_without_docstring_is_rejected_clearly
tests/test_tools.py::test_tool_rejects_unknown_param_type
tests/test_tools.py::test_tool_run_coerces_non_str_return
tests/test_tools.py::test_bash_timeout_returns_partial_output
tests/test_tools.py::test_the_default_timeout_matches_the_two_reference_implementations
tests/test_tools.py::test_timeout_message_tells_the_model_what_to_do_next
tests/test_tools.py::test_timeout_message_reports_exit_code
tests/test_tools.py::test_interrupt_message_does_not_offer_the_timeout_way_out
tests/test_tools.py::test_omitted_timeout_falls_back_to_the_default
tests/test_tools.py::test_a_model_supplied_timeout_is_clamped_to_the_cap
tests/test_tools.py::test_the_cap_matches_the_two_reference_implementations
tests/test_tools.py::test_a_negative_timeout_is_reported_not_silently_ignored
tests/test_tools.py::test_a_model_supplied_timeout_actually_takes_effect
tests/test_tools.py::test_bash_schema_exposes_timeout_as_an_optional_integer
tests/test_tools.py::test_bash_normal_path_unchanged
tests/test_tools.py::test_bash_skips_execution_when_already_interrupted
tests/test_tools.py::test_bash_kills_running_command_and_returns_fast
tests/test_tools.py::test_bash_kills_whole_process_group_not_just_the_child
tests/test_tools.py::test_bash_keeps_partial_output_on_interrupt
tests/test_tools.py::test_ask_returns_asker_answer
tests/test_tools.py::test_ask_without_asker_returns_error_string
tests/test_tools.py::test_ask_rejects_malformed_options
tests/test_tools.py::test_ask_schema_is_generated_from_signature
tests/test_tools.py::test_get_tools_excludes_ask_by_default
tests/test_tools.py::test_remember_writes_a_memory_file_and_indexes_it
tests/test_tools.py::test_remember_appends_without_clobbering
tests/test_tools.py::test_remember_indexes_each_memory_once
tests/test_tools.py::test_remember_rejects_path_traversal
tests/test_tools.py::test_remember_returns_error_string_instead_of_raising
tests/test_tools.py::test_remember_writes_frontmatter_that_scan_can_read_back
tests/test_tools.py::test_remember_type_defaults_to_project
tests/test_tools.py::test_same_name_updates_instead_of_creating_a_second_file
tests/test_tools.py::test_origin_session_id_is_recorded_when_injected
tests/test_tools.py::test_deleted_memory_disappears_from_the_index
tests/test_tools.py::test_index_is_rebuilt_so_hand_edits_are_overwritten
tests/test_tools.py::test_legacy_file_gets_frontmatter_on_next_write
tests/test_tools.py::test_writes_leave_no_temp_files_behind
tests/test_tools.py::test_remember_is_in_the_default_tool_set
tests/test_tools.py::test_remember_notifies_the_assembly_layer
tests/test_tools.py::test_spawned_process_groups_are_reaped_on_exit
tests/test_tools.py::test_reap_is_idempotent_and_safe_when_empty
tests/test_tools.py::test_reap_does_not_raise_on_already_dead_groups
tests/test_tools.py::test_write_failure_leaves_the_original_file_intact
tests/test_tools.py::test_edit_failure_leaves_the_original_file_intact
tests/test_tools.py::test_no_temp_files_left_behind
tests/test_tools.py::test_write_preserves_file_mode
tests/test_tools.py::test_update_keeps_the_existing_type_when_not_specified
tests/test_tools.py::test_new_memory_without_type_defaults_to_project
tests/test_tools.py::test_capabilities_default_to_false_for_undeclared_tools
tests/test_tools.py::test_capabilities_accept_plain_bools
tests/test_tools.py::test_capabilities_accept_callables_that_look_at_args
tests/test_tools.py::test_capability_raising_is_treated_as_unsafe
tests/test_tools.py::test_capability_with_non_dict_args_is_unsafe
tests/test_tools.py::test_capabilities_for_rejects_unregistered_tools
tests/test_tools.py::test_builtin_tool_capabilities
tests/test_tools.py::test_the_registry_is_restored_between_tests
tests/test_tools.py::test_the_previous_probe_did_not_leak_into_this_test
tests/test_tools.py::test_a_single_over_budget_line_says_offset_cannot_help
tests/test_tools.py::test_a_crashing_capability_judge_leaves_a_trace
tests/test_tools.py::test_the_normal_degraded_paths_stay_silent
tests/test_tools.py::test_read_file_offset_starts_at_that_line
tests/test_tools.py::test_read_file_limit_caps_the_line_count
tests/test_tools.py::test_segmented_reads_reassemble_the_file_verbatim
tests/test_tools.py::test_truncation_cuts_at_a_line_boundary_so_the_next_offset_is_exact
tests/test_tools.py::test_read_file_truncation_points_at_offset_not_at_sed
tests/test_tools.py::test_read_file_rejects_negative_offset_and_limit
tests/test_tools.py::test_read_file_offset_past_the_end_says_how_many_lines_there_are
tests/test_tools.py::test_read_file_schema_exposes_offset_and_limit_as_optional_integers
tests/test_tools.py::test_whole_file_read_is_byte_for_byte_unchanged
tests/test_tools.py::test_near_line_picks_the_occurrence_closest_to_it
tests/test_tools.py::test_near_line_does_not_need_to_be_exact
tests/test_tools.py::test_a_tie_picks_the_earlier_occurrence_and_says_so
tests/test_tools.py::test_without_near_line_the_old_behaviour_is_unchanged
tests/test_tools.py::test_ambiguous_without_near_line_still_refuses_but_now_points_at_the_way_out
tests/test_tools.py::test_a_negative_near_line_is_reported
tests/test_tools.py::test_near_line_on_a_missing_old_still_says_not_found
tests/test_tools.py::test_edit_file_schema_exposes_near_line_as_an_optional_integer
tests/test_trace.py::test_every_event_type_is_covered_by_samples
tests/test_trace.py::test_each_event_round_trips_with_its_type_name
tests/test_trace.py::test_message_delta_is_not_written
tests/test_trace.py::test_path_is_derived_from_the_session_file
tests/test_trace.py::test_write_failure_never_raises_and_warns_exactly_once
tests/test_trace.py::test_compose_fans_out_to_every_handler
tests/test_trace.py::test_compose_skips_none_handlers
tests/test_trace.py::test_compose_does_not_swallow_handler_errors
tests/test_trace_wiring.py::test_once_writes_the_event_stream_next_to_the_session
tests/test_trace_wiring.py::test_events_carry_their_payload_not_just_the_type_name
tests/test_trace_wiring.py::test_no_session_means_no_event_file
tests/test_trace_wiring.py::test_the_caller_supplied_handler_still_runs
tests/test_trace_wiring.py::test_interactive_writes_one_event_file_for_the_whole_repl
tests/test_trace_wiring.py::test_slash_clear_leaves_a_marker_in_the_event_stream
tests/test_trace_wiring.py::test_manual_compact_emits_the_same_event_as_the_automatic_one
tests/test_trace_wiring.py::test_the_tui_path_also_writes_the_event_stream
tests/test_trace_wiring.py::test_tui_command_dispatch_carries_on_event
tests/test_trace_wiring.py::test_the_tui_path_swaps_the_event_sink
tests/test_trace_wiring.py::test_the_tui_path_also_feeds_the_state_listener
tests/test_trace_wiring.py::test_the_tui_uninstalls_the_heartbeat_on_the_way_out
tests/test_tui_alt_lifecycle.py::test_entering_alt_screen_sends_the_whole_preamble
tests/test_tui_alt_lifecycle.py::test_alt_screen_is_entered_before_any_frame_is_written
tests/test_tui_alt_lifecycle.py::test_leaving_alt_screen_restores_everything
tests/test_tui_alt_lifecycle.py::test_exit_alt_comes_after_re_enabling_autowrap
tests/test_tui_alt_lifecycle.py::test_restores_alt_screen_even_when_the_body_raises
tests/test_tui_alt_lifecycle.py::test_stop_is_idempotent
tests/test_tui_alt_lifecycle.py::test_alt_screen_off_sends_no_alt_sequences_at_all
tests/test_tui_alt_lifecycle.py::test_stop_still_restores_the_terminal_when_a_write_fails
tests/test_tui_alt_lifecycle.py::test_alt_screen_defaults_to_on
tests/test_tui_alt_lifecycle.py::test_project_settings_can_turn_alt_screen_off
tests/test_tui_alt_lifecycle.py::test_project_layer_overrides_the_user_layer
tests/test_tui_alt_lifecycle.py::test_non_boolean_value_warns_and_falls_back
tests/test_tui_alt_lifecycle.py::test_broken_json_does_not_take_down_the_ui
tests/test_tui_alt_wiring.py::test_alt_mode_keeps_committed_content_in_the_transcript
tests/test_tui_alt_wiring.py::test_dock_mode_hands_content_to_the_terminal_and_keeps_nothing
tests/test_tui_alt_wiring.py::test_dock_mode_output_is_unchanged_by_the_entry_refactor
tests/test_tui_alt_wiring.py::test_answers_are_wrapped_to_width_in_alt_mode
tests/test_tui_alt_wiring.py::test_tool_lines_re_render_at_the_new_width
tests/test_tui_alt_wiring.py::test_user_input_band_re_renders_at_the_new_width
tests/test_tui_alt_wiring.py::test_page_keys_scroll_the_transcript_in_alt_mode
tests/test_tui_alt_wiring.py::test_ctrl_home_and_ctrl_end_jump_to_the_ends
tests/test_tui_alt_wiring.py::test_plain_home_and_end_still_belong_to_the_editor
tests/test_tui_alt_wiring.py::test_scroll_keys_do_nothing_in_dock_mode
tests/test_tui_alt_wiring.py::test_typing_while_scrolled_up_does_not_yank_the_view_back
tests/test_tui_alt_wiring.py::test_new_output_while_scrolled_up_does_not_yank_the_view_back
tests/test_tui_alt_wiring.py::test_status_line_shows_that_you_are_scrolled_up
tests/test_tui_alt_wiring.py::test_status_line_flags_unseen_content
tests/test_tui_altscreen.py::test_frame_is_exactly_terminal_height_with_dock_at_the_bottom
tests/test_tui_altscreen.py::test_transcript_fills_the_space_above_the_dock
tests/test_tui_altscreen.py::test_short_transcript_leaves_blank_rows_not_garbage
tests/test_tui_altscreen.py::test_viewport_keeps_at_least_one_row_when_the_dock_is_huge
tests/test_tui_altscreen.py::test_second_frame_only_rewrites_changed_rows
tests/test_tui_altscreen.py::test_unchanged_frame_writes_no_rows_at_all
tests/test_tui_altscreen.py::test_never_clears_the_screen
tests/test_tui_altscreen.py::test_never_re_enters_alt_screen
tests/test_tui_altscreen.py::test_every_frame_is_wrapped_in_synchronized_output
tests/test_tui_altscreen.py::test_cursor_marker_places_the_hardware_cursor_and_shows_it
tests/test_tui_altscreen.py::test_no_marker_hides_the_cursor
tests/test_tui_altscreen.py::test_cursor_column_counts_chinese_as_two_columns
tests/test_tui_altscreen.py::test_lines_are_truncated_to_the_terminal_width
tests/test_tui_altscreen.py::test_resize_repaints_every_row_and_still_does_not_clear
tests/test_tui_altscreen.py::test_scroll_position_is_reflected_in_the_frame
tests/test_tui_altscreen.py::test_dock_stays_put_while_the_transcript_scrolls
tests/test_tui_altscreen.py::test_a_redraw_triggered_from_inside_a_write_does_not_interleave
tests/test_tui_altscreen.py::test_resize_forces_a_full_repaint_even_if_the_frame_is_identical
tests/test_tui_app.py::test_typing_shows_up_in_the_dock
tests/test_tui_app.py::test_enter_submits_and_the_line_is_committed_to_scrollback
tests/test_tui_app.py::test_slash_command_is_reported_as_a_command
tests/test_tui_app.py::test_bang_command_is_reported_as_a_command
tests/test_tui_app.py::test_shift_tab_asks_for_a_mode_cycle
tests/test_tui_app.py::test_ctrl_c_and_ctrl_d
tests/test_tui_app.py::test_ctrl_d_with_text_in_the_box_is_not_eof
tests/test_tui_app.py::test_empty_enter_does_nothing
tests/test_tui_app.py::test_dialog_takes_over_the_input_position
tests/test_tui_app.py::test_bang_command_during_a_question_is_executed_not_answered
tests/test_tui_app.py::test_slash_command_during_a_question_is_executed_not_answered
tests/test_tui_app.py::test_answering_a_question_resolves_it
tests/test_tui_app.py::test_typing_suppresses_a_pending_dialog_and_the_status_line_says_so
tests/test_tui_app.py::test_typing_while_busy_still_reaches_the_input_box
tests/test_tui_app.py::test_enter_while_busy_is_a_submit_for_the_queue
tests/test_tui_app.py::test_bang_command_while_busy_is_queued_not_run
tests/test_tui_app.py::test_queued_count_shows_up_in_the_dock
tests/test_tui_app.py::test_tool_events_render_in_the_dock_not_in_scrollback
tests/test_tui_app.py::test_agent_end_commits_a_summary_line_to_scrollback
tests/test_tui_app.py::test_history_is_wired_into_the_editor
tests/test_tui_app.py::test_idle_dock_does_not_need_ticking
tests/test_tui_app.py::test_a_running_turn_needs_ticking_for_the_spinner
tests/test_tui_app.py::test_a_suppressed_dialog_needs_ticking_so_it_can_be_released
tests/test_tui_app.py::test_the_model_answer_actually_reaches_the_screen
tests/test_tui_app.py::test_answer_is_committed_once_not_twice
tests/test_tui_app.py::test_a_synthesized_end_text_is_shown_even_without_deltas
tests/test_tui_app.py::test_tool_only_turn_shows_no_empty_answer
tests/test_tui_app.py::test_commit_splits_embedded_newlines
tests/test_tui_app.py::test_commit_wraps_lines_longer_than_the_terminal
tests/test_tui_app.py::test_commit_wraps_on_display_width_not_character_count
tests/test_tui_app.py::test_tool_result_is_collapsed_to_one_line_by_default
tests/test_tui_app.py::test_short_tool_result_is_not_padded_with_a_useless_hint
tests/test_tui_app.py::test_user_line_is_the_most_prominent_thing_on_screen
tests/test_tui_app.py::test_the_user_band_spans_the_whole_terminal_width
tests/test_tui_app.py::test_a_blank_line_separates_turns
tests/test_tui_app.py::test_user_line_and_agent_line_are_visually_distinct
tests/test_tui_app.py::test_collapsed_line_says_how_much_is_hidden
tests/test_tui_app.py::test_ctrl_o_expands_the_most_recent_collapsed_result
tests/test_tui_app.py::test_expanding_twice_walks_further_back
tests/test_tui_app.py::test_expanding_with_nothing_collapsed_says_so
tests/test_tui_app.py::test_collapsed_history_is_bounded
tests/test_tui_app.py::test_paste_recovered_key_surfaces_a_notice
tests/test_tui_arbiter.py::test_editor_owns_input_when_nothing_is_pending
tests/test_tui_arbiter.py::test_dialog_owns_input_when_the_input_box_is_empty
tests/test_tui_arbiter.py::test_typing_suppresses_pending_dialogs
tests/test_tui_arbiter.py::test_dialog_appears_after_the_typing_lull
tests/test_tui_arbiter.py::test_clearing_the_input_releases_immediately
tests/test_tui_arbiter.py::test_whitespace_only_input_does_not_count_as_typing
tests/test_tui_arbiter.py::test_each_keystroke_restarts_the_lull
tests/test_tui_arbiter.py::test_user_invoked_dialogs_are_not_suppressed
tests/test_tui_arbiter.py::test_pending_count_is_visible_so_it_is_not_silent
tests/test_tui_arbiter.py::test_not_suppressing_when_there_is_nothing_to_suppress
tests/test_tui_arbiter.py::test_dialogs_are_answered_in_order
tests/test_tui_arbiter.py::test_time_is_injected_so_tests_never_sleep
tests/test_tui_arbiter.py::test_resolve_removes_the_named_item_not_whichever_is_first
tests/test_tui_arbiter.py::test_resolve_without_an_argument_still_pops_the_head
tests/test_tui_arbiter.py::test_resolving_something_already_gone_is_a_no_op
tests/test_tui_click_expand.py::test_collapsed_by_default
tests/test_tui_click_expand.py::test_toggle_expands_and_collapses
tests/test_tui_click_expand.py::test_the_cache_key_includes_the_expanded_state
tests/test_tui_click_expand.py::test_expanded_state_survives_a_width_change
tests/test_tui_click_expand.py::test_owner_at_maps_a_line_to_its_entry
tests/test_tui_click_expand.py::test_owner_at_out_of_range_is_none
tests/test_tui_click_expand.py::test_clicking_a_tool_line_expands_it
tests/test_tui_click_expand.py::test_clicking_it_again_collapses
tests/test_tui_click_expand.py::test_dragging_selects_instead_of_expanding
tests/test_tui_click_expand.py::test_clicking_blank_space_does_nothing
tests/test_tui_click_expand.py::test_clicking_the_dock_does_not_touch_the_transcript
tests/test_tui_click_expand.py::test_clicking_a_non_expandable_entry_is_a_no_op
tests/test_tui_clipboard.py::test_local_copy_uses_the_system_clipboard_command
tests/test_tui_clipboard.py::test_a_nonzero_exit_falls_back_to_osc52
tests/test_tui_clipboard.py::test_a_timeout_falls_back_and_does_not_propagate
tests/test_tui_clipboard.py::test_a_missing_command_is_skipped_not_crashed
tests/test_tui_clipboard.py::test_no_command_available_at_all_goes_straight_to_osc52
tests/test_tui_clipboard.py::test_ssh_sessions_skip_the_local_clipboard
tests/test_tui_clipboard.py::test_osc52_payload_is_base64
tests/test_tui_clipboard.py::test_the_osc52_path_never_claims_success
tests/test_tui_clipboard.py::test_the_system_path_does_claim_success
tests/test_tui_clipboard.py::test_empty_text_copies_nothing
tests/test_tui_component.py::test_text_renders_one_line
tests/test_tui_component.py::test_container_concatenates_children_in_order
tests/test_tui_component.py::test_container_passes_width_down
tests/test_tui_component.py::test_invalidate_reaches_every_descendant
tests/test_tui_component.py::test_container_mutation_api
tests/test_tui_component.py::test_cursor_marker_is_zero_width
tests/test_tui_dialog.py::test_renders_question_and_options
tests/test_tui_dialog.py::test_arrow_keys_move_the_selection
tests/test_tui_dialog.py::test_enter_answers_with_the_selected_option
tests/test_tui_dialog.py::test_digit_keys_pick_directly_in_a_permission_dialog
tests/test_tui_dialog.py::test_out_of_range_digit_is_ignored_in_a_permission_dialog
tests/test_tui_dialog.py::test_question_dialog_does_not_eat_digit_prefixed_free_text
tests/test_tui_dialog.py::test_question_dialog_judges_the_whole_string_like_the_repl
tests/test_tui_dialog.py::test_question_dialog_out_of_range_number_is_free_text
tests/test_tui_dialog.py::test_esc_cancels
tests/test_tui_dialog.py::test_free_text_is_allowed_so_the_human_is_not_locked_into_options
tests/test_tui_dialog.py::test_typing_then_backspacing_to_empty_returns_to_option_mode
tests/test_tui_dialog.py::test_bang_command_is_not_an_answer
tests/test_tui_dialog.py::test_slash_command_is_not_an_answer
tests/test_tui_dialog.py::test_handoff_is_none_for_ordinary_text
tests/test_tui_dialog.py::test_permission_dialog_cancel_means_deny
tests/test_tui_dialog.py::test_render_never_exceeds_width
tests/test_tui_dialog.py::test_multiline_question_renders_as_multiple_lines
tests/test_tui_dialog.py::test_selected_option_is_marked_and_the_others_are_not
tests/test_tui_dialog.py::test_permission_dialog_uses_a_different_mark_than_a_question
tests/test_tui_dialog.py::test_a_fresh_dialog_is_not_resolved
tests/test_tui_dialog.py::test_settling_records_the_answer_on_the_dialog
tests/test_tui_dialog.py::test_cancelling_is_a_conclusion_not_a_pending_state
tests/test_tui_dialog.py::test_suppression_does_not_make_a_dialog_look_answered
tests/test_tui_dock.py::test_idle_dock_has_no_activity_lines
tests/test_tui_dock.py::test_tool_start_shows_up_in_the_activity_area
tests/test_tui_dock.py::test_concurrent_tools_are_visible_at_the_same_time
tests/test_tui_dock.py::test_same_tool_running_twice_shows_a_count_of_two
tests/test_tui_dock.py::test_activity_summary_aggregates_by_action_not_one_line_per_tool
tests/test_tui_dock.py::test_tool_end_removes_it_from_the_activity_area
tests/test_tui_dock.py::test_status_line_shows_elapsed_and_tokens
tests/test_tui_dock.py::test_status_line_shows_a_spinner_that_moves
tests/test_tui_dock.py::test_permission_mode_lives_in_the_footer_not_the_status_line
tests/test_tui_dock.py::test_status_line_appears_only_when_there_is_something_to_say
tests/test_tui_dock.py::test_status_line_says_how_many_requests_are_waiting
tests/test_tui_dock.py::test_queue_area_shows_pending_steering_messages
tests/test_tui_dock.py::test_agent_end_clears_activity_and_yields_a_summary_to_commit
tests/test_tui_dock.py::test_every_rendered_line_fits_the_terminal
tests/test_tui_dock.py::test_real_session_trajectory_drives_the_dock
tests/test_tui_dock.py::test_dock_has_a_separator_rule_above_the_input
tests/test_tui_dock.py::test_footer_shows_cwd_and_model_and_context
tests/test_tui_dock.py::test_footer_right_aligns_the_model_side
tests/test_tui_dock.py::test_footer_degrades_gracefully_on_a_narrow_terminal
tests/test_tui_dock.py::test_cwd_is_shortened_with_a_tilde_for_home
tests/test_tui_dock.py::test_render_includes_rule_and_footer
tests/test_tui_dock.py::test_activity_summary_carries_a_bullet_and_elapsed
tests/test_tui_dock.py::test_shell_command_detail_is_prefixed_with_a_dollar
tests/test_tui_dock.py::test_multiline_command_keeps_its_own_lines_aligned
tests/test_tui_dock.py::test_long_command_is_capped_with_a_remainder_hint
tests/test_tui_dock.py::test_each_tool_shows_its_own_elapsed_time
tests/test_tui_dock.py::test_activity_lines_still_fit_any_width
tests/test_tui_dock.py::test_summary_line_is_dimmed_like_tool_lines
tests/test_tui_driver.py::test_everything_already_waiting_is_read_into_one_batch
tests/test_tui_driver.py::test_a_partial_sequence_is_not_split_across_batches
tests/test_tui_driver.py::test_the_idle_tick_lets_time_based_work_happen
tests/test_tui_driver.py::test_a_pending_resize_is_redrawn_by_the_poll_loop
tests/test_tui_driver.py::test_no_pending_resize_means_no_extra_redraw
tests/test_tui_editor.py::test_typing_inserts_text
tests/test_tui_editor.py::test_enter_submits_and_clears
tests/test_tui_editor.py::test_backspace_deletes_before_cursor
tests/test_tui_editor.py::test_backspace_deletes_a_whole_wide_char
tests/test_tui_editor.py::test_left_right_and_insert_in_the_middle
tests/test_tui_editor.py::test_home_and_end
tests/test_tui_editor.py::test_delete_removes_under_cursor
tests/test_tui_editor.py::test_ctrl_a_and_ctrl_e
tests/test_tui_editor.py::test_ctrl_u_kills_to_start_ctrl_k_kills_to_end
tests/test_tui_editor.py::test_ctrl_w_kills_previous_word
tests/test_tui_editor.py::test_ctrl_w_at_start_is_a_noop
tests/test_tui_editor.py::test_word_navigation
tests/test_tui_editor.py::test_paste_inserts_at_cursor_without_submitting
tests/test_tui_editor.py::test_cursor_marker_sits_at_the_cursor_and_is_zero_width
tests/test_tui_editor.py::test_render_shows_prompt_and_text
tests/test_tui_editor.py::test_trailing_backslash_continues_instead_of_submitting
tests/test_tui_editor.py::test_continuation_lines_render_with_their_own_prompt
tests/test_tui_editor.py::test_history_up_and_down
tests/test_tui_editor.py::test_history_down_past_the_end_restores_the_draft
tests/test_tui_editor.py::test_history_up_at_the_top_stays_put
tests/test_tui_editor.py::test_submitting_resets_history_position
tests/test_tui_editor.py::test_unknown_key_is_ignored
tests/test_tui_editor.py::test_empty_enter_submits_empty_string
tests/test_tui_editor.py::test_render_width_never_exceeds_terminal[]
tests/test_tui_editor.py::test_render_width_never_exceeds_terminal[a]
tests/test_tui_editor.py::test_render_width_never_exceeds_terminal[\u4e2d\u6587]
tests/test_tui_editor.py::test_render_width_never_exceeds_terminal[a\u4e2db]
tests/test_tui_editor.py::test_render_width_never_exceeds_terminal[\U0001f389]
tests/test_tui_editor.py::test_overwide_line_wraps_instead_of_overflowing
tests/test_tui_editor.py::test_cursor_marker_survives_wrapping_and_lands_on_the_right_row
tests/test_tui_editor.py::test_cursor_at_the_end_of_an_overwide_line_is_still_visible
tests/test_tui_editor.py::test_wide_characters_never_split_across_wrapped_rows
tests/test_tui_editor.py::test_selection_highlight_is_balanced_on_every_wrapped_row
tests/test_tui_editor.py::test_up_moves_within_wrapped_line_before_history
tests/test_tui_editor.py::test_up_at_first_display_row_still_reaches_history
tests/test_tui_editor.py::test_down_moves_between_display_rows_then_does_nothing
tests/test_tui_editor.py::test_vertical_movement_without_render_falls_back_to_history
tests/test_tui_editor_selection.py::test_point_at_maps_row_and_column_to_a_character_index
tests/test_tui_editor_selection.py::test_point_at_across_lines
tests/test_tui_editor_selection.py::test_selecting_and_reading_the_text
tests/test_tui_editor_selection.py::test_selection_normalises_backwards_drags
tests/test_tui_editor_selection.py::test_a_bare_click_selects_nothing
tests/test_tui_editor_selection.py::test_typing_clears_the_selection
tests/test_tui_editor_selection.py::test_the_selection_is_reversed_on_screen
tests/test_tui_editor_selection.py::test_the_cursor_marker_survives_a_selection
tests/test_tui_editor_selection.py::test_selection_spanning_two_lines
tests/test_tui_editor_selection.py::test_dragging_inside_the_input_box_selects_text
tests/test_tui_editor_selection.py::test_releasing_copies_the_input_selection
tests/test_tui_editor_selection.py::test_a_new_press_in_the_input_box_clears_the_old_selection
tests/test_tui_editor_selection.py::test_dragging_in_the_input_box_does_not_touch_the_transcript_selection
tests/test_tui_editor_selection.py::test_typing_over_a_selection_replaces_it
tests/test_tui_editor_selection.py::test_backspace_over_a_selection_deletes_the_selection
tests/test_tui_editor_selection.py::test_delete_over_a_selection_deletes_the_selection
tests/test_tui_editor_selection.py::test_pasting_over_a_selection_replaces_it
tests/test_tui_editor_selection.py::test_an_arrow_key_only_clears_the_selection
tests/test_tui_editor_selection.py::test_a_backwards_drag_in_the_transcript_still_copies
tests/test_tui_editor_selection.py::test_the_copy_notice_sits_above_the_dock_border
tests/test_tui_editor_selection.py::test_point_at_display_maps_wrapped_rows
tests/test_tui_editor_selection.py::test_point_at_display_counts_wide_chars_by_columns
tests/test_tui_editor_selection.py::test_point_at_display_handles_continuation_lines
tests/test_tui_groups.py::test_collapsible_set_follows_cc
tests/test_tui_groups.py::test_summary_counts_by_action_in_past_and_present_tense
tests/test_tui_groups.py::test_unknown_tools_get_a_generic_wording
tests/test_tui_groups.py::test_text_and_edits_break_groups
tests/test_tui_groups.py::test_active_group_shows_present_tense_and_the_current_tool
tests/test_tui_groups.py::test_expanding_a_group_lists_every_call_with_its_full_output_on_a_band
tests/test_tui_groups.py::test_no_color_means_no_escape_sequences
tests/test_tui_groups.py::test_ctrl_o_toggles_the_latest_group_in_alt_screen
tests/test_tui_groups.py::test_a_new_user_line_closes_a_dangling_group
tests/test_tui_groups.py::test_replay_groups_the_same_way
tests/test_tui_groups.py::test_summary_is_english_and_only_the_first_verb_is_capitalised
tests/test_tui_groups.py::test_one_call_uses_the_singular
tests/test_tui_groups.py::test_expanding_scrolls_to_the_bottom
tests/test_tui_groups.py::test_collapsing_goes_back_to_where_you_were
tests/test_tui_groups.py::test_clicking_to_expand_also_jumps_to_the_bottom
tests/test_tui_keys.py::test_printable_ascii_becomes_char_keys
tests/test_tui_keys.py::test_multibyte_char_split_across_reads_is_reassembled
tests/test_tui_keys.py::test_enter_from_both_cr_and_lf
tests/test_tui_keys.py::test_backspace_from_both_del_and_bs
tests/test_tui_keys.py::test_arrow_keys
tests/test_tui_keys.py::test_home_and_end_in_both_common_encodings
tests/test_tui_keys.py::test_delete_key
tests/test_tui_keys.py::test_shift_tab_is_csi_z
tests/test_tui_keys.py::test_control_keys
tests/test_tui_keys.py::test_alt_word_navigation
tests/test_tui_keys.py::test_escape_sequence_split_across_reads
tests/test_tui_keys.py::test_unknown_escape_is_dropped_not_typed
tests/test_tui_keys.py::test_lone_escape_only_becomes_esc_on_flush
tests/test_tui_keys.py::test_bracketed_paste_is_one_key_with_the_whole_payload
tests/test_tui_keys.py::test_newlines_inside_paste_do_not_submit
tests/test_tui_keys.py::test_paste_split_across_reads
tests/test_tui_keys.py::test_incomplete_paste_stays_buffered
tests/test_tui_keys.py::test_a_split_escape_sequence_is_not_settled_as_esc
tests/test_tui_keys.py::test_a_real_esc_still_settles_once_the_keyboard_goes_quiet
tests/test_tui_keys.py::test_two_quick_escapes_produce_two_esc_keys
tests/test_tui_keys.py::test_arrow_keys_arriving_in_one_packet_are_unaffected
tests/test_tui_keys.py::test_a_lost_paste_end_does_not_kill_the_keyboard
tests/test_tui_keys.py::test_a_slow_paste_is_not_cut_in_half
tests/test_tui_keys.py::test_recovery_does_not_fire_for_an_empty_paste_buffer
tests/test_tui_logo.py::test_logo_is_a_block_of_lines_with_uniform_width
tests/test_tui_logo.py::test_logo_fits_a_narrow_terminal_by_falling_back_to_a_wordmark
tests/test_tui_logo.py::test_frames_differ_so_the_shimmer_actually_moves
tests/test_tui_logo.py::test_shimmer_changes_only_color_never_geometry
tests/test_tui_logo.py::test_no_escape_codes_when_color_is_off
tests/test_tui_logo.py::test_frames_wrap_around
tests/test_tui_logo.py::test_banner_includes_a_subtitle_line
tests/test_tui_logo.py::test_narrow_fallback_still_names_the_program
tests/test_tui_logo.py::test_settled_frame_has_no_moving_highlight
tests/test_tui_lost_release.py::test_a_lost_release_is_settled_by_the_next_press
tests/test_tui_lost_release.py::test_a_pause_copies_but_does_not_end_the_drag
tests/test_tui_lost_release.py::test_a_slow_drag_keeps_extending_after_a_pause
tests/test_tui_lost_release.py::test_the_pause_copy_does_not_fire_while_still_moving
tests/test_tui_lost_release.py::test_the_same_selection_is_not_copied_twice
tests/test_tui_lost_release.py::test_dragging_keeps_the_ticker_alive
tests/test_tui_lost_release.py::test_a_normal_release_still_copies_immediately
tests/test_tui_lost_release.py::test_a_lost_release_on_an_empty_selection_copies_nothing
tests/test_tui_lost_release.py::test_a_press_after_a_lost_release_still_cleans_up
tests/test_tui_lost_release.py::test_the_input_box_pause_copies_too
tests/test_tui_lost_release.py::test_a_burst_of_drag_events_does_not_draw_a_frame_each
tests/test_tui_lost_release.py::test_the_last_drag_move_is_still_drawn
tests/test_tui_lost_release.py::test_a_slow_drag_still_draws_every_move
tests/test_tui_lost_release.py::test_keystrokes_are_never_throttled
tests/test_tui_markdown.py::test_the_whole_rendering_verbatim
tests/test_tui_markdown.py::test_a_mixed_width_table_really_aligns
tests/test_tui_markdown.py::test_table_columns_start_at_the_same_column_on_every_row
tests/test_tui_markdown.py::test_a_too_wide_table_is_compressed_not_overflowed
tests/test_tui_markdown.py::test_the_same_table_reflows_when_the_width_changes
tests/test_tui_markdown.py::test_a_pipe_line_without_a_separator_row_is_not_a_table
tests/test_tui_markdown.py::test_inline_rules_do_not_touch_code_block_content
tests/test_tui_markdown.py::test_an_unclosed_fence_still_renders_its_content
tests/test_tui_markdown.py::test_long_code_lines_wrap_instead_of_being_cut
tests/test_tui_markdown.py::test_no_escape_bytes_at_all_when_color_is_off
tests/test_tui_markdown.py::test_color_changes_bytes_but_not_a_single_column
tests/test_tui_markdown.py::test_inline_markers_are_stripped_not_left_as_text
tests/test_tui_markdown.py::test_unmatched_inline_markers_are_left_alone
tests/test_tui_markdown.py::test_headings_are_distinguishable_without_color
tests/test_tui_markdown.py::test_nested_lists_indent_one_level
tests/test_tui_markdown.py::test_ordered_lists_keep_their_own_numbers
tests/test_tui_markdown.py::test_a_long_list_item_wraps_aligned_under_its_text
tests/test_tui_markdown.py::test_blockquote_and_rule
tests/test_tui_markdown.py::test_nothing_is_lost
tests/test_tui_markdown.py::test_closing_punctuation_never_starts_a_line
tests/test_tui_markdown.py::test_avoiding_a_line_start_never_drops_or_duplicates_a_character
tests/test_tui_markdown.py::test_a_single_newline_is_a_hard_break_not_a_soft_one
tests/test_tui_markdown.py::test_plain_text_without_any_markdown_is_untouched
tests/test_tui_markdown.py::test_the_answer_goes_through_markdown_and_reflows_with_width
tests/test_tui_markdown.py::test_the_answer_still_wears_its_dot
tests/test_tui_markdown.py::test_continuation_lines_align_under_the_first
tests/test_tui_markdown.py::test_markdown_can_be_turned_off
tests/test_tui_markdown.py::test_the_setting_defaults_to_on_and_rejects_garbage
tests/test_tui_mouse.py::test_press_is_zero_based
tests/test_tui_mouse.py::test_release_ends_with_lowercase_m
tests/test_tui_mouse.py::test_drag_sets_bit_32
tests/test_tui_mouse.py::test_wheel_up_and_down
tests/test_tui_mouse.py::test_wheel_carries_the_pointer_position
tests/test_tui_mouse.py::test_a_sequence_split_across_reads_is_reassembled
tests/test_tui_mouse.py::test_split_right_after_the_escape
tests/test_tui_mouse.py::test_a_burst_of_wheel_events_all_come_through
tests/test_tui_mouse.py::test_right_and_middle_buttons_are_kept
tests/test_tui_mouse.py::test_unknown_mouse_encodings_are_discarded_not_guessed
tests/test_tui_mouse.py::test_mouse_bytes_never_become_text
tests/test_tui_mouse.py::test_mouse_keys_never_reach_the_editor
tests/test_tui_mouse_lifecycle.py::test_mouse_tracking_is_enabled_after_entering_alt_screen
tests/test_tui_mouse_lifecycle.py::test_we_ask_for_1002_not_1003
tests/test_tui_mouse_lifecycle.py::test_mouse_tracking_is_disabled_before_leaving_alt_screen
tests/test_tui_mouse_lifecycle.py::test_every_enabled_mode_is_disabled_again
tests/test_tui_mouse_lifecycle.py::test_mouse_is_restored_even_when_the_body_raises
tests/test_tui_mouse_lifecycle.py::test_mouse_off_sends_no_mouse_sequences_at_all
tests/test_tui_mouse_lifecycle.py::test_no_alt_screen_means_no_mouse
tests/test_tui_mouse_lifecycle.py::test_mouse_defaults_to_on
tests/test_tui_mouse_lifecycle.py::test_mouse_can_be_turned_off_in_settings
tests/test_tui_mouse_lifecycle.py::test_non_boolean_falls_back_and_warns
tests/test_tui_mouse_merge.py::test_a_burst_of_wheel_events_becomes_one
tests/test_tui_mouse_merge.py::test_wheel_up_and_down_cancel_out
tests/test_tui_mouse_merge.py::test_consecutive_drags_keep_only_the_last
tests/test_tui_mouse_merge.py::test_press_and_release_are_never_merged_or_reordered
tests/test_tui_mouse_merge.py::test_merging_does_not_cross_a_state_transition
tests/test_tui_mouse_merge.py::test_empty_batch
tests/test_tui_mouse_merge.py::test_142_wheel_events_produce_exactly_one_frame
tests/test_tui_mouse_merge.py::test_the_scroll_actually_moved_by_the_summed_delta
tests/test_tui_mouse_merge.py::test_the_scroll_state_machine_is_called_once_not_142_times
tests/test_tui_mouse_realuse.py::test_the_highlight_goes_away_after_the_copy
tests/test_tui_mouse_realuse.py::test_a_bare_click_does_not_leave_a_stale_anchor
tests/test_tui_mouse_realuse.py::test_the_copy_notice_is_right_aligned_above_the_input_row
tests/test_tui_mouse_realuse.py::test_the_copy_notice_disappears_by_itself
tests/test_tui_mouse_realuse.py::test_a_pending_notice_keeps_the_ticker_alive
tests/test_tui_mouse_realuse.py::test_clicking_the_input_row_moves_the_cursor
tests/test_tui_mouse_realuse.py::test_clicking_past_the_end_of_the_text_goes_to_the_end
tests/test_tui_mouse_realuse.py::test_clicking_the_input_row_does_not_start_a_transcript_selection
tests/test_tui_mouse_realuse.py::test_a_real_tool_result_is_expandable
tests/test_tui_mouse_realuse.py::test_clicking_a_real_tool_result_expands_it
tests/test_tui_mouse_realuse.py::test_the_collapsed_line_carries_no_hint_text
tests/test_tui_mouse_realuse.py::test_a_single_line_tool_result_still_expands_to_the_command_and_its_output
tests/test_tui_mouse_realuse.py::test_motion_without_a_button_is_not_a_drag
tests/test_tui_mouse_realuse.py::test_moving_the_mouse_after_release_does_not_extend_the_selection
tests/test_tui_mouse_realuse.py::test_releasing_over_the_input_row_still_finishes_the_drag
tests/test_tui_mouse_realuse.py::test_expanding_keeps_the_command_visible
tests/test_tui_mouse_realuse.py::test_expanded_output_is_indented_under_the_command
tests/test_tui_mouse_realuse.py::test_pasted_multiline_input_has_no_continuation_marker
tests/test_tui_mouse_realuse.py::test_the_collapsed_hint_follows_ccs_shape
tests/test_tui_mouse_wheel.py::test_wheel_up_scrolls_the_transcript
tests/test_tui_mouse_wheel.py::test_wheel_down_scrolls_back
tests/test_tui_mouse_wheel.py::test_wheel_up_turns_off_following
tests/test_tui_mouse_wheel.py::test_scrolling_back_to_the_bottom_restores_following
tests/test_tui_mouse_wheel.py::test_wheel_over_the_dock_still_scrolls_the_transcript
tests/test_tui_mouse_wheel.py::test_wheel_does_nothing_in_dock_mode_and_does_not_crash
tests/test_tui_mouse_wheel.py::test_wheel_line_count_is_documented_as_a_guess
tests/test_tui_record.py::test_recording_is_off_unless_asked
tests/test_tui_record.py::test_wrap_passes_through_unchanged
tests/test_tui_record.py::test_recording_carries_the_terminal_size
tests/test_tui_record.py::test_a_broken_recording_file_never_breaks_the_session
tests/test_tui_record.py::test_replay_reconstructs_the_screen
tests/test_tui_record.py::test_replay_keeps_colour_and_background
tests/test_tui_record.py::test_replay_is_lenient_about_unknown_sequences
tests/test_tui_record.py::test_png_is_produced_and_non_trivial
tests/test_tui_record.py::test_width_changes_are_detected_and_only_the_last_segment_is_replayed
tests/test_tui_renderer.py::test_first_draw_puts_every_line_on_screen
tests/test_tui_renderer.py::test_cursor_ends_on_the_last_dock_line
tests/test_tui_renderer.py::test_every_write_is_wrapped_in_synchronized_output
tests/test_tui_renderer.py::test_redraw_same_height_replaces_content
tests/test_tui_renderer.py::test_redraw_never_clears_screen_or_scrollback
tests/test_tui_renderer.py::test_shrinking_dock_leaves_no_residue
tests/test_tui_renderer.py::test_shrinking_dock_leaves_cursor_on_new_last_line
tests/test_tui_renderer.py::test_growing_dock_keeps_content_above_it
tests/test_tui_renderer.py::test_redraw_is_whole_dock_not_a_diff
tests/test_tui_renderer.py::test_commit_puts_lines_above_the_dock
tests/test_tui_renderer.py::test_commit_does_not_interleave_with_dock
tests/test_tui_renderer.py::test_redraw_after_commit_does_not_cover_committed_lines
tests/test_tui_renderer.py::test_commit_without_root_leaves_no_dock
tests/test_tui_renderer.py::test_commit_scrolls_old_content_into_scrollback
tests/test_tui_renderer.py::test_clear_removes_the_dock_entirely
tests/test_tui_renderer.py::test_marker_is_stripped_and_never_reaches_the_screen
tests/test_tui_renderer.py::test_hardware_cursor_lands_on_the_marker_column_by_display_width
tests/test_tui_renderer.py::test_hardware_cursor_lands_on_the_right_row_when_the_dock_has_more_below
tests/test_tui_renderer.py::test_next_redraw_uses_the_cursor_row_as_its_base_not_the_last_line
tests/test_tui_renderer.py::test_dock_taller_than_terminal_is_clamped_to_the_tail
tests/test_tui_renderer.py::test_dock_within_terminal_height_is_untouched
tests/test_tui_sanitize.py::test_tabs_are_expanded_to_real_tab_stops
tests/test_tui_sanitize.py::test_tabs_are_expanded_per_line_not_across_the_whole_blob
tests/test_tui_sanitize.py::test_cursor_movement_and_erase_sequences_are_stripped
tests/test_tui_sanitize.py::test_osc_sequences_are_stripped
tests/test_tui_sanitize.py::test_colour_is_stripped_too_and_that_is_a_choice
tests/test_tui_sanitize.py::test_newlines_survive_and_other_c0_does_not
tests/test_tui_sanitize.py::test_plain_text_is_returned_unchanged
tests/test_tui_sanitize.py::test_the_simulator_and_a_real_terminal_agree_after_sanitising
tests/test_tui_sanitize.py::test_the_model_still_receives_the_raw_output
tests/test_tui_sanitize.py::test_tool_output_is_sanitised_before_it_reaches_the_transcript
tests/test_tui_screen.py::test_plain_text_and_newline
tests/test_tui_screen.py::test_carriage_return_overwrites_in_place
tests/test_tui_screen.py::test_clear_line_erases_whole_row
tests/test_tui_screen.py::test_cursor_up_and_down_move_between_rows
tests/test_tui_screen.py::test_wide_chars_take_two_columns
tests/test_tui_screen.py::test_newline_at_bottom_scrolls_into_scrollback
tests/test_tui_screen.py::test_synchronized_output_markers_are_transparent
tests/test_tui_screen.py::test_absolute_column_is_one_indexed
tests/test_tui_screen.py::test_unknown_escape_raises_instead_of_being_ignored
tests/test_tui_screen.py::test_alt_screen_starts_empty_and_hides_main
tests/test_tui_screen.py::test_leaving_alt_screen_restores_main_cell_for_cell
tests/test_tui_screen.py::test_reentering_alt_screen_clears_it_and_homes_cursor
tests/test_tui_screen.py::test_alt_screen_saves_and_restores_the_cursor
tests/test_tui_screen.py::test_alt_screen_scrolling_does_not_pollute_main_scrollback
tests/test_tui_screen.py::test_leaving_alt_when_not_in_alt_is_a_no_op
tests/test_tui_screen.py::test_cursor_position_is_one_indexed_row_and_column
tests/test_tui_screen.py::test_cursor_position_defaults_to_home_and_clamps
tests/test_tui_screen.py::test_erase_display_modes
tests/test_tui_screen.py::test_autowrap_off_truncates_at_the_right_edge
tests/test_tui_screen.py::test_wide_char_at_the_edge_with_autowrap_off_is_dropped_not_split
tests/test_tui_screen.py::test_cursor_visibility_and_unrelated_private_modes_stay_no_ops
tests/test_tui_scroll.py::test_starts_following_the_end
tests/test_tui_scroll.py::test_new_content_sticks_to_the_bottom_while_following
tests/test_tui_scroll.py::test_scrolling_up_turns_following_off
tests/test_tui_scroll.py::test_new_content_does_not_move_the_viewport_after_manual_scroll
tests/test_tui_scroll.py::test_scrolling_back_to_the_bottom_reenables_following
tests/test_tui_scroll.py::test_to_end_reenables_following_and_clears_unseen
tests/test_tui_scroll.py::test_to_start_goes_to_the_top
tests/test_tui_scroll.py::test_scroll_by_clamps_at_both_ends_and_returns_unused_delta
tests/test_tui_scroll.py::test_page_up_and_down_keep_an_overlap
tests/test_tui_scroll.py::test_page_up_still_moves_when_the_viewport_is_tiny
tests/test_tui_scroll.py::test_viewport_growth_keeps_following_at_the_bottom
tests/test_tui_scroll.py::test_viewport_change_preserves_position_when_not_following
tests/test_tui_scroll.py::test_content_shorter_than_viewport_stays_pinned_at_zero
tests/test_tui_scroll.py::test_unseen_only_while_scrolled_away
tests/test_tui_selection.py::test_press_alone_does_not_select_anything
tests/test_tui_selection.py::test_the_first_move_at_the_anchor_cell_does_not_count
tests/test_tui_selection.py::test_a_real_drag_creates_a_selection
tests/test_tui_selection.py::test_dragging_backwards_normalises
tests/test_tui_selection.py::test_release_keeps_the_selection
tests/test_tui_selection.py::test_clear_drops_it
tests/test_tui_selection.py::test_a_new_press_starts_over
tests/test_tui_selection.py::test_text_of_a_single_line_range
tests/test_tui_selection.py::test_text_across_lines_joins_with_newlines
tests/test_tui_selection.py::test_text_strips_escape_sequences
tests/test_tui_selection.py::test_text_slices_by_display_column_not_character_index
tests/test_tui_selection.py::test_a_column_landing_inside_a_wide_char_keeps_the_whole_char
tests/test_tui_selection.py::test_trailing_whitespace_is_stripped_per_line
tests/test_tui_selection.py::test_empty_selection_is_an_empty_string_not_a_space
tests/test_tui_selection.py::test_content_far_outside_the_viewport_is_still_selectable
tests/test_tui_selection.py::test_out_of_range_rows_clamp_instead_of_raising
tests/test_tui_selection.py::test_resize_clears_the_selection
tests/test_tui_selection_render.py::test_no_selection_leaves_the_frame_byte_identical
tests/test_tui_selection_render.py::test_selected_range_is_reversed
tests/test_tui_selection_render.py::test_selection_spans_multiple_lines
tests/test_tui_selection_render.py::test_columns_are_display_columns_not_character_indexes
tests/test_tui_selection_render.py::test_highlight_is_applied_after_truncation
tests/test_tui_selection_render.py::test_the_dock_is_never_highlighted
tests/test_tui_selection_render.py::test_a_colour_reset_inside_the_selection_does_not_kill_the_reverse
tests/test_tui_selection_render.py::test_scrolling_moves_the_highlight_with_the_content
tests/test_tui_terminal.py::test_tui_is_unavailable_when_stdout_is_not_a_tty
tests/test_tui_terminal.py::test_env_var_is_an_explicit_escape_hatch
tests/test_tui_terminal.py::test_same_size_resize_event_is_dropped
tests/test_tui_terminal.py::test_changed_size_defers_the_redraw_to_the_main_loop
tests/test_tui_terminal.py::test_sigwinch_handler_is_installed_on_start
tests/test_tui_terminal.py::test_start_enters_raw_mode_and_enables_bracketed_paste
tests/test_tui_terminal.py::test_stop_restores_everything_unconditionally
tests/test_tui_terminal.py::test_stop_still_restores_raw_mode_when_writing_fails
tests/test_tui_terminal.py::test_context_manager_restores_on_exception
tests/test_tui_terminal.py::test_double_stop_is_harmless
tests/test_tui_terminal.py::test_non_main_thread_warns_instead_of_failing_silently
tests/test_tui_terminal.py::test_main_thread_produces_no_warning
tests/test_tui_terminal.py::test_the_signal_handler_does_not_draw
tests/test_tui_terminal.py::test_taking_the_pending_flag_clears_it
tests/test_tui_terminal.py::test_a_same_size_event_still_sets_nothing
tests/test_tui_theme.py::test_no_glyph_is_emoji_presentation[\u25cf]
tests/test_tui_theme.py::test_no_glyph_is_emoji_presentation[\u2733]
tests/test_tui_theme.py::test_no_glyph_is_emoji_presentation[\u29d7]
tests/test_tui_theme.py::test_no_glyph_is_emoji_presentation[\u2500]
tests/test_tui_theme.py::test_no_glyph_is_emoji_presentation[\u203a]
tests/test_tui_theme.py::test_no_glyph_is_emoji_presentation[\u2026]
tests/test_tui_theme.py::test_no_glyph_is_emoji_presentation[\u2514]
tests/test_tui_theme.py::test_no_glyph_is_emoji_presentation[\u276f]
tests/test_tui_theme.py::test_no_glyph_is_emoji_presentation[\u273b]
tests/test_tui_theme.py::test_every_glyph_is_exactly_one_column[\u25cf]
tests/test_tui_theme.py::test_every_glyph_is_exactly_one_column[\u2733]
tests/test_tui_theme.py::test_every_glyph_is_exactly_one_column[\u29d7]
tests/test_tui_theme.py::test_every_glyph_is_exactly_one_column[\u2500]
tests/test_tui_theme.py::test_every_glyph_is_exactly_one_column[\u203a]
tests/test_tui_theme.py::test_every_glyph_is_exactly_one_column[\u2026]
tests/test_tui_theme.py::test_every_glyph_is_exactly_one_column[\u2514]
tests/test_tui_theme.py::test_every_glyph_is_exactly_one_column[\u276f]
tests/test_tui_theme.py::test_every_glyph_is_exactly_one_column[\u273b]
tests/test_tui_theme.py::test_paint_adds_color_when_enabled
tests/test_tui_theme.py::test_paint_is_a_noop_when_disabled
tests/test_tui_theme.py::test_use_color_respects_no_color_env
tests/test_tui_transcript.py::test_entry_renders_lines_for_a_width
tests/test_tui_transcript.py::test_text_entry_wraps_by_display_width
tests/test_tui_transcript.py::test_text_entry_counts_chinese_as_two_columns
tests/test_tui_transcript.py::test_same_width_is_served_from_cache
tests/test_tui_transcript.py::test_changing_width_must_recompute
tests/test_tui_transcript.py::test_total_lines_follows_width
tests/test_tui_transcript.py::test_slice_takes_a_viewport_across_entry_boundaries
tests/test_tui_transcript.py::test_slice_clamps_instead_of_raising
tests/test_tui_transcript.py::test_empty_transcript_is_empty_not_an_error
tests/test_tui_transcript.py::test_clear_drops_everything
tests/test_tui_transcript.py::test_entry_render_returns_a_copy_callers_cannot_corrupt_the_cache
tests/test_tui_transcript.py::test_render_width_zero_or_negative_does_not_hang
tests/test_tui_transcript.py::test_entry_is_the_component_contract_shape
tests/test_viz_collect.py::test_tools_are_introspected_from_registry
tests/test_viz_collect.py::test_pipeline_nodes_and_edges_reference_each_other
tests/test_viz_collect.py::test_structure_is_json_serializable_and_has_model
tests/test_viz_collect.py::test_parse_status_table_normal
tests/test_viz_collect.py::test_parse_status_table_malformed_returns_empty
tests/test_viz_collect.py::test_build_structure_reads_real_status
tests/test_viz_collect.py::test_real_status_md_parses_to_nonempty_stages_with_expected_keys
tests/test_viz_collect.py::test_real_status_md_covers_all_pipeline_stage_keys
tests/test_viz_collect.py::test_every_tool_reports_where_its_code_lives
tests/test_viz_collect.py::test_pipeline_nodes_know_their_source_file
tests/test_viz_collect.py::test_event_source_map_covers_exactly_the_event_types
tests/test_viz_collect.py::test_stage_keys_are_clean_identifiers
tests/test_viz_flow.py::test_real_session_groups_into_one_turn
tests/test_viz_flow.py::test_real_session_pairs_both_parallel_tool_calls
tests/test_viz_flow.py::test_real_session_reports_tokens_and_cache_hit
tests/test_viz_flow.py::test_llm_step_carries_the_assistant_text_and_its_tool_calls
tests/test_viz_flow.py::test_steps_are_in_wall_clock_order
tests/test_viz_flow.py::test_a_turn_that_never_ended_is_kept_and_flagged
tests/test_viz_flow.py::test_multiple_turns_split_on_each_user_message
tests/test_viz_flow.py::test_broken_lines_are_skipped_and_counted
tests/test_viz_flow.py::test_missing_event_file_still_yields_turns
tests/test_viz_flow.py::test_harness_events_land_inside_the_turn_they_belong_to
tests/test_viz_flow.py::test_cleared_marks_the_start_of_a_new_conversation
tests/test_viz_flow.py::test_empty_or_missing_file_is_not_an_error
tests/test_viz_flow.py::test_a_shell_only_turn_is_not_unfinished
tests/test_viz_flow.py::test_an_interrupted_turn_is_still_unfinished
tests/test_viz_flow.py::test_tool_lifecycle_events_merge_into_the_tool_step
tests/test_viz_flow.py::test_assistant_message_event_is_not_shown_twice
tests/test_viz_flow.py::test_tool_duration_falls_back_when_there_is_no_event_stream
tests/test_viz_flow.py::test_event_payload_never_collides_with_the_step_discriminator
tests/test_viz_flow.py::test_turn_totals_only_sum_what_is_meaningful_to_sum
tests/test_viz_flow.py::test_miss_falls_back_when_the_provider_omits_it
tests/test_viz_flow.py::test_v1_session_files_are_normalized_before_grouping
tests/test_viz_server.py::test_index_served
tests/test_viz_server.py::test_api_structure_returns_collected_json
tests/test_viz_server.py::test_index_is_real_page_not_placeholder
tests/test_viz_server.py::test_unknown_path_404
tests/test_viz_server.py::test_collect_returns_500_on_subprocess_error
tests/test_viz_server.py::test_collect_returns_500_when_stdout_is_not_valid_json
tests/test_viz_server.py::test_sessions_lists_newest_first
tests/test_viz_server.py::test_sessions_reports_which_ones_have_an_event_stream
tests/test_viz_server.py::test_flow_returns_grouped_turns
tests/test_viz_server.py::test_flow_defaults_to_the_newest_session
tests/test_viz_server.py::test_events_first_poll_returns_only_the_cursor
tests/test_viz_server.py::test_events_returns_only_what_arrived_after_the_cursor
tests/test_viz_server.py::test_events_survives_a_truncated_cursor
tests/test_viz_server.py::test_unknown_session_is_a_clean_error_not_a_traceback
tests/test_viz_server.py::test_session_name_cannot_escape_the_sessions_directory
tests/test_viz_server.py::test_reveal_refuses_paths_outside_the_repo
tests/test_viz_server.py::test_reveal_opens_a_repo_file_in_the_editor
tests/test_viz_server.py::test_events_tells_the_client_which_session_it_resolved
tests/test_viz_server.py::test_flow_also_reports_which_session_it_resolved
tests/test_viz_server.py::test_page_has_the_timeline_and_session_picker
tests/test_viz_server.py::test_every_api_the_page_calls_actually_has_a_route
tests/test_viz_server.py::test_animation_map_only_references_real_pipeline_nodes
tests/test_viz_server.py::test_event_types_in_the_animation_map_are_real_events
tests/test_viz_server.py::test_sessions_lists_every_project_not_just_the_cwd_one
tests/test_viz_server.py::test_a_session_from_another_project_can_be_opened
tests/test_viz_server.py::test_latest_across_projects_wins
tests/test_viz_server.py::test_same_name_in_two_projects_is_disambiguated
tests/test_viz_server.py::test_a_session_id_still_cannot_escape_the_projects_root
tests/test_viz_server.py::test_reveal_falls_back_to_the_editor_url_scheme
tests/test_viz_server.py::test_reveal_reports_when_there_is_no_editor_at_all

1965/1973 tests collected (8 deselected) in 1.77s
```

## 强杀注入插件与调用

仅该次显式 -p 加载，无仓库源码变更。

```python
import os
import signal
import subprocess
import pytest

@pytest.fixture(autouse=True)
def inject_worker_group_only(monkeypatch):
    import pai.evals.task_runner as runner
    def old_stop(proc):
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=1)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(proc.pid,signal.SIGKILL)
                except ProcessLookupError:
                    pass
                proc.wait()
        return True
    monkeypatch.setattr(runner,'_stop',old_stop)
```

命令：`PYTHONPATH=/private/tmp:<repo>/src python3 -B -m pytest tests/test_task_runner.py -k forced_stop -p pai56_stop_fault -p no:cacheprovider`。

## full-final（标准 ./test.sh）

```text
........................................................................ [  3%]
........................................................................ [  7%]
........................................................................ [ 10%]
........................................................................ [ 14%]
........................................................................ [ 18%]
........................................................................ [ 21%]
........................................................................ [ 25%]
........................................................................ [ 29%]
........................................................................ [ 32%]
........................................................................ [ 36%]
........................................................................ [ 40%]
........................................................................ [ 43%]
........................................................................ [ 47%]
........................................................................ [ 51%]
........................................................................ [ 54%]
........................................................................ [ 58%]
........................................................................ [ 62%]
........................................................................ [ 65%]
........................................................................ [ 69%]
........................................................................ [ 73%]
........................................................................ [ 76%]
........................................................................ [ 80%]
........................................................................ [ 84%]
........................................................................ [ 87%]
........................................................................ [ 91%]
........................................................................ [ 95%]
........................................................................ [ 98%]
.....................                                                    [100%]
1965 passed, 8 deselected in 205.72s (0:03:25)
```

## eval-default

```text
.                                                                        [100%]
1 passed, 5 deselected in 2.14s
```

## eval-tasks

```text
.                                                                        [100%]
1 passed, 1 deselected in 2.13s
```

## final-doc-viz

```text
.....................s...................                                [100%]
40 passed, 1 skipped in 0.71s
```

## typed-tests

```text
......................................                                   [100%]
38 passed in 20.31s
```
