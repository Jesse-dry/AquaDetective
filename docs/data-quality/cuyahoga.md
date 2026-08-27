# Cuyahoga HUC8 公开数据 · 数据质量报告

## 1. 表概览

| 表 | 行数 | 说明 |
|---|---|---|
| observations | 117,372 | 水质+水文观测长表 |
| sites | 2,233 | 统一站点/设施注册表 |
| flow_network | 17,719 | 河网拓扑边 |
| sources | 231 | NPDES 污染源设施 |
| source_discharge | 56,239 | DMR 排放记录 |
| source_violations | 39,425 | 排放违规记录 |

## 2. 观测分布

### 按数据集

```
dataset_id
usgs_nwis_cuyahoga    40678
usgs_wqp_cuyahoga     76694
```
### 按统一参数编码（Top 15）

```
parameter_code
discharge               36082
temperature              5609
specific_conductance     1736
do                       1559
ph                       1467
tds                      1367
ammonia_n                 970
nitrite_n                 959
nitrate_nitrite_n         909
lead                      884
cadmium                   884
selenium                  874
barium                    873
chromium                  871
arsenic                   871
```
### 时间覆盖

- usgs_nwis_cuyahoga: 2018-01-01 ~ 2024-12-31
- usgs_wqp_cuyahoga: 2018-01-02 ~ 2024-12-11

## 3. 站点吸附

```
dataset_id          snap_flag
epa_echo_cuyahoga   far            49
                    ok            182
usgs_nwis_cuyahoga  far             1
                    ok            111
usgs_wqp_cuyahoga   far            52
                    ok           1838
```
- 吸附距离中位数：16.0 m；>500m 的站点 102 个

## 4. 污染源

- NPDES 设施 231 个（许可状态见 sources.csv）
- DMR 记录覆盖 138 个设施；违规记录覆盖 187 个设施

## 5. 已知限制与注意事项

- **WQP 时间戳非真 UTC**：`timestamp_utc` 由 ActivityStartDate+Time 拼接并加 `Z`，实际为站点本地时区（各站 TimeZoneCode 不同），跨站对比传播时间前需统一时区。
- **USGS 为逐日值**：无日内时间，`timestamp_utc` 统一为当日 00:00Z。
- **参数编码**：核心指标走 `parameters.csv` 映射；未映射的 WQP 特征按名称 slug 化保留，未做近似合并。
- **非检出**：WQP 非检出（value 为空）保留 `detection_limit`，value 为 NaN，qc_flag 含 `Not Detected`。
- **吸附超距**：102 个站点距最近河段 >500m，需逐一核验（湖泊站/坐标误差/离线）。