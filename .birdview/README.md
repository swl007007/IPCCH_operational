# IPCCH现有架构与约束快照

查看 [全景图](architecture.html)、[手动交付图](manual.html)、[云流程图](cloud.html)。三个页面均可切换架构/约束；[来源索引](architecture.sources.html)保留已提交规则原文及Git行历史。中文内容，离线可用。这是当前源码与明确标识的本地文件快照，不是实时运行监控。

项目：`ipcch-operational`；地图：`ipcch-operations` / `ipcch-manual` / `ipcch-cloud`；revision均为1。
代码基线：`4a42f1f666a4f2d5d2616069fe25ddd81f2662cb`；GitNexus索引落后10个提交，只作定位，关键关系以源码为依据。

## 手动与云的接口比较

| 方面 | 手动/本地 | 云 | 当前整合边界 |
|---|---|---|---|
| 数据准备 | 来源脚本、ArcPy、旧notebook；h5另有WFP/ACLED刷新 | IPCCH云仅自动EVI；FEWS云消费已规范化快照 | 外部表格刷新尚未统一调度；不画成已接通 |
| IPCCH月度组装 | `Final_harmonise/00_build_monthly_ipcch_base_input.py` | `cloud/orchestrator/assembly.py`显式合并EVI long | 两套实现；按键/列/人口来源做一致性核验后再考虑整合 |
| IPCCH模型 | 本地默认0/6/12推理；h5单独四目标训练及5m评分 | 固定包0/6/12，Vertex纯推理 | `run_scope`和launch runtime已共用；h5训练不是云入口的一部分 |
| FEWS模型 | 原local runner为0/6/12；h5单独调用core训练5m | 云suite仍固定0/6/12，1训练job+3 Batch | core共用；local模型包不能直接注册为云生产包 |
| 国家诊断 | h5交付含v3国家表、置信标签、最大阶段proxy | 当前两套云主流程未自动调用这些h5步骤 | 与预测CSV、模型包、诊断版本应分别绑定 |
| 发布 | 本地版本目录、manifest、tar、可搬移runtime | IPCCH release_manifest CAS；FEWS三alias+current指针 | 三种发布语义独立，不能只复制文件就声称云发布成功 |
| 消费者 | 本地模型包/CSV/GeoJSON供应用方使用 | 消费权威manifest或FEWS Batch服务 | 仓库未实现已部署的用户web应用；FastAPI是Batch推理容器 |

## 主要现状

手动链：来源脚本 → 旧notebook面板（当前衔接待核实） → 本地月度输入 → IPCCH共享推理；h5则是原料刷新 → FEWS单独规范化 → 两套训练/重加载 → 国家诊断及portable bundle。各步骤为独立命令，不存在已核实的统一手动总编排。

IPCCH云链：manifest/run门禁 → Batch/GEE/rasterio EVI → 云月度组装/QA → Vertex调用共享纯推理 → 原子release manifest。FEWS云链：规范化快照 → CustomJob三预测期训练 → 三模型版本 → 精确版本Batch → 统一验证 → 三alias及发布指针。

## 约束审阅范围与缺口

- 来源收集：初始103份，加5份显式检查的运行契约，共108份；2项排除，167个未解析引用，扫描队列剩余0。未解析项大多为技能模板的占位路径，原记录未删除。
- 语义规则：43条有提交来源、可编译Git行历史的架构相关规则；另7条v3本地规范约束及本轮查看范围记录在地图。未逐条审阅全部技能/模板，因此`semanticReview=pending`，不得称全仓有效规则全集。
- v3规则来源：`Outcome/model_delivery/202609_h5/20260923_country_confidence_v3/reports/country_confidence_v3_spec.md`，SHA256=`8ea3c70e77310ed31a659b614aa72427c652ce40777f0326afc9ef84595beed6`。此文件位于忽略目录，不受代码HEAD固定，不伪造Git vN。其关键规则已在country-bundle模块详情中列出。
- v2等面积均值+强制20% low已被v3交付中的人口加权误差+固定10%/20%覆盖。FEWS Stage3 fs1/4月lag只作h5 proxy；IPCCH仍是训练重代入。最大阶段bootstrap是另一项proxy，不是已校准预测区间。
- 未读私有配置、密钥、大型原始数据或所有历史notebook；未核验实际GCP部署/IAM/当前release，不重放模型或交付验收。现有报告中的passed不作为本轮验收结论。
- CLAUDE.md仍称没有测试/依赖manifest，并引用不存在的四个Final_harmonise脚本；旧ArcPy Python2设计与ArcGIS Pro说明存在环境口径差异，迁移前需确认。README也未覆盖FEWS/h5全貌。
- 本次只新增.birdview查看材料，保留原先未提交的Trellis相关改动；未建任务、未修改实现/配置、未进行云调用或模型运行。

