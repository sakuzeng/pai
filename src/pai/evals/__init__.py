"""evals（阶段 7，feature 32）：回放评测与跑批的可复用逻辑。

评测套件本体住仓库根的 evals/（pytest 文件，经 ./eval.sh 跑，不进
./test.sh 的收集范围）；本包只放能离线单测的纯逻辑——工件索引
（artifacts.py）与会话轨迹派生（replay.py）。
"""
