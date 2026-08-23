# 26-reattach-test-fix（修 25 复核发现的假绿：压缩重挂锚测试无鉴别力）
状态：已交付
分支：test/26-reattach-fake-green（本档案全部工作）
流程：中等改动直做（无 spec/plan）——单条测试的场景与断言修正，改动面一个文件；
按 features/README 规矩 9 的教训，验收项直接写进「需求」节。

## 需求

feature 25 的验收标准 4（「压缩后已加载的 skill 仍有效」）由
`tests/test_skills.py::test_compaction_reinjects_loaded_skill_body` 钉住，但 25 复核
（2026-08-23）注入反证证明它是假绿：掐断 `make_instructions` 的重挂（`load()` 只回
`base()`）后测试仍绿。原因：场景里 skill 的 tool_result 落在压缩 keep-recent 保住的
尾段（诊断打印 token 在消息[4]），断言 `"TOKEN" in json.dumps(messages)` 区分不了
「重挂生效」与「压缩根本没摘掉正文」。重挂机制本身有效（复原后 token 同时出现在
指令消息[1]），坏的只是测试。出处：TODO「25 复核发现」高级第 1 条；链回
[25 档案](../25-20260822-skills/README.md)。

验收标准（怎么算做完）：

1. 修后的测试在当前实现下绿；
2. 注入反证必红：掐断重挂（`make_instructions` 只回 `base()`）后该测试必须红，
   红的输出记进 devlog（features/README 规矩 9 附带教训：e2e/关键测试必配注入反证）；
3. 场景自证：断言能证明 skill 正文不是靠 keep-recent 尾段存活的
   （具体形态按拍板方案）；
4. `./test.sh` 全绿；不动 src/（只补测试，不动被测代码——分支类型 `test` 的判据）。

## 候选方案与确认

### 方案 A · 只改断言定位（最小改动）

场景不动，把「token 在整份 messages 里」改成「token 在重建后的指令消息里」——
重挂产物只会出现在 instructions loader 输出的那条 user 消息，断言直接认它。
25 复核已实证此断言形态可判别（掐断重挂后指令消息里无 token）。

- 好处：改动最小（几行断言），不碰压缩场景的参数，不会引入对切点细节的依赖。
- 代价：场景里 skill 的 tool_result 仍被 keep-recent 保住——测试没有复现
  「正文真的被压缩摘掉」的处境，验收标准 4 的字面（模型仍持有）只测了一半：
  证明了重挂发生，没证明重挂是雪中送炭而非锦上添花。

### 方案 B · 场景加填充让切点真摘掉正文 + 双向断言（推荐）

在 skill 轮之后加填充轮（bash 轮 + 递增 usage），把压缩切点推到 skill 轮之后，
让 skill 的 tool_result 真的被摘出上下文；然后双向断言：
`token 不在任何 tool 消息里`（自证场景成立——正文确实被摘掉了，这条防场景漂移）
+ `token 在指令消息里`（证明是重挂救回来的）。

- 好处：忠实复现验收标准 4 的字面处境（CC 踩的坑就是这个处境）；双向断言
  自带场景漂移报警——将来压缩参数变了导致尾段又保住 tool_result，第一条断言
  会先红，测试不会退化回假绿。
- 代价：场景要跟 find_cut_point 的切点行为配合（usage 数字要调），比 A 多
  一点工作量；对压缩实现的行为变化更敏感（但敏感正是这里想要的）。

### 确认

2026-08-23 用户拍板（AskUserQuestion，两问与本档案相关，选项原文见上两节；
另一问是 27 的修法，用户未选、要求先查 CC 的做法，记在 27 档案）：

问 1：26（假绿修复）：测试怎么改才算有鉴别力？
- 候选 A·只改断言定位：场景不动，断言从「token 在整份 messages」改为
  「token 在重建后的指令消息里」。改动最小，但场景仍是 keep-recent 保住
  正文的顺风局。
- 候选 B·场景摘掉正文+双向断言（AI 推荐）：加填充轮让压缩切点真的摘掉
  skill 的 tool_result，再双向断言：token 不在任何 tool 消息（自证场景，
  防漂移回假绿）+ token 在指令消息（证明重挂救回）。
选择：B。（理由栏用户未附文字，只记选择本身。）

问 2：26 的范围：要不要顺带补上复核发现的另一条纯测试缺口
（disable-model-invocation 的 skill /skill 通道可调，spec 验收 2 后半句
无测试，现行为正确、补上即绿）？
- 候选 A·顺带补上（AI 推荐）：同一个「补强 25 的测试缺口」交付，一条绿
  测试的成本，TODO 低级第 1 条即可销账。
- 候选 B·不带：严格一档案一事，缺口留 TODO 走 !小修。
选择：顺带补上。

## 结果与总结

只动 `tests/test_skills.py`，src 一行未改（分支类型 `test` 的判据成立）：

- `test_compaction_reinjects_loaded_skill_body` 场景两锚改三锚：改法从
  `find_cut_point` 机制推出（两锚时 `anchors[:-1]` 只剩 skill 轮自己的锚，
  刀必然落在它上面 = skill 轮整个保留，这就是假绿成因），不是调参试出。
  断言改双向：token 不在任何 tool 消息（自证正文真被摘掉，防场景漂移回假绿）
  + token 在指令消息（只可能来自重挂）。
- 新增 `test_repl_skill_can_invoke_disable_model_invocation`（拍板问 2 顺带）：
  disable 的 skill 走 /skill 照常展开跑轮次 + 同 skill 不在模型可见目录。
- 注入反证两处各红各的（掐断重挂 → 红在重挂断言；拦用户通道 → 红在
  requests 空），红的输出存 [devlog.md](devlog.md)，注入均已复原。
- 全量 `./test.sh` → `1292 passed, 3 deselected in 152.61s`（交付前 1291）。
  首跑 STATUS 数字对账测试先红（1291 过期），护栏按设计起效，改 1292 后全绿。
- TODO 销账两条：25 复核高 1（假绿）、低 1（/skill 覆盖缺口）。

## 遗留问题

无新增。两条记录性质疑见 [复盘.md](复盘.md)「我现在质疑什么」
（指令消息识别靠头部字符串、极端 keep_recent 参数的代表性），
均不够格立 TODO——后者已并在 25 遗留 3（预算校准）的范畴里。

## 用到的知识

- [25 档案](../25-20260822-skills/README.md)（被修测试的出身与验收标准 4 原文）
- 25 复核诊断（2026-08-23 会话）：注入反证与消息级 token 定位的实测输出，
  关键数字已转录进本档案「需求」节与 TODO「25 复核发现」。
