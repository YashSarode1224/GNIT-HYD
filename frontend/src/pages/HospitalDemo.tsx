import { motion, AnimatePresence } from 'framer-motion';
import { Slider } from '@/components/ui/slider';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Activity, AlertTriangle } from 'lucide-react';
import { getHospitalDemo, postHospitalDemo } from '../api';
import { HospitalDemoActionName, HospitalDemoZone, HospitalDemoSnapshot } from '../types';
import './ClassroomVisualizer.css';
import HospitalBlueprint from './HospitalBlueprint';
import HospitalFaultRehearsal from './HospitalFaultRehearsal';

export default function HospitalDemo() {
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
    normal: 'Full supply applied.',
    overload: 'Overload preset applied.',
    reset: 'Hospital demo reset.',
    inject_fault: zoneId ? `Fault injected at ${zoneId}.` : 'Fault injected.',
    clear_fault: 'Injected fault cleared.',
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
      if (mounted.current) setError(cause instanceof Error ? cause.message : 'The hospital action failed.');
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
      <h1>{error ? 'Hospital demo unavailable' : 'Connecting to hospital supply…'}</h1>
      {error && <><p role="alert">{error}</p><button className="classroom-demo__button" onClick={() => void refresh()}>Try again</button></>}
    </main>;
  }

  return <main className="classroom-demo">
    {error && <div className="classroom-demo__alert" role="alert">Connection lost — displaying last known simulated state. {error}</div>}
    <div className="classroom-demo__layout">
      <section className="classroom-demo__main" aria-label="Hospital power state">
        <div className="classroom-demo__metrics">
          <div className="classroom-demo__metric">
            <span className="classroom-demo__metric-label">Campus Capacity (Total)</span>
            <span className="classroom-demo__metric-value">{snapshot.contract.campus_totals?.capacity_w?.toLocaleString() ?? '?'} W</span>
            <span className="classroom-demo__metric-note">Served: {snapshot.contract.campus_totals?.served_w.toLocaleString() ?? 0} W</span>
          </div>
          <div className="classroom-demo__metric">
            <span className="classroom-demo__metric-label">Hospital View Supply</span>
            <span className="classroom-demo__metric-value">{(snapshot.effective_capacity_w ?? snapshot.capacity_w).toLocaleString()} W</span>
            {snapshot.limited_by === 'campus feeder A' && <span className="classroom-demo__metric-note">Limited by campus feeder A ({(snapshot.campus_limit_w ?? 0).toLocaleString()} W)</span>}
          </div>
          <div className="classroom-demo__metric"><span className="classroom-demo__metric-label">View Requested</span><span className="classroom-demo__metric-value">{snapshot.requested_w.toLocaleString()} W</span></div>
          <div className="classroom-demo__metric"><span className="classroom-demo__metric-label">View Served</span><span className="classroom-demo__metric-value">{snapshot.served_w.toLocaleString()} W</span></div>
          <div className="classroom-demo__metric"><span className="classroom-demo__metric-label">View Unmet</span><span className="classroom-demo__metric-value">{snapshot.shortfall_w.toLocaleString()} W</span></div>
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
            <AnimatePresence>
            {snapshot.transformers.map((tx, i) => {
              const act = tx.activity;
              return <motion.article initial={{opacity:0, y:20}} animate={{opacity:1, y:0}} exit={{opacity:0, y:20}} transition={{delay: i * 0.05}} key={tx.zone} className={`classroom-demo__ml-card ${tx.rfid_active ? 'is-scanned' : ''}`} aria-label={`${tx.zone} activity estimate`}>
                <header><strong>{tx.zone}</strong><span>{tx.priority_rank ? `Priority #${tx.priority_rank}` : 'Not scanned'}</span></header>
                <span className={`classroom-demo__state classroom-demo__state--${act.state.toLowerCase()}`}>{act.state}</span>
                <dl>
                  <div><dt>Score</dt><dd>{act.score === null ? '—' : act.score.toFixed(2)}</dd></div>
                  <div><dt>CO₂</dt><dd>{act.evidence.co2_ppm == null ? '—' : `${Math.round(act.evidence.co2_ppm)} ppm`}</dd></div>
                  <div><dt>Temp</dt><dd>{act.evidence.temperature_c == null ? '—' : `${act.evidence.temperature_c.toFixed(1)} °C`}</dd></div>
                </dl>
                <p>{act.reason}</p>
                {tx.diagnosis && tx.diagnosis.code !== 'NORMAL' && (
                  <div style={{ marginTop: '0.4rem', paddingTop: '0.4rem', borderTop: '1px solid #ddd' }}>
                    <span className={`hospital-diagnosis-badge severity-${tx.diagnosis.severity}`}>
                      {tx.diagnosis.code.replace(/_/g, ' ')}
                    </span>
                    {tx.diagnosis.hypotheses && tx.diagnosis.hypotheses.length > 1 && (
                      <div style={{ display: 'flex', gap: '0.3rem', flexWrap: 'wrap', marginTop: '0.3rem' }}>
                        {tx.diagnosis.hypotheses.map(h => (
                          <span key={h.id} style={{ fontSize: '0.7rem', padding: '0.1rem 0.3rem', borderRadius: '3px', background: '#eee' }}>
                            {h.code} ({h.evidence_score})
                          </span>
                        ))}
                      </div>
                    )}
                    {tx.diagnosis.abstention && (
                      <p style={{ fontSize: '0.75rem', color: '#b23b18', margin: '0.2rem 0' }}>
                        ⚠️ Abstained: {tx.diagnosis.abstention.next_check_needed}
                      </p>
                    )}
                  </div>
                )}
              </motion.article>
              ;})}
            </AnimatePresence>
          </div>
          <p className="classroom-demo__ml-note">Only scanned zones are ranked: ACTIVE first, then UNKNOWN, then INACTIVE; within the same state, the zone scanned first goes first. The model is an office-occupancy proxy, not a measurement of these hospital zones.</p>
        </section>
        <section aria-label="Hospital floor plans" aria-describedby="classzone-blueprint-key">
          <p id="classzone-blueprint-key" className="classroom-demo__blueprint-key">A shared supply feeds three hospital zones. Bright moving pulses show powered equipment; gray branches have been cut. {error ? 'Motion pauses while the connection is unavailable.' : ''}</p>
          <div className="overflow-x-auto whitespace-nowrap scrollbar-hide pb-4 w-full">
            <HospitalBlueprint snapshot={snapshot} connected={!error} />
          </div>
        </section>
        <HospitalFaultRehearsal />
      </section>
      <aside className="classroom-demo__panel classroom-demo__controls" aria-labelledby="classzone-controls-title" aria-busy={pending}>
        <h2 id="classzone-controls-title">Demo controls</h2>
        <p>Scan any number of zones, then lower the supply to see which zones keep their equipment.</p>
        <div className="classroom-demo__button-stack" role="group" aria-label="Scan hospital ward RFID cards">
          {snapshot.transformers.map(({ zone: id }) => {
            const scanned = snapshot.scanned_zone_ids.includes(id);
            return <button key={id} className={`classroom-demo__button ${scanned ? 'classroom-demo__button--primary' : ''}`} aria-pressed={scanned} disabled={pending} onClick={() => void runAction(scanned ? 'unscan' : 'scan', id)}>{scanned ? `✓ ${id} scanned · tap to end` : `Scan ${id}`}</button>;
          })}
        </div>
        <div className="classroom-demo__control-divider" />
        {(() => {
          const [low, high] = snapshot.capacity_range_w;
          const value = capacityDraft ?? snapshot.capacity_w;
          return <div className="classroom-demo__slider">
            <label id="hospital-capacity-label">Supply limit <strong>{value.toLocaleString()} W</strong></label>
            <Slider aria-labelledby="hospital-capacity-label" value={[value]} min={low} max={high} step={100} onValueChange={(vals: number[]) => onCapacityChange(vals[0])} />
            <div className="classroom-demo__slider-scale"><span>{low.toLocaleString()} W</span><span>{high.toLocaleString()} W</span></div>
          </div>;
        })()}
        <div className="classroom-demo__button-stack">
          <button className="classroom-demo__button" disabled={pending} onClick={() => void runAction('normal')}>Full supply · {snapshot.capacity_range_w[1].toLocaleString()} W</button>
          <button className="classroom-demo__button classroom-demo__button--warn" disabled={pending} onClick={() => void runAction('overload')}>Overload preset</button>
          <button className="classroom-demo__button" disabled={pending} onClick={() => void runAction('reset')}>Reset demo</button>
        </div>
        <p className="classroom-demo__feedback" aria-live="polite">{pending ? 'Updating hospital state…' : feedback ?? ''}</p>
        <p><strong>Policy:</strong> {snapshot.policy}</p>
        <p>RFID scan state is shown as session evidence. This 6,000 W hospital load is campus feeder A (L0, L1 and L2) broken into equipment, so campus shortages and feeder A trips apply here too.</p>
      </aside>
    </div>
  </main>;
}









