import { useCallback, useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { Activity, AlertTriangle, Zap } from 'lucide-react';
import { getHospitalDemo, postHospitalDemo } from '../api';
import { HospitalDemoActionName, HospitalDemoZone, HospitalDemoSnapshot } from '../types';
import './ClassroomVisualizer.css';
import HospitalBlueprint from './HospitalBlueprint';

export default function HospitalDemo({ hideHeader }: { hideHeader?: boolean }) {
  console.log(hideHeader);
  const [snapshot, setSnapshot] = useState<HospitalDemoSnapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);
  const pollInFlight = useRef(false);
  const actionInFlight = useRef(false);
  const requestVersion = useRef(0);
  const mounted = useRef(false);

  const refresh = useCallback(async (signal?: AbortSignal) => {
    if (pollInFlight.current || actionInFlight.current) return;
    pollInFlight.current = true;
    const version = requestVersion.current;
    try {
      const data = await getHospitalDemo(signal);
      if (mounted.current && version === requestVersion.current) {
        setSnapshot(data);
        setError(null);
      }
    } catch (cause) {
      if (mounted.current && version === requestVersion.current && !signal?.aborted) {
        setError(cause instanceof Error ? cause.message : 'Could not load hospital state.');
      }
    } finally {
      pollInFlight.current = false;
    }
  }, []);

  useEffect(() => {
    mounted.current = true;
    const controller = new AbortController();
    void refresh(controller.signal);
    const timer = window.setInterval(() => void refresh(controller.signal), 1000);
    return () => {
      mounted.current = false;
      controller.abort();
      window.clearInterval(timer);
    };
  }, [refresh]);

  const [capacityDraft, setCapacityDraft] = useState<number | null>(null);
  const capacityTimer = useRef<number | null>(null);
  useEffect(() => () => { if (capacityTimer.current) window.clearTimeout(capacityTimer.current); }, []);

  const describe = (action: HospitalDemoActionName, zoneId?: string, capacity?: number) => ({
    scan: `Scanned ${zoneId}.`,
    unscan: `Ended ${zoneId}'s session.`,
    set_capacity: `Supply set to ${capacity?.toLocaleString()} W.`,
    normal: 'Full supply 7,000 W applied.',
    overload: 'Overload preset 3,000 W applied.',
    reset: 'Classzone demo reset.',
    replay_pause: 'Sensor replay paused.',
    replay_resume: 'Sensor replay resumed.',
    replay_step: 'Moved to the next recorded reading.',
  }[action]);

  const runAction = async (action: HospitalDemoActionName, zoneId?: HospitalDemoZone['id'], capacity?: number) => {
    if (actionInFlight.current) return;
    actionInFlight.current = true;
    requestVersion.current += 1;
    setPending(true);
    setError(null);
    setFeedback(null);
    try {
      const next = await postHospitalDemo(action, zoneId, capacity);
      if (mounted.current) {
        setSnapshot(next);
        setFeedback(describe(action, zoneId, capacity));
        if (action === 'set_capacity' || action === 'normal' || action === 'overload' || action === 'reset') setCapacityDraft(null);
      }
    } catch (cause) {
      if (mounted.current) setError(cause instanceof Error ? cause.message : 'The classzone action failed.');
    } finally {
      actionInFlight.current = false;
      if (mounted.current) setPending(false);
    }
  };

  const onCapacityChange = (value: number) => {
    setCapacityDraft(value);
    if (capacityTimer.current) window.clearTimeout(capacityTimer.current);
    capacityTimer.current = window.setTimeout(() => void runAction('set_capacity', undefined, value), 300);
  };

  if (!snapshot) {
    return <main className="classroom-demo classroom-demo__loading" aria-busy={!error}>
      {error ? <AlertTriangle size={30} aria-hidden="true" /> : <Activity size={30} aria-hidden="true" />}
      <h1>{error ? 'Classzone demo unavailable' : 'Connecting to classzone supply…'}</h1>
      {error && <><p role="alert">{error}</p><button className="classroom-demo__button" onClick={() => void refresh()}>Try again</button></>}
    </main>;
  }

  return <main className="classroom-demo">
    <header className="classroom-demo__header">
      <div className="classroom-demo__brand"><span className="classroom-demo__brand-icon"><Zap size={22} aria-hidden="true" /></span><div><span className="classroom-demo__eyebrow">PriorityGrid · Simulated</span><h1 className="classroom-demo__title">Classzone power map</h1></div></div>
      <nav className="classroom-demo__nav" aria-label="Visualizer navigation"><Link className="classroom-demo__back" to="/hospital">Hospital demo</Link><Link className="classroom-demo__back" to="/">Back to overview</Link></nav>
    </header>
    {error && <div className="classroom-demo__alert" role="alert">Connection lost — displaying last known simulated state. {error}</div>}
    <div className="classroom-demo__layout">
      <section className="classroom-demo__main" aria-label="Classzone power state">
        <div className="classroom-demo__metrics">
          <div className="classroom-demo__metric"><span className="classroom-demo__metric-label">Hospital-only supply</span><span className="classroom-demo__metric-value">{snapshot.capacity_w.toLocaleString()} W</span></div>
          <div className="classroom-demo__metric"><span className="classroom-demo__metric-label">Requested</span><span className="classroom-demo__metric-value">{snapshot.requested_w.toLocaleString()} W</span></div>
          <div className="classroom-demo__metric"><span className="classroom-demo__metric-label">Served</span><span className="classroom-demo__metric-value">{snapshot.served_w.toLocaleString()} W</span></div>
          <div className="classroom-demo__metric"><span className="classroom-demo__metric-label">Unmet</span><span className="classroom-demo__metric-value">{snapshot.shortfall_w.toLocaleString()} W</span></div>
        </div>
        <section className="classroom-demo__panel classroom-demo__ml" aria-labelledby="classzone-ml-title">
          <header className="classroom-demo__ml-head">
            <div><h2 id="classzone-ml-title">ML priority for scanned zones</h2>
              <p>{snapshot.model.ready ? `Activity model ${snapshot.model.model_version}` : `Model unavailable: ${snapshot.model.fallback_reason ?? 'unknown reason'}`} · recorded office sensor replay, reading {snapshot.replay.length ? snapshot.replay.index + 1 : 0} of {snapshot.replay.length}{snapshot.replay.running ? `, changes every ${snapshot.replay.step_s} s` : ', paused'}</p></div>
            <div className="classroom-demo__ml-actions">
              <button className="classroom-demo__button" disabled={pending || !snapshot.replay.length} onClick={() => void runAction(snapshot.replay.running ? 'replay_pause' : 'replay_resume')}>{snapshot.replay.running ? 'Pause readings' : 'Resume readings'}</button>
              <button className="classroom-demo__button" disabled={pending || !snapshot.replay.length} onClick={() => void runAction('replay_step')}>Next reading</button>
            </div>
          </header>
          <div className="classroom-demo__ml-grid">
            {snapshot.transformers.map(tx => {
              const act = tx.activity;
              return <article key={tx.zone} className={`classroom-demo__ml-card ${tx.rfid_active ? 'is-scanned' : ''}`} aria-label={`${tx.zone} activity estimate`}>
                <header><strong>{tx.zone}</strong><span>{tx.priority_rank ? `Priority #${tx.priority_rank}` : 'Not scanned'}</span></header>
                <span className={`classroom-demo__state classroom-demo__state--${act.state.toLowerCase()}`}>{act.state}</span>
                <dl>
                  <div><dt>Score</dt><dd>{act.score === null ? '—' : act.score.toFixed(2)}</dd></div>
                  <div><dt>CO₂</dt><dd>{act.evidence.co2_ppm == null ? '—' : `${Math.round(act.evidence.co2_ppm)} ppm`}</dd></div>
                  <div><dt>Temp</dt><dd>{act.evidence.temperature_c == null ? '—' : `${act.evidence.temperature_c.toFixed(1)} °C`}</dd></div>
                </dl>
                <p>{act.reason}</p>
              </article>;
            })}
          </div>
          <p className="classroom-demo__ml-note">Only scanned zones are ranked: ACTIVE first, then UNKNOWN, then INACTIVE; within the same state, the zone scanned first goes first. The model is an office-occupancy proxy, not a measurement of these classzones.</p>
        </section>
        <section aria-label="Classzone floor plans" aria-describedby="classzone-blueprint-key">
          <p id="classzone-blueprint-key" className="classroom-demo__blueprint-key">A shared supply feeds three tiled classzones. Bright moving pulses show powered equipment; gray branches have been cut. {error ? 'Motion pauses while the connection is unavailable.' : ''}</p>
          <HospitalBlueprint snapshot={snapshot} connected={!error} />
        </section>
      </section>
      <aside className="classroom-demo__panel classroom-demo__controls" aria-labelledby="classzone-controls-title" aria-busy={pending}>
        <h2 id="classzone-controls-title">Demo controls</h2>
        <p>Scan any number of classzones, then lower the supply to see which zones keep their equipment.</p>
        <div className="classroom-demo__button-stack" role="group" aria-label="Scan hospital ward RFID cards">
          {(['ICU', 'Theatre', 'Wards'] as const).map(id => {
            const scanned = snapshot.scanned_zone_ids.includes(id);
            return <button key={id} className={`classroom-demo__button ${scanned ? 'classroom-demo__button--primary' : ''}`} aria-pressed={scanned} disabled={pending} onClick={() => void runAction(scanned ? 'unscan' : 'scan', id)}>{scanned ? `✓ ${id} scanned · tap to end` : `Scan ${id}`}</button>;
          })}
        </div>
        <div className="classroom-demo__control-divider" />
        {(() => {
          const [low, high] = snapshot.capacity_range_w;
          const value = capacityDraft ?? snapshot.capacity_w;
          return <div className="classroom-demo__slider">
            <label htmlFor="hospital-capacity">Supply limit <strong>{value.toLocaleString()} W</strong></label>
            <input id="hospital-capacity" type="range" min={low} max={high} step={100} value={value} onChange={event => onCapacityChange(Number(event.target.value))} aria-valuetext={`${value} watts`} />
            <div className="classroom-demo__slider-scale"><span>{low.toLocaleString()} W</span><span>{high.toLocaleString()} W</span></div>
          </div>;
        })()}
        <div className="classroom-demo__button-stack">
          <button className="classroom-demo__button" disabled={pending} onClick={() => void runAction('normal')}>Full supply · 7,000 W</button>
          <button className="classroom-demo__button classroom-demo__button--warn" disabled={pending} onClick={() => void runAction('overload')}>Overload preset · 3,000 W</button>
          <button className="classroom-demo__button" disabled={pending} onClick={() => void runAction('reset')}>Reset demo</button>
        </div>
        <p className="classroom-demo__feedback" aria-live="polite">{pending ? 'Updating hospital state…' : feedback ?? ''}</p>
        <p><strong>Policy:</strong> {snapshot.policy}</p>
        <p>RFID scan state is shown as session evidence. The 7,000 W budget belongs to this hospital demo and is separate from the six-service campus model.</p>
      </aside>
    </div>
  </main>;
}
