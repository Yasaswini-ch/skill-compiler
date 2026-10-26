import { useEffect, useReducer, useRef, useState } from 'react';
import ThoughtLine from './rb/ThoughtLine';
import StepList from './StepList';

const DEFAULT_SERVER = 'http://127.0.0.1:5001';
const initial = { phase: 'idle', skill: '', steps: [], warnings: [], trace: null, error: '' };

const mapStep = (state, id, fn) => ({ ...state, steps: state.steps.map(s => (s.id === id ? fn(s) : s)) });

function reduce(state, e) {
  switch (e.type) {
    case 'reset':
      return { ...initial, phase: 'splitting' };
    case 'run_start':
      return { ...initial, phase: e.will_split ? 'splitting' : 'running' };
    case 'plan':
      return {
        ...state,
        phase: 'running',
        skill: e.skill,
        warnings: e.warnings || [],
        steps: e.steps.map(s => ({ id: s.id, title: s.title, state: 'pending', kind: null, attempts: [] }))
      };
    case 'step_start':
      return mapStep(state, e.step_id, s => ({ ...s, state: 'running' }));
    case 'attempt_start':
      return mapStep(state, e.step_id, s => ({
        ...s,
        attempts: [...s.attempts, { n: e.attempt, chip: 'running', latencyMs: null, output: '', note: '', ok: false, showNote: false }]
      }));
    case 'attempt_end':
      return mapStep(state, e.step_id, s => ({
        ...s,
        attempts: s.attempts.map(a =>
          a.n === e.attempt
            ? { ...a, chip: e.ok ? 'done' : 'error', latencyMs: e.latency_ms, output: e.output, note: e.checker_note, ok: e.ok, showNote: true }
            : a
        )
      }));
    case 'step_end':
      return mapStep(state, e.step_id, s => ({ ...s, state: e.status === 'fail' ? 'failed' : 'done', kind: e.status }));
    case 'run_end':
      return { ...state, phase: 'done', trace: e.trace };
    case 'stopped':
      return { ...state, phase: 'stopped' };
    case 'error':
    case 'fail_local':
      return { ...state, phase: 'error', error: e.message };
    default:
      return state;
  }
}

function download(trace) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(trace, null, 2)], { type: 'application/json' }));
  const a = document.createElement('a');
  a.href = url;
  a.download = `${trace.run_id || 'trace'}.json`;
  a.click();
  URL.revokeObjectURL(url);
}

