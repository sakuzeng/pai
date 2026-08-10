# 进程组与中断：怎么真的杀掉一条跑飞的命令

- 来源：无单一外部原文。POSIX 进程组语义 + Python `subprocess` 行为 +
  2026-08-10 在 pai 上的实测（features/05 task 4 的注入反证）
- 精读日期：2026-08-10
- pai 锚点：`src/pai/core/tools/shell.py`、`src/pai/core/interrupt.py`

任何要执行 shell 命令的 agent 都会撞上这一套。换个语言、换个项目，结论一样成立。

## 一、`proc.kill()` 杀的是 shell，不是它生的孩子

```python
proc = subprocess.Popen("sleep 30 & echo $!; sleep 30", shell=True, ...)
proc.kill()          # 只杀了那个 shell
```

`&` 派生的后台进程**不是** `proc` 的直接子进程视角里能被一起收掉的东西——
shell 死了，它变成孤儿被 init 收养，**继续跑**。对 agent 来说就是：
用户按了中断、界面说「已中断」，而机器上那条命令还在烧 CPU。

## 二、比「孙进程还活着」更早暴露的症状：输出全丢

实测中最反直觉的一点（注入反证时撞出来的）：把正确实现换成 `proc.kill()` 之后，
测试**不是**在「孙进程还活着」那条断言上红的，而是更靠前的「连命令已经打印的内容都没拿到」。

原因是管道：后台那个 `sleep` **继承了 stdout 的写端**。只要它还活着，管道就不会 EOF，
`proc.communicate()` 收不到流结束，于是超时抛异常、已产出的输出一并丢掉。

**所以「杀不干净」的第一个可见后果不是资源泄漏，是数据丢失**——
而丢掉部分输出会让模型看到「零输出」，进而误判重试（pai 在超时分支上早就吃过一次，R3#3）。

## 三、正确形态：起独立进程组 + 整组杀 + 杀完再收

```python
proc = subprocess.Popen(cmd, shell=True, stdout=PIPE, stderr=PIPE,
                        text=True, start_new_session=True)   # ← 独立会话/进程组
...
os.killpg(os.getpgid(proc.pid), signal.SIGKILL)              # ← 整组
out, err = proc.communicate(timeout=5)                       # ← 杀完才收得到 EOF
```

三个细节：

1. **`start_new_session=True`**（等价于 `setsid`）让子进程成为新会话的首进程，
   它派生的一切都在同一个进程组里，`killpg` 才收得干净。
2. **顺序不能反**：先杀后收。写端没关闭就 `communicate()` 会一直等。
3. **代价**：独立会话意味着这个进程组**不再接收终端的 SIGINT**——用户按 Ctrl+C
   信号送不到它。所以中断必须由程序自己发（见下一节）。这是个真实的取舍，不是免费午餐。

`killpg` 可能抛 `ProcessLookupError`（组已经没了）或 `PermissionError`，
兜底回退到 `proc.kill()`——收不了组至少收子进程。

## 四、中断信号：轮询标志，而不是让信号直接抛异常

既然进程组收不到终端信号，中断就得程序自己传。两种做法：

| 做法 | 问题 |
|---|---|
| SIGINT handler 里抛 `KeyboardInterrupt` | 异常从**任意**一行弹出，已完成的工作连同栈一起丢；且线程里根本抛不出去 |
| handler 只**置标志**，执行侧轮询 | 中断点可控，收尾有序 |

pai 选后者：`InterruptFlag` 包 `threading.Event`（未来有读输入的线程时不用重写），
等待循环用 `communicate(timeout=0.1)` 轮询，每轮查一次标志。
0.1 秒是响应粒度——再小只是空转，再大用户会觉得「按了没反应」。

**可迁移的判断**：当「异常情况」需要**留下痕迹**（有序收尾、配对回填、审计），
它就不该走异常路径。异常擅长「放弃并向上传播」，不擅长「有序收尾」。

## 五、怎么验证「真的杀干净了」

行为测试比 mock 可靠得多：

```
命令：sleep 30 & echo PID=$!; sleep 30
中断后：从输出里抠出 PID → os.kill(pid, 0) 应抛 ProcessLookupError
```

`os.kill(pid, 0)` 是标准的「探活不发信号」写法。测试末尾别忘了兜底
`os.kill(pid, SIGKILL)`——断言失败时也不该把跑飞的进程留给这台机器。

**注入反证**（把 `killpg` 换回 `proc.kill()` 看测试是否变红）在这里额外有价值：
它告诉你**错误实现的真实后果**（连输出都丢），而那比我预想的更糟。
