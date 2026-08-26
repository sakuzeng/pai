"""工具输出的共用上限与截断（feature 42）。

`MAX_OUTPUT_CHARS` 此前在 `fs.py` 与 `shell.py` 各有一份拷贝，`recall.py` 与
`rules.py` 的注释还各自引用着「read_file 的那个 4000」——同一个数四处引用、
两处定义。本轮要加第三、第四个工具，与其把拷贝变成四份，不如先把家安在这里，
两个老模块改成从这里导入并原样再导出（`from ... import MAX_OUTPUT_CHARS` 的
既有写法一个字不用改）。

两种截断，用在不同地方，区别是**判决在哪一头**：

- 头部截断（`fs.read_file` / `search_files` 自己做）：文件与搜索结果从上往下读，
  前面那段就是要的东西。
- 保头保尾（`head_and_tail`）：跑测试与 `git log` 这类，结论在**尾部**。
  pytest 那行 `1534 passed` 永远是最后几行之一，头部截断恰好把它扔掉——
  于是模型拿到一堆用例名，却不知道到底过没过。这不是「输出不好看」，
  是把唯一有判决力的那行删了。
"""

MAX_OUTPUT_CHARS = 4000

# 保头保尾时头尾各留多少。三七开而不是对半：头部只要够看清「跑的是什么、
# 从哪开始崩」，尾部要装下失败清单 + 汇总行，后者长得多。
HEAD_SHARE = 0.3


def head_and_tail(text: str, limit: int = MAX_OUTPUT_CHARS) -> str:
    """超长输出保住开头与结尾，中间挖掉并如实说挖了多少。

    挖掉的量要报出来（同 read_file / bash 那条规矩：截断了必须说）——
    只留省略号的话，模型无从判断自己错过的是 3 行还是 3 万行。
    """
    if len(text) <= limit:
        return text
    head_len = int(limit * HEAD_SHARE)
    tail_len = limit - head_len
    dropped = len(text) - head_len - tail_len
    return (text[:head_len]
            + f"\n\n[... 中间截掉 {dropped} 字符（共 {len(text)} 字符）；"
              f"开头与结尾都保留了，结论通常在结尾 ...]\n\n"
            + text[-tail_len:])
