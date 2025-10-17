from __future__ import annotations

import collections
from typing import Dict, Iterable, Mapping

Node = str


def local_push_ppr(
    adjacency: Mapping[Node, Iterable[Node]],
    source: Node,
    *,
    alpha: float = 0.85,
    tolerance: float = 1e-4,
) -> Dict[Node, float]:
    """Compute approximate personalised PageRank using the push algorithm."""

    residual: Dict[Node, float] = collections.defaultdict(float)
    result: Dict[Node, float] = collections.defaultdict(float)
    residual[source] = 1.0
    queue = collections.deque([source])
    while queue:
        node = queue.popleft()
        degree = len(list(adjacency.get(node, [])))
        if degree == 0:
            result[node] += residual[node]
            residual[node] = 0.0
            continue
        if residual[node] / degree <= tolerance:
            continue
        push_val = residual[node]
        result[node] += (1 - alpha) * push_val
        share = alpha * push_val / degree
        residual[node] = 0.0
        for neighbour in adjacency.get(node, []):
            residual[neighbour] += share
            if residual[neighbour] / max(len(list(adjacency.get(neighbour, []))), 1) > tolerance:
                queue.append(neighbour)
    total = sum(result.values())
    if not total:
        return {source: 1.0}
    return {node: value / total for node, value in result.items() if value > 0.0}
