# 2026 年 9 月 FEWSNET / IPCCH 本地模型更新与交付规格

日期：2026-09-09

状态：用户已批准实施。实施补充指令：跳过 TDD，不运行回归测试；仅做聚焦测试和独立检验。

工作分支：`feat/local-202609-h5`

## 1. 目标与已确认决策

从 `https://github.com/IFPRI/MTI-GOOGLE-FOOD-CRISIS-MODEL` 获取最新 WFP、ACLED 数据，更新本地模型入口，重新训练 FEWSNET 和 IPCCH，交付可由 web app 开发方消费的模型和结果。web app 开发、接入及部署由对方负责。

| 项目 | 本次约定 |
| --- | --- |
| 预测输入月份 | `2026-04` |
| 唯一预测目标月份 | `2026-09` |
| 唯一训练及交付 horizon | `5` 个月；`X(t) → Y(t+5)` |
| 特征观测月份上限 | `2026-04`，含当月 |
| 训练标签月份上限 | `2026-04`，含当月；仅使用现有非空标签 |
| 数据版本 | 使用最新来源中的历史修订值，明确记录下载版本 |
| WFP 尺度 | 以既有输入为参照，按重叠国家月份核对指标和量纲；仅在证据明确时转换 |
| 模型方法 | 保留各自现有方法、特征定义、超参数和时间划分规则 |
| 模型更新 | 两套模型都重新训练，生成新版本模型包 |
| 空间范围 | 各自原生 polygon，以及各自现有全量国家和地区覆盖 |
| 新入口数据库 | 两套版本化历史 panel CSV、4 月预测输入和来源校验清单 |
| polygon 交付 | 完整模型包、polygon→实际模型/cluster 映射、预测 CSV、对应边界 |
| 国家交付 | 两套现有人口加权国家预测表，目标改为 9 月、horizon 改为 5 |

月份 cutoff 约束观测和标签所指月份，并不证明这些数据在 4 月当时已经发布。本次属于使用当前来源版本重建的 4 月输入预测，不能作为严格历史数据版本回测，也不报告 9 月预测准确率。

## 2. 已核对的实现事实

- 上游默认分支为 `main`；设计阶段查询到提交 `92b4fb20fc4f4b0a3fa69c89b2382ffd4b2b1ab6`。其中存在 `ACLED/ACLED Data_2026-07-22.csv`（35,743,195 bytes）和 `WFP_indicator/wfp_data_7.22.26.csv`（3,757,183 bytes）。已按该 SHA 下载。ACLED 实际观测为 2025-05-01 至 2025-07-22，7 月覆盖不完整；WFP 仅使用截至 2026-04 的 Aggregated 行，排除 Forecast。
- 当前 operational 仓库的 origin 是 `swl007007/IPCCH_operational`，与用户指定的数据来源仓库不同。执行时在独立本地来源目录拉取指定上游，记录实际获取的提交；不把上游分支合并进本项目。
- IPCCH 月度入口 `Final_harmonise/00_build_monthly_ipcch_base_input.py` 读取已组装 panel，不能仅更新原料后直接预测。
- FEWSNET 本地入口、模型契约及国家汇总当前主要限制为 `0/6/12m`；IPCCH 旧训练导出入口也固定这三个 scope。必须贯通 `5m` 的训练、加载、预测和国家汇总，不能改写已有 `6m` 结果的标签。
- FEWSNET 使用固定 cluster RF 和 pooled fallback。IPCCH 每个 horizon 的四个 XGBoost 回归模型由所有 polygon 共享。没有每个 polygon 独立拟合的模型权重，也没有模型混合权重。
- IPCCH 旧导出器只按特征月份过滤训练帧。本次须同时保证标签月份不超过 4 月，不能仅依赖 `--feature-month 2026-04`。

## 3. 来源快照与本地入口

### 3.1 获取与版本

执行开始时重新核对指定上游默认分支，固定实际下载的 commit SHA。只获取本次所需 WFP/ACLED 文件及解释它们所需的来源信息，保留未经修改的原始文件。

