import { Snapshot } from '../types';
import '../pages/ClassroomBlueprint.css';

interface Props {
  snapshot: Snapshot;
}

export default function NetworkBlueprint({ snapshot }: Props) {
  const { source, feeder_limits_w, services, fault_diagnosis } = snapshot;

  const wire = (id: string, d: string, on: boolean, main = false, fault = false) => (
    <g key={id} data-circuit={id} className={`power-map__circuit ${on ? 'is-on' : 'is-off'} ${main ? 'is-main' : ''}`}>
      <path className="power-map__cable-bed" d={d} stroke={fault ? '#ffcccc' : undefined} />
      <path className="power-map__cable" d={d} stroke={fault ? '#ff4444' : undefined} />
      {on && !fault && <path className="power-map__current" d={d} />}
    </g>
  );

  const isFeederAOn = snapshot.services.some(s => s.feeder === 'A' && s.modeled_served) || !fault_diagnosis?.diagnosis.includes('Feeder A');
  const isFeederBOn = snapshot.services.some(s => s.feeder === 'B' && s.modeled_served) || !fault_diagnosis?.diagnosis.includes('Feeder B');

  return (
    <section className="power-map" aria-label="Campus electrical network map">
      <header className="power-map__toolbar">
        <div>
          <span className="power-map__eyebrow">Campus / macro layer</span>
          <h2>Electrical Network Topology</h2>
        </div>
        <div className="power-map__legend">
          <span><i className="live" />Live current</span>
          <span><i />Cut circuit / Fault</span>
        </div>
      </header>
      
      <div className="power-map__viewport" tabIndex={0} role="region">
        <svg className="power-map__drawing" viewBox="0 0 1080 460">
          <defs>
            <pattern id="campus-tiles" width="20" height="20" patternUnits="userSpaceOnUse">
              <rect width="20" height="20" fill="#edece5" />
              <path d="M20 0H0V20" fill="none" stroke="#d9dad2" strokeWidth=".7" />
            </pattern>
            <pattern id="zone-tiles" width="20" height="20" patternUnits="userSpaceOnUse">
              <rect width="20" height="20" fill="#f5efdd" />
              <path d="M20 0H0V20" fill="none" stroke="#e6dfcb" strokeWidth=".8" />
            </pattern>
          </defs>
          <rect width="1080" height="460" fill="url(#campus-tiles)" />
          <text x="30" y="26" className="power-map__map-note">MAIN GRID / CAMPUS DISTRIBUTION</text>
          
          {/* Main Source Block */}
          <g>
            <rect x={444} y={40} width={192} height={80} fill="#c6c6bc" />
            <rect x={440} y={36} width={192} height={80} fill="#4b5563" stroke="#1f2937" strokeWidth="4" />
            <text x={536} y={66} fill="#f8fafc" fontSize="16" fontWeight="bold" textAnchor="middle">PRIMARY SOURCE</text>
            <text x={536} y={86} fill="#94a3b8" fontSize="14" textAnchor="middle">{source.capacity_w} W Cap.</text>
          </g>

          {/* Source to Feeders Bus */}
          {wire('source-bus', 'M536 116 V160 H280 M536 160 H792', true, true)}

          {/* Feeder A Block */}
          <g>
            <rect x={184} y={164} width={192} height={70} fill="#c6c6bc" />
            <rect x={180} y={160} width={192} height={70} fill="url(#zone-tiles)" stroke="#52786a" strokeWidth="4" />
            <text x={276} y={190} fill="#1f2937" fontSize="16" fontWeight="bold" textAnchor="middle">Feeder A (Hospital)</text>
            <text x={276} y={210} fill="#4b5563" fontSize="14" textAnchor="middle">Limit: {feeder_limits_w.A} W</text>
            {fault_diagnosis?.diagnosis.includes('Feeder A') && (
              <text x={276} y={150} fill="#ef4444" fontSize="14" fontWeight="bold" textAnchor="middle">FAULT / DISCONNECTED</text>
            )}
          </g>

          {/* Feeder B Block */}
          <g>
            <rect x={696} y={164} width={192} height={70} fill="#c6c6bc" />
            <rect x={692} y={160} width={192} height={70} fill="url(#zone-tiles)" stroke="#52786a" strokeWidth="4" />
            <text x={788} y={190} fill="#1f2937" fontSize="16" fontWeight="bold" textAnchor="middle">Feeder B (Classrooms)</text>
            <text x={788} y={210} fill="#4b5563" fontSize="14" textAnchor="middle">Limit: {feeder_limits_w.B} W</text>
            {fault_diagnosis?.diagnosis.includes('Feeder B') && (
              <text x={788} y={150} fill="#ef4444" fontSize="14" fontWeight="bold" textAnchor="middle">FAULT / DISCONNECTED</text>
            )}
          </g>

          {/* Wires to Feeder A Services */}
          {wire('fa-l0', 'M280 230 V290 H100 V320', isFeederAOn && (services.find(s=>s.id==='L0')?.modeled_served || false))}
          {wire('fa-l1', 'M280 230 V320', isFeederAOn && (services.find(s=>s.id==='L1')?.modeled_served || false))}
          {wire('fa-l2', 'M280 230 V290 H460 V320', isFeederAOn && (services.find(s=>s.id==='L2')?.modeled_served || false))}

          {/* Feeder A Services */}
          {[
            { id: 'L0', x: 40, name: 'Essential (L0)' },
            { id: 'L1', x: 220, name: 'Emergency (L1)' },
            { id: 'L2', x: 400, name: 'Pump (L2)' }
          ].map(svc => {
            const s = services.find(x => x.id === svc.id);
            const isOn = s?.modeled_served;
            return (
              <g key={svc.id}>
                <rect x={svc.x+4} y={324} width={120} height={80} fill="#c6c6bc" />
                <rect x={svc.x} y={320} width={120} height={80} fill="#fff" stroke={isOn ? "#52786a" : "#9ca3af"} strokeWidth="4" />
                <text x={svc.x+60} y={345} fill="#1f2937" fontSize="14" fontWeight="bold" textAnchor="middle">{svc.name}</text>
                <text x={svc.x+60} y={365} fill="#4b5563" fontSize="12" textAnchor="middle">{s?.watts} W</text>
                <rect x={svc.x+30} y={375} width={60} height={18} rx={9} fill={isOn ? "#dcfce7" : "#fee2e2"} stroke={isOn ? "#166534" : "#991b1b"} />
                <text x={svc.x+60} y={388} fill={isOn ? "#166534" : "#991b1b"} fontSize="11" fontWeight="bold" textAnchor="middle">{isOn ? 'SERVED' : 'SHED'}</text>
              </g>
            );
          })}

          {/* Wires to Feeder B Services */}
          {wire('fb-l3', 'M792 230 V290 H612 V320', isFeederBOn && (services.find(s=>s.id==='L3')?.modeled_served || false))}
          {wire('fb-l4', 'M792 230 V320', isFeederBOn && (services.find(s=>s.id==='L4')?.modeled_served || false))}
          {wire('fb-l5', 'M792 230 V290 H972 V320', isFeederBOn && (services.find(s=>s.id==='L5')?.modeled_served || false))}

          {/* Feeder B Services */}
          {[
            { id: 'L3', x: 552, name: 'Class 1 (L3)' },
            { id: 'L4', x: 732, name: 'Class 2 (L4)' },
            { id: 'L5', x: 912, name: 'Class 3 (L5)' }
          ].map(svc => {
            const s = services.find(x => x.id === svc.id);
            const isOn = s?.modeled_served;
            return (
              <g key={svc.id}>
                <rect x={svc.x+4} y={324} width={120} height={80} fill="#c6c6bc" />
                <rect x={svc.x} y={320} width={120} height={80} fill="#fff" stroke={isOn ? "#52786a" : "#9ca3af"} strokeWidth="4" />
                <text x={svc.x+60} y={345} fill="#1f2937" fontSize="14" fontWeight="bold" textAnchor="middle">{svc.name}</text>
                <text x={svc.x+60} y={365} fill="#4b5563" fontSize="12" textAnchor="middle">{s?.watts} W</text>
                <rect x={svc.x+30} y={375} width={60} height={18} rx={9} fill={isOn ? "#dcfce7" : "#fee2e2"} stroke={isOn ? "#166534" : "#991b1b"} />
                <text x={svc.x+60} y={388} fill={isOn ? "#166534" : "#991b1b"} fontSize="11" fontWeight="bold" textAnchor="middle">{isOn ? 'SERVED' : 'SHED'}</text>
              </g>
            );
          })}

        </svg>
      </div>
    </section>
  );
}
