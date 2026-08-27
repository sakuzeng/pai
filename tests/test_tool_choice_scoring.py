"""工具选择评测的纯逻辑（feature 47）——离线那一半。

这里能验的：计分对不对、案例集有没有写坏、对照组提示词是不是冻结的。
这里**验不了**的：模型会不会选对——那要真 API，在 `evals/test_tool_choice.py`
（`./eval.sh --llm`）。这条分界线是 feature 45 的教训：
离线断言证明不了模型行为，别拿这一半冒充那一半。
"""
import pytest

from pai.evals.tool_choice import Case, Outcome, first_tool_name, run_cases, score


def _case(expect="run_tests", negative=False):
    return Case(intent="跑测试", expect=expect, why="测试用", negative=negative)


def test_score_counts_hits_and_misses():
    outcomes = [Outcome(_case(), ("run_tests",)), Outcome(_case(), ("bash",)),
                Outcome(_case(), (None,))]
    s = score(outcomes)
    assert (s.hits, s.total) == (1.0, 3)
    assert len(s.misses) == 2
    assert s.rate == pytest.approx(1 / 3)


def test_a_partial_hit_is_a_fraction_not_a_boolean():
    """provider 在 temp=0 下也会抖（实测同 case 6 次采样 5:1）。

    取多数会把 3/5 与 5/5 抹成同一个数——而那正是改提示词时要看的东西。
    这条钉的就是「不许退化成布尔」。
    """
    o = Outcome(_case(), ("run_tests", "run_tests", "run_tests", "bash", "list_dir"))
    assert o.hit_rate == pytest.approx(0.6)
    s = score([o])
    assert s.hits == pytest.approx(0.6)
    assert "60%" in s.render("有引导")
    assert "bash" in s.render("有引导") and "list_dir" in s.render("有引导"), \
        "没说清它错的时候选了什么，就改不动提示词"


def test_negatives_are_counted_separately_but_weighted_the_same():
    """负例只用于分组报告，**不参与加权**。

    加权的话「一律不选 bash」这种退化策略就能靠调权重变得好看，
    而那正是这个指标最容易被玩坏的方式。
    """
    outcomes = [Outcome(_case(), ("run_tests",)),
                Outcome(_case("bash", negative=True), ("bash",)),
                Outcome(_case("bash", negative=True), ("search_files",))]
    s = score(outcomes)
    assert (s.negative_hits, s.negative_total) == (1.0, 2)
    assert (s.hits, s.total) == (2.0, 3), "负例被加权了"


def test_a_miss_records_what_was_picked_instead():
    """只知道「没命中」没用，要知道它选了什么才改得动提示词。"""
    s = score([Outcome(_case(), ("bash",))])
    assert s.misses == (("跑测试", "run_tests", 0.0, "bash"),)
    assert "bash" in s.render("有引导")


def test_no_tool_call_is_a_result_not_a_crash():
    """模型直接说话不调工具，本身是一个要记录的结果。"""
    s = score([Outcome(_case(), (None,))])
    assert "没调工具" in s.render("有引导")


def test_first_tool_name_survives_junk():
    """真 provider 的返回结构可能缺字段；评测不该因此整轮炸掉。"""
    class _Empty:
        choices = []

    class _NoCalls:
        class _C:
            class message:
                tool_calls = None
        choices = [_C()]

    assert first_tool_name(_Empty()) is None
    assert first_tool_name(_NoCalls()) is None
    assert first_tool_name(None) is None


def test_run_cases_uses_the_injected_asker():
    cases = (_case(), _case("search_files"))
    out = run_cases(cases, ask=lambda c: c.expect)
    assert [o.hit_rate for o in out] == [1.0, 1.0]


def test_samples_controls_how_many_times_each_case_is_asked():
    """采样次数是这套方法在首轮被证伪之后补上的那一半，得有守卫。"""
    calls = []
    out = run_cases((_case(),), ask=lambda c: calls.append(c) or "run_tests", samples=5)
    assert len(calls) == 5 and len(out[0].picks) == 5


# ---- 案例集本身 ----


def test_the_case_set_is_the_shape_the_archive_pre_registered():
    """预先注册里写死了 18 条、其中 4 条 bash 该赢。改这张表就是改测量本身。"""
    from evals.cases import CASES

    assert len(CASES) == 18
    assert sum(1 for c in CASES if c.negative) == 4


def test_every_case_expects_a_real_tool_and_explains_itself():
    from evals.cases import CASES
    from pai.core.tools import get_tools

    names = set(get_tools())
    for c in CASES:
        assert c.expect in names, f"{c.intent} 期望了一个不存在的工具 {c.expect}"
        assert c.why, f"{c.intent} 没写 why——跑挂时没法一眼看出它想验什么"
        assert c.negative == (c.expect == "bash"), \
            f"{c.intent} 的 negative 标记与期望工具对不上"


def test_the_baseline_prompt_is_frozen_text_not_regenerated():
    """对照组必须是**冻结的文本**，不能跟着当前代码走。

    跟着走的话它会随每次改动漂，而漂了之后前后两次的数字就不可比——
    对照组的全部价值就在于它不动。
    """
    from evals.cases import baseline_prompt
    from pai.core.loop import build_system_prompt
    from pai.core.tools import get_tools

    tools = get_tools()
    base, current = baseline_prompt(tools), build_system_prompt(tools)
    assert "找代码用 search_files" not in base, "对照组里混进了 feature 46 的引导"
    assert "改代码时优先用 edit_file" in base, "对照组丢了它本来就有的那一句"
    assert base != current
