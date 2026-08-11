# 13-alt-screen · 开发日志

<!-- 一步一条，不攒着最后补。全局 devlog 只记里程碑一行 + 指到这里。 -->

## 2026-08-11 立项（未动工）

**目标**：把「工具结果能点」「transcript 能滚」「像新开一个窗口」三件事单独立项。

**为什么现在立**：用户在真跑 feature 12 时连问三条，追下去发现它们**底下是同一个约束**——
谁拥有屏幕。方案 A（12 交付的）只接管底部 dock，进 scrollback 的内容 pai 再也够不着，
所以「点击」不是没做而是**做不到**。要做就得进 alt-screen，那会推翻 roadmap 阶段 2
已拍板的设计原则 2，属「改变那次交付的结果」→ 按 features/README 规矩 7 新建档案。

**用户拍板（三选一）**：甲=键盘展开 / 乙=转 alt-screen / 丙=先甲再单独立项 → **选丙**。
甲已在 feature 12 交付（`^O` 展开被折叠的工具输出）。

**动了哪些文件**：本档案（README 含需求与三个候选）、features/README 交付总览、
TODO、roadmap 阶段 2 就地注记。

**测试**：未动 src，`./test.sh` 不受影响。

**遗留**：三个候选未拍板；前置精读全部未做（`tui-plan.md` 的主体、
`tui-alt-screen.ts`、CC 的 hit-test/selection、SGR 1006 与 DECSET 1049 的实测）。
