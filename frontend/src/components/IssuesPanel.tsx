import { useState } from 'react';
import type { AnalyzeResponse, Issue } from '../api/types';
import { Card } from './ui';

const TYPE_LABEL: Record<Issue['type'], string> = {
  typo: 'Опечатка', layout: 'Раскладка', unit_mismatch: 'Единица измерения', value_not_allowed: 'Недопустимое значение',
  out_of_range: 'Вне диапазона', missing_required: 'Не хватает данных', contradiction: 'Противоречие',
  unknown_characteristic: 'Неизвестная характеристика', category_mismatch: 'Категория',
};
const SEV_LABEL = { error: 'Ошибка', warning: 'Предупреждение', info: 'Подсказка' } as const;

function Icon({ sev }: { sev: Issue['severity'] }) {
  return <span className={`sev sev-${sev}`} role="img" aria-label={SEV_LABEL[sev]}>{sev === 'info' ? 'i' : '!'}</span>;
}

function IssueItem({ issue, onFix, onIgnore }: { issue: Issue; onFix: (i: Issue) => void; onIgnore: (id: string) => void }) {
  const [open, setOpen] = useState(false);
  return (
    <li className={`issue issue-${issue.severity}`}>
      <Icon sev={issue.severity} />
      <div className="issue-body">
        <div className="issue-top">
          <span className="chip chip-type">{TYPE_LABEL[issue.type]}</span>
          {issue.auto_applied && <span className="chip chip-ok">исправлено автоматически</span>}
        </div>
        <p className="issue-msg">{issue.message}</p>
        {issue.span && <p className="issue-frag">Фрагмент: <code>{issue.span.text}</code></p>}
        <button type="button" className="linkbtn" aria-expanded={open} onClick={() => setOpen(!open)}>
          {open ? 'Скрыть пояснение' : 'Почему так?'}
        </button>
        {open && <p className="issue-reason">{issue.reason}</p>}
        <div className="issue-actions">
          {issue.suggestion && issue.span && (
            <button type="button" className="btn btn-primary btn-sm" onClick={() => onFix(issue)}>
              {issue.suggestion.label || 'Исправить'}
            </button>
          )}
          <button type="button" className="btn btn-ghost btn-sm" title="Скрыть эту подсказку" onClick={() => onIgnore(issue.id)}>Пропустить</button>
        </div>
      </div>
    </li>
  );
}

interface Props {
  data: AnalyzeResponse | null; text: string;
  onReplace: (text: string) => void; onIgnore: (id: string) => void; onAppend: (chunk: string) => void;
}

export default function IssuesPanel({ data, text, onReplace, onIgnore, onAppend }: Props) {
  const issues = data?.issues ?? [];
  const recs = data?.recommendations ?? [];
  const fix = (i: Issue) => {
    if (!i.span || !i.suggestion) return;
    const cur = text.slice(i.span.start, i.span.end);
    const at = cur === i.span.text ? i.span.start : text.indexOf(i.span.text);
    if (at < 0) return;
    onReplace(text.slice(0, at) + i.suggestion.replacement + text.slice(at + i.span.text.length));
  };
  const count = issues.length;
  return (
    <Card id="h-issues" title="Ошибки и подсказки" aside={count ? <span className="count-badge" aria-label={`Найдено подсказок: ${count}`}>{count}</span> : null}>
      {data && count === 0 && recs.length === 0 && (
        <p className="ok-note"><span className="sev sev-ok" aria-hidden="true">✓</span> Всё в порядке: ошибок не найдено, описание согласуется со справочником КТРУ.</p>
      )}
      {!data && <p className="muted">Здесь появятся опечатки, неверные единицы и недостающие характеристики — с кнопкой быстрого исправления.</p>}
      {count > 0 && (
        <ul className="issues">{issues.map((i) => <IssueItem key={i.id} issue={i} onFix={fix} onIgnore={onIgnore} />)}</ul>
      )}
      {recs.length > 0 && (
        <div className="recs">
          <h3>Что уточнить, чтобы сузить выбор</h3>
          {recs.map((r) => (
            <div className="rec" key={r.id}>
              <p className="rec-msg"><strong>{r.message}</strong>
                {r.expected_remaining != null && <span className="muted"> — останется вариантов: {r.expected_remaining}</span>}
              </p>
              {r.options.length > 0 && (
                <div className="chips" role="group" aria-label={`Варианты: ${r.message}`}>
                  {r.options.map((o) => (
                    <button type="button" key={o} className="chip chip-btn"
                      onClick={() => onAppend(r.characteristic ? `, ${r.characteristic.toLowerCase()} ${o}` : (text.trim() ? `, ${o.toLowerCase()}` : o))}>
                      + {o}
                    </button>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}
