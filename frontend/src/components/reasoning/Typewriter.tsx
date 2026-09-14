import { useEffect, useRef, useState } from 'react'
import { useUiStore } from '../../store/uiStore'

// 打字机效果:文本完整到达后才开始播,动画只影响展示不影响数据
// 已完成(播完/已跳过)的文本不重播;被中断的(如 StrictMode 双调用清理)会重新播
// 步长/间隔按"渲染次数"调优:每次 4 字 / 30ms,比逐字刷新减少一半重渲染
export function Typewriter({ text, speed = 30, step = 4 }: {
  text: string; speed?: number; step?: number
}) {
  const enabled = useUiStore((s) => s.typewriterEnabled)
  const [shown, setShown] = useState(enabled ? 0 : text.length)
  // 已完成播放(或被跳过)的文本,切开关/重渲染时不重播
  const doneFor = useRef<string | null>(null)

  useEffect(() => {
    if (!enabled) {
      setShown(text.length)
      doneFor.current = text
      return
    }
    // 该文本已播完或已跳过 → 直接显示全文,不重播
    if (doneFor.current === text) return
    setShown(0)
    const timer = setInterval(() => {
      setShown((n) => {
        if (n >= text.length) {
          clearInterval(timer)
          doneFor.current = text
          return n
        }
        const next = n + step
        if (next >= text.length) doneFor.current = text
        return next
      })
    }, speed)
    return () => clearInterval(timer)
  }, [text, enabled, speed, step])

  return (
    <span>
      {text.slice(0, shown)}
      {shown < text.length && <span className="animate-pulse text-accent">▌</span>}
    </span>
  )
}
