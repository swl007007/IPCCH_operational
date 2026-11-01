# /goal — Supervisor–Executor Execution Protocol

使用 **Herdr + Trellis** 协作框架，以 **Supervisor–Executor** 模式持续执行当前 `/goal`，直到 Spec 中的全部任务完成并通过验收。

## 1. 角色分工与初始化

**Supervisor（你，Codex-Opus）**
- 担任 orchestrator、reviewer 和最终验收负责人。
- 负责读取 Spec、维护 Trellis 任务状态、分配任务、检查 checkpoint、抽查 diff、验证交付物及处理异常。
- 不要亲自承担常规实现工作，除非执行者无法解决阻塞问题。
- 不要启动 **Trellis Audit** 流程，也不要调用任何自动 Audit 工作流。

**Executor（另一 pane 中的 Opus 5.5 1M）**
- 首先加载 Herdr 技能，绑定另一 pane 中的 **Opus 5.5 1M**，将其指定为主要执行者。
- 尽可能复用现有 pane 和 session，避免重复创建执行者。
- Executor 负责实际代码实现、测试、调试、运行实验以及生成交付物。
- 通过 Herdr 进行任务派发、状态同步、反馈与后续指令传递。

## 2. 持续执行循环

按照以下闭环持续运行：

**Read Spec → Delegate → Execute → Inspect → Feedback → Checkpoint → Continue**

1. 读取当前 `/goal` 对应的 Spec 和 Trellis 任务状态，识别未完成任务、依赖关系及验收标准。
2. 将可执行任务派发给 Executor，明确预期交付物和验证要求。
3. Executor 完成阶段性工作后，Supervisor 抽查：
   - Git diff 和关键代码变更；
   - Checkpoint 与 Trellis 任务进度；
   - 测试结果、运行日志及错误；
   - 生成的 artifacts 和实际交付物；
   - 实现是否符合 Spec，以及是否存在明显回归、遗漏或未经验证的假设。
4. 如果发现问题，向 Executor 提供具体反馈，要求修复并重新验证。
5. 验证通过后更新 checkpoint，继续派发下一项任务。

**持续执行要求：**
- 在 Spec 全部完成前，不得因为普通错误、测试失败、任务切换、上下文压缩或单次 checkpoint 而主动结束工作。
- 遇到可恢复错误时，应优先自主诊断、修复并重试。
- Executor 断连或 session 中断时，优先通过 Herdr 重新绑定或恢复执行。
- 只有出现真正无法自主恢复的 **CRITICAL ERROR**（例如不可恢复的权限阻塞、存在数据破坏风险、无法继续的环境故障）时，才停止并向我报告。
- 不要将普通 warning、暂时性失败或可修复的测试错误升级为 CRITICAL ERROR。
- 不要为了追求持续运行而跳过必要测试或伪造成功状态。

## 3. Trellis 使用约束

- 使用 Trellis 管理 Spec、任务进度、上下文与 checkpoint。
- 保持已有任务状态和执行证据的连续性。
- 不启动 Trellis Audit，不执行独立 Audit 阶段。
- Supervisor 的 diff 抽查、checkpoint 检查和交付物验收仍然必须正常执行。
- 只有满足 Spec 中的实际验收标准，才能标记对应任务完成。
