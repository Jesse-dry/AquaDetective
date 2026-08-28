# 太湖国控断面公开数据 · 统一导入质量报告

## 1. 表概览

| 表 | 行数 | 说明 |
|---|---:|---|
| observations | 3,090,295 | 调查可读的数值观测长表 |
| evaluation_labels | 326,928 | 离线评测水质类别 |
| sites | 105 | 太湖断面及 HydroRIVERS 吸附 |
| sources | 37 | 企业候选源及河网吸附 |
| flow_network | 2,082 | HydroRIVERS 河段拓扑 |

## 2. 隔离保证

- `observations.csv.gz` 不包含 `quality_class`、`truth_source` 或企业标签。
- 发布水质类别仅写入 `evaluation_labels.csv.gz`，只供离线验证读取。
- 旧版按站点宽表继续保留，现有异常检测与前端演示不受影响。

## 3. 已知限制

- 河网吸附标记为 `ok` 的断面 44/105。
- 河网吸附标记为 `ok` 的企业 24/37。
- 断面坐标来自汇编方地图查询，正式归因前仍需用官方坐标复核。
- HydroRIVERS 流速与传播时间只能用于候选排序，不能作为污染因果证据。