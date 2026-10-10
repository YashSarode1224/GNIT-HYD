from pydantic import BaseModel, Field, ConfigDict, StrictStr, StrictFloat, StrictInt, StrictBool
from enum import Enum
from typing import List, Optional, Dict
from datetime import datetime

class HardwareLinkStatus(str, Enum):
    NOT_CONNECTED = "NOT_CONNECTED"
    CONNECTED = "CONNECTED"
    ERROR = "ERROR"

class SourceKind(str, Enum):
    SIMULATED = "SIMULATED"

class Tier(str, Enum):
    T1 = "T1"
    T2 = "T2"
    T3 = "T3"

class SourceInfo(BaseModel):
    kind: SourceKind
    capacity_w: int

class ServiceSnapshot(BaseModel):
    id: str
    name: str
    tier: Tier
    feeder: str
    watts: int
    requested: bool
    modeled_served: bool
    indicator_confirmed: Optional[bool] = None
    model_reason: str

class RfidReaderStatus(str, Enum):
    NOT_CONNECTED = "NOT_CONNECTED"
    CONNECTED = "CONNECTED"
    ERROR = "ERROR"

class RfidEventType(str, Enum):
    CARD_RECOGNIZED = "CARD_RECOGNIZED"
    UNKNOWN_CARD = "UNKNOWN_CARD"
    DUPLICATE_SUPPRESSED = "DUPLICATE_SUPPRESSED"

class HospitalRoom(BaseModel):
    id: str
    name: str
    lighting_service: str
    led_bit: int

class ClassroomInfo(BaseModel):
    id: str
    name: str
    service_id: str
    rfid_card_registered: bool
    led_bit: int
    load_event_active: bool

class HospitalZone(BaseModel):
    rooms: List[HospitalRoom]

class ClassroomZone(BaseModel):
    active_classroom_ids: List[str] = Field(default_factory=list)
    recent_rfid_scan: Optional[str] = None
    rfid_reader_status: RfidReaderStatus = RfidReaderStatus.NOT_CONNECTED
    classrooms: List[ClassroomInfo]

class FacilityZones(BaseModel):
    hospital: HospitalZone
    classroom: ClassroomZone

class SystemEvent(BaseModel):
    timestamp: str
    type: str
    description: str

class FaultDiagnosis(BaseModel):
    has_fault: bool
    diagnosis: str
    severity: str
    status: str


class ApplianceSnapshot(BaseModel):
    id: str
    name: str
    room: str
    tier: str
    watts: int
    requested: bool
    modeled_served: bool
    model_reason: str

class SystemSnapshot(BaseModel):
    control_revision: int
    generated_at: datetime
    source: SourceInfo
    feeder_limits_w: Dict[str, int]
    requested_mask: int
    modeled_mask: int
    proposed_mask: int
    indicator_command_mask: Optional[int] = None
    indicator_confirmed_mask: Optional[int] = None
    hardware_link: HardwareLinkStatus
    services: List[ServiceSnapshot]
    appliances: List[ApplianceSnapshot] = Field(default_factory=list)
    zones: Optional[FacilityZones] = None
    events: List[SystemEvent] = []
    fault_diagnosis: Optional[FaultDiagnosis] = None
    activity: Dict[str, "ActivitySnapshot"] = Field(default_factory=dict)
    model: Dict[str, object] = Field(default_factory=dict)
    replay: "ReplaySnapshot"
    allocation: "AllocationSnapshot"


class ActivityObservationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    classroom_id: StrictStr
    temperature_c: Optional[StrictFloat | StrictInt] = None
    humidity_pct: Optional[StrictFloat | StrictInt] = None
    co2_ppm: Optional[StrictFloat | StrictInt] = None
    humidity_ratio: Optional[StrictFloat | StrictInt] = None
    observed_at: StrictStr
    source: StrictStr


class ActivitySnapshot(BaseModel):
    state: str
    score: Optional[float] = None
    reason: str
    source: Optional[str] = None
    observed_at: Optional[datetime] = None
    model_version: str
    priority: str
    evidence: Optional[Dict[str, Optional[float]]] = None


class ReplaySnapshot(BaseModel):
    running: bool
    index: int
    length: int


class AllocationSnapshot(BaseModel):
    objective: str
    critical_shortfall_w: int
    served_w: int
    baseline_mask: int


class ReplayActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    action: StrictStr

class RfidScanRequest(BaseModel):
    uid: str
    event_id: Optional[str] = None

class RfidScanResponse(BaseModel):
    accepted: bool
    active_classroom_ids: List[str] = Field(default_factory=list)
    classroom_name: Optional[str] = None
    service_id: Optional[str] = None
    event_type: RfidEventType

class CapacityChangeRequest(BaseModel):
    capacity_w: StrictInt = Field(ge=0, le=20000)

class CapacityChangeResponse(BaseModel):
    accepted: bool
    new_capacity_w: int
    control_revision: int

class ClassroomLoadRequest(BaseModel):
    classroom_id: StrictStr
    active: StrictBool

class ClassroomLoadResponse(BaseModel):
    accepted: bool
    classroom_id: str
    load_event_active: bool

class FeederChangeRequest(BaseModel):
    feeder: StrictStr
    available: StrictBool

class FeederChangeResponse(BaseModel):
    accepted: bool
    feeder: str
    available: bool
    control_revision: int
