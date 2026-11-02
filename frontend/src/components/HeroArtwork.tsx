import { useState, type PointerEvent } from 'react'

// Chuyển động trang trí được tách khỏi dữ liệu AI/matching.
export function HeroArtwork() {
  const [paused, setPaused] = useState(false)

  function followPointer(event: PointerEvent<HTMLDivElement>) {
    if (paused || event.pointerType !== 'mouse' || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
    const bounds = event.currentTarget.getBoundingClientRect()
    const x = (event.clientX - bounds.left) / bounds.width - 0.5
    const y = (event.clientY - bounds.top) / bounds.height - 0.5
    event.currentTarget.style.setProperty('--tilt-x', `${-y * 9}deg`)
    event.currentTarget.style.setProperty('--tilt-y', `${x * 9}deg`)
  }

  function resetPointer(event: PointerEvent<HTMLDivElement>) {
    event.currentTarget.style.setProperty('--tilt-x', '0deg')
    event.currentTarget.style.setProperty('--tilt-y', '0deg')
  }

  return (
    <div className={`hero-art ${paused ? 'motion-paused' : ''}`}
      onPointerMove={followPointer} onPointerLeave={resetPointer}>
      <div className="art-scene" role="img" aria-label="AI가 나의 역량과 커리어를 연결하는 모습">
        <div className="orbit orbit-one" />
        <div className="orbit orbit-two" />
        <div className="orbit orbit-three" />
        <span className="orbit-dot dot-one" />
        <span className="orbit-dot dot-two" />
        <div className="floating-label top-label">
          <span className="tiny-spark">✦</span> YOUR POTENTIAL, CONNECTED</div>
        <div className="match-float">
          <span className="check-circle">✓</span>
          <div>
            <small>나에게 꼭 맞는 기회 발견!</small>
            <b>AI 매칭 완료</b>
          </div>
          <span className="float-stars">✦</span>
        </div>
        <div className="core-shape">
          <span>✳</span>
        </div>
        <div className="art-profile">
          <span className="profile-emoji">👩🏻‍💻</span>
          <div>
            <b>김지원님의 다음 챕터</b>
            <small>Frontend Developer</small>
          </div>
          <span className="profile-badge">✦</span>
        </div>
        <div className="score-float">
          <div className="score-ring">96<small>%</small>
          </div>
          <div>
            <b>완벽에 가까운 연결</b>
            <small>경험과 가능성을 함께 분석해요</small>
          </div>
        </div>
        <span className="art-caption">A LITTLE AI. A BIG NEXT STEP.</span>
        <span className="decor-spark">✧</span>
      </div>
      <button className="motion-toggle" aria-pressed={paused}
        aria-label={paused ? '장식 애니메이션 재생' : '장식 애니메이션 일시정지'}
        onClick={() => setPaused(value => !value)}>
        <span aria-hidden="true">{paused ? '▶' : 'Ⅱ'}</span>
        {paused ? '모션 재생' : '모션 일시정지'}
      </button>
    </div>
  )
}
