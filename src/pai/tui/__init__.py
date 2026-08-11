"""TUI（阶段 2 后半程）：scrollback 在上、pai 接管的 dock 在下。

分层判据——**只有 `renderer.py` 碰终端**，其余全是纯函数或纯状态机。
这条边界是本模块可测性的全部来源：组件树能在没有终端的地方渲染成行数组，
渲染器则通过注入的 `write` / `width` 回调与终端打交道。

设计原则见 docs/dev/roadmap.md 阶段 2（四条已拍板不再议），
方案取舍见 docs/dev/features/12-20260811-tui/。
"""
