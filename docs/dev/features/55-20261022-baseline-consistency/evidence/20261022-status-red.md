# 2026-10-22 · 交付总览状态校验红灯

展示副本仅去除行尾空白，逐字原件见 [raw-test-output.json](raw-test-output.json)。

```text
.............F.......s...................                                [100%]
=================================== FAILURES ===================================
__________________ test_feature_index_status_matches_archives __________________

    def test_feature_index_status_matches_archives() -> None:
        text = (FEATURES / "README.md").read_text(encoding="utf-8")
        entries = re.findall(
            r"^\| \[[^\]]+\]\((\d{2}-\d{8}-[^/]+)/README\.md\) \| ([^|]+)\|", text, re.M)
        mismatches: list[tuple[str, str, str]] = []
        for name, indexed in entries:
            archive = (FEATURES / name / "README.md").read_text(encoding="utf-8")
            actual = re.search(r"^状态：[^\S\n]*([^\s（]+)", archive, re.M)
            assert actual is not None, f"{name} 缺档案状态"
            if indexed.strip() != actual.group(1):
                mismatches.append((name, indexed.strip(), actual.group(1)))
>       assert not mismatches, f"交付总览状态与档案头部不一致：{mismatches}"
E       AssertionError: 交付总览状态与档案头部不一致：[('05-20260810-repl', '已交付', '已验收'), ('16-20260811-mouse-and-selection', '实现中', '已交付')]
E       assert not [('05-20260810-repl', '已交付', '已验收'), ('16-20260811-mouse-and-selection', '实现中', '已交付')]

tests/test_docs_consistency.py:143: AssertionError
=========================== short test summary info ============================
FAILED tests/test_docs_consistency.py::test_feature_index_status_matches_archives
1 failed, 39 passed, 1 skipped in 0.76s
```
