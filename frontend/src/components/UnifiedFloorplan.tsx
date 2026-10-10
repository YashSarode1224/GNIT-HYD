import { Snapshot } from '../types';
import '../pages/ClassroomBlueprint.css';
import { 
  Wind, Activity, Droplets, Lightbulb, 
  Thermometer, Crosshair, Server, Bell, 
  Fan, Monitor, Projector, FlaskConical, Zap 
} from 'lucide-react';

interface Props {
  snapshot: Snapshot;
}

const getIconForAppliance = (id: string, on: boolean) => {
  const color = on ? "#059669" : "#6b7280";
  const props = { size: 20, color, strokeWidth: 2 };
  
  if (id.includes('vent')) return <Wind {...props} />;
  if (id.includes('mon')) return <Activity {...props} />;
  if (id.includes('inf')) return <Droplets {...props} />;
  if (id.includes('light')) return <Lightbulb {...props} />;
  if (id.includes('o2')) return <Thermometer {...props} />;
  if (id.includes('surg')) return <Crosshair {...props} />;
  if (id.includes('anes')) return <Server {...props} />;
  if (id.includes('call')) return <Bell {...props} />;
  if (id.includes('pump')) return <Droplets {...props} />;
  if (id.includes('ac')) return <Fan {...props} />;
  if (id.includes('comp')) return <Monitor {...props} />;
  if (id.includes('proj')) return <Projector {...props} />;
  if (id.includes('inst')) return <FlaskConical {...props} />;
  return <Zap {...props} />;
};