记录仓库 URL、commit SHA、仓库内路径、获取时间、文件大小、SHA-256、实际观测年月范围、过滤到 cutoff 前后的记录数。若上游变化导致字段或指标定义不同，先核实兼容性；不能自动换成其他来源或其他价格指标。

原始快照可含 5 月以后的记录；这些记录在构造特征之前排除，不参与聚合、滚动特征、填补统计或训练。现有标签和其他特征来源不额外更新；按已确认 cutoff 截断。

### 3.2 保留特征定义

**已确认的 WFP 尺度处理原则。** 以既有 FEWSNET/IPCCH 数据集中 WFP 相关变量的实际数值范围为参照，按重叠的国家和月份比较新旧值，并核对来源指标定义、量纲和原处理过程。同一量纲的历史修订直接沿用现有特征定义；只有证据明确说明尺度差异及换算关系时，才按该关系转换为既有量纲。不能直接将新值压入旧值最小—最大范围，也不能仅因极值或中位数不同而引入 z-score/min-max 标准化。

执行时输出 WFP 尺度审计：两模型基准和新聚合值的非缺失数、缺失数、min/p1/median/p99/max、同国同月差值及非零旧值上的比值、重叠键数量，以及指标/单位来源证据。国家月份比较不能被 polygon 重复行隐含加权；原有同国同月多值需单独列出。明确记录结论为无需转换或采用有来源依据的具体公式，并保存转换前后统计。若没有足够重叠或单位证据，不能根据范围猜测换算关系，应说明具体缺口并确认后再用该来源建模。如果需要依赖样本拟合的标准化，那是新增模型预处理决策，须先说明拟合范围和对现有填补/SMOTE的影响；不在本次已确认原则下自动添加。

只读基准检查已得到以下 panel 行级范围（分位数受各国 polygon 行数加权）：FEWSNET `WFP_Price` 为 `0.244367..4591.94145`，中位数 `66.32321`；IPCCH 为 `0.244367..42691.037577`，中位数 `277.338569`。FEWSNET 4 月 5,718 行的两 WFP 基础列全缺失；IPCCH 4 月 6,227 行中 `WFP_Price` 有 2,431 个非缺失值。追溯最新 assembled notebook 后确认两模型的 WFP 指标不同（见下），没有在这些步骤进行 z-score/min-max；`WFP_Price_std` 不是标准化价格。FEWSNET `WFP_Price_m4/m12` 是先滞后一月再求完整 4/12 月窗口和。这些事实不能独自证明新旧来源量纲一致。IPCCH 历史 panel 部分同国同月存在不同 WFP 值，对照时须报告该冲突，不能任取首行作为国家月基准。

- WFP 保留各自最新 assembled 输入的定义：FEWSNET 使用月度价格变化百分比的国家年月均值 + 100，IPCCH 使用 `Trend` 的国家年月均值 + 100；两者 `WFP_Price_std` 均为对应未平移指标的样本标准差。新来源 FEWSNET 百分比按同 market/admin/commodity/type/unit/currency 系列的前一日历月价格计算 `100*(Price(t)/Price(t-1)-1)`，不跨缺月计算。该公式在旧 Price_ALPS.xlsx 的 3,669 对连续月份上与既有百分比字段相差不超过 0.0001 个百分点。保留无支持键的旧值；不使用拟合 scaler。商品篮子变动单独记录，不当成量纲换算。保留两模型各自的国家代码映射，避免 FEWSNET 的 ISO 二位码与 IPCCH 的 ISO3 映射混用。
- ACLED 保留现有事件类型、事件计数、死亡人数和行政层级聚合。`_w5`、`_w10` 表示现有 adm2、adm1 聚合，并非 5/10 km 缓冲区。保留现有同月最近聚合点匹配及 500 km 上限；不在此次更新中改变空间方法。
- 对已有派生特征，凡依赖更新后的 WFP/ACLED，均沿原公式重新计算；不把新原始列与旧的依赖列拼成不一致输入。
- 其他特征、目标定义、polygon 身份和原始人口值保持现有来源含义。仅保留原有流程明确要求的派生和规范化步骤，不增加新预测变量。

