import { useEffect, useLayoutEffect, useMemo, useRef } from 'react';
import type { AnalyzeResponse } from '../api/types';

type Kind = 'ok' | 'fix' | 'err';
const prio: Record<Kind, number> = { ok: 1, fix: 2, err: 3 };

export function buildSegments(text: string, data: AnalyzeResponse | null) {
  const marks: { s: number; e: number; k: Kind }[] = [];
  if (data && data.text === text) {
    for (const c of data.characteristics) {
      if (!c.span) continue;
      marks.push({ s: c.span.start, e: c.span.end, k: c.status === 'error' ? 'err' : c.status === 'corrected' ? 'fix' : 'ok' });
    }
    for (const i of data.issues) {
      if (!i.span) continue;
      marks.push({ s: i.span.start, e: i.span.end, k: i.severity === 'error' ? 'err' : 'fix' });
    }
  }
  const cuts = new Set<number>([0, text.length]);
  marks.forEach((m) => { cuts.add(Math.max(0, Math.min(text.length, m.s))); cuts.add(Math.max(0, Math.min(text.length, m.e))); });
  const pts = [...cuts].sort((a, b) => a - b);
  const segs: { t: string; k: Kind | null }[] = [];
  for (let i = 0; i < pts.length - 1; i++) {
    const [a, b] = [pts[i], pts[i + 1]];
    if (a === b) continue;
    let k: Kind | null = null;
    for (const m of marks) if (m.s <= a && m.e >= b && (!k || prio[m.k] > prio[k])) k = m.k;
    segs.push({ t: text.slice(a, b), k });
  }
  return segs;
}

interface Props {
  value: string; data: AnalyzeResponse | null; onChange: (v: string) => void; max?: number;
}

export default function Highlight({ value, data, onChange, max = 2000 }: Props) {
  const ta = useRef<HTMLTextAreaElement>(null);
  const segs = useMemo(() => buildSegments(value, data), [value, data]);

  const fit = () => { const el = ta.current; if (el) { el.style.height = 'auto'; el.style.height = el.scrollHeight + 'px'; } };
  useLayoutEffect(fit, [value]);
  useEffect(() => { window.addEventListener('resize', fit); return () => window.removeEventListener('resize', fit); }, []);

  return (
    <div className="hl-wrap">
      <div className="hl-mirror" aria-hidden="true">
        {segs.map((s, i) => (s.k ? <mark key={i} className={`hl hl-${s.k}`}>{s.t}</mark> : <span key={i}>{s.t}</span>))}
        {'\n'}
      </div>
      <textarea
        ref={ta} id="desc" className="hl-input" value={value} maxLength={max} rows={4}
        placeholder="Например: молоток слесарный 500 г, длина рукоятки 300 мм"
        aria-describedby="desc-help desc-count" spellCheck={false}
        onChange={(e) => onChange(e.target.value)}
      />
    </div>
  );
}
