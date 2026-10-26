import { useRef, useState } from 'react';
import ThoughtLine from './rb/ThoughtLine';
import StepList from './StepList';
import Live from './Live';
import mixed from '../../../../skillcompiler/examples/traces/ticket-triage_gemma3-4b_pass-repaired-fail.json';
import repaired from '../../../../skillcompiler/examples/traces/ticket-triage_gemma-4-26b_one-repair.json';
import allpass from '../../../../skillcompiler/examples/traces/complaint-resolution_gemma-4-26b_12-steps-all-pass.json';
import './app.css';

const SAMPLES = [
  { id: 'mixed', label: 'ticket-triage on gemma3:4b (pass, repaired, fail)', trace: mixed },
  { id: 'repaired', label: 'ticket-triage on gemma-4-26b (one repair)', trace: repaired },
  { id: 'allpass', label: 'complaint-resolution, 12 steps, no retries', trace: allpass }
];

const sleep = ms => new Promise(r => setTimeout(r, ms));
const attemptOk = a => a.format_ok && a.verified;
const stateOf = status => (status === 'fail' ? 'failed' : 'done');

function validTrace(t) {
  return t && Array.isArray(t.steps) && t.steps.every(s => Array.isArray(s.attempts)) && t.totals;
}

// A recorded trace as the rows StepList draws.
function rowsFromTrace(trace) {
  return trace.steps.map(s => ({
    id: s.step_id,
    title: s.title,
    state: stateOf(s.status),
    kind: s.status,
    attempts: s.attempts.map((a, j) => ({
      n: j + 1,
      chip: attemptOk(a) ? 'done' : 'error',
      latencyMs: a.latency_ms,
      output: a.output,
      note: a.checker_note,
      ok: attemptOk(a),
      showNote: true
    }))
  }));
}

// The same trace part-way through a replay.
function rowsFromReplay(trace, r) {
  return trace.steps.map((s, i) => ({
    id: s.step_id,
    title: s.title,
    state: r.step[i],
    kind: r.step[i] === 'done' || r.step[i] === 'failed' ? s.status : null,
    attempts: s.attempts.map((a, j) => ({
      n: j + 1,
      chip: r.chip[i][j],
      latencyMs: a.latency_ms,
      output: a.output,
      note: a.checker_note,
      ok: attemptOk(a),
      showNote: r.note[i][j]
    }))
  }));
}

function TraceView() {
  const [trace, setTrace] = useState(SAMPLES[0].trace);
  const [replayState, setReplayState] = useState(null); // null = show the recorded final states
  const [playing, setPlaying] = useState(false);
  const [error, setError] = useState('');
  const token = useRef(0);

  function show(next) {
    token.current += 1; // cancels a replay in progress
    setPlaying(false);
    setReplayState(null);
    setError('');
    setTrace(next);
  }

  function onFile(event) {
    const file = event.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      try {
        const parsed = JSON.parse(reader.result);
        if (!validTrace(parsed)) throw new Error('not a trace.json (needs steps with attempts, and totals)');
        show(parsed);
      } catch (e) {
        setError(`Could not read ${file.name}: ${e.message}`);
      }
    };
    reader.readAsText(file);
  }

  async function replay() {
    const me = ++token.current;
    const steps = trace.steps;
    const state = {
      step: steps.map(() => 'pending'),
      chip: steps.map(s => s.attempts.map(() => 'idle')),
      note: steps.map(s => s.attempts.map(() => false))
    };
    const push = () => setReplayState(JSON.parse(JSON.stringify(state)));
    setPlaying(true);
    push();
    for (let i = 0; i < steps.length; i++) {
      state.step[i] = 'running';
      push();
      for (let j = 0; j < steps[i].attempts.length; j++) {
        const a = steps[i].attempts[j];
        state.chip[i][j] = 'running';
        push();
        await sleep(Math.min(Math.max(a.latency_ms / 20, 700), 2200)); // sped up
        if (token.current !== me) return;
        state.chip[i][j] = attemptOk(a) ? 'done' : 'error';
        state.note[i][j] = true;
        push();
        await sleep(450);
        if (token.current !== me) return;
      }
      state.step[i] = stateOf(steps[i].status);
      push();
    }
    setPlaying(false);
    setReplayState(null);
  }

  const { totals = {} } = trace;
  const retried = trace.steps.filter(s => s.status === 'repaired').length;
  const failed = trace.steps.filter(s => s.status === 'fail').length;
  const rows = replayState ? rowsFromReplay(trace, replayState) : rowsFromTrace(trace);

  return (
    <>
      {trace.mock ? <div className="mock">MOCK DATA: a stand-in or recorded run, not the real harness</div> : null}
      <p className="kicker">Run trace</p>
      <h1>{trace.skill}</h1>
      <p className="meta">
        {trace.model} · {trace.mode} · {totals.llm_calls} model calls · {totals.retries} retries
        {totals.cache_hits != null ? ` · ${totals.cache_hits} cache hits` : ''}
      </p>

      <div className="controls">
        <select
          aria-label="Sample trace"
          onChange={e => show(SAMPLES.find(s => s.id === e.target.value).trace)}
          defaultValue="mixed"
        >
          {SAMPLES.map(s => (
            <option key={s.id} value={s.id}>
              {s.label}
            </option>
          ))}
        </select>
        <label className="file">
          Open a trace.json
          <input type="file" accept=".json,application/json" onChange={onFile} />
        </label>
        <button type="button" onClick={replay} disabled={playing}>
          {playing ? 'Replaying…' : 'Replay (sped up)'}
        </button>
      </div>
      {error ? <p className="err">{error}</p> : null}

      <div className="run">
        <ThoughtLine
          label="Replaying the run…"
          doneLabel={`Ran ${trace.steps.length} steps in`}
          working={playing}
          elapsed={playing ? undefined : (totals.latency_ms || 0) / 1000}
          collapsible={false}
          fontSize={19}
          color="var(--ink)"
        />
        <p className="summary">
          {trace.steps.length - retried - failed} passed first try · {retried} repaired · {failed} failed
        </p>
      </div>

      <StepList steps={rows} shake={playing} />

      <details className="final">
        <summary>Final output</summary>
        <pre>{trace.final_output}</pre>
      </details>
    </>
  );
}

export default function App() {
  const [tab, setTab] = useState('trace');
  return (
    <main className="sheet">
      <nav className="tabs" aria-label="Views">
        <button type="button" className={tab === 'trace' ? 'on' : ''} onClick={() => setTab('trace')}>
          Recorded trace
        </button>
        <button type="button" className={tab === 'live' ? 'on' : ''} onClick={() => setTab('live')}>
          Live run
        </button>
      </nav>
      {tab === 'trace' ? <TraceView /> : <Live />}
    </main>
  );
}
