import { useEffect, useState } from 'react';
import type { CharStatus, ExtractedCharacteristic } from '../api/types';
import { Card, Info, pct } from './ui';

const ST: Record<CharStatus, { t: string; c: string }> = {
  ok: { t: 'OK', c: 'ok' }, corrected: { t: 'Исправлено', c: 'warn' }, error: { t: 'Ошибка', c: 'err' },
  missing: { t: 'Не указана', c: 'muted' }, suggested: { t: 'Предложено', c: 'info' },
};

function ValueCell({ c, onCommit }: { c: ExtractedCharacteristic; onCommit: (c: ExtractedCharacteristic, v: string) => void }) {
  const [v, setV] = useState(c.value ?? '');
  useEffect(() => setV(c.value ?? ''), [c.value]);
  const commit = (val: string) => { if (val.trim() && val !== (c.value ?? '')) onCommit(c, val.trim()); };
  const label = `Значение: ${c.name}`;
  if (c.value_kind === 'qualitative' && c.allowed_values.length > 0) {
    const opts = c.allowed_values.includes(v) || !v ? c.allowed_values : [v, ...c.allowed_values];
    return (
      <select className="cell-in" aria-label={label} value={v} onChange={(e) => { setV(e.target.value); commit(e.target.value); }}>
        {!v && <option value="">— выберите —</option>}
        {opts.map((o) => <option key={o} value={o}>{o}</option>)}
      </select>
    );
  }
  const listId = `dl-${c.id}`;
  return (
    <>
      <input className="cell-in" aria-label={label} value={v} placeholder="—" list={c.allowed_values.length ? listId : undefined}
        inputMode={c.value_kind === 'quantitative' ? 'decimal' : 'text'}
        onChange={(e) => setV(e.target.value)} onBlur={(e) => commit(e.target.value)}
        onKeyDown={(e) => { if (e.key === 'Enter') commit((e.target as HTMLInputElement).value); }} />
      {c.allowed_values.length > 0 && <datalist id={listId}>{c.allowed_values.map((o) => <option key={o} value={o} />)}</datalist>}
    </>
  );
}

interface Props {
  items: ExtractedCharacteristic[]; overridden: Set<string>;
  onEdit: (c: ExtractedCharacteristic, v: string) => void; onReset: (name: string) => void;
}

export default function CharTable({ items, onEdit, onReset, overridden }: Props) {
  return (
    <Card id="h-chars" title="Характеристики">
      {items.length === 0 ? <p className="muted">Характеристики появятся после распознавания товара.</p> : (
        <div className="table-wrap">
          <table className="tbl">
            <thead>
              <tr><th scope="col">Характеристика</th><th scope="col">Значение</th><th scope="col">Ед.</th><th scope="col">Статус</th><th scope="col">Уверенность</th></tr>
            </thead>
            <tbody>
              {items.map((c) => {
                const s = ST[c.status];
                return (
                  <tr key={c.id} className={`row-${c.status}`}>
                    <th scope="row" data-label="Характеристика">
                      <span className="cn">{c.name}</span>
                      {c.required && <span className="req" title="Обязательная характеристика">обязательная</span>}
                      {c.raw_value && c.raw_value !== c.value && (
                        <span className="raw">во вводе: {c.raw_value}{c.raw_unit ? ' ' + c.raw_unit : ''}</span>
                      )}
                    </th>
                    <td data-label="Значение">
                      <ValueCell c={c} onCommit={onEdit} />
                      {overridden.has(c.name) && <button type="button" className="linkbtn small" onClick={() => onReset(c.name)}>сбросить правку</button>}
                    </td>
                    <td data-label="Ед." className="unit">{c.unit ?? '—'}</td>
                    <td data-label="Статус"><span className={`badge badge-${s.c}`}>{s.t}</span></td>
                    <td data-label="Уверенность">
                      <div className="conf">
                        <div className="conf-bar" role="img" aria-label={`Уверенность ${pct(c.confidence)}`}>
                          <div className={`conf-fill ${c.confidence >= 0.8 ? 'hi' : c.confidence >= 0.5 ? 'mid' : 'lo'}`} style={{ width: pct(c.confidence) }} />
                        </div>
                        <span className="conf-n">{pct(c.confidence)}</span>
                        {c.reason && <Info text={c.reason} label={`Почему так: ${c.name}`} />}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}
