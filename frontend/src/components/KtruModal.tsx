import { useEffect, useRef, useState } from 'react';
import { getKtru } from '../api/client';
import type { KtruPosition } from '../api/types';

export default function KtruModal({ code, onClose }: { code: string; onClose: () => void }) {
  const [pos, setPos] = useState<KtruPosition | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const boxRef = useRef<HTMLElement>(null);

  useEffect(() => {
    const ctrl = new AbortController();
    setPos(null); setErr(null);
    getKtru(code, ctrl.signal).then(setPos).catch((e) => {
      if (e.name !== 'AbortError') setErr(e.status === 404 ? 'Позиция не найдена в справочнике.' : 'Не удалось загрузить карточку КТРУ. Закройте окно и откройте позицию снова.');
    });
    return () => ctrl.abort();
  }, [code]);

  useEffect(() => {
    const prev = document.activeElement as HTMLElement | null;
    closeRef.current?.focus();
    const h = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
      if (e.key !== 'Tab' || !boxRef.current) return;
      const f = boxRef.current.querySelectorAll<HTMLElement>('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])');
      if (!f.length) return;
      const first = f[0], last = f[f.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    };
    document.addEventListener('keydown', h);
    return () => { document.removeEventListener('keydown', h); prev?.focus(); };
  }, [onClose]);

  return (
    <div className="overlay" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <aside ref={boxRef} className="drawer" role="dialog" aria-modal="true" aria-labelledby="m-title">
        <header className="drawer-h">
          <div>
            <p className="muted small">Карточка позиции КТРУ</p>
            <h2 id="m-title">{pos?.name ?? code}</h2>
            <code className="code code-sm">{code}</code>
          </div>
          <button ref={closeRef} type="button" className="btn btn-ghost" onClick={onClose} aria-label="Закрыть карточку">×</button>
        </header>
        {err && <p className="alert alert-err" role="alert">{err}</p>}
        {!pos && !err && <p className="muted" role="status">Загружаем карточку…</p>}
        {pos && (
          <>
            <dl className="res-meta">
              <div><dt>ОКПД2</dt><dd>{pos.okpd2_code} — {pos.okpd2_name}</dd></div>
              <div><dt>Единица</dt><dd>{pos.unit ?? '—'}</dd></div>
              <div><dt>Статус</dt><dd>{pos.status === 'ACTIVE' ? 'Действует' : pos.status}</dd></div>
            </dl>
            <h3>Характеристики и допустимые значения</h3>
            <ul className="kch">
              {pos.characteristics.map((c) => (
                <li key={c.code ?? c.name}>
                  <div className="kch-n">{c.name}{c.required && <span className="req">обязательная</span>}</div>
                  <div className="chips">{c.values.slice(0, 30).map((v, i) => <span key={i} className="chip">{v.display}</span>)}
                    {c.values.length === 0 && <span className="muted">любое значение</span>}</div>
                </li>
              ))}
            </ul>
          </>
        )}
      </aside>
    </div>
  );
}