### 3.3 历史更新规则

新原料不假定覆盖全部训练历史。先计算实际可更新键，再合并：WFP 使用来源中实际出现且国家身份可解析的国家年月；ACLED 使用来源实际出现的年月，按原方法为这些月份重算 polygon 特征。

在可更新键内用重新计算的整组指标替换旧值，包括原规则产生的缺失值；未被新来源覆盖的历史键保留原有值，并记录其基准来源。缺失不自动当作零，不将新来源未覆盖的整段历史清空，不产生 `_x/_y` 重复特征列。

报告每个来源的实际覆盖、替换/保留键数、匹配失败、缺失值变化和数值变化。如果解析失败、国家映射冲突或来源含义不明，不能把失败伪装成“未覆盖”并静默保留旧值。

### 3.4 两套 CSV 入口

- 分别保存截止 `2026-04` 的更新历史 panel，包含训练和现有滞后计算所需历史；标签保持真实缺失，不填造标签月份。
- 分别保存完整原生 polygon 集合的 `2026-04` 预测输入。FEWSNET 的月度输入包含冻结模型所需的已计算特征，使重新评分不依赖未交付的历史大表。
- FEWSNET 继续使用现有规范化流程和与新 panel 匹配的新 audit；新 panel 不能附用旧文件的 checksum/audit。
- 验证 polygon+月份键唯一、列定义与顺序兼容、预测输入与历史特征构建一致，并逐列验证非更新源的保留情况。
- 保留原始和旧版本文件。生成物写入独立版本目录，不覆盖已接受的 202604 输入、结果或模型包。

## 4. 训练与推理约定

### 4.1 共同时间规则

按 polygon 身份和日历月份连接 `X(t)` 与 `Y(t+5)`；禁止用第 5 行位移代替 5 个日历月。训练标签须 `target_month <= 2026-04`，因此本次训练特征月份最多为 `2025-11`；更晚特征只能用于构造预测输入或保留历史入口，不能与更晚标签进入训练。

最终只用 `X(2026-04)` 预测 `Y(2026-09)`。输出、模型 metadata、路由表和国家表必须一致声明上述月份及 `horizon_months=5`（现有 IPCCH 对应字段为 `scope_months=5`）。

### 4.2 FEWSNET

- 保留 Stage 3 特征契约、固定 17-cluster 映射、RF 参数、SMOTE 及 pooled fallback。
- 使用 horizon 对齐后、cutoff 内最新的 36 个实际有标签的不同月份。按现有规则，前 30 个用于临时拟合，后 6 个用于阈值选择，最终在全部 36 个标签月份重新拟合。
- 36 是观测到的标签月份数，不是连续 36 个日历月；不插值、填充或缩短窗口。实际月份及样本数从新输入重新验证和报告，不能照抄旧运行数值。
- 填补统计、阈值网格、并列选择规则和最终 refit 均沿用现有实现。阈值选择阶段的填补统计仅来自相应 fit 部分。
- 输出原有 `probability_crisis`、`threshold`、`predicted_crisis`、cluster/fallback 和人口来源字段；概率有限且在 `[0,1]`，类别等于概率与阈值比较的结果。

### 4.3 IPCCH

- 沿用 production-safe launch exporter 的四个累计人口占比目标 `phase2_worse` 至 `phase5_worse`、XGBRegressor、原超参数和训练期中位数填补。
- 保留现有 production-safe 特征定义与顺序。若新训练窗口导致原有特征全缺失或契约无法复用，报告具体特征并解决原因，不能静默删除原有特征或引入标签列。
- 保留现有固定 `0.2` 判定阈值、二元累计判定的 `cummax` 规则及 `overall_phase_pred` 解码。旧方法没有 FEWSNET 式 30/6 验证拆分，本次不为 IPCCH 新增该拆分或调参。
- 显式限制训练标签截止 4 月，并记录特征/标签的实际最小、最大月份及训练行数。
- 原有累计占比分数为回归输出；保留原评分行为，不擅自裁剪或重新校准。验收要求有限数值，并报告超出 `[0,1]` 或累计分数顺序不一致的情况；离散阶段判断按原有规则验证。

## 5. 模型包和 polygon 交付

两套交付共用时间/版本语义，保留各自原始指标字段。交付根目录为 `Outcome/model_delivery/202609_h5/{run_id}/`，含以下逻辑内容：

| 内容 | 交付要求 |
| --- | --- |
| `inputs/` | 两套历史 panel CSV、4 月模型输入 CSV、规范化及来源 audit |
| `sources/` | 原始 WFP/ACLED 快照及来源清单 |
| `fewsnet/model_package/` | 新 `5m` RF 模型、填补状态、冻结特征契约、partition map、阈值、训练报告、运行依赖及校验信息 |
| `ipcch/model_package/` | 新 `scope_5m` 四个 XGBoost 模型、特征契约、填补统计、阈值/解码配置及训练报告 |
| 各模型 `polygon_predictions.csv` | 唯一目标月份的原生 polygon 全量预测，保留人口、身份、月份及模型版本字段 |
| 各模型 `polygon_model_mapping.csv` | 每个 polygon 一行，使用字符串 `polygon_id`、`model_system` 和原生 ID；记录模型包、horizon 及实际路由 |
| 各模型 `polygons.geojson` | 原生边界转换为 EPSG:4326，保留字符串 ID，不重新分区、裁剪或简化；与结果和路由键一致 |
| 各模型 `country_predictions.csv` | 本次唯一 5m 国家汇总表 |
| 国家人口参考 | 现有 Census 参考表及来源版本，用于解释国家表参考列 |
| `README.md` | 字段定义、单位、缺失值、ID 连接方式、模型区别和本地重新加载/评分命令 |
| `manifest.json` | 实际版本、来源、code commit、依赖、运行参数、产物相对路径/大小/hash、验收状态 |

FEWSNET 路由表须同时记录指定 cluster、实际使用的 cluster RF 或 pooled RF、fallback 原因。IPCCH 路由表记录 polygon 对应的共享 `scope_5m` 模型包，该包内含四目标模型；cluster 留空并解释含义。

模型运行所需代码和依赖清单随交付提供或在交付内形成可安装的现有运行包。执行引用采用交付目录内相对路径；来源审计可保留原始路径，但重加载不能依赖原工作站绝对路径、外部研究 checkout、云凭据或训练时的内存对象。先加载导出的模型包，再产生被接受的最终预测。

边界可以与大历史 panel 分开供应用方选择读取；manifest 必须明确所有交付成员。CSV 空值、ID 字符串和日期格式在 README 中定义。JSON/GeoJSON 使用标准 JSON，缺失值为 null，不输出 NaN/Infinity。

## 6. 国家表口径

### FEWSNET

按国家对 `probability_crisis` 做人口加权均值，权重沿用 polygon `population`。仅正人口权重参与均值/离散度，分母为参与计算的 polygon 人口总和。保留 missing/zero/positive population area counts、权重总和、polygon 数和人口来源信息。

人口加权危机概率不能改称为危机人口占比或直接解释成需要援助人数；不新增国家二元危机分类。

### IPCCH

按国家对四个 `phase*_worse_score` 做人口加权均值，权重沿用 `population_estimate`，分母为现有方法规定的 polygon 权重总和。保留各累计占比分数、原有加权离散度和覆盖信息。

两表均保留 Census `referenced_population` 及来源版本作为独立参考列；该列不进入上述加权均值分母。已有 `aggregation_uncertainty`/dispersion 字段解释为 polygon 分数的加权标准差，不是置信区间。本次不新增国家预测人数表。

## 7. 验收条件

