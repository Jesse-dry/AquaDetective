# AquaDetective 前端

> 水质预警溯源智能体 Web 大屏。只消费后端 API,零数值计算。
> 详细设计见 `docs/前端开发方案.md`。

## 技术栈

React 18 + TypeScript + Vite · MapLibre(流域地图) · ECharts(时序/EEM 等高线) ·
Tailwind(深色大屏) · Zustand(WS 驱动的状态)

## 快速开始

```bash
cd frontend
npm install          # 或 pnpm install

# Mock 模式(无需后端,推理流走 public/mock 回放)
cp .env.example .env # 把 VITE_MOCK 改为 1
npm run dev          # http://localhost:5173

# 联调模式(后端先启动:uvicorn app.main:app --port 8000)
# .env 中 VITE_MOCK=0,/api 与 /ws 由 Vite proxy 转发到 :8000
npm run dev
```

## 页面

| 路由 | 说明 |
|---|---|
| `/` | 大屏主页:告警面板 / 流域地图 / 推理流面板 / 断面曲线 |
| `/station/:id` | 断面详情:时序 + EEM 等高线对比 |
| `/report/:id` | 溯源报告(Markdown 渲染,`导出 PDF` 走浏览器打印) |
| `/replay` | 历史调查回放(答辩兜底) |
| `/benchmark` | 真实数据对标页(W5) |

## 目录约定

- `src/types/` 契约 TS 类型,与 `docs/API契约.md` 对齐,变更需双方确认
- `src/api/` REST 封装,与端点一一对应
- `src/ws/` WS 连接管理(自动重连 + REST 补齐)、6 类消息守卫、mock 回放流
- `public/mock/` Mock 数据,`VITE_MOCK=1` 时生效

## 测试

```bash
npm run build   # tsc 类型检查 + 生产构建
npm run test    # vitest(组件与 store 单测,W2 起补齐)
```
