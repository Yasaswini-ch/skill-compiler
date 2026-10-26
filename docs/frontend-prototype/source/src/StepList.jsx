import { useEffect, useState } from 'react';
import StatusMark from './rb/StatusMark';
import CallChip from './rb/CallChip';

const AMBER = '#b45309';
export const secs = ms => (ms < 10000 ? `${(ms / 1000).toFixed(1)} s` : `${Math.round(ms / 1000)} s`);
const WORD = { pass: 'passed', repaired: 'repaired', fail: 'failed' };

// CallChip paints its red wash only when it moves running -> error, so a chip that is
// mounted already failed looks unstyled. Mount it running, then settle it a moment later.
function SettledChip({ status, ...props }) {
  const [shown, setShown] = useState(status === 'idle' ? 'idle' : 'running');
  useEffect(() => {
    if (status === 'running' || status === 'idle') {
      setShown(status);
      return undefined;
    }
    const t = setTimeout(() => setShown(status), 60);
    return () => clearTimeout(t);
  }, [status]);
  return <CallChip {...props} status={shown} />;
}

/**
 * steps: [{ id, title, state: 'pending'|'running'|'done'|'failed', kind: 'pass'|'repaired'|'fail'|null,
 *           attempts: [{ n, chip: 'idle'|'running'|'done'|'error', latencyMs, output, note, ok, showNote }] }]
 * liveTimers: show each chip's own running clock (real runs) instead of the recorded latency.
 */
export default function StepList({ steps, liveTimers = false, shake = false }) {
  return (
    <ol className="steps">
      {steps.map(step => {
        const waiting = step.state === 'pending';
        const settled = step.state === 'done' || step.state === 'failed';
        const markColor = step.kind === 'repaired' && step.state === 'done' ? AMBER : undefined;
        return (
          <li key={step.id} className="step" data-state={step.state} data-kind={step.kind || ''}>
            <div className="step-head">
              <StatusMark
                status={step.state}
                size={22}
                color="var(--ink)"
                doneColor={markColor || 'var(--pass)'}
                errorColor="var(--fail)"
              />
              <span className="step-no">Step {step.id}</span>
              <span className="step-title">{step.title}</span>
              <span className="step-word">{settled && step.kind ? WORD[step.kind] : ''}</span>
            </div>
            {waiting ? null : (
              <ul className="attempts">
                {step.attempts
                  .filter(a => a.chip !== 'idle')
                  .map(a => (
                    <li key={a.n} className="attempt">
                      <SettledChip
                        icon="terminal"
                        shake={shake ? 6 : 0}
                        name={`attempt ${a.n}`}
                        argument={liveTimers || a.latencyMs == null ? '' : secs(a.latencyMs)}
                        status={a.chip}
                        expectedMs={12000}
                        showTimer={liveTimers && a.chip === 'running'}
                        size={32}
                        radius={4}
                        color="var(--ink)"
                        surfaceColor="var(--chip)"
                        progressColor="var(--ink)"
                        doneColor="var(--pass)"
                        errorColor="var(--fail)"
                      />
                      {a.showNote ? (
                        <div className="note">
                          <code>
                            {a.output && a.output.length > 160 ? `${a.output.slice(0, 160)}…` : a.output || '(no output)'}
                          </code>
                          {!a.ok ? <span className="why">checker: {a.note}</span> : null}
                          {liveTimers && a.latencyMs != null ? <span className="took">{secs(a.latencyMs)}</span> : null}
                        </div>
                      ) : null}
                    </li>
                  ))}
              </ul>
            )}
          </li>
        );
      })}
    </ol>
  );
}