export default function UnifiedFloorplan({ snapshot }: Props) {
  const { services, appliances, fault_diagnosis } = snapshot;

  const wire = (id: string, d: string, on: boolean, main = false, fault = false) => (
    <g key={id} data-circuit={id} className={`power-map__circuit ${on ? 'is-on' : 'is-off'} ${main ? 'is-main' : ''}`}>
      <path className="power-map__cable-bed" d={d} stroke={fault ? '#ffcccc' : undefined} />
      <path className="power-map__cable" d={d} stroke={fault ? '#ff4444' : undefined} />
      {on && !fault && <path className="power-map__current" d={d} />}
    </g>
  );

  const getSvc = (id: string) => services.find(s => s.id === id);
  const isSvcServed = (id: string) => getSvc(id)?.modeled_served || false;

  const feederAFault = fault_diagnosis?.diagnosis.includes('Feeder A');
  const feederBFault = fault_diagnosis?.diagnosis.includes('Feeder B');

  const FloorplanSymbol = ({ x, y, id, busX, fault = false }: { x: number, y: number, id: string, busX: number, fault?: boolean }) => {
    const app = appliances?.find((a: any) => a.id === id);
    if (!app) return null;
    const on = app.modeled_served;
    const isLeft = x < busX;
    
    const wireY = y;
    const wireX1 = isLeft ? x + 12 : x - 12;
    const wireX2 = busX;
    const pathD = `M ${wireX1} ${wireY} H ${wireX2}`;
    
    const fill = on && !fault ? "#ecfdf5" : "#f9fafb";
    const stroke = on && !fault ? "#059669" : "#d1d5db";
    const textColor = on && !fault ? "#065f46" : "#6b7280";
    
    return (
      <g className="appliance-item" style={{ cursor: 'pointer' }} onClick={() => alert(`${app.name}
Requested: ${app.requested}
Served: ${on}
Reason: ${app.model_reason}`)}>
        {wire(`branch-${id}`, pathD, on, false, fault)}
        
        <circle cx={x} cy={y} r="14" fill={fill} stroke={stroke} strokeWidth="1.5" />
        <g transform={`translate(${x - 10}, ${y - 10})`}>
          {getIconForAppliance(id, on && !fault)}
        </g>
        
        <text x={x} y={y + 24} fill={textColor} fontSize="9" fontWeight="bold" textAnchor="middle">{app.name}</text>
        <text x={x} y={y + 34} fill={textColor} fontSize="8" textAnchor="middle">{app.watts}W</text>
      </g>
    );
  };

  const icuMainServed = isSvcServed('L0');
  const theatreMainServed = isSvcServed('L0') || isSvcServed('L1') || isSvcServed('L2');
  const wardsMainServed = isSvcServed('L0') || isSvcServed('L1') || isSvcServed('L2');

  return (
    <div className="power-map__viewport" style={{ height: "100%" }} tabIndex={0} role="region">
      <svg className="power-map__drawing" viewBox="0 0 1080 700" style={{ width: "100%", height: "100%", maxHeight: "560px" }}>
        <defs>
          <pattern id="campus-tiles" width="20" height="20" patternUnits="userSpaceOnUse">
            <rect width="20" height="20" fill="#edece5" />
            <path d="M20 0H0V20" fill="none" stroke="#d9dad2" strokeWidth=".7" />
          </pattern>
          <pattern id="hosp-tiles" width="20" height="20" patternUnits="userSpaceOnUse">
            <rect width="20" height="20" fill="#e8ece8" />
            <path d="M20 0H0V20" fill="none" stroke="#d0d6d0" strokeWidth=".7" />
          </pattern>
          <pattern id="class-tiles" width="20" height="20" patternUnits="userSpaceOnUse">
            <rect width="20" height="20" fill="#f5efdd" />
            <path d="M20 0H0V20" fill="none" stroke="#e6dfcb" strokeWidth=".8" />
          </pattern>
        </defs>
        <rect width="1080" height="700" fill="url(#campus-tiles)" />
        <text x="30" y="26" className="power-map__map-note">INTEGRATED CAMPUS FLOOR PLAN (APPLIANCE LEVEL)</text>

        {/* Main Source Bus */}
        <rect x="180" y="315" width="80" height="50" fill="#2d3748" rx="4" />
        <text x="220" y="335" fill="white" fontSize="12" fontWeight="bold" textAnchor="middle">UTILITY</text>
        <text x="220" y="352" fill="#a0aec0" fontSize="10" textAnchor="middle">SOURCE</text>
        
        {wire('main-bus-h1', 'M 260 340 H 680', true, true)}
        {wire('main-bus-v-right', 'M 680 90 V 640', true, true)}

        {/* Hospital Zone (Left) */}
        <text x="50" y="70" className="power-map__map-note" fontSize="14">HOSPITAL ZONE (FEEDER A)</text>
        {feederAFault && <text x="50" y="90" fill="red" fontWeight="bold">FEEDER A OUTAGE</text>}

        {/* ICU Room */}
        <g>
          <rect x={30} y={100} width="300" height="220" fill="url(#hosp-tiles)" stroke="#5a7a5e" strokeWidth="6" />
          <text x={40} y={120} className="power-map__room-name">ICU</text>
          {wire('fa-icu-main', 'M 260 340 V 335 H 180 V 120 V 270', icuMainServed, true, feederAFault)}
          
          <FloorplanSymbol x={90} y={135} id="icu_vent" busX={180} fault={feederAFault} />
          <FloorplanSymbol x={90} y={200} id="icu_inf" busX={180} fault={feederAFault} />
          <FloorplanSymbol x={90} y={265} id="icu_light" busX={180} fault={feederAFault} />
          <FloorplanSymbol x={270} y={160} id="icu_mon" busX={180} fault={feederAFault} />
          <FloorplanSymbol x={270} y={230} id="icu_o2" busX={180} fault={feederAFault} />
        </g>

        {/* Theatre Room */}
        <g>
          <rect x={350} y={100} width="300" height="220" fill="url(#hosp-tiles)" stroke="#5a7a5e" strokeWidth="6" />
          <text x={360} y={120} className="power-map__room-name">Theatre</text>
          {wire('fa-theatre-main', 'M 500 340 V 120 V 270', theatreMainServed, true, feederAFault)}
          
          <FloorplanSymbol x={410} y={135} id="the_surg" busX={500} fault={feederAFault} />
          <FloorplanSymbol x={410} y={200} id="the_vmon" busX={500} fault={feederAFault} />
          <FloorplanSymbol x={410} y={265} id="the_ac" busX={500} fault={feederAFault} />
          <FloorplanSymbol x={590} y={160} id="the_anes" busX={500} fault={feederAFault} />
          <FloorplanSymbol x={590} y={230} id="the_light" busX={500} fault={feederAFault} />
        </g>

        {/* Wards Room */}
        <g>
          <rect x={30} y={370} width="300" height="200" fill="url(#hosp-tiles)" stroke="#5a7a5e" strokeWidth="6" />
          <text x={40} y={390} className="power-map__room-name">Wards</text>
          {wire('fa-wards-main', 'M 260 340 V 360 H 180 V 390 V 500', wardsMainServed, true, feederAFault)}
          
          <FloorplanSymbol x={90} y={420} id="war_call" busX={180} fault={feederAFault} />
          <FloorplanSymbol x={90} y={510} id="war_pump" busX={180} fault={feederAFault} />
          <FloorplanSymbol x={270} y={420} id="war_light" busX={180} fault={feederAFault} />
          <FloorplanSymbol x={270} y={510} id="war_ac" busX={180} fault={feederAFault} />
        </g>

        {/* Classrooms Zone (Right) */}
        <text x="730" y="70" className="power-map__map-note" fontSize="14">CLASSROOMS ZONE (FEEDER B)</text>
        {feederBFault && <text x="730" y="90" fill="red" fontWeight="bold">FEEDER B OUTAGE</text>}

        {/* CR1 */}
        <g>
          <rect x={720} y={90} width="330" height="170" fill="url(#class-tiles)" stroke="#747c76" strokeWidth="6" />
          <text x={730} y={110} className="power-map__room-name">Classroom 1</text>
          {wire('fb-cr1-main', 'M 680 140 H 885 V 110 V 230', isSvcServed('L3'), true, feederBFault)}
          
          <FloorplanSymbol x={780} y={140} id="cr1_light" busX={885} fault={feederBFault} />
          <FloorplanSymbol x={780} y={210} id="cr1_proj" busX={885} fault={feederBFault} />
          <FloorplanSymbol x={990} y={175} id="cr1_fan" busX={885} fault={feederBFault} />
        </g>

        {/* CR2 */}
        <g>
          <rect x={720} y={280} width="330" height="170" fill="url(#class-tiles)" stroke="#747c76" strokeWidth="6" />
          <text x={730} y={300} className="power-map__room-name">Classroom 2</text>
          {wire('fb-cr2-main', 'M 680 330 H 885 V 300 V 420', isSvcServed('L4'), true, feederBFault)}
          
          <FloorplanSymbol x={780} y={330} id="cr2_light" busX={885} fault={feederBFault} />
          <FloorplanSymbol x={780} y={400} id="cr2_proj" busX={885} fault={feederBFault} />
          <FloorplanSymbol x={990} y={365} id="cr2_fan" busX={885} fault={feederBFault} />
        </g>

        {/* CR3 */}
        <g>
          <rect x={720} y={470} width="330" height="200" fill="url(#class-tiles)" stroke="#747c76" strokeWidth="6" />
          <text x={730} y={490} className="power-map__room-name">Classroom 3</text>
          {wire('fb-cr3-main', 'M 680 520 H 885 V 490 V 640', isSvcServed('L5'), true, feederBFault)}
          
          <FloorplanSymbol x={780} y={530} id="cr3_light" busX={885} fault={feederBFault} />
          <FloorplanSymbol x={780} y={590} id="cr3_proj" busX={885} fault={feederBFault} />
          <FloorplanSymbol x={780} y={640} id="cr3_fan" busX={885} fault={feederBFault} />
          <FloorplanSymbol x={990} y={580} id="cr3_comp" busX={885} fault={feederBFault} />
        </g>

      </svg>
    </div>
  );
}
