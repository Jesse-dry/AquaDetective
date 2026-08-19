import { create } from 'zustand'

// UI 状态:选中断面 / 大屏模式 / 当前场景脚本
interface UiState {
  selectedStationId: string | null
  selectedIndicator: string
  fullscreen: boolean
  typewriterEnabled: boolean
  selectStation: (id: string | null) => void
  setIndicator: (ind: string) => void
  toggleFullscreen: () => void
  toggleTypewriter: () => void
}

export const useUiStore = create<UiState>((set) => ({
  selectedStationId: null,
  selectedIndicator: 'cod',
  fullscreen: false,
  typewriterEnabled: true,
  selectStation: (selectedStationId) => set({ selectedStationId }),
  setIndicator: (selectedIndicator) => set({ selectedIndicator }),
  toggleFullscreen: () => set((s) => ({ fullscreen: !s.fullscreen })),
  toggleTypewriter: () => set((s) => ({ typewriterEnabled: !s.typewriterEnabled })),
}))
