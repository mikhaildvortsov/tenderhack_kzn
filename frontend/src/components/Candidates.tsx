import type { Candidate } from '../api/types';
import { Card, pct } from './ui';

interface Props {
  items: Candidate[]; total: number; selected: string | null; finalCode?: string;
  onPick: (c: Candidate) => void; onClear: () => void;
}

export default function Candidates({ items, total, selected, finalCode, onPick, onClear }: Props) {
  return (
    <Card id="h-cand" title="Кандидаты КТРУ"
      aside={<span className="muted small">{items.length ? `показано ${items.length} из ${total}` : ''}</span>}>
      {items.length === 0 ? <p className="muted">Здесь появятся подходящие позиции КТРУ. Нажмите на позицию, чтобы увидеть её характеристики.</p> : (
        <>
          <ul className="cands">
            {items.map((c) => (
              <li key={c.code}>
                <button type="button" className={`cand${selected === c.code ? ' sel' : ''}${finalCode === c.code ? ' fin' : ''}`}
                  aria-pressed={selected === c.code} onClick={() => onPick(c)}>
                  <span className="cand-top"><code>{c.code}</code><span className="cand-m">{c.matched_chars}/{c.total_chars} характеристик</span></span>
                  <span className="cand-name">{c.name}</span>
                  <span className="cand-bar" role="img" aria-label={`Релевантность ${pct(c.score)}`}><span style={{ width: pct(Math.min(1, c.score)) }} /></span>
                  <span className="cand-sc">{pct(c.score)}</span>
                </button>
              </li>
            ))}
          </ul>
          {selected && <button type="button" className="linkbtn" onClick={onClear}>Отменить ручной выбор</button>}
        </>
      )}
    </Card>
  );
}
