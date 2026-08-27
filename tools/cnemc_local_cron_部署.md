# CNEMC 本地 cron 部署(主力轨)

> 经 8 轮 GitHub Actions 运行分析(6 失败 75%):CNEMC API(`szzdjc.cnemc.cn:8070`)
> 对 GitHub Actions 美国 IP 不稳定(瞬时拒连/超时)。本地中国 IP 4 次手动运行 100% 成功。
> 故采用**本地中国 cron 为主力轨,GitHub Actions 为异地冗余备份**的双轨架构。

## 双轨架构

| 轨 | 运行环境 | IP | 成功率 | 职责 |
|----|---------|-----|--------|------|
| 主力 | 本地 cron(中国 IP) | 中国 | ~100% | 日常 4h 级存档 |
| 备份 | GitHub Actions | 美国 | ~30-50% | 异地冗余,本地宕机时兜底 |

两轨写入同一 `data/interim/cnemc_archive/all_stations.csv`,去重键为
`(抓取年份, 断面名称, 监测时间)`,互不冲突不重复。

## 本地 cron 部署

```bash
# 编辑 crontab
crontab -e

# 添加(每 4h 错峰 13 分,官方 00/04/08/12/16/20 出数,延 1h 抓):
13 1,5,9,13,17,21 * * * cd /root/projects/AquaDetective && /usr/bin/python3 tools/cnemc_archive.py >> /tmp/cnemc_archive.log 2>&1
```

## 部署后验证

```bash
# 等一个轮次后查看日志
tail -20 /tmp/cnemc_archive.log
# 应见:[OK] 覆盖率 9X.X%(拉 NNNN/系统 NNNN) + 追加 N 条新记录

# 查数据连续性
python3 -c "import csv;rows=list(csv.DictReader(open('data/interim/cnemc_archive/all_stations.csv')));print(f'{len(rows)} 行,时次:',sorted(set(r['监测时间'] for r in rows))[-3:])"
```

## 健康检查(脚本已内置)

`tools/cnemc_archive.py` 的 `main()` 入口三道断言,不达标 `sys.exit(1)`:
1. **空响应**:rows 为 0 → 退出不提交
2. **覆盖率**:`len(rows)/records < 90%` → 退出不提交(防页1成功后续全失败的假全量)
3. **新鲜度**:本次最新时次早于已存末行 → 退出不提交(防 API 返回缓存旧数据)

本地 cron 若失败,日志会打印 `[FAILED] ...`,可 `grep FAILED /tmp/cnemc_archive.log` 巡检。

## 备份轨(GitHub Actions)

`.github/workflows/cnemc-archive.yml` 保留为异地冗余:
- 每 4h cron +17 分(本地 13 分后,错开避免并发)
- 健康检查不达标会 `sys.exit(1)` 让工作流 failed
- 失败自动创建 issue 告警(标签 cnemc-archive/auto-alert)
- 若本地宕机数日,Actions 仍可部分兜底(成功率 30-50%,有总比无)

## 切换策略

- 正常:本地 cron 主力,Actions 备份(去重机制保证不冲突)
- 本地宕机:Actions 兜底(虽不稳定,但有总比无)
- 恢复后:本地恢复,Actions 多拉的数据已在 CSV 中(去重不重复)
