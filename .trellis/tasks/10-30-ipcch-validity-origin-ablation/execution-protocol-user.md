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

## 4. Cloud Run 与 MLflow 最终验收（强制）

完成 Spec 的主要实现和实验执行后，必须检查 Cloud Run → MLflow 的整个实验记录链路。

**A. Cloud Run**

- 确认对应 Cloud Run Job/Execution 已成功完成。
- 检查运行日志，确认模型训练、评估、artifact 输出及 MLflow logging 是否正常。
- 确认没有仅凭 Cloud Run 执行成功就错误地认定 MLflow 注册成功。

**B. MLflow Registration**

- 验证 Cloud Run 是否已经通过现有自动流程将对应实验正确登记到 MLflow。
- 确认 experiment、run、artifacts、metrics、parameters 和必要的 model registration 状态。
- 如果自动登记失败或缺少必要内容，优先定位并修复现有 registration pipeline，再通过适当方式补全或重新执行。
- 避免产生重复、冲突或错误归属的 MLflow runs。

**C. Model Card & Tags**

参照 MLflow 中同一实验下的 **AlphaEarth Pooled** 等现有 runs，检查并补齐：

- Model Card：沿用已有模型卡片的格式、结构、命名约定和内容粒度。
- Model Tags：沿用同一 experiment 中其他 runs 的 key/value 规范。
- 保证模型名称、配置、数据版本、训练参数、评估指标、Cloud Run execution 与 MLflow run 之间的对应关系正确。
- 所有信息必须来自真实配置、日志和 artifacts，不得虚构指标或实验元数据。

**D. IPCCH Dashboard**

**本次实验必须能够在 MLflow 端 IPCCH Dashboard 的 Experiments Tab 中被正确检索和查看。**

请验证：
- Experiment/run 归属正确；
- 对应实验记录确实存在；
- Model Card、Tags、Metrics 和 Artifacts 正确关联；
- Dashboard 所依赖的记录与字段完整；
- 不仅完成后端写入，还应在可用条件下检查 Dashboard 展示结果。

如果无法直接检查 UI，应使用可用的 API、配置或日志进行交叉验证，并明确说明 UI 尚未实际确认，不能将其报告为已验证通过。

## 5. 最终完成条件

只有同时满足以下条件，才允许结束 `/goal`：

1. Spec 全部任务完成，且对应验收标准通过。
2. Executor 的代码变更、测试、checkpoint 和交付物已由 Supervisor 抽查验证。
3. Cloud Run 实验成功完成。
4. MLflow 实验记录和必要的模型注册已验证。
5. Model Card 和 Model Tags 符合 AlphaEarth Pooled 等现有 runs 的规范。
6. IPCCH Dashboard Experiments Tab 中的实验记录及其展示已验证；若受外部权限或 UI 限制而无法验证，应明确报告该阻塞，不得宣称全部完成。
7. 不存在尚未解决的阻断性问题。

完成后输出简洁的最终报告，包括 Spec 完成情况、关键 diff、测试结果、Cloud Run execution ID、MLflow experiment/run ID、Model Card/Tags 验证情况、Dashboard 验证结果，以及任何残留风险。

**核心指令：持续推进 `/goal` 直至完成。Supervisor 负责监督与验收，Executor 负责实际实现。除 CRITICAL ERROR 外，不要中途停止或等待人工确认。禁止启动 Trellis Audit。**