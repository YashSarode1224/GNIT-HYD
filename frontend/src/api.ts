import type { components } from './schema';
import { 
  Snapshot, 
  HealthResponse, 
  RfidScanResponse, 
  CapacityChangeResponse, 
  ClassroomLoadResponse, 
  FeederChangeResponse,
  ModelStatus,
  ClassroomDemoSnapshot,
  ClassroomDemoActionName,
  ClassroomDemoRoom,
  HospitalDemoSnapshot,
  HospitalDemoActionName,
  HospitalDemoFault,
  HardwareStatus
} from './types';
import type { CityDemoSnapshot, DemoEvidence, DemandForecast, SiteScenarios, SiteScenarioSwitch } from './types';
import type { HospitalDemoScenario, HospitalFaultSnapshot, DistrictActionRequest, DistrictGenerationRequest, DistrictSnapshot } from './types';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000';

export function getWebSocketUrl(path = '/ws/live'): string {
  const url = new URL(API_BASE_URL);
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
  url.pathname = path;
  url.search = '';
  return url.toString();
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = 'ApiError';
  }
}

async function fetchJson<T>(endpoint: string, options?: RequestInit): Promise<T> {
  try {
    const response = await fetch(`${API_BASE_URL}${endpoint}`, {
      ...options,
      headers: {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        ...options?.headers,
      },
    });

    if (!response.ok) {
      throw new ApiError(response.status, `HTTP error ${response.status}`);
    }

    return await response.json() as T;
  } catch (error) {
    if (error instanceof ApiError) {
      throw error;
    }
    throw new Error('Network or connection error. Backend may be unavailable.');
  }
}

export async function fetchHealth(signal?: AbortSignal): Promise<HealthResponse> {
  return fetchJson<HealthResponse>('/api/v1/health', { signal });
}

export async function fetchSnapshot(signal?: AbortSignal): Promise<Snapshot> {
  return fetchJson<Snapshot>('/api/v1/snapshot', { signal });
}

export function getCityDemo(source: DemandForecast['source'], replayIndex: number, signal?: AbortSignal): Promise<CityDemoSnapshot> {
  return fetchJson(`/api/v1/demo?source=${source}&replay_index=${replayIndex}`, { signal });
}

export function getDemoEvidence(signal?: AbortSignal): Promise<DemoEvidence> {
  return fetchJson('/api/v1/demo/evidence', { signal });
}

export async function fetchModelStatus(signal?: AbortSignal): Promise<ModelStatus> {
  return fetchJson<ModelStatus>('/api/v1/model/status', { signal });
}

export function getDistrictSnapshot(signal?: AbortSignal): Promise<DistrictSnapshot> {
  return fetchJson<DistrictSnapshot>('/api/v1/district', { signal });
}

export function districtAction(action: DistrictActionRequest): Promise<DistrictSnapshot> {
  return fetchJson<DistrictSnapshot>('/api/v1/district/action', { method: 'POST', body: JSON.stringify(action) });
}

export function generateDistrictTopology(request: DistrictGenerationRequest): Promise<DistrictSnapshot> {
  return fetchJson<DistrictSnapshot>('/api/v1/district/generation', { method: 'POST', body: JSON.stringify(request) });
}

export async function setReplayAction(action: 'start' | 'pause' | 'reset'): Promise<void> {
  await fetchJson('/api/v1/replay', { method: 'POST', body: JSON.stringify({ action }) });
}

function sessionEventIdentity(run_id: string) {
  return { run_id, event_id: crypto.randomUUID(), observed_at: new Date().toISOString() };
}

export async function processRfidScan(uid: string, run_id: string): Promise<RfidScanResponse> {
  return fetchJson<RfidScanResponse>('/api/v1/rfid/scan', {
    method: 'POST',
    body: JSON.stringify({ uid, ...(run_id ? sessionEventIdentity(run_id) : {}) })
  });
}

export async function changeCapacity(capacity_w: number): Promise<CapacityChangeResponse> {
  return fetchJson<CapacityChangeResponse>('/api/v1/simulation/capacity', {
    method: 'POST',
    body: JSON.stringify({ capacity_w })
  });
}

export async function getSiteScenarios(): Promise<SiteScenarios> {
  return fetchJson<SiteScenarios>('/api/v1/site/scenarios');
}

/** Switch every route to a named teaching scenario in one command (#33). */
export async function switchSiteScenario(scenario: string): Promise<SiteScenarioSwitch> {
  return fetchJson<SiteScenarioSwitch>('/api/v1/site/scenario', {
    method: 'POST',
    body: JSON.stringify({ scenario })
  });
}

export async function changeClassroomLoad(classroom_id: string, active: boolean, run_id: string): Promise<ClassroomLoadResponse> {
  return fetchJson<ClassroomLoadResponse>('/api/v1/simulation/classroom-load', {
    method: 'POST',
    body: JSON.stringify({ classroom_id, active, ...(run_id ? sessionEventIdentity(run_id) : {}) })
  });
}

export async function changeFeeder(feeder: string, available: boolean): Promise<FeederChangeResponse> {
  return fetchJson<FeederChangeResponse>('/api/v1/simulation/feeder', {
    method: 'POST',
    body: JSON.stringify({ feeder, available })
  });
}

export async function getClassroomDemo(signal?: AbortSignal): Promise<ClassroomDemoSnapshot> {
  return fetchJson<ClassroomDemoSnapshot>('/api/v1/visualizers/classrooms', { signal });
}

export async function connectHardware(port: string, board: 'A' | 'B' = 'A'): Promise<HardwareStatus> {
  return fetchJson<HardwareStatus>('/api/v1/hardware/connect', { method: 'POST', body: JSON.stringify({ port, board }) });
}

export async function disconnectHardware(): Promise<HardwareStatus> {
  return fetchJson<HardwareStatus>('/api/v1/hardware/disconnect', { method: 'POST' });
}

export async function postClassroomDemo(action: ClassroomDemoActionName, classroom_id?: ClassroomDemoRoom['id'], capacity_w?: number, run_id?: string): Promise<ClassroomDemoSnapshot> {
  return fetchJson<ClassroomDemoSnapshot>('/api/v1/visualizers/classrooms', {
    method: 'POST', body: JSON.stringify({ action, ...(classroom_id ? { classroom_id } : {}), ...(capacity_w !== undefined ? { capacity_w } : {}),
      ...(run_id && (action === 'scan' || action === 'unscan') ? sessionEventIdentity(run_id) : {}) })
  });
}

export async function getHospitalDemo(signal?: AbortSignal): Promise<HospitalDemoSnapshot> {
  return fetchJson<HospitalDemoSnapshot>('/api/v1/visualizers/hospital', { signal });
}

export function postHospitalScenario(rehearsal: NonNullable<HospitalDemoScenario>, signal?: AbortSignal): Promise<HospitalFaultSnapshot> {
  return fetchJson('/api/v1/visualizers/hospital', { method: 'POST', body: JSON.stringify({ rehearsal }), signal });
}

export async function postHospitalDemo(action: HospitalDemoActionName, zone_id?: string, capacity_w?: number, fault?: HospitalDemoFault): Promise<HospitalDemoSnapshot> {
  return fetchJson<HospitalDemoSnapshot>('/api/v1/visualizers/hospital', {
    method: 'POST', body: JSON.stringify({ action, ...(zone_id ? { zone_id } : {}), ...(capacity_w !== undefined ? { capacity_w } : {}), ...(fault ? { fault } : {}) })
  });
}

export async function getPowerSystem(signal?: AbortSignal): Promise<components['schemas']['PowerSystemResponse']> {
  return fetchJson('/api/v1/power-system', { signal });
}

export async function requestAppliance(appliance_id: string, requested: boolean): Promise<components['schemas']['ApplianceRequestResponse']> {
  return fetchJson('/api/v1/appliances/request', { method: 'POST', body: JSON.stringify({ appliance_id, requested }) });
}

export async function postNewRun(): Promise<components['schemas']['SiteIdentityResponse']> {
  return fetchJson<components['schemas']['SiteIdentityResponse']>('/api/v1/site/new-run', { method: 'POST' });
}
