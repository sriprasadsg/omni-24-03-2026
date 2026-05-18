// ─── State ─────────────────────────────────────────────────────────────────────

const N = PAGES.length;   // number of leaves (9 → states 0..9)

let state       = 0;      // 0 = cover only, N = back cover only
let isAnimating = false;

// ─── DOM refs ──────────────────────────────────────────────────────────────────

const scene        = document.getElementById('scene');
const stage        = document.getElementById('stage');
const bookWrapper  = document.getElementById('book-wrapper');
const leftPanel    = document.getElementById('left-panel');
const rightPanel   = document.getElementById('right-panel');
const leftContent  = document.getElementById('left-content');
const rightContent = document.getElementById('right-content');
const spine        = document.getElementById('spine');
const pageStack    = document.getElementById('page-stack');
const flipper      = document.getElementById('flipper');
const flipFront    = document.getElementById('flipper-front');
const flipBack     = document.getElementById('flipper-back');
const zoneRight    = document.getElementById('zone-right');
const zoneLeft     = document.getElementById('zone-left');
const dotsEl       = document.getElementById('dots');
const btnPrev      = document.getElementById('btn-prev');
const btnNext      = document.getElementById('btn-next');
const tip          = document.getElementById('tip');

// ─── Helpers ───────────────────────────────────────────────────────────────────

function leftFace(s)  { return s === 0 ? null : PAGES[s - 1].back; }
function rightFace(s) { return s === N ? null : PAGES[s].front;     }

// ─── Render (static state, no animation) ──────────────────────────────────────

function render(s) {
  const lf = leftFace(s);
  leftContent.innerHTML = lf || '';
  leftPanel.classList.toggle('visible', !!lf);

  const rf = rightFace(s);
  rightContent.innerHTML = rf || '';

  bookWrapper.classList.toggle('open', s > 0);
  spine.classList.toggle('visible',    s > 0);
  pageStack.style.opacity = s === 0 ? '1' : '0';

  btnPrev.disabled = s === 0;
  btnNext.disabled = s === N;
  zoneLeft.style.cursor  = s > 0 && !isAnimating ? 'pointer' : 'default';
  zoneRight.style.cursor = s < N && !isAnimating ? 'pointer' : 'default';

  dotsEl.querySelectorAll('.page-dot').forEach((d, i) => {
    d.classList.toggle('active', i === s);
  });
}

// ─── Forward flip (right page turns to become left page) ──────────────────────

function turnForward() {
  if (isAnimating || state >= N) return;
  isAnimating = true;

  const ffHTML = PAGES[state].front;
  const fbHTML = PAGES[state].back;
  const nextRF = state + 1 < N ? PAGES[state + 1].front : '';

  flipper.style.cssText =
    'display:block;left:340px;width:340px;transform-origin:left center;transform:rotateY(0deg);transition:none;';
  flipFront.innerHTML = ffHTML;
  flipBack.innerHTML  = fbHTML;

  rightContent.innerHTML = nextRF;

  requestAnimationFrame(() => requestAnimationFrame(() => {
    flipper.style.transition = 'transform 0.75s cubic-bezier(0.645,0.045,0.355,1)';
    flipper.style.transform  = 'rotateY(-180deg)';
  }));

  setTimeout(() => {
    state++;
    flipper.style.display    = 'none';
    flipper.style.transition = '';
    render(state);
    isAnimating = false;
  }, 780);
}

// ─── Backward flip (left page turns back to become right page) ────────────────

function turnBackward() {
  if (isAnimating || state <= 0) return;
  isAnimating = true;

  const ffHTML = PAGES[state - 1].back;
  const fbHTML = PAGES[state - 1].front;
  const prevLF = state - 1 === 0 ? null : PAGES[state - 2].back;

  flipper.style.cssText =
    'display:block;left:0;width:340px;transform-origin:right center;transform:rotateY(0deg);transition:none;';
  flipFront.innerHTML = ffHTML;
  flipBack.innerHTML  = fbHTML;

  leftContent.innerHTML = prevLF || '';
  leftPanel.classList.toggle('visible', !!prevLF);

  requestAnimationFrame(() => requestAnimationFrame(() => {
    flipper.style.transition = 'transform 0.75s cubic-bezier(0.645,0.045,0.355,1)';
    flipper.style.transform  = 'rotateY(180deg)';
  }));

  setTimeout(() => {
    state--;
    flipper.style.display    = 'none';
    flipper.style.transition = '';
    render(state);
    isAnimating = false;
  }, 780);
}

// ─── Click handler ─────────────────────────────────────────────────────────────

function handleClick(side) {
  if (side === 'right') turnForward();
  else                  turnBackward();
}

// ─── Dots ──────────────────────────────────────────────────────────────────────

for (let i = 0; i <= N; i++) {
  const d = document.createElement('div');
  d.className = 'page-dot';
  d.onclick = () => jumpTo(i);
  dotsEl.appendChild(d);
}

function jumpTo(target) {
  if (target === state || isAnimating) return;
  state = target;
  render(state);
}

// ─── Keyboard ──────────────────────────────────────────────────────────────────

document.addEventListener('keydown', e => {
  if (e.key === 'ArrowRight' || e.key === 'ArrowDown') turnForward();
  if (e.key === 'ArrowLeft'  || e.key === 'ArrowUp')   turnBackward();
});

// ─── Touch swipe ───────────────────────────────────────────────────────────────

let tx = 0, ty = 0;
document.addEventListener('touchstart', e => {
  tx = e.changedTouches[0].screenX;
  ty = e.changedTouches[0].screenY;
}, { passive: true });
document.addEventListener('touchend', e => {
  const dx = e.changedTouches[0].screenX - tx;
  const dy = e.changedTouches[0].screenY - ty;
  if (Math.abs(dx) > Math.abs(dy) && Math.abs(dx) > 40) {
    if (dx < 0) turnForward(); else turnBackward();
  }
}, { passive: true });

// ─── Responsive scale ──────────────────────────────────────────────────────────

const BOOK_W = 680, BOOK_H = 500;

function rescale() {
  const pad = 16;
  const sc = Math.min(
    (stage.clientWidth  - pad) / BOOK_W,
    (stage.clientHeight - pad) / BOOK_H,
    1.0
  );
  scene.style.transform = `scale(${sc})`;
}
window.addEventListener('resize', rescale);
requestAnimationFrame(() => requestAnimationFrame(rescale));

// ─── Boot ──────────────────────────────────────────────────────────────────────

render(0);
setTimeout(() => tip.classList.add('hidden'), 5000);
