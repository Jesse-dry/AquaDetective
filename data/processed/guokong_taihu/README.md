# data/processed/guokong_taihu — 太湖流域国控断面标准化水质数据

由 `tools/import_taihu_subset.py` 从 `data/interim/guokong_surface_water_2021_2025/` 生成,
字段编码遵循《中国数据获取指南》§2.1。

## 结构

- `stations.csv` — 断面注册表:station_id / name / province / records / first_ts / last_ts / records_per_day
- `readings/<station_id>.csv` — 按断面分表(105 个断面,按 epoch 升序)
- `import_report.json` — 导入质量报告

## readings 字段

| 列 | 含义 | 单位 |
|---|---|---|
| ts | 监测时间(ISO 8601) | UTC+8 |
| epoch | 监测时间 | 秒级 epoch |
| temperature | 水温 | ℃ |
| ph | pH | 无量纲 |
| do | 溶解氧 | mg/L |
| conductivity | 电导率 | μS/cm |
| turbidity | 浊度 | NTU |
| codmn | 高锰酸盐指数(**非 COD**) | mg/L |
| ammonia_n | 氨氮(以 N 计) | mg/L |
| tp | 总磷 | mg/L |
| tn | 总氮 | mg/L |
| chla | 叶绿素α(多数缺失,仅湖库站) | mg/L |
| algae_density | 藻密度(多数缺失) | cells/L |
| quality_class | 水质类别(Ⅰ~劣Ⅴ) | — |

## 标准化规则(导入器口径)

1. 时间戳:`监测时间` 优先;空/非法时回退源文件名抓取时刻;去重按(省份,断面,时刻)保留首条
2. `*`/`-` 等占位符 → 空值;不做任何插值/平滑
3. 主要指标缺失率 3~5%,chla/algae_density 缺失 ~90%(源数据即如此)

坐标说明:断面坐标见 raw 目录 `站点经纬度坐标.csv`(汇编方百度模糊查询,仅供参考)。
