"""Regenerate the checked-in GNITC topology using SHIFT at 995004c84c16df7c8ebfd3ddddf3e723a0938a99.

From the repository root, run the automated setup and generation script:
`python tools/setup_shift_and_generate.py`
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess

import networkx as nx
import numpy as np
from gdm.distribution import CatalogSystem
from gdm.distribution.components import DistributionBranchBase, DistributionLoad, DistributionTransformer, DistributionVoltageSource, MatrixImpedanceBranch
from gdm.distribution.equipment import (
    DistributionTransformerEquipment, LoadEquipment, MatrixImpedanceBranchEquipment,
    PhaseLoadEquipment, PhaseVoltageSourceEquipment, VoltageSourceEquipment, WindingEquipment,
)
from gdm.distribution.common.sequence_pair import SequencePair
from gdm.distribution.enums import ConnectionType, VoltageTypes
from gdm.quantities import (ActivePower, Angle, ApparentPower, CapacitancePULength, Current,
                             Distance, ReactivePower, ResistancePULength, ReactancePULength, Voltage)
from shapely.geometry import shape
import shift
from shift.data_model import GeoLocation, GroupModel
from shift.data_model import TransformerPhaseMapperModel, TransformerTypes, TransformerVoltageModel
from shift.graph.prsgb import PRSG
from shift.graph.distribution_graph import DistributionGraph
from shift.mapper.balanced_phase_mapper import BalancedPhaseMapper
from shift.mapper.edge_equipment_mapper import EdgeEquipmentMapper
from shift.mapper.transformer_voltage_mapper import TransformerVoltageMapper
from shift.system_builder import DistributionSystemBuilder
from shift.graph.secondary import MeshSteinerStrategy, RadialStrategy

ROOT = Path(__file__).resolve().parents[2]
MAP = ROOT / "backend/app/district/data/gnitc_map.geojson"
OUTPUT = ROOT / "backend/app/district/data/gnitc_topology.json"
CENTER = GeoLocation(78.659909, 17.161849)
SHIFT_COMMIT = "995004c84c16df7c8ebfd3ddddf3e723a0938a99"
STRATEGIES = {"RadialStrategy": RadialStrategy, "MeshSteinerStrategy": MeshSteinerStrategy}


def _verify_shift_commit() -> None:
    source_root = Path(shift.__file__).resolve().parents[2]
    actual = subprocess.run(
        ["git", "-C", str(source_root), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    if actual != SHIFT_COMMIT:
        raise RuntimeError(f"SHIFT source commit mismatch: expected {SHIFT_COMMIT}, found {actual}")


def _synthetic_catalog() -> CatalogSystem:
    """Small in-code catalog: all ratings and impedance values are demo assumptions."""
    system = CatalogSystem(name="blackout_mesh_synthetic_catalog", auto_add_composed_components=True)
    system.add_component(DistributionTransformerEquipment(
        name="synthetic_11kv_400v_100kva", windings=[
            WindingEquipment(num_phases=3, rated_power=ApparentPower(100, "kva"),
                rated_voltage=Voltage(11, "kilovolt"), voltage_type=VoltageTypes.LINE_TO_GROUND,
                connection_type=ConnectionType.STAR, resistance=0.01, is_grounded=True, tap_positions=[1.0, 1.0, 1.0]),
            WindingEquipment(num_phases=3, rated_power=ApparentPower(100, "kva"),
                rated_voltage=Voltage(0.4, "kilovolt"), voltage_type=VoltageTypes.LINE_TO_GROUND,
                connection_type=ConnectionType.STAR, resistance=0.01, is_grounded=True, tap_positions=[1.0, 1.0, 1.0]),
        ], coupling_sequences=[SequencePair(0, 1)], winding_reactances=[0.02], is_center_tapped=False,
        pct_no_load_loss=0.1, pct_full_load_loss=1.0,
    ))
    system.add_component(MatrixImpedanceBranchEquipment(
        name="synthetic_three_phase_branch_100a", r_matrix=ResistancePULength(np.eye(3) * 0.4, "ohm/mile"),
        x_matrix=ReactancePULength(np.eye(3) * 0.3, "ohm/mile"),
        c_matrix=CapacitancePULength(np.zeros((3, 3)), "nanofarad/mile"), ampacity=Current(100, "ampere"),
    ))
    return system


class _SyntheticEdgeEquipmentMapper(EdgeEquipmentMapper):
    # SHIFT 995004c omits node equipment mapping from EdgeEquipmentMapper.
    @property
    def node_asset_equipment_mapping(self):
        result = {}
        for node in self.graph.get_nodes():
            result[node.name] = {}
            for asset in node.assets or set():
                if asset is DistributionVoltageSource:
                    source = PhaseVoltageSourceEquipment(name=f"synthetic_source_{node.name}",
                        voltage=Voltage(11, "kilovolt"), angle=Angle(0, "degree"),
                        voltage_type=VoltageTypes.LINE_TO_GROUND, r0=0.0, r1=0.0, x0=0.0, x1=0.0)
                    result[node.name][asset] = VoltageSourceEquipment(
                        name=f"synthetic_source_equipment_{node.name}", sources=[source])
                elif asset is DistributionLoad:
                    loads = [PhaseLoadEquipment(name=f"synthetic_load_phase_{node.name}_{phase}",
                        real_power=ActivePower(5, "kilowatt"), reactive_power=ReactivePower(1, "kilovar"),
                        z_real=0.0, z_imag=0.0, i_real=0.0, i_imag=0.0, p_real=1.0, p_imag=1.0)
                        for phase in "ABC"]
                    result[node.name][asset] = LoadEquipment(
                        name=f"synthetic_load_equipment_{node.name}", phase_loads=loads)
        return result


def _run_shift_stages(prsg_graph: DistributionGraph) -> dict:
    graph = DistributionGraph()
    graph.add_nodes(list(prsg_graph.get_nodes()))
    for from_node, to_node, edge in prsg_graph.get_edges():
        edge_type = MatrixImpedanceBranch if edge.edge_type is DistributionBranchBase else edge.edge_type
        graph.add_edge(from_node, to_node, edge.model_copy(update={"edge_type": edge_type}))

    transformers = [(a, b, edge) for a, b, edge in graph.get_edges()
                    if edge.edge_type is DistributionTransformer]
    if not transformers:
        raise ValueError("SHIFT graph has no transformer edges to map")
    phase_mapper = BalancedPhaseMapper(graph, [TransformerPhaseMapperModel(
        tr_name=edge.name, tr_type=TransformerTypes.THREE_PHASE,
        tr_capacity=ApparentPower(100, "kva"), location=graph.get_node(a).location)
        for a, _, edge in transformers], method="greedy")
    voltage_mapper = TransformerVoltageMapper(graph, [TransformerVoltageModel(
        name=edge.name, voltages=[Voltage(11, "kilovolt"), Voltage(0.4, "kilovolt")])
        for _, _, edge in transformers])
    equipment_mapper = _SyntheticEdgeEquipmentMapper(graph, _synthetic_catalog(), voltage_mapper, phase_mapper)
    DistributionSystemBuilder(name="blackout_mesh_synthetic_demo", dist_graph=graph,
        phase_mapper=phase_mapper, voltage_mapper=voltage_mapper,
        equipment_mapper=equipment_mapper).get_system()
    phase_names = {"A": 0, "B": 1, "C": 2, "N": 3, "S1": 4, "S2": 5}
    node_fields = {}
    for node in graph.get_nodes():
        phases = phase_mapper.node_phase_mapping[node.name]
        node_fields[node.name] = {
            "phase": "".join(sorted((phase.value for phase in phases), key=phase_names.__getitem__)),
            "voltage_v": round(float(voltage_mapper.node_voltage_mapping[node.name].to("volt").magnitude)),
            "rating_va": None,
        }
        if node.assets and DistributionLoad in node.assets:
            equipment = equipment_mapper.node_asset_equipment_mapping[node.name][DistributionLoad]
            node_fields[node.name]["rating_va"] = round(sum(
                math.hypot(float(load.real_power.to("watt").magnitude),
                           float(load.reactive_power.to("var").magnitude))
                for load in equipment.phase_loads))

    edge_fields = {}
    for from_node, to_node, edge in graph.get_edges():
        equipment = equipment_mapper.edge_equipment_mapping[edge.name]
        phases = phase_mapper.node_phase_mapping[from_node] & phase_mapper.node_phase_mapping[to_node]
        phase_count = len(phases)
        if edge.edge_type is DistributionTransformer:
            rating_va = round(min(winding.rated_power.to("va").magnitude for winding in equipment.windings))
            edge_fields[edge.name] = {"phase": "".join(sorted((phase.value for phase in phases), key=phase_names.__getitem__)),
                                      "voltage_v": None, "rating_a": None, "limit_w": rating_va}
        else:
            voltage_v = node_fields[from_node]["voltage_v"]
            rating_a = round(float(equipment.ampacity.to("ampere").magnitude))
            rating_va = round(rating_a * voltage_v * phase_count)
            edge_fields[edge.name] = {"phase": "".join(sorted((phase.value for phase in phases), key=phase_names.__getitem__)),
                                      "voltage_v": voltage_v, "rating_a": rating_a,
                                      "limit_w": rating_va}
        for node_name in (from_node, to_node):
            current = node_fields[node_name]["rating_va"]
            node_fields[node_name]["rating_va"] = rating_va if current is None else min(current, rating_va)
    if any(field["rating_va"] is None for field in node_fields.values()):
        raise ValueError("synthetic equipment mapping did not produce a rating for every node")
    return {"phase_nodes": len(phase_mapper.node_phase_mapping),
            "voltage_nodes": len(voltage_mapper.node_voltage_mapping),
            "edge_equipment": len(equipment_mapper.edge_equipment_mapping),
            "system_nodes": len(list(graph.get_nodes())),
            "system_edges": len(list(graph.get_edges())),
            "nodes": node_fields, "edges": edge_fields}


def _groups(features: list[dict], count: int) -> tuple[list[GroupModel], dict[str, str], dict[str, str]]:
    if not 2 <= count <= 6:
        raise ValueError("cluster_count must be 2..6")
    points = []
    for feature in sorted(features, key=lambda item: item["id"]):
        centroid = shape(feature["geometry"]).centroid
        points.append((feature["id"], GeoLocation(centroid.x, centroid.y)))
    if len(points) < count:
        raise ValueError(f"need at least {count} mapped buildings; found {len(points)}")

    # Deterministic farthest-first seeds and bounded Lloyd steps keep all OSM buildings assigned.
    centers = [points[0][1]]
    while len(centers) < count:
        _, point = max(points, key=lambda item: (min((item[1].longitude-c.longitude)**2 + (item[1].latitude-c.latitude)**2 for c in centers), item[0]))
        centers.append(point)
    assignments = []
    for _ in range(25):
        assignments = [min(range(count), key=lambda i: ((point.longitude-centers[i].longitude)**2 + (point.latitude-centers[i].latitude)**2, i)) for _, point in points]
        groups = [[entry for entry, group in zip(points, assignments) if group == i] for i in range(count)]
        if any(not group for group in groups):
            raise ValueError("deterministic clustering produced an empty group")
        updated = [GeoLocation(sum(entry[1].longitude for entry in group)/len(group), sum(entry[1].latitude for entry in group)/len(group)) for group in groups]
        if updated == centers:
            break
        centers = updated

    members = [sorted(entry[0] for entry in group) for group in groups]
    order = sorted(range(count), key=lambda i: members[i])
    remap = {old: new for new, old in enumerate(order)}
    groups = [groups[i] for i in order]
    centers = [centers[i] for i in order]
    assignments = [remap[i] for i in assignments]
    group_members = {f"group-{i:02}": members[old] for i, old in enumerate(order)}
    return [GroupModel(center=center, points=[point for _, point in group]) for center, group in zip(centers, groups)], group_members


def generate(map_path: Path = MAP, cluster_count: int = 6, secondary_strategy: str = "MeshSteinerStrategy") -> dict:
    _verify_shift_commit()
    geo = json.loads(map_path.read_text())
    buildings = [feature for feature in geo["features"] if feature["properties"]["kind"] == "building"]
    groups, group_members = _groups(buildings, cluster_count)
    strategy = STRATEGIES[secondary_strategy]()
    distribution_graph = PRSG(groups=groups, source_location=CENTER, buffer=Distance(20, "m"), offline=True,
                 snap_to_roads=False, secondary_strategy=strategy).get_distribution_graph()
    stage_diagnostics = _run_shift_stages(distribution_graph)
    graph = distribution_graph._graph
    if not nx.is_tree(graph):
        raise ValueError("SHIFT output must be a connected tree")

    building_points = [(feature["id"], shape(feature["geometry"]).centroid) for feature in buildings]
    descriptors = []
    for raw_id, data in graph.nodes(data=True):
        model = data["node_data"]
        lon, lat = float(model.location.x), float(model.location.y)
        assets = {asset.__name__ for asset in model.assets}
        group_id = min(group_members, key=lambda key: abs(groups[int(key[-2:])].center.longitude-lon) + abs(groups[int(key[-2:])].center.latitude-lat))
        if "DistributionVoltageSource" in assets:
            node_id, role, extra = "source", "source", {}
        elif "DistributionLoad" in assets:
            building_id, _ = min(building_points, key=lambda item: abs(item[1].x-lon) + abs(item[1].y-lat))
            node_id, role, extra = f"load:{building_id}", "load", {"building_id": building_id}
        elif raw_id.endswith("_ht"):
            node_id, role, extra = f"junction:{group_id}:primary", "junction", {"group_id": group_id, "side": "primary"}
        elif any(edge["edge_data"].edge_type.__name__ == "DistributionTransformer" for *_, edge in graph.edges(raw_id, data=True)):
            node_id, role, extra = f"transformer:{group_id}", "transformer", {"group_id": group_id}
        else:
            node_id, role, extra = f"junction:{lon:.7f}:{lat:.7f}", "junction", {}
        extra.update(stage_diagnostics["nodes"][raw_id])
        descriptors.append({"raw_id": raw_id, "id": node_id, "role": role,
                            "lon": round(lon, 7), "lat": round(lat, 7), **extra})
    by_id = {}
    for node in descriptors:
        by_id.setdefault(node["id"], []).append(node)
    for node_id, same_place_nodes in by_id.items():
        if len(same_place_nodes) == 1:
            continue
        for node in same_place_nodes:
            neighbors = []
            for neighbor in graph.neighbors(node["raw_id"]):
                n = graph.nodes[neighbor]["node_data"].location
                edge = graph.edges[node["raw_id"], neighbor]["edge_data"]
                neighbors.append((round(n.x, 7), round(n.y, 7), edge.edge_type.__name__,
                                  round(float(edge.length.to("m").magnitude), 2) if edge.length is not None else None))
            signature = json.dumps(sorted(neighbors), separators=(",", ":"))
            node["id"] = f"{node_id}:{hashlib.sha256(signature.encode()).hexdigest()[:8]}"
    node_ids = {node["raw_id"]: node["id"] for node in descriptors}
    if len(set(node_ids.values())) != len(node_ids):
        raise ValueError("duplicate stable node IDs after geometry-signature disambiguation")
    node_rows = [{key: value for key, value in node.items() if key != "raw_id"} |
                 {"rating_provenance": "SYNTHETIC_DEMO_ASSUMPTION"} for node in descriptors]

    edge_rows = []
    for raw_u, raw_v, data in graph.edges(data=True):
        u, v = node_ids[raw_u], node_ids[raw_v]
        edge_type = data["edge_data"].edge_type.__name__
        mapped = stage_diagnostics["edges"][data["edge_data"].name]
        edge_rows.append({"id": f"edge:{min(u,v)}:{max(u,v)}", "from": u, "to": v,
                          "kind": "feeder" if "source" in (u, v) else "branch", "component_type": edge_type,
                          "length_m": round(float(data["edge_data"].length.to("m").magnitude), 2) if data["edge_data"].length is not None else None,
                          **mapped, "normally_open": False,
                          "provenance": "SHIFT_SYNTHETIC_GEOMETRY", "rating_provenance": "SYNTHETIC_DEMO_ASSUMPTION"})

    transformer_nodes = sorted((row for row in node_rows if row["role"] == "transformer"), key=lambda row: row["id"])
    if len(transformer_nodes) >= 2:
        left, right = transformer_nodes[0], transformer_nodes[-1]
        dlon, dlat = math.radians(right["lon"]-left["lon"]), math.radians(right["lat"]-left["lat"])
        a = math.sin(dlat/2)**2 + math.cos(math.radians(left["lat"])) * math.cos(math.radians(right["lat"])) * math.sin(dlon/2)**2
        edge_rows.append({"id": "tie:declared-demo", "from": left["id"], "to": right["id"], "kind": "tie",
                          "component_type": "DeclaredSyntheticTie", "length_m": round(2*6371008.8*math.asin(math.sqrt(a)),2),
                          "phase": "ABC", "voltage_v": 400, "rating_a": 50, "limit_w": 20000,
                          "normally_open": True, "provenance": "SYNTHETIC_OPERATIONAL_TIE",
                          "rating_provenance": "SYNTHETIC_DEMO_ASSUMPTION"})
    node_rows.sort(key=lambda row: row["id"])
    edge_rows.sort(key=lambda row: row["id"])
    return {"schema_version": "district-topology-v1", "engine": "SHIFT PRSG", "engine_version": SHIFT_COMMIT,
            "engine_license": "BSD-3-Clause", "secondary_strategy": secondary_strategy, "cluster_count": cluster_count,
            "group_members": group_members,
            "provenance": "SYNTHETIC_GEOMETRY; OSM building centroids are virtual group centers, not electrical asset locations",
            "equipment_stage": ("SHIFT BalancedPhaseMapper, TransformerVoltageMapper, EdgeEquipmentMapper, "
                "and DistributionSystemBuilder completed with declared synthetic catalog assumptions; "
                f"mapped {stage_diagnostics['phase_nodes']} phase nodes, {stage_diagnostics['voltage_nodes']} voltage nodes, "
                f"{stage_diagnostics['edge_equipment']} edge equipment items; limits assume unity power factor; "
                "no simulation or export"),
            "nodes": node_rows, "edges": edge_rows}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--map", type=Path, default=MAP)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--clusters", type=int, default=6)
    parser.add_argument("--secondary-strategy", choices=sorted(STRATEGIES), default="MeshSteinerStrategy")
    args = parser.parse_args()
    result = generate(args.map, args.clusters, args.secondary_strategy)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(f"wrote {args.output}: {len(result['nodes'])} nodes, {len(result['edges'])} edges")
