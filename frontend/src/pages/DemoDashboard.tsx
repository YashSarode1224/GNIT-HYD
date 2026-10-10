import { useState, useEffect, useRef } from 'react';
import { Link } from 'react-router-dom';
import { Activity, Server } from 'lucide-react';
import { changeCapacity, changeFeeder } from '../api';
import { Snapshot, FaultDiagnosis } from '../types';
import NetworkBlueprint from '../components/NetworkBlueprint';
import UnifiedFloorplan from '../components/UnifiedFloorplan';
import LawsBlueprint from '../components/LawsBlueprint';
import SourceCapacityDemandChart from '../components/SourceCapacityDemandChart';
import AllocationHistoryChart from '../components/AllocationHistoryChart';
import IncidentTimeline from '../components/IncidentTimeline';
import HospitalDemo from './HospitalDemo';
import ClassroomsDemo from './ClassroomsDemo';
import './DemoDashboard.css';

interface TimeSeriesPoint {
  time: string;
  capacity: number;
  demand: number;
  servedCount: number;
  shedCount: number;
}

export default function DemoDashboard() {
  const [activeTab, setActiveTab] = useState("overview");
  const [floorplanView, setFloorplanView] = useState<"hospital" | "classrooms">("hospital");
  const [faultVizView, setFaultVizView] = useState<"floorplan" | "network">("floorplan");
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [healthOk, setHealthOk] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [actionPending, setActionPending] = useState<boolean>(false);
  const [actionFeedback, setActionFeedback] = useState<{msg: string, isError: boolean} | null>(null);

  const [history, setHistory] = useState<TimeSeriesPoint[]>([]);
  const MAX_HISTORY = 50;

  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    const connectWs = () => {
      const ws = new WebSocket('ws://127.0.0.1:8000/ws/live');
      wsRef.current = ws;

      ws.onopen = () => {
        setHealthOk(true);
        setError(null);
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data) as Snapshot;
          setSnapshot(data);
          
          const now = new Date(data.generated_at).toLocaleTimeString();
          const demand = data.services.filter(s => s.requested).reduce((sum, s) => sum + s.watts, 0);
          const servedCount = data.services.filter(s => s.modeled_served).length;
          const shedCount = data.services.filter(s => !s.modeled_served && s.requested).length;

          setHistory(prev => {
            const next = [...prev, { time: now, capacity: data.source.capacity_w, demand, servedCount, shedCount }];
            if (next.length > MAX_HISTORY) return next.slice(next.length - MAX_HISTORY);
            return next;
          });

        } catch (err) {
          console.error("Failed to parse websocket message", err);
        }
      };

      ws.onclose = () => {
        setHealthOk(false);
        setTimeout(connectWs, 2000);
      };

      ws.onerror = () => {
        setHealthOk(false);
        setError("WebSocket connection error");
      };
    };

    connectWs();
    return () => {
      if (wsRef.current) wsRef.current.close();
    };
  }, []);

  const handleAction = async (actionFn: () => Promise<any>, successMsg: string) => {
    if (actionPending) return;
    setActionPending(true);
    setActionFeedback(null);
    try {
      const res = await actionFn();
      if (res.accepted) {
        setActionFeedback({ msg: successMsg, isError: false });
      } else {
        setActionFeedback({ msg: `Action rejected: ${res.event_type || 'Constraints violated'}`, isError: true });
      }
    } catch (err: any) {
      setActionFeedback({ msg: `Failed: ${err.message}`, isError: true });
    } finally {
      setActionPending(false);
      setTimeout(() => setActionFeedback(null), 3000);
    }
  };

  const doCapacity = (watts: number) => handleAction(() => changeCapacity(watts), `Capacity set to ${watts}W`);
  const doFeeder = (feeder: string, available: boolean) => handleAction(() => changeFeeder(feeder, available), `Feeder ${feeder} available: ${available}`);

  if (!snapshot) {
    return (
      <div className="dashboard-container loading">
        <Activity className="spin" size={48} />
        <h2>Connecting to Live Feed...</h2>
        {error && <p className="text-err">{error}</p>}
      </div>
    );
  }

  const { services, fault_diagnosis, events } = snapshot;
  const servedWatts = services.filter(s => s.modeled_served).reduce((sum, s) => sum + s.watts, 0);
  const servedCount = services.filter(s => s.modeled_served).length;
  const demand = services.filter(s => s.requested).reduce((sum, s) => sum + s.watts, 0);

  const getLawForFault = (fault?: FaultDiagnosis) => {
    if (!fault || !fault.has_fault) {
      if (demand > snapshot.source.capacity_w) return "capacity";
      return null;
    }
    if (fault.diagnosis.toLowerCase().includes('capacity')) return 'ohm';
    if (fault.diagnosis.toLowerCase().includes('feeder')) return 'continuity';
    return null;
  };

  const activeLaw = getLawForFault(fault_diagnosis);

  return (
    <div className="dashboard-container">
      <header className="dash-header">
        <div className="dash-brand">
          <Activity className="brand-icon" />
          <div>
            <span className="brand-name">PriorityGrid</span>
            <span className="brand-badge">Live Console</span>
          </div>
        </div>
        
        <div className="dash-status-indicators">
          <div className={`status-pill ${healthOk ? 'ok' : 'error'}`}>
            <Server size={14} /> Backend {healthOk ? 'Live' : 'Disconnected'}
          </div>
        </div>
        
        <div className="dash-actions">
          <Link to="/" className="btn-secondary">Back to Home</Link>
        </div>
      </header>

      <nav className="tab-navigation">
        <button className={activeTab === 'overview' ? 'active' : ''} onClick={() => setActiveTab('overview')}>Overview</button>
        <button className={activeTab === 'floorplan' ? 'active' : ''} onClick={() => setActiveTab('floorplan')}>Floor Plan</button>
        <button className={activeTab === 'network' ? 'active' : ''} onClick={() => setActiveTab('network')}>Electrical Network</button>
        <button className={activeTab === 'faults' ? 'active' : ''} onClick={() => setActiveTab('faults')}>Fault Detection</button>
        <button className={activeTab === 'laws' ? 'active' : ''} onClick={() => setActiveTab('laws')}>Electrical Laws</button>
      </nav>

      <main className="tab-content">
        {activeTab === 'overview' && (
          <div className="overview-tab">
            <div className="metrics-grid">
              <div className="metric-box">
                <div className="metric-label">Source Capacity</div>
                <div className="metric-value">{snapshot.source.capacity_w} <small>W</small></div>
              </div>
              <div className="metric-box">
                <div className="metric-label">Modeled Demand Served</div>
                <div className="metric-value text-ok">{servedWatts} <small>W</small></div>
              </div>
              <div className="metric-box">
                <div className="metric-label">Modeled Services</div>
                <div className="metric-value">{servedCount} <small>/ {services.length}</small></div>
              </div>
              <div className="metric-box">
                <div className="metric-label">Grid Health</div>
                <div className={`metric-value ${fault_diagnosis?.has_fault ? 'text-err' : 'text-ok'}`}>
                  {!fault_diagnosis?.has_fault ? 'NOMINAL' : fault_diagnosis?.has_fault ? 'FAULT DETECTED' : 'NOMINAL'}
                </div>
              </div>
            </div>
            
            <div className="charts-grid">
              <div className="chart-panel">
                <h3>Capacity vs Demand (W)</h3>
                <SourceCapacityDemandChart data={history} />
              </div>
              <div className="chart-panel">
                <h3>Allocation (Count)</h3>
                <AllocationHistoryChart data={history} />
              </div>
            </div>
          </div>
        )}

        {activeTab === 'floorplan' && (
          <div className="floorplan-tab">
             <div style={{ display: 'flex', gap: '1rem', marginBottom: '1rem', borderBottom: '1px solid #e2e8f0', paddingBottom: '1rem' }}>
                <button 
                  onClick={() => setFloorplanView('hospital')}
                  style={{ padding: '0.5rem 1rem', background: floorplanView === 'hospital' ? '#0ea5e9' : '#f1f5f9', color: floorplanView === 'hospital' ? 'white' : '#334155', border: 'none', borderRadius: '4px', cursor: 'pointer', fontWeight: 'bold' }}
                >
                  Hospital Zone
                </button>
                <button 
                  onClick={() => setFloorplanView('classrooms')}
                  style={{ padding: '0.5rem 1rem', background: floorplanView === 'classrooms' ? '#0ea5e9' : '#f1f5f9', color: floorplanView === 'classrooms' ? 'white' : '#334155', border: 'none', borderRadius: '4px', cursor: 'pointer', fontWeight: 'bold' }}
                >
                  Classrooms Zone
                </button>
             </div>
             <div className="floorplan-view">
               {floorplanView === 'hospital' ? <HospitalDemo hideHeader={true} /> : <ClassroomsDemo hideHeader={true} />}
             </div>
          </div>
        )}

        {activeTab === 'network' && (
          <div className="network-tab" style={{ height: '70vh', overflow: 'hidden' }}>
            <NetworkBlueprint snapshot={snapshot} />
          </div>
        )}

        {activeTab === 'faults' && (
          <div className="fault-detection-tab">
            <div className="fault-main-panel">
              <div className="fault-viz" style={{ display: 'flex', flexDirection: 'column' }}>
                 <div style={{ display: 'flex', gap: '1rem', paddingBottom: '1rem', borderBottom: '1px solid #e2e8f0', marginBottom: '1rem' }}>
                   <button 
                     onClick={() => setFaultVizView('floorplan')}
                     style={{ padding: '0.5rem 1rem', background: faultVizView === 'floorplan' ? '#0ea5e9' : '#f1f5f9', color: faultVizView === 'floorplan' ? 'white' : '#334155', border: 'none', borderRadius: '4px', cursor: 'pointer', fontWeight: 'bold' }}
                   >
                     Floor Plan
                   </button>
                   <button 
                     onClick={() => setFaultVizView('network')}
                     style={{ padding: '0.5rem 1rem', background: faultVizView === 'network' ? '#0ea5e9' : '#f1f5f9', color: faultVizView === 'network' ? 'white' : '#334155', border: 'none', borderRadius: '4px', cursor: 'pointer', fontWeight: 'bold' }}
                   >
                     Electrical Network
                   </button>
                 </div>
                 
                 <div style={{ height: '560px', overflow: 'hidden' }}>
                   {faultVizView === 'floorplan' ? (
                     <UnifiedFloorplan snapshot={snapshot} />
                   ) : (
                     <NetworkBlueprint snapshot={snapshot} />
                   )}
                 </div>
              </div>
              
              {/* Laws panel inside fault detection */}
              <div className="fault-laws-panel">
                 <h3>Relevant Electrical Principle</h3>
                 {activeLaw === 'capacity' && (
                   <div className="law-card">
                     <h4>Capacity Constraint</h4>
                     <p>Requested Demand ({demand}W) exceeds Source Capacity ({snapshot.source.capacity_w}W). The CP-SAT optimizer uses tier-priority sorting to shed loads mathematically.</p>
                     <code>demand ≤ source_capacity</code>
                   </div>
                 )}
                 {activeLaw === 'ohm' && (
                   <div className="law-card">
                     <h4>Ohm's Law & Overload</h4>
                     <p>I = V / R. When current exceeds 110% of the transformer's rating, heat accumulation threatens the insulation. The system sheds load to reduce total current draw.</p>
                   </div>
                 )}
                 {activeLaw === 'continuity' && (
                   <div className="law-card">
                     <h4>Circuit Continuity (Upstream Loss)</h4>
                     <p>A break in the supply path means V_in = 0. Without voltage potential, current cannot flow. Downstream loads are physically unreachable.</p>
                   </div>
                 )}
                 {!activeLaw && (
                   <div className="law-card normal">
                     <p>Grid is operating nominally. All electrical constraints are satisfied.</p>
                   </div>
                 )}
              </div>
            </div>

            <div className="fault-side-panel">
               <h3>Fault Lab</h3>
               <div className="fault-controls">
                 <h4>Inject Simulated Faults</h4>
                 <div className="fault-buttons">
                   <button onClick={() => doFeeder('A', false)}>Kill Feeder A (Outage)</button>
                   <button onClick={() => doFeeder('A', true)}>Restore Feeder A</button>
                   <button onClick={() => doCapacity(2000)}>Drop Capacity (Overload)</button>
                   <button onClick={() => doCapacity(14000)}>Restore Capacity</button>
                 </div>
                 {actionFeedback && (
                    <div className={`feedback-alert ${actionFeedback.isError ? 'err' : 'ok'}`}>
                      {actionFeedback.msg}
                    </div>
                  )}
               </div>

               <div className="fault-diagnosis">
                 <h4>Backend Diagnosis</h4>
                 {fault_diagnosis ? (
                   <div className={`diagnosis-card ${!fault_diagnosis.has_fault ? 'ok' : 'err'}`}>
                      <h5>{fault_diagnosis.has_fault ? 'FAULT' : 'NORMAL'}</h5>
                      <p>{fault_diagnosis.diagnosis}</p>
                   </div>
                 ) : (
                   <div className="diagnosis-card ok">
                     <h5>NOMINAL</h5>
                     <p>No faults detected.</p>
                   </div>
                 )}
               </div>

               <div className="fault-timeline">
                 <h4>Incident Timeline</h4>
                 <div style={{ maxHeight: '200px', overflowY: 'auto' }}>
                   <IncidentTimeline events={events || []} />
                 </div>
               </div>
            </div>
          </div>
        )}

        {activeTab === 'laws' && (
          <div className="laws-tab" style={{height: "80vh"}}><LawsBlueprint /></div>
        )}
      </main>
    </div>
  );
}
