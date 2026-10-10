import { useId, useState, type ReactNode } from 'react';

export function Info({ text, label = 'Пояснение' }: { text: string; label?: string }) {
  const id = useId();
  return (
    <span className="tip">
      <button type="button" className="tip-btn" aria-label={label} aria-describedby={id}
        onKeyDown={(e) => { if (e.key === 'Escape') (e.currentTarget as HTMLElement).blur(); }}>i</button>
      <span role="tooltip" id={id} className="tip-body">{text}</span>
    </span>
  );
}

export function Card({ title, children, aside, id }: { title: string; children: ReactNode; aside?: ReactNode; id?: string }) {
  return (
    <section className="card" aria-labelledby={id}>
      <header className="card-h"><h2 id={id}>{title}</h2>{aside}</header>
      {children}
    </section>
  );
}

export function CopyButton({ value, label = 'Копировать' }: { value: string; label?: string }) {
  const [done, setDone] = useState(false);
  const copy = async () => {
    try { await navigator.clipboard.writeText(value); } catch {
      const ta = document.createElement('textarea'); ta.value = value; document.body.appendChild(ta); ta.select();
      try { document.execCommand('copy'); } catch { /* ignore */ }
      ta.remove();
    }
    setDone(true); setTimeout(() => setDone(false), 1800);
  };
  return <><button type="button" className="btn btn-ghost btn-sm" onClick={copy}>{done ? 'Скопировано' : label}</button><span className="sr-only" role="status">{done ? 'Код скопирован в буфер обмена' : ''}</span></>;
}

export const pct = (x: number) => `${Math.round(x * 100)}%`;
