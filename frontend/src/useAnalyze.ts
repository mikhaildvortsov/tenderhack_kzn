import { useCallback, useEffect, useRef, useState } from 'react';
import { analyze, ApiError } from './api/client';
import type { AnalyzeResponse, Override } from './api/types';

export interface AnalyzeState {
  text: string; overrides: Override[]; ignored: string[]; selected: string | null;
}

/** debounce 400 мс, отмена предыдущего запроса, прошлый результат сохраняется пока идёт новый. */
export function useAnalyze(initialText: string) {
  const [state, setState] = useState<AnalyzeState>({ text: initialText, overrides: [], ignored: [], selected: null });
  const [data, setData] = useState<AnalyzeResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [retryTick, setRetryTick] = useState(0);
  const immediate = useRef(false);

  useEffect(() => {
    const ctrl = new AbortController();
    const delay = immediate.current ? 0 : 400;
    immediate.current = false;
    setLoading(true);
    const t = setTimeout(async () => {
      try {
        const res = await analyze({
          text: state.text, overrides: state.overrides, ignored_issues: state.ignored, selected_code: state.selected,
        }, ctrl.signal);
        setData(res); setError(null); setLoading(false);
      } catch (e) {
        if ((e as Error).name === 'AbortError') return;
        setError(e instanceof ApiError && e.network
          ? 'Нет связи с сервером анализа. Проверьте подключение к интернету — введённый текст сохранён.'
          : e instanceof ApiError && e.status != null && e.status >= 500
            ? 'Сервер временно не справился с запросом. Повторите попытку через минуту — введённый текст сохранён.'
            : e instanceof ApiError && e.status === 422
              ? 'Описание не удалось обработать. Проверьте текст: он не должен быть пустым или длиннее 2000 символов.'
              : 'Что-то пошло не так. Повторите попытку — введённый текст сохранён.');
        setLoading(false);
      }
    }, delay);
    return () => { clearTimeout(t); ctrl.abort(); };
  }, [state, retryTick]);

  const setText = useCallback((text: string, now = false) => {
    immediate.current = now;
    setState((s) => ({ ...s, text, overrides: [], selected: null }));
  }, []);
  const setOverride = useCallback((o: Override) => {
    immediate.current = true;
    setState((s) => ({ ...s, overrides: [...s.overrides.filter((x) => x.name !== o.name), o] }));
  }, []);
  const clearOverride = useCallback((name: string) => {
    immediate.current = true;
    setState((s) => ({ ...s, overrides: s.overrides.filter((x) => x.name !== name) }));
  }, []);
  const ignore = useCallback((id: string) => {
    immediate.current = true;
    setState((s) => ({ ...s, ignored: [...s.ignored, id] }));
  }, []);
  const select = useCallback((code: string | null) => {
    immediate.current = true;
    setState((s) => ({ ...s, selected: code }));
  }, []);
  const retry = useCallback(() => { immediate.current = true; setRetryTick((n) => n + 1); }, []);

  return { state, data, loading, error, setText, setOverride, clearOverride, ignore, select, retry };
}
