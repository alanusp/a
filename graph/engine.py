from __future__ import annotations

import collections
import collections
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, MutableMapping, Set, Tuple

from graph.centrality import ego_betweenness
from graph.ppr import local_push_ppr
from app.core.limits import get_limit_registry, severity_score
from app.core.durability import get_durability_manager

Node = str

LOGGER = logging.getLogger(__name__)


def _severity_rank(value: str) -> int:
    return int(severity_score(value))


@dataclass(frozen=True)
class GraphSnapshot:
    timestamp: datetime
    event_id: str
    metrics: Mapping[str, float]


class GraphEngine:
    """Maintain an incremental entity interaction graph."""

    def __init__(self) -> None:
        self._adjacency: MutableMapping[Node, Set[Node]] = collections.defaultdict(set)
        self._edges: Set[Tuple[Node, Node]] = set()
        self._risk_sum: MutableMapping[Node, float] = collections.defaultdict(float)
        self._risk_count: MutableMapping[Node, int] = collections.defaultdict(int)
        self._snapshots: MutableMapping[str, GraphSnapshot] = {}
        self._limits = get_limit_registry()
        self._limit_state: str = "ok"
        self._limit_reason: str | None = None
        self._durability = get_durability_manager()
        self._durability.recover("graph", self._apply_delta)

    def ingest(
        self,
        *,
        event_id: str,
        timestamp: datetime,
        relationships: Mapping[str, str],
        fraud_probability: float,
    ) -> None:
        record = {
            "event_id": event_id,
            "timestamp": timestamp.isoformat(),
            "relationships": dict(relationships),
            "fraud_probability": fraud_probability,
        }
        self._apply_delta(record, persist=True)

    def _apply_delta(self, record: Mapping[str, object], persist: bool = False) -> None:
        event_id = str(record.get("event_id", "unknown"))
        timestamp_raw = record.get("timestamp")
        if isinstance(timestamp_raw, str):
            timestamp = datetime.fromisoformat(timestamp_raw)
        else:  # pragma: no cover - defensive default
            timestamp = datetime.utcnow()
        relationships = record.get("relationships", {})
        if not isinstance(relationships, Mapping):
            return
        nodes = {
            self._node_key(self._role_name(role), identifier)
            for role, identifier in relationships.items()
            if identifier
        }
        if not nodes:
            return

        node_cap = self._limits.for_resource("graph_nodes")
        edge_cap = self._limits.for_resource("graph_edges")
        existing_nodes = set(self._adjacency)
        new_nodes = {node for node in nodes if node not in existing_nodes}
        candidate_edges = {
            tuple(sorted((left, right)))
            for left in nodes
            for right in nodes
            if left < right
        }
        new_edges = {edge for edge in candidate_edges if edge not in self._edges}

        prospective_nodes = len(existing_nodes) + len(new_nodes)
        prospective_edges = len(self._edges) + len(new_edges)

        node_decision = node_cap.assess(prospective_nodes)
        edge_decision = edge_cap.assess(prospective_edges)
        if not node_decision.allowed or not edge_decision.allowed:
            self._limit_state = "hard"
            self._limit_reason = node_decision.reason or edge_decision.reason or "graph_cap"
            node_cap.commit(len(existing_nodes))
            edge_cap.commit(len(self._edges))
            LOGGER.warning(
                "graph ingest shed",
                extra={
                    "event_id": event_id,
                    "reason": self._limit_reason,
                },
            )
            return

        severity = max(node_decision.severity, edge_decision.severity, key=_severity_rank)
        self._limit_state = severity
        self._limit_reason = node_decision.reason or edge_decision.reason

        for left in nodes:
            neighbours = nodes - {left}
            if not neighbours:
                continue
            self._adjacency[left].update(neighbours)
            for right in neighbours:
                self._adjacency[right].add(left)
        self._edges.update(new_edges)
        node_cap.commit(prospective_nodes)
        edge_cap.commit(len(self._edges))
        risk = float(record.get("fraud_probability", 0.0))
        for node in nodes:
            self._risk_sum[node] += risk
            self._risk_count[node] += 1
        metrics = self.compute_metrics(relationships)
        self._snapshots[event_id] = GraphSnapshot(timestamp=timestamp, event_id=event_id, metrics=metrics)
        if persist:
            self._durability.append("graph", dict(record))

    def compute_metrics(self, relationships: Mapping[str, str]) -> Dict[str, float]:
        customer = relationships.get("customer_id")
        device = relationships.get("device_id")
        merchant = relationships.get("merchant_id")
        card = relationships.get("card_id")
        ip_address = relationships.get("ip_address")

        metrics: Dict[str, float] = {}
        if customer:
            metrics["customer_degree"] = float(self.degree(self._node_key("customer", customer)))
            metrics["customer_component"] = float(
                self.connected_component_size(self._node_key("customer", customer))
            )
        if device:
            metrics["shared_device_customers"] = float(
                self.shared_neighbours(self._node_key("device", device), prefix="customer")
            )
        if merchant:
            metrics["merchant_degree"] = float(self.degree(self._node_key("merchant", merchant)))
        if customer and merchant:
            metrics["customer_to_merchant_steps"] = float(
                self.shortest_path_length(
                    self._node_key("customer", customer), self._node_key("merchant", merchant), max_hops=3
                )
            )
        metrics["triangle_count"] = float(
            self.triangle_count(
                [
                    ("customer", customer),
                    ("device", device),
                    ("merchant", merchant),
                    ("card", card),
                    ("ip", ip_address),
                ]
            )
        )
        focus_nodes = [
            self._node_key(role, identifier)
            for role, identifier in (
                ("customer", customer),
                ("device", device),
                ("merchant", merchant),
                ("card", card),
                ("ip", ip_address),
            )
            if identifier
        ]
        metrics["neighbour_risk"] = float(self._average_risk(focus_nodes))
        adjacency = self._adjacency_view()
        if customer:
            node = self._node_key("customer", customer)
            ppr = local_push_ppr(adjacency, node)
            metrics["customer_ppr_focus"] = float(ppr.get(node, 0.0))
            metrics["customer_ego_betweenness"] = ego_betweenness(adjacency, node)
        metrics["graph_limit_severity"] = severity_score(self._limit_state)
        if self._limit_state == "hard":
            metrics["graph_limit_hard"] = 1.0
        elif self._limit_state == "soft":
            metrics["graph_limit_soft"] = 1.0
        return metrics

    def degree(self, node: Node) -> int:
        return len(self._adjacency.get(node, set()))

    def shared_neighbours(self, node: Node, *, prefix: str) -> int:
        neighbours = self._adjacency.get(node, set())
        return sum(1 for neighbour in neighbours if neighbour.startswith(f"{prefix}:"))

    def connected_component_size(self, node: Node) -> int:
        if node not in self._adjacency:
            return 1
        seen = {node}
        queue = collections.deque([node])
        while queue:
            current = queue.popleft()
            for neighbour in self._adjacency[current]:
                if neighbour not in seen:
                    seen.add(neighbour)
                    queue.append(neighbour)
        return len(seen)

    def triangle_count(self, nodes: Iterable[tuple[str, str | None]]) -> int:
        node_keys = [self._node_key(role, identifier) for role, identifier in nodes if identifier]
        triangles = 0
        for idx, node in enumerate(node_keys):
            neighbours = self._adjacency.get(node, set())
            for other in node_keys[idx + 1 :]:
                if other in neighbours:
                    intersection = neighbours & self._adjacency.get(other, set())
                    triangles += len(intersection)
        return triangles

    def shortest_path_length(self, start: Node, goal: Node, *, max_hops: int = 3) -> int:
        if start == goal:
            return 0
        visited = {start}
        queue: collections.deque[tuple[Node, int]] = collections.deque([(start, 0)])
        while queue:
            node, depth = queue.popleft()
            if depth >= max_hops:
                continue
            for neighbour in self._adjacency.get(node, set()):
                if neighbour == goal:
                    return depth + 1
                if neighbour not in visited:
                    visited.add(neighbour)
                    queue.append((neighbour, depth + 1))
        return max_hops + 1

    def label_propagation(self, *, max_iters: int = 5) -> Dict[Node, int]:
        labels = {node: idx for idx, node in enumerate(self._adjacency)}
        for _ in range(max_iters):
            changed = False
            for node, neighbours in self._adjacency.items():
                if not neighbours:
                    continue
                counts: Dict[int, int] = collections.Counter(labels[neighbour] for neighbour in neighbours)
                label = max(counts, key=counts.get)
                if label != labels[node]:
                    labels[node] = label
                    changed = True
            if not changed:
                break
        return labels

    def export_state(self) -> str:
        payload = {
            "adjacency": {node: sorted(neighbours) for node, neighbours in self._adjacency.items()},
            "risk_sum": dict(self._risk_sum),
            "risk_count": dict(self._risk_count),
        }
        return json.dumps(payload, sort_keys=True)

    def adjacency(self) -> Mapping[Node, Set[Node]]:
        return self._adjacency

    def _adjacency_view(self) -> Dict[Node, Set[Node]]:
        return {node: set(neighbours) for node, neighbours in self._adjacency.items()}

    def _average_risk(self, nodes: Iterable[Node]) -> float:
        risks: List[float] = []
        for node in nodes:
            total = self._risk_sum.get(node)
            count = self._risk_count.get(node, 0)
            if total is not None and count:
                risks.append(total / count)
        return sum(risks) / len(risks) if risks else 0.0

    @property
    def limit_state(self) -> str:
        return self._limit_state

    @property
    def limit_reason(self) -> str | None:
        return self._limit_reason

    @staticmethod
    def _node_key(role: str, identifier: str) -> Node:
        return f"{role}:{identifier}"

    @staticmethod
    def _role_name(role: str) -> str:
        mapping = {
            "customer_id": "customer",
            "device_id": "device",
            "merchant_id": "merchant",
            "card_id": "card",
            "ip_address": "ip",
        }
        return mapping.get(role, role.split("_", 1)[0])

    def snapshot_payload(self) -> Dict[str, object]:
        return {
            "nodes": {node: sorted(neighbours) for node, neighbours in self._adjacency.items()},
            "edges": sorted([list(edge) for edge in self._edges]),
            "risk_sum": dict(self._risk_sum),
            "risk_count": dict(self._risk_count),
        }

    def flush(self, path: Path | None = None) -> Path:
        target = path or Path("artifacts/graph_snapshot.json")
        payload = self.snapshot_payload()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        return target


_engine = GraphEngine()


def get_graph_engine() -> GraphEngine:
    return _engine
