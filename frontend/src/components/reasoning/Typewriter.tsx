import { useEffect, useRef, useState } from 'react'
import { useUiStore } from '../../store/uiStore'

// 打字机效果:文本完整到达后才开始播,动画只影响展示不影响数据
// 已完成(播完/已跳过)的文本不重播;被中断的(如 StrictMode 双调用清理)会重新播
export function Typewriter({ text, speed = 18 }: { text: string; speed?: number }) {
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
        return n + 2
      })
    }, speed)
    return () => clearInterval(timer)
  }, [text, enabled, speed])

  return (
    <span>
      {text.slice(0, shown)}
      {shown < text.length && <span className="animate-pulse text-accent">▌</span>}
    </span>
  )
}
