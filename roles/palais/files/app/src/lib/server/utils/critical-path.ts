type TaskNode = { id: number; duration: number; deps: number[] };

export function computeCriticalPath(taskNodes: TaskNode[]): number[] {
	if (taskNodes.length === 0) return [];

	const nodeMap = new Map(taskNodes.map((t) => [t.id, t]));
	const adj = new Map<number, number[]>(); // dep → tasks that depend on it
	const inDegree = new Map<number, number>();

	for (const t of taskNodes) {
		inDegree.set(t.id, t.deps.length);
		for (const dep of t.deps) {
			if (!adj.has(dep)) adj.set(dep, []);
			adj.get(dep)!.push(t.id);
		}
	}

	// Topological sort + longest path (Kahn's algorithm)
	const dist = new Map<number, number>();
	const prev = new Map<number, number>();
	const queue: number[] = [];

	for (const t of taskNodes) {
		dist.set(t.id, t.duration);
		if (t.deps.length === 0) queue.push(t.id);
	}

	while (queue.length > 0) {
		const u = queue.shift()!;
		for (const v of adj.get(u) || []) {
			const newDist = dist.get(u)! + (nodeMap.get(v)?.duration ?? 1);
			if (newDist > (dist.get(v) ?? 0)) {
				dist.set(v, newDist);
				prev.set(v, u);
			}
			inDegree.set(v, (inDegree.get(v) ?? 1) - 1);
			if (inDegree.get(v) === 0) queue.push(v);
		}
	}

	// Trace back from node with max distance
	let maxNode = taskNodes[0].id;
	let maxDist = 0;
	for (const [id, d] of dist) {
		if (d > maxDist) { maxDist = d; maxNode = id; }
	}

	const path: number[] = [];
	let current: number | undefined = maxNode;
	while (current !== undefined) {
		path.unshift(current);
		current = prev.get(current);
	}

	return path;
}