1. 原始快照的真实来源/版本可追溯，WFP 尺度审计有证据支持的结论；更新日志证明 WFP/ACLED 经处理后实际进入两套训练 panel 和 4 月预测输入；值未变化的覆盖键也如实记录，不强求预测必须变化。
2. cutoff 在聚合、派生及训练标签连接之前落实；实际训练样本逐行满足 `target_month = feature_month + 5` 和 `target_month <= 2026-04`。
3. FEWSNET 36/30/6 稀疏标签月份规则及 IPCCH 原拟合、填补和阈值方法符合第 4 节；训练超参数及来源身份完整记录。
4. 两模型均完成全量训练，导出、重新加载和实际预测。结果、边界、路由表的 polygon 集合与各自输入权威集合完全一致，键唯一；允许人口缺失，不删除相应预测。
5. 所有正式预测、路由和国家表仅对应 `2026-04 → 2026-09`、`5m`。本次没有附带 0/6/12m 预测产物。
6. 主代理从最终 polygon CSV 独立重算国家加权均值、离散度和覆盖计数，与交付国家表核对。
7. 在不同的临时目录中重新加载完整交付包并用随附 4 月输入评分；类别逐项相同，连续预测 `rtol=0, atol=1e-12` 一致。缺失值与原生 ID 按声明规则保留。
8. 对有改动的时间对齐、来源替换、包重加载和国家聚合逻辑保留针对性可运行检查，并独立检验真实产物。按用户实施补充指令，跳过 TDD，不运行回归测试；旧默认工作流通过改动范围核验保持原有契约，不声称其回归测试已通过。
9. 最终 manifest 在全套产物校验通过后写入 `status: passed`；不存在一套成功、一套失败却宣称整体通过的交付。记录实际大小和 SHA-256。
10. 原始基准及此前接受的模型/预测保持原样；没有 web app、GCP/GCS/Vertex、生产发布指针或远程代码 push 操作。

## 8. 执行顺序与边界

本文最终确认后，编写与本规格对应的实施计划，再按以下顺序执行：固定上游并下载原料 → 核验覆盖、基准与 WFP 尺度兼容性 → 生成两套新入口 → 补齐本地 5m 路径并测试 → 从可追溯代码版本全量重训 → 重加载预测 → 导出映射/边界/国家表 → 异地路径重加载和最终产物验收。

复用现有聚合、特征、训练和国家汇总函数，最小适配单一 5m 本地任务；不引入新数据库服务、通用工作流框架、模型家族、聚类方法、SHAP 或 web app 功能。现有 0/6/12m、云生产契约及旧产物保持可用。

实施需修改已有函数/类/方法时，主代理先完整读目标代码，执行 GitNexus upstream impact，说明调用方、流程及风险；HIGH/CRITICAL 先报告。提交前运行 detect_changes 并核对实际 diff。子代理仅做限定探索或独立核验，主代理负责代码修改、方法选择和最终验证。

## 9. 参考依据

- `specs/001-cloud-base-input/plan.md`：现有云流程背景；本次执行平台由用户确认的本地任务约定覆盖。
- `docs/superpowers/specs/2026-07-26-fewsnet-local-202604-prediction-experiment-design.md`。
- `docs/superpowers/specs/2026-07-26-fewsnet-sparse-label-training-window-design.md`：取代旧连续日历窗口解释。
- `fewsnet_partitioned_rf_pipeline/{core,local,cli}/`：现有 RF、路由、打包及本地运行实现。
- `ACLED/00_add_acled_features.py`、`WFP_indicator/00_add_wfp_price_features.py`、`Final_harmonise/00_build_monthly_ipcch_base_input.py`。
- 外部 `Google fund/Analysis/2.source_code/Step1_ACLED/00_add_ACLED_FEWS.ipynb` 与 `Step1_WFP/00_add_WFP_FEWS.ipynb`：FEWSNET 原料处理参考，不作为交付运行时依赖。
- 外部 `Google fund/Analysis/2.source_code/Step5_Geo_RF_trial/IPCCH/scripts/modeling/train_export_operational_launch_production_safe.py`：现有 IPCCH 重训方法。
- `model_artifacts/launch_2026_04/training_export_summary.json`、`model_pipeline/ipcch_launch_runtime/`。
- `tools/build_fewsnet_country_level_predictions.py`、`tools/build_ipcch_country_level_predictions.py`。
