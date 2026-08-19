import { useEffect, useState } from 'react'
import { useUiStore } from '../../store/uiStore'

// 打字机效果:文本完整到达后才开始播,动画只影响展示不影响数据
export function Typewriter({ text, speed = 18 }: { text: string; speed?: number }) {
  const enabled = useUiStore((s) => s.typewriterEnabled)
  const [shown, setShown] = useState(enabled ? 0 : text.length)

  useEffect(() => {
    if (!enabled) {
      setShown(text.length)
      return
    }
    setShown(0)
    const timer = setInterval(() => {
      setShown((n) => {
        if (n >= text.length) {
          clearInterval(timer)
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
