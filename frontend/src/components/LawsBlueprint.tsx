import '../pages/ClassroomBlueprint.css';

export default function LawsBlueprint() {
  return (
    <section className="power-map" aria-label="Electrical Laws Educational Map">
      <header className="power-map__toolbar">
        <div>
          <span className="power-map__eyebrow">Engineering / Educational layer</span>
          <h2>Governing Electrical Principles</h2>
        </div>
      </header>
      
      <div className="power-map__viewport" tabIndex={0} role="region" style={{ background: '#edece5' }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '2rem', padding: '2rem', height: '100%', boxSizing: 'border-box' }}>
          
          <div className="law-blueprint-card">
             <div className="blueprint-title">Ohm's Law</div>
             <div className="blueprint-formula">V = I × R</div>
             <p>Voltage equals Current times Resistance. Used by the grid to detect and mitigate overcurrent faults by shedding loads to reduce I.</p>
          </div>

          <div className="law-blueprint-card">
             <div className="blueprint-title">Electrical Power</div>
             <div className="blueprint-formula">P = V × I</div>
             <p>Power (Watts) is Voltage times Current. All capacity and demand calculations use this fundamental law for steady-state estimation.</p>
          </div>

          <div className="law-blueprint-card">
             <div className="blueprint-title">Kirchhoff's Current Law (KCL)</div>
             <div className="blueprint-formula">Σ I_in = Σ I_out</div>
             <p>Total current entering a node equals total current leaving. Verifies feeder balance and detects upstream/downstream leakage.</p>
          </div>

          <div className="law-blueprint-card">
             <div className="blueprint-title">Capacity Constraints</div>
             <div className="blueprint-formula">Σ Demand_served ≤ Capacity</div>
             <p>The core CP-SAT optimizer constraint. Ensures we never allocate more active watts than the primary source can safely supply.</p>
          </div>

        </div>
      </div>
    </section>
  );
}
