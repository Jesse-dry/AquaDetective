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

## 真实数据验证(tools/validate_anomaly_real.py)

对记录最多的 8 个断面 × 3 指标 × 4 种检测方法,用"水质类别一致性"交叉验证
(检出点落在 Ⅳ/Ⅴ/劣Ⅴ 类的比例应高于断面基线):

| 方法 | 平均检出率 | 一致性通过率 | 结论 |
|---|---|---|---|
| threesigma | 0.78% | 22/24 (92%) | ✅ 推荐用于真实数据 |
| cusum | 0.13% | 4/4 (100%) | ✅ 最稳健,适合渐变检出 |
| ewma | 19.49% | 20/24 (83%) | ⚠️ 对不规则采样过敏感 |
| seasonal | 10.12% | 19/24 (79%) | ⚠️ 周期参数按 15 分钟规则数据标定,不适用本数据 |

完整报告见 `anomaly_validation.json`。结论:引擎的 3σ 与 CUSUM 在真实太湖数据上有效;
EWMA/seasonal 面向规则采样设计,真实不规则序列上误报偏高,真实场景应优先前两种。
