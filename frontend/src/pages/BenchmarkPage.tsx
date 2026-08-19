// 真实数据对标页(W5):公开数据集验证结果 + 行业案例图文
export function BenchmarkPage() {
  return (
    <div className="min-h-screen bg-ink p-6 text-slate-200">
      <div className="mx-auto max-w-3xl space-y-4">
        <h1 className="text-lg font-bold">📊 真实数据对标</h1>
        <p className="rounded-lg border border-warn/50 bg-warn/10 p-3 text-sm text-warn">
          声明:演示流域为模拟数据,真实数据仅用于算法验证。
        </p>
        <p className="text-sm text-slate-400">
          W5 交付:公开数据集异常检测结果图表 + 椒江/长治/黄河乌海/宁波真实案例对标。
        </p>
      </div>
    </div>
  )
}
