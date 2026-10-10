import { useEffect, useRef } from 'react';

const SYMBOLS = [
  'AAPL', 'TSLA', 'NVDA', 'MSFT', 'AMZN', 'GOOG', 'META', 'AMD', 'INTC', 'NFLX',
  'JPM', 'V', 'XOM', 'SPY', 'QQQ', 'BABA', '0700.HK', '9988.HK', 'BTC', 'ETH',
];

const UP_COLOR = '#00ff88';
const DOWN_COLOR = '#ff3355';
const FONT_SIZE = 17;
const ROW_H = 38;
const COL_W = 235;
const TEXT_ALPHA = 0.25;
const HALO_ALPHA = 0.09; // faint second pass, no shadowBlur (GPU-expensive)
const MAX_DT = 0.05; // clamp tab-switch jumps
const FADE_H = 90; // px of vertical fade at the top and bottom edges

interface Row {
  text: string;
  color: string;
}

interface Column {
  x: number; // center x of the column
  rows: Row[];
  offset: number; // continuous float in [0, ROW_H)
  speed: number; // px per second
  dir: 1 | -1;
}

function randomRow(): Row {
  const up = Math.random() < 0.5;
  const symbol = SYMBOLS[(Math.random() * SYMBOLS.length) | 0];
  const price = (20 + Math.random() * 900).toFixed(2);
  const pct = (Math.random() * 4).toFixed(2);
  return {
    text: `${symbol} ${price} ${up ? '▲' : '▼'}${up ? '+' : '-'}${pct}%`,
    color: up ? UP_COLOR : DOWN_COLOR,
  };
}

export default function Background() {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    let raf = 0;
    let columns: Column[] = [];
    let width = 0;
    let height = 0;
    let last = performance.now();
    let topFade: CanvasGradient | null = null;
    let bottomFade: CanvasGradient | null = null;

    const setup = () => {
      const dpr = window.devicePixelRatio || 1;
      width = window.innerWidth;
      height = window.innerHeight;
      canvas.width = width * dpr;
      canvas.height = height * dpr;
      canvas.style.width = `${width}px`;
      canvas.style.height = `${height}px`;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      // Text style is stateful on the context: set once here, not per frame.
      ctx.font = `${FONT_SIZE}px "SF Mono", "Cascadia Code", Consolas, monospace`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';

      // Distribute columns evenly and center the whole block: any leftover
      // width is split equally on both sides instead of hugging the left edge.
      const colCount = Math.max(1, Math.floor(width / COL_W));
      const margin = (width - colCount * COL_W) / 2;
      const rowsPerCol = Math.ceil(height / ROW_H) + 3;
      columns = Array.from({ length: colCount }, (_, i) => ({
        x: margin + i * COL_W + COL_W / 2,
        rows: Array.from({ length: rowsPerCol }, randomRow),
        offset: Math.random() * ROW_H,
        speed: 20 + Math.random() * 35,
        dir: i % 2 === 0 ? 1 : -1,
      }));

      // Edge fade gradients, rebuilt on resize. Applied with destination-out
      // so rows fade out smoothly instead of popping at the viewport edge.
      topFade = ctx.createLinearGradient(0, 0, 0, FADE_H);
      topFade.addColorStop(0, 'rgba(0,0,0,1)');
      topFade.addColorStop(1, 'rgba(0,0,0,0)');
      bottomFade = ctx.createLinearGradient(0, height - FADE_H, 0, height);
      bottomFade.addColorStop(0, 'rgba(0,0,0,0)');
      bottomFade.addColorStop(1, 'rgba(0,0,0,1)');
    };

    const draw = () => {
      ctx.clearRect(0, 0, width, height);
      for (const col of columns) {
        for (let i = 0; i < col.rows.length; i++) {
          const y = (i - 1) * ROW_H + col.offset;
          if (y < -ROW_H || y > height + ROW_H) continue;
          const row = col.rows[i];
          // Cheap fake glow: 4 low-alpha offset copies, then the crisp text.
          ctx.globalAlpha = HALO_ALPHA;
          ctx.fillStyle = row.color;
          ctx.fillText(row.text, col.x - 1, y);
          ctx.fillText(row.text, col.x + 1, y);
          ctx.fillText(row.text, col.x, y - 1);
          ctx.fillText(row.text, col.x, y + 1);
          ctx.globalAlpha = TEXT_ALPHA;
          ctx.fillText(row.text, col.x, y);
        }
      }
      if (topFade && bottomFade) {
        ctx.globalCompositeOperation = 'destination-out';
        ctx.globalAlpha = 1;
        ctx.fillStyle = topFade;
        ctx.fillRect(0, 0, width, FADE_H);
        ctx.fillStyle = bottomFade;
        ctx.fillRect(0, height - FADE_H, width, FADE_H);
        ctx.globalCompositeOperation = 'source-over';
      }
    };

    const tick = (now: number) => {
      const dt = Math.min((now - last) / 1000, MAX_DT);
      last = now;
      for (const col of columns) {
        // True marquee: offset is a continuous float, and rows only enter
        // from the off-screen end / are recycled after fully leaving the
        // other end. A visible row's content and color never change in place.
        if (col.dir === 1) {
          // Scrolling down: rows enter at the top, exit at the bottom.
          col.offset += col.speed * dt;
          if (col.offset >= ROW_H) {
            col.offset -= ROW_H;
            col.rows.pop(); // bottom row is fully off-screen -> recycle
            col.rows.unshift(randomRow()); // new row spawns above the viewport
          }
        } else {
          // Scrolling up: rows enter at the bottom, exit at the top.
          col.offset -= col.speed * dt;
          if (col.offset < 0) {
            col.offset += ROW_H;
            col.rows.shift(); // top row is fully off-screen -> recycle
            col.rows.push(randomRow()); // new row spawns below the viewport
          }
        }
      }
      draw();
      raf = requestAnimationFrame(tick);
    };

    setup();
    if (reducedMotion) {
      draw(); // static frame only, no animation
    } else {
      raf = requestAnimationFrame(tick);
    }

    const onResize = () => {
      setup();
      if (reducedMotion) draw();
    };
    window.addEventListener('resize', onResize);

    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener('resize', onResize);
    };
  }, []);

  return <canvas ref={canvasRef} className="background-canvas" aria-hidden="true" />;
}
