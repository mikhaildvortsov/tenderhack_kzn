import { useEffect, useMemo, useState } from 'react';
import { detectMode, getExamples, type Mode } from './api/client';
import type { Candidate, Example, ExtractedCharacteristic } from './api/types';
import { useAnalyze } from './useAnalyze';
import Header from './components/Header';
import Highlight from './components/Highlight';
import IssuesPanel from './components/IssuesPanel';
import Result from './components/Result';
import Funnel from './components/Funnel';
import CharTable from './components/CharTable';
import Candidates from './components/Candidates';
import KtruModal from './components/KtruModal';
import { Card } from './components/ui';
import HowItWorks from './components/HowItWorks';

const LOCAL_EXAMPLES: Example[] = [
  { category: 'Инструменты', text: 'Молоток слесарный 500 г, длина рукоятки 300 мм', note: '' },
  { category: 'Мебель', text: 'Стол письменный', note: '' },
  { category: 'Инструменты', text: 'Молатак слесарный, длина рукоятки 5 кг', note: '' },
];

const BADGE = {
  resolved: ['ok', 'Код определён'], ambiguous: ['warn', 'Неоднозначно'], not_found: ['err', 'Не найдено'], empty: ['muted', 'Ждём описание'],
} as const;

export default function App() {
  const a = useAnalyze('');
  const { state, data, loading, error } = a;
  const [examples, setExamples] = useState<Example[]>(LOCAL_EXAMPLES);
  const [mode, setMode] = useState<Mode | null>(null);
  const [modal, setModal] = useState<string | null>(null);

  useEffect(() => {
    detectMode().then(setMode);
    getExamples().then((e) => e.length && setExamples(e.slice(0, 6)));
  }, []);

  const overridden = useMemo(() => new Set(state.overrides.map((o) => o.name)), [state.overrides]);
  const status = loading && !data ? (['info', 'Анализ…'] as const) : data ? BADGE[data.status] : BADGE.empty;
  const len = state.text.length;

  const onEdit = (c: ExtractedCharacteristic, value: string) => a.setOverride({ name: c.name, value, unit: c.unit });
  const onPick = (c: Candidate) => { a.select(c.code); setModal(c.code); };
  const append = (chunk: string) => a.setText(state.text.replace(/[,\s]+$/, '') + chunk, true);

  return (
    <>
      <a className="skip" href="#desc">Перейти к вводу описания</a>
      <Header />
      <main className="page" id="top">
        <nav aria-label="Хлебные крошки" className="crumbs">
          <ol>
            <li><a href="#top">Главная</a></li><li><a href="#top">Каталог</a></li><li><a href="#top">Создание СТЕ</a></li>
            <li aria-current="page">Автозаполнение характеристик</li>
          </ol>
        </nav>
        <h1>Автозаполнение характеристик СТЕ по КТРУ</h1>

        {mode === 'mock' && (
          <p className="alert alert-info" role="status">Демонстрационный режим: сервер анализа недоступен, поэтому показаны тестовые данные. Результаты не относятся к реальному справочнику КТРУ.</p>
        )}
        {error && (
          <div className="alert alert-err" role="alert">
            <span><strong>Не получилось обновить результат.</strong> {error}{data ? ' Ниже — последний успешный результат.' : ''}</span>
            <button type="button" className="btn btn-primary btn-sm" onClick={a.retry}>Повторить попытку</button>
          </div>
        )}

        <div className="grid">
          <div className="col">
            <Card id="h-desc" title="Описание товара" aside={<span className={`badge badge-${status[0]}`} role="status" aria-live="polite">{status[1]}</span>}>
              <HowItWorks />
              <label htmlFor="desc" className="lbl">Опишите товар своими словами</label>
              <Highlight value={state.text} data={data} onChange={(v) => a.setText(v)} />
              <div className="meta-row">
                <p id="desc-help" className="muted small">
                  Подсветка в тексте: <span className="lg lg-ok" aria-hidden="true" /> распознано <span className="lg lg-fix" aria-hidden="true" /> исправлено <span className="lg lg-err" aria-hidden="true" /> требует внимания
                </p>
                <p id="desc-count" className={`small ${len > 1800 ? 'warn-t' : 'muted'}`}>{len} / 2000</p>
              </div>
              <div className="examples">
                <span className="muted small" id="ex-l">Не знаете, с чего начать? Нажмите на пример:</span>
                <div className="chips" role="group" aria-labelledby="ex-l">
                  {examples.map((e) => (
                    <button type="button" key={e.text} className="chip chip-btn" title={e.note || e.category} onClick={() => a.setText(e.text, true)}>{e.text}</button>
                  ))}
                </div>
              </div>
            </Card>
            <IssuesPanel data={data} text={state.text}
              onReplace={(t) => a.setText(t, true)} onIgnore={a.ignore} onAppend={append} />
          </div>

          <div className="col">
            <Card id="h-res" title="Подбор кода КТРУ"
              aside={loading && data ? <span className="spin" role="status" aria-label="Обновляем результат" /> : null}>
              <Result data={data} stale={loading && !!data} />
            </Card>
            <Funnel steps={data?.narrowing ?? []} />
            <CharTable items={data?.characteristics ?? []} overridden={overridden} onEdit={onEdit} onReset={a.clearOverride} />
            <Candidates items={data?.candidates ?? []} total={data?.candidates_total ?? 0} selected={state.selected}
              finalCode={data?.final?.code} onPick={onPick} onClear={() => a.select(null)} />
          </div>
        </div>

        <footer className="foot">
          {data?.timings_ms.total != null && <span>Анализ занял {Math.round(data.timings_ms.total)} мс</span>}
          <span>Подсказки носят рекомендательный характер. Если сомневаетесь, ориентируйтесь на справочник КТРУ.</span>
        </footer>
      </main>
      {modal && <KtruModal code={modal} onClose={() => setModal(null)} />}
    </>
  );
}