## 模块表

| 模块 | 职责 | 所属文件/目录 | 证据 | 不确定性 |
|---|---|---|---|---|
| 表格特征准备 (`source-tabular`) | 按来源处理ACLED、WFP、FAO、WB；输出scaffold加特征，使用本地INI配置。 | `ACLED`, `WFP_indicator`, `FAO_price`, `WB_indicator`, `workflow_config.py`, `config` | `WFP_indicator/00_add_wfp_price_features.py:181`, `ACLED/00_add_acled_features.py:478` | 源码支持职责；未验证运行结果 |
| 手动遥感提取 (`source-raster`) | GEE/直接下载 → Windows ArcPy；EVI、FLDAS四分片、GOSIF、VIIRS输出宽表。 | `EVI`, `FLDAS`, `GOSIF_GPP`, `VIIRS_nightlight` | `EVI/02_arcpy_extract_evi.py:125`, `FLDAS/02_arcpy_extract_fldas_part1.py:228` | 源码支持职责；未验证运行结果 |
| 归档面板组装 (`legacy-panel`) | 旧notebook消费表格与栅格输出；保留为历史接口证据，当前自动更新衔接尚未核实。 | `archive/notebooks/Final_harmonise` | `archive/notebooks/Final_harmonise/00_combine_all_ch.ipynb:17` | 源特征输出如何更新当前source_panel，是否仍由这些notebook执行？旧文档所指四个同名.py文件已不存在。 |
| IPC API参考获取 (`api-reference`) | 下载areas/analyses逐年及合并文件；未证实直接接入当前月度组装。 | `curl_IPC` | `curl_IPC/00_download_ipc_api.py:28`, `curl_IPC/00_download_ipc_api.py:196` | 源码支持职责；未验证运行结果 |
| 手动IPCCH月度输入 (`local-base`) | 目标月scaffold + fixed/slow + 历史panel → base CSV/summary；不直接接收云EVI long。 | `Final_harmonise`, `tools/build_monthly_ipcch_scaffold.py`, `tools/build_ipcch_fixed_slow_features.py`, `tools/build_ipcch_schema_contract.py`, `tools/build_ipcch_source_vintage_manifest.py`, `tools/validate_ipcch_schema.py`, `tools/validate_csv_contract.py`, `Outcome/ipcch_unified/schema` | `Final_harmonise/00_build_monthly_ipcch_base_input.py:398`, `tools/build_monthly_ipcch_scaffold.py:163` | 源码支持职责；未验证运行结果 |
| h5手动来源更新 (`h5-refresh`) | 版本化WFP/ACLED原料 → 两套历史panel及April输入；FEWS规范化仍需独立调用。 | `tools/refresh_h5_inputs.py`, `tools/audit_h5_inputs.py`, `tools/check_h5_delivery_focus.py` | `tools/refresh_h5_inputs.py:73`, `tools/refresh_h5_inputs.py:177` | 源码支持职责；未验证运行结果 |
| h5训练与重加载评分 (`h5-models`) | 独立action命令重训FEWS RF及IPCCH四目标XGB；固定2026-04 → 2026-09；复用共享评分器。 | `tools/run_h5_model_delivery.py` | `tools/run_h5_model_delivery.py:48`, `tools/run_h5_model_delivery.py:89`, `tools/run_h5_model_delivery.py:139` | 源码支持职责；未验证运行结果 |
| FEWS本地0/6/12实验 (`local-fews`) | 独立本地训练/重加载CLI；固定三预测期，local包不能直接作为Vertex生产包注册。 | `fewsnet_partitioned_rf_pipeline/local`, `fewsnet_partitioned_rf_pipeline/cli/run_local_experiment.py` | `fewsnet_partitioned_rf_pipeline/local/runner.py:1022`, `docs/09_fewsnet_partitioned_rf_runbook.md:2811` | 源码支持职责；未验证运行结果 |
| 国家诊断与交付包 (`country-bundle`) | 人口加权国家表、v2/v3诊断、polygon映射/GeoJSON、可搬移runtime和tar包；不等于web应用已部署。 | `tools/build_fewsnet_country_level_predictions.py`, `tools/build_ipcch_country_level_predictions.py`, `tools/revise_h5_confidence.py`, `tools/revise_h5_country_v3.py`, `tools/package_h5_delivery.py`, `tools/verify_h5_confidence.py`, `tools/verify_h5_country_v3.py`, `tools/verify_h5_model_delivery.py` | `tools/run_h5_model_delivery.py:184`, `tools/revise_h5_country_v3.py:59`, `tools/package_h5_delivery.py:30` | 被Git忽略的实际交付runtime与当前源码是否逐字一致？本轮未重放验证。v3重建还依赖外部Stage3证据；搬移后评分与重新生成历史诊断是不同能力。 |
| 共享IPCCH推理 (`ipcch-runtime`) | 固定列契约、人口快照、四个XGB累计占比分数和0.2解码；本地CLI可出图，云wrapper传--no-map。 | `model_pipeline` | `model_pipeline/run_operational_launch_inference.py:157`, `model_pipeline/ipcch_launch_runtime/inference.py:60` | 源码支持职责；未验证运行结果 |
| 共享FEWSNET RF核心 (`rf-core`) | 冻结Stage3特征和17分区、pooled fallback、30/6选择阈值后36标签月refit；核心支持5m，云仍0/6/12。 | `fewsnet_partitioned_rf_pipeline/core`, `fewsnet_partitioned_rf_pipeline/config.py`, `fewsnet_partitioned_rf_pipeline/assets`, `fewsnet_partitioned_rf_pipeline/schemas`, `fewsnet_partitioned_rf_pipeline/cli/normalize_panel.py` | `fewsnet_partitioned_rf_pipeline/core/training.py:438`, `fewsnet_partitioned_rf_pipeline/core/horizons.py:26`, `fewsnet_partitioned_rf_pipeline/core/inference.py:106` | 源码支持职责；未验证运行结果 |
| IPCCH Cloud Run编排 (`ipcch-cloud`) | 校验manifest、获取独占run前缀、提交Batch和Vertex、依据对象报告推进；单月0/6/12纯推理。 | `cloud/orchestrator/main.py`, `cloud/orchestrator/run_state.py`, `cloud/orchestrator/roots.py`, `cloud/orchestrator/batch_client.py`, `cloud/orchestrator/vertex_client.py`, `cloud/orchestrator/model_package.py`, `cloud/orchestrator/inference.py`, `cloud/common`, `cloud/schemas`, `docker/Dockerfile`, `requirements-cloud.txt` | `cloud/orchestrator/main.py:185`, `cloud/orchestrator/inference.py:120`, `cloud/orchestrator/run_state.py:38` | 源码支持职责；未验证运行结果 |
| 云EVI提取 (`cloud-evi`) | Batch worker发起GEE月度EVI导出；rasterio区域mean/std → wide/long CSV与验证报告。 | `cloud/batch`, `tools/reshape_remote_sensing_wide_to_long.py` | `cloud/batch/evi_worker.py:115`, `cloud/batch/evi_service.py:141` | 源码支持职责；未验证运行结果 |
| 云IPCCH月度输入 (`cloud-base`) | 独立pandas组装器显式合并EVI long；scaffold决定行集合，生成schema QA与人口来源。 | `cloud/orchestrator/assembly.py`, `cloud/orchestrator/base_input_validation.py` | `cloud/orchestrator/assembly.py:33`, `cloud/orchestrator/assembly.py:95` | 源码支持职责；未验证运行结果 |
| IPCCH原子发布 (`ipcch-release`) | 复制已验收文件到不可变run目录；generation CAS最后更新release_manifest；消费者先读manifest。 | `cloud/orchestrator/release.py`, `cloud/orchestrator/release_manifest.py` | `cloud/orchestrator/release.py:97`, `cloud/orchestrator/release.py:270`, `cloud/common/release_reader.py:12` | 源码支持职责；未验证运行结果 |
| FEWS云套件编排 (`rf-cloud`) | 快照→一个CustomJob训练三预测期→3模型版本→3个精确版本Batch预测→统一验收。 | `fewsnet_partitioned_rf_pipeline/cli/run_latest.py`, `fewsnet_partitioned_rf_pipeline/cli/train.py`, `fewsnet_partitioned_rf_pipeline/cli/stage_snapshot.py`, `fewsnet_partitioned_rf_pipeline/vertex`, `docker/Dockerfile.fewsnet-partitioned-rf`, `requirements-fewsnet-partitioned-rf.txt` | `fewsnet_partitioned_rf_pipeline/cli/run_latest.py:279`, `fewsnet_partitioned_rf_pipeline/cli/run_latest.py:540` | 源码支持职责；未验证运行结果 |
| FEWS Batch推理服务 (`rf-server`) | FastAPI /health /predict加载精确模型包；供Vertex Batch使用，源码服务不证明在线Endpoint存在。 | `fewsnet_partitioned_rf_pipeline/vertex/predictor_server.py` | `fewsnet_partitioned_rf_pipeline/vertex/predictor_server.py:82`, `fewsnet_partitioned_rf_pipeline/vertex/predictor_server.py:118` | 源码支持职责；未验证运行结果 |
| FEWS套件发布 (`rf-release`) | 协调三production alias、可逆回滚、租约保护，最后写released/current.json；与IPCCH根隔离。 | `fewsnet_partitioned_rf_pipeline/vertex/promotion.py` | `fewsnet_partitioned_rf_pipeline/vertex/promotion.py:329`, `docs/09_fewsnet_partitioned_rf_runbook.md:28` | 源码支持职责；未验证运行结果 |

