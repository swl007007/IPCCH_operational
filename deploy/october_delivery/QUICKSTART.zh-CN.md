# 月度交付简要操作说明

当前部署：Google Cloud 项目 `manuel-remote-sensing`，区域 `us-central1`。
固定变量和模型直接复用，不训练、不重新溯源。

## 1. 更新遥感

创建新的 `prepare_id`，生成并上传准备请求，然后执行 Cloud Run Job **`oct-prepare-plan`**。
它会通过 Batch 更新 EVI、FLDAS、VIIRS、GOSIF，并为 FEWSNET、IPCCH 分别装配特征。

等待输出桶中的 `prepared/<prepare_id>/prepare_status.json` 为 `succeeded`，查看同目录
`prepared_manifest.json` 的实际最新月份。必须准备成功，才进入下一步。

## 2. 选择 ACLED 和 WFP

两个来源分别选择：

- **keep**：沿用已有数据。
- **refresh**：上传兼容的 raw 文件，并在 manifest 中填写 `raw_upload` 引用；系统自动转换、装配，不需要手工制作特征表。

每个引用包括文件 URI、generation 和 SHA-256。具体 JSON 和请求构建命令见 [完整操作说明](README.md)。

## 3. 上传运行请求

使用新的 `run_id`，构建 `run_manifest.json`，绑定已成功的准备结果和两项来源选择，然后上传到：

```text
gs://manuel-remote-sensing-oct-delivery-requests/requests/<run_id>/run_manifest.json
```

上传即自动触发 **Eventarc → Workflows → Cloud Run Job `oct-delivery`**，无需另开预测服务。
同一请求重复通知不会重算；失败重试用新的 `run_id`。

## 4. 查看结果

输出桶：`gs://manuel-remote-sensing-oct-delivery-debug`。

| 内容 | 桶内位置 |
|---|---|
| 成功或失败状态 | `runs/<run_id>/run_status.json` |
| 30 张交付 CSV | `deliveries/<run_id>/scopes/{0m,6m,12m}/{fewsnet,ipcch}/` |
| 补齐及诊断说明 | `deliveries/<run_id>/reports/` |
| 可离线重放的完整包 | `deliveries/<run_id>/webapp_model_bundle.tar.gz` |

以 `run_status.json` 的 `succeeded` 为准；工作流提交成功不等于预测完成。

## 本次十月结果

- `run_id`：`oct-final-20261008a`，已成功并通过离线重放。
- 预测月份：2026-10、2027-04、2027-10。
- 本地文件：`Outcome/model_delivery/october_cloud_delivery/oct-final-20261008a/`。
- 本次 ACLED/WFP 均为 keep；EVI/FLDAS/VIIRS 更新至 2026-08，GOSIF 至 2024-12。

当前请求构建示例固定为十月版本；下个月需要明确调整 origin/cutoff，并确认所用模型期限。
尚未切换既有生产消费者。遥感滞后会按约定补齐并标注；缺少证据的历史诊断留空。
