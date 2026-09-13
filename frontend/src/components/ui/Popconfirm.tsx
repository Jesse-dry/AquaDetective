import { useEffect, useRef, useState, type ReactNode } from 'react'

// 轻量 Popconfirm:点击触发元素后在其下方弹出确认气泡(替代原生 confirm)
// 点击外部区域关闭;确认/取消后关闭。气泡右对齐触发元素,避免窄容器横向溢出。
interface PopconfirmProps {
  message: string
  onConfirm: () => void
  children: ReactNode
  confirmText?: string
  cancelText?: string
}

export function Popconfirm({
  message,
  onConfirm,
  children,
  confirmText = '删除',
  cancelText = '取消',
}: PopconfirmProps) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLSpanElement>(null)

  // 点击气泡外部关闭
  useEffect(() => {
    if (!open) return
    const onDocDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    const onEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onDocDown)
    document.addEventListener('keydown', onEsc)
    return () => {
      document.removeEventListener('mousedown', onDocDown)
      document.removeEventListener('keydown', onEsc)
    }
  }, [open])

  return (
    <span ref={ref} className="relative inline-block">
      <span
        onClick={(e) => {
          e.stopPropagation()
          setOpen((v) => !v)
        }}
      >
        {children}
      </span>
      {open && (
        <div
          className="absolute right-0 top-full z-30 mt-1 w-52 rounded-lg border border-edge bg-panel p-2.5 text-left shadow-lg"
          onClick={(e) => e.stopPropagation()}
        >
          <p className="mb-2 text-xs leading-relaxed text-slate-200">{message}</p>
          <div className="flex justify-end gap-1.5">
            <button
              onClick={() => setOpen(false)}
              className="rounded bg-edge px-2 py-0.5 text-xs text-slate-300 hover:bg-slate-600"
            >
              {cancelText}
            </button>
            <button
              onClick={() => {
                setOpen(false)
                onConfirm()
              }}
              className="rounded bg-danger px-2 py-0.5 text-xs font-semibold text-white hover:bg-red-400"
            >
              {confirmText}
            </button>
          </div>
        </div>
      )}
    </span>
  )
}
