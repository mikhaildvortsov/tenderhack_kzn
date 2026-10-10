import type { AnalyzeResponse } from '../api/types';
import { CopyButton } from './ui';

export default function Result({ data, stale }: { data: AnalyzeResponse | null; stale: boolean }) {
  if (!data || data.status === 'empty') {
    return (
      <div className="res res-empty">
        <p className="res-title">Здесь появится код КТРУ</p>
        <p className="muted">Опишите товар в поле слева: название и ключевые характеристики через запятую. Например:</p>
        <code className="example-code">молоток слесарный 500 г, длина рукоятки 300 мм</code>
        <p className="muted">Пока работаем с тремя категориями: инструменты, мебель, одежда.</p>
      </div>
    );
  }
  const cls = `res res-${data.status}${stale ? ' is-stale' : ''}`;
  if (data.status === 'resolved' && data.final) {
    const f = data.final;
    return (
      <div className={cls}>
        <div className="res-head"><span className="res-ico" aria-hidden="true">✓</span><p className="res-title">Код КТРУ определён</p></div>
        <div className="code-row">
          <code className="code" data-testid="ktru-code">{f.code}</code>
          <CopyButton value={f.code} label="Копировать код" />
        </div>
        <p className="res-name">{f.name}</p>
        <dl className="res-meta">
          <div><dt>ОКПД2</dt><dd>{f.okpd2_code} — {f.okpd2_name}</dd></div>
          <div><dt>Единица измерения</dt><dd>{f.unit ?? '—'}</dd></div>
          <div><dt>Категория</dt><dd>{data.category.name}</dd></div>
        </dl>
      </div>
    );
  }
  if (data.status === 'ambiguous') {
    return (
      <div className={cls}>
        <div className="res-head"><span className="res-ico" aria-hidden="true">?</span>
          <p className="res-title">Найдено {data.candidates_total} {plural(data.candidates_total)} — уточните данные</p></div>
        <p>Описания не хватает для одного кода. Добавьте уточнения из блока «Что уточнить» слева или выберите подходящую позицию в списке кандидатов.</p>
      </div>
    );
  }
  return (
    <div className={cls}>
      <div className="res-head"><span className="res-ico" aria-hidden="true">×</span><p className="res-title">Подходящих позиций КТРУ не найдено</p></div>
      <p>Проверьте название товара и значения характеристик. Нажмите «Исправить» у подсказок слева или начните с названия, например «молоток слесарный».</p>
    </div>
  );
}

function plural(n: number) {
  const m10 = n % 10, m100 = n % 100;
  if (m10 === 1 && m100 !== 11) return 'позиция';
  if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return 'позиции';
  return 'позиций';
}
