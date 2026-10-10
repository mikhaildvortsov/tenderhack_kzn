import { useState } from 'react';

const KEY = 'ktru-how-hidden';
const read = () => { try { return localStorage.getItem(KEY) === '1'; } catch { return false; } };

const STEPS = [
  ['Опишите товар', 'Название и ключевые параметры своими словами, как в обычном тексте.'],
  ['Проверьте подсказки', 'Исправим опечатки и единицы измерения, покажем, чего не хватает.'],
  ['Получите код КТРУ', 'Список кандидатов сужается на каждом шаге, значения можно поправить вручную.'],
] as const;

export default function HowItWorks() {
  const [hidden, setHidden] = useState(read);
  const hide = () => { setHidden(true); try { localStorage.setItem(KEY, '1'); } catch { /* ignore */ } };
  if (hidden) return <button type="button" className="linkbtn small how-show" onClick={() => setHidden(false)}>Как это работает?</button>;
  return (
    <section className="how" aria-label="Как это работает">
      <ol>
        {STEPS.map(([t, d], i) => (
          <li key={t}><span className="how-n" aria-hidden="true">{i + 1}</span><div><strong>{t}</strong><span>{d}</span></div></li>
        ))}
      </ol>
      <button type="button" className="linkbtn small" onClick={hide}>Скрыть</button>
    </section>
  );
}