export default function Live() {
  const [server, setServer] = useState(DEFAULT_SERVER);
  const [presets, setPresets] = useState([]);
  const [skill, setSkill] = useState('');
  const [input, setInput] = useState('');
  const [verify, setVerify] = useState(true);
  const [state, dispatch] = useReducer(reduce, initial);
  const [wall, setWall] = useState(null);
  const abortRef = useRef(null);
  const startRef = useRef(0);
  const [loadError, setLoadError] = useState('');

  async function loadPresets() {
    setLoadError('');
    try {
      const res = await fetch(`${server}/presets`);
      const list = await res.json();
      setPresets(list);
      if (list.length && !skill) {
        setSkill(list[0].skill_text);
        setInput(list[0].input);
      }
    } catch {
      setPresets([]);
      setLoadError(`Cannot reach ${server}. Start the server with:  python server.py`);
    }
  }
  useEffect(() => {
    loadPresets();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const running = state.phase === 'splitting' || state.phase === 'running';

  async function run() {
    const ctl = new AbortController();
    abortRef.current = ctl;
    dispatch({ type: 'reset' });
    setWall(null);
    startRef.current = Date.now();
    try {
      const res = await fetch(`${server}/run-stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ skill_text: skill, input, verify }),
        signal: ctl.signal
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.error || `the server answered ${res.status}`);
      }
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        let nl;
        while ((nl = buffer.indexOf('\n')) >= 0) {
          const line = buffer.slice(0, nl).trim();
          buffer = buffer.slice(nl + 1);
          if (!line) continue;
          const event = JSON.parse(line);
          if (event.type === 'run_end') setWall((Date.now() - startRef.current) / 1000);
          dispatch(event);
        }
      }
    } catch (e) {
      setWall((Date.now() - startRef.current) / 1000);
      if (e.name === 'AbortError') dispatch({ type: 'stopped' });
      else dispatch({ type: 'fail_local', message: /Failed to fetch|NetworkError/.test(e.message) ? `Cannot reach ${server}. Start the server with:  python server.py` : e.message });
    }
  }

  const n = state.steps.length;
  const finished = state.steps.filter(s => s.state === 'done' || s.state === 'failed').length;
  const trace = state.trace;
  const retried = state.steps.filter(s => s.kind === 'repaired').length;
  const failed = state.steps.filter(s => s.kind === 'fail').length;

  let label = 'Splitting the skill into steps…';
  if (state.phase === 'running') label = `Running step ${Math.min(finished + 1, n)} of ${n}…`;
  const doneLabel =
    state.phase === 'done' ? `Ran ${n} steps in` : state.phase === 'stopped' ? 'Stopped after' : 'Stopped by an error after';

  return (
    <>
      <p className="kicker">Live run</p>
      <h1>{state.skill || 'Run a skill'}</h1>
      <p className="meta">Steps appear as the harness finishes them. This page shows the harness only, not the plain-model comparison.</p>

      <div className="controls">
        <select
          aria-label="Example skill"
          disabled={running}
          onChange={e => {
            const p = presets.find(x => x.name === e.target.value);
            if (p) {
              setSkill(p.skill_text);
              setInput(p.input);
            }
          }}
          value={presets.find(p => p.skill_text === skill)?.name || ''}
        >
          <option value="">{presets.length ? 'Example skills' : 'No examples loaded'}</option>
          {presets.map(p => (
            <option key={p.name} value={p.name}>
              {p.name}
            </option>
          ))}
        </select>
        <label className="check">
          <input type="checkbox" checked={verify} disabled={running} onChange={e => setVerify(e.target.checked)} /> verifier on
        </label>
        {running ? (
          <button type="button" onClick={() => abortRef.current?.abort()}>
            Stop
          </button>
        ) : (
          <button type="button" onClick={run} disabled={!skill.trim() || !input.trim()}>
            Run
          </button>
        )}
        <label className="server">
          server
          <input type="text" value={server} disabled={running} onChange={e => setServer(e.target.value)} onBlur={loadPresets} />
        </label>
      </div>
      {loadError ? <p className="err">{loadError}</p> : null}

      <div className="fields">
        <label>
          SKILL.md
          <textarea value={skill} disabled={running} onChange={e => setSkill(e.target.value)} rows={9} spellCheck={false} />
        </label>
        <label>
          Input
          <textarea value={input} disabled={running} onChange={e => setInput(e.target.value)} rows={9} spellCheck={false} />
        </label>
      </div>

      {state.phase !== 'idle' ? (
        <div className="run">
          <ThoughtLine
            label={label}
            doneLabel={doneLabel}
            working={running}
            elapsed={running ? undefined : wall ?? 0}
            collapsible={false}
            fontSize={19}
            color="var(--ink)"
          />
          {state.phase === 'done' ? (
            <p className="summary">
              {n - retried - failed} passed first try · {retried} repaired · {failed} failed · {trace.totals.llm_calls} model calls
            </p>
          ) : null}
        </div>
      ) : null}
      {state.warnings.length ? <p className="err">Plan warning: {state.warnings.join(' ')}</p> : null}
      {state.phase === 'error' ? <p className="err">{state.error}</p> : null}

      <StepList steps={state.steps} liveTimers shake />

      {trace ? (
        <>
          <details className="final" open>
            <summary>Final output</summary>
            <pre>{trace.final_output}</pre>
          </details>
          <p>
            <button type="button" onClick={() => download(trace)}>
              Download trace.json
            </button>
          </p>
        </>
      ) : null}
    </>
  );
}
