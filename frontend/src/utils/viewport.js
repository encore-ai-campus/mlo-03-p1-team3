// iOS는 키보드가 열려도 레이아웃 높이를 줄이지 않아 하단 버튼이 가려진다.
// 실제로 보이는 영역을 CSS 변수로 넘겨 앱 프레임을 그 크기에 맞춘다.
export function trackVisualViewport() {
  const viewport = window.visualViewport
  if (!viewport) return

  const root = document.documentElement
  const sync = () => {
    root.style.setProperty('--viewport-top', `${viewport.offsetTop}px`)
    root.style.setProperty('--viewport-height', `${viewport.height}px`)
  }

  viewport.addEventListener('resize', sync)
  viewport.addEventListener('scroll', sync)
  sync()
}