## 当前有向关系

- `source-tabular` → `legacy-panel`：旧来源CSV接口
- `source-raster` → `legacy-panel`：旧遥感宽表接口
- `legacy-panel` → `local-base`：历史panel衔接待核实（待核实）
- `local-base` → `ipcch-runtime`：monthly base输入 / 本地0/6/12评分
- `h5-refresh` → `h5-models`：版本化panel；FEWS须先规范化
- `h5-models` → `rf-core`：调用5m RF训练
- `h5-models` → `ipcch-runtime`：调用run_scope(5m)
- `h5-models` → `local-fews`：复用local模型包加载器
- `h5-models` → `country-bundle`：预测→国家表/映射/交付
- `local-fews` → `rf-core`：调用共享训练与预测
- `ipcch-runtime` → `country-bundle`：分数及人口→国家聚合
- `local-fews` → `country-bundle`：概率及人口→国家聚合
- `ipcch-cloud` → `cloud-evi`：提交Cloud Batch worker
- `cloud-evi` → `cloud-base`：EVI mean/std long
- `ipcch-cloud` → `cloud-base`：组装并检查输入
- `cloud-base` → `ipcch-runtime`：月度输入→Vertex wrapper评分
- `ipcch-cloud` → `ipcch-runtime`：Vertex执行CLI --no-map
- `ipcch-cloud` → `ipcch-release`：所有门禁通过后发布
- `ipcch-runtime` → `ipcch-release`：3份scope CSV及推理报告
- `cloud-base` → `ipcch-release`：base CSV/summary及QA
- `rf-cloud` → `rf-core`：CustomJob调用三预测期训练
- `rf-cloud` → `rf-server`：精确版本Batch Prediction
- `rf-server` → `rf-core`：加载冻结包并预测
- `rf-cloud` → `rf-release`：候选验证后统一promote
- `rf-server` → `rf-release`：经suite validator验收的预测

## 生成与浏览器验证

严格authoring校验、规则编译、Git行历史及HTML渲染结果见delivery-receipt.json；浏览器检查另记录于visual-review.md。渲染成功不代表实现合规或云部署成功。
