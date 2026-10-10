import type { AnalyzeRequest, AnalyzeResponse, Example, KtruPosition, NarrowingStep } from './types';
import { MOCK_EXAMPLES, mockAnalyze, mockKtru } from './mock';

const BASE = '/api/v1';

export class ApiError extends Error {
  constructor(message: string, public status: number | null, public network = false) { super(message); }
}

export type Mode = 'api' | 'mock';
let mode: Mode | null = null;

const forcedMock = () => new URLSearchParams(window.location.search).get('mock') === '1';

/** Определяет режим один раз: ?mock=1 или недоступный /health => мок. */
export async function detectMode(): Promise<Mode> {
  if (mode) return mode;
  if (forcedMock()) return (mode = 'mock');
  try {
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), 2500);
    const r = await fetch('/health', { signal: ctrl.signal });
    clearTimeout(t);
    const ct = r.headers.get('content-type') ?? '';
    mode = r.ok && ct.includes('json') ? 'api' : 'mock';
  } catch {
    mode = 'mock';
  }
  return mode;
}

const sleep = (ms: number, signal?: AbortSignal) =>
  new Promise<void>((res, rej) => {
    const t = setTimeout(res, ms);
    signal?.addEventListener('abort', () => { clearTimeout(t); rej(new DOMException('aborted', 'AbortError')); });
  });

async function http<T>(url: string, init?: RequestInit): Promise<T> {
  let r: Response;
  try {
    r = await fetch(url, init);
  } catch (e) {
    if ((e as Error).name === 'AbortError') throw e;
    throw new ApiError('Нет связи с сервером', null, true);
  }
  if (!r.ok) {
    let detail = '';
    try { detail = JSON.stringify((await r.json()).detail ?? ''); } catch { /* ignore */ }
    throw new ApiError(`Сервер вернул ошибку ${r.status}${detail && detail !== '""' ? ': ' + detail : ''}`, r.status);
  }
  return r.json() as Promise<T>;
}

export async function analyze(req: AnalyzeRequest, signal?: AbortSignal): Promise<AnalyzeResponse> {
  if ((await detectMode()) === 'mock') {
    await sleep(350, signal);
    return mockAnalyze(req);
  }
  return http<AnalyzeResponse>(`${BASE}/analyze`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(req), signal,
  });
}

export async function getKtru(code: string, signal?: AbortSignal): Promise<KtruPosition> {
  if ((await detectMode()) === 'mock') { await sleep(200, signal); return mockKtru(code); }
  return http<KtruPosition>(`${BASE}/ktru/${encodeURIComponent(code)}`, { signal });
}

export async function getExamples(): Promise<Example[]> {
  if ((await detectMode()) === 'mock') return MOCK_EXAMPLES;
  try {
    const ex = await http<Example[]>(`${BASE}/examples`);
    return ex.length ? ex : MOCK_EXAMPLES;
  } catch {
    return MOCK_EXAMPLES;
  }
}

/** SSE: события stage (NarrowingStep) и финальное result (AnalyzeResponse). Возвращает функцию закрытия. */
export function streamAnalyze(
  text: string,
  on: { stage?: (s: NarrowingStep) => void; result?: (r: AnalyzeResponse) => void; error?: () => void },
): () => void {
  const es = new EventSource(`${BASE}/stream?text=${encodeURIComponent(text)}`);
  es.addEventListener('stage', (e) => on.stage?.(JSON.parse((e as MessageEvent).data)));
  es.addEventListener('result', (e) => { on.result?.(JSON.parse((e as MessageEvent).data)); es.close(); });
  es.onerror = () => { on.error?.(); es.close(); };
  return () => es.close();
}
