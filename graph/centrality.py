from __future__ import annotations

import collections
from typing import Dict, Iterable, Mapping, MutableMapping

Node = str


def ego_betweenness(adjacency: Mapping[Node, Iterable[Node]], ego: Node, *, max_depth: int = 3) -> float:
    """Approximate betweenness centrality in the ego network up to ``max_depth``."""

    if ego not in adjacency:
        return 0.0
    neighbours = list(adjacency.get(ego, []))
    if len(neighbours) < 2:
        return 0.0
    paths: MutableMapping[tuple[Node, Node], int] = collections.defaultdict(int)
    for idx, source in enumerate(neighbours):
        queue = collections.deque([(source, 0)])
        seen = {ego, source}
        while queue:
            node, depth = queue.popleft()
            if depth >= max_depth:
                continue
            for neighbour in adjacency.get(node, []):
                if neighbour in seen:
                    continue
                seen.add(neighbour)
                queue.append((neighbour, depth + 1))
                if neighbour in neighbours and neighbour != source and neighbours.index(neighbour) > idx:
                    key = tuple(sorted((source, neighbour)))
                    paths[key] += 1
    if not paths:
        return 0.0
    return float(sum(1.0 / count for count in paths.values()))
