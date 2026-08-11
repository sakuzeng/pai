

# --- 权限询问的可读性（用户 2026-08-11 指出 bash 命令显示成了 Python repr）----

def test_bash_permission_question_shows_the_command_verbatim():
    """`repr()` 会把引号转义成 `\\'`，一条正常的 shell 命令看起来像乱码。

    用户截图里的原文：
    `bash(command='ls -la && echo "---" && find . -type f -not -path \\'./.git/*\\'')`
    要看的是**命令本身**，不是 Python 的字符串字面量。
    """
    from pai.core.gate import make_before_tool_call
    from pai.core.permissions import RuleSet

    seen = {}

    def asker(question, options):
        seen["q"] = question
        return options[1]

    gate = make_before_tool_call(RuleSet.from_lists(ask=["bash(*)"]), asker=asker)
    command = "ls -la && find . -not -path './.git/*' | head -50"
    gate("bash", {"command": command})

    assert command in seen["q"]                 # 原样，不转义
    assert "\\\\'" not in seen["q"]
    assert "command=" not in seen["q"]          # 不摆 Python 参数名


def test_long_argument_values_are_truncated_not_dumped():
    """`write_file` 的 content 可能是几千字符——整段倒进问题里，用户看不到自己在批什么。"""
    from pai.core.gate import make_before_tool_call
    from pai.core.permissions import RuleSet

    seen = {}
    gate = make_before_tool_call(
        RuleSet.from_lists(ask=["write_file(*)"]),
        asker=lambda q, o: seen.setdefault("q", q) and o[1] or o[1])
    gate("write_file", {"path": "a.py", "content": "x" * 5000})
    assert len(seen["q"]) < 500
    assert "a.py" in seen["q"]                  # 关键参数不能被截没
