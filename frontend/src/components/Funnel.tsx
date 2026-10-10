import type { NarrowingStep } from '../api/types';
import { Card } from './ui';

const STAGE: Record<NarrowingStep['stage'], string> = {
  category: 'Категория', name: 'Наименование', characteristic: 'Характеристика', ranking: 'Ранжирование',
};

export default function Funnel({ steps }: { steps: NarrowingStep[] }) {
  const total = steps[0]?.before || 1;
  return (
    <Card id="h-funnel" title="Сужение кодов КТРУ">
      {steps.length === 0 ? <p className="muted">Здесь появится воронка: как от всего справочника мы приходим к нескольким позициям.</p> : (
        <ol className="funnel">
          {steps.map((s, i) => {
            const w = Math.max(2, (s.after / total) * 100);
            const dropped = s.before - s.after;
            return (
              <li key={s.step} className="f-step" tabIndex={0}>
                <span className="f-dot" aria-hidden="true">{i + 1}</span>
                <div className="f-main">
                  <div className="f-top">
                    <span className="f-stage">{STAGE[s.stage]}</span>
                    <span className="f-label">{s.label}</span>
                  </div>
                  <div className="f-nums"><span>{s.before}</span><span aria-hidden="true"> → </span><span className="sr-only"> сократилось до </span><strong>{s.after}</strong>
                    {dropped > 0 && <span className="muted"> (−{dropped})</span>}</div>
                  <div className="bar" role="img" aria-label={`Осталось ${s.after} из ${total}`}>
                    <div className="bar-fill" style={{ width: `${w}%` }} />
                  </div>
                  {s.excluded_sample.length > 0 && (
                    <div className="f-pop" role="tooltip">
                      <strong>Исключены, например:</strong>
                      {s.excluded_sample.map((c) => <code key={c}>{c}</code>)}
                    </div>
                  )}
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </Card>
  );
}
