import { db } from '$lib/server/db';
import { taskDependencies } from '$lib/server/db/schema';

export async function hasCycle(taskId: number, dependsOnId: number): Promise<boolean> {
	const allDeps = await db.select().from(taskDependencies);
	const adj = new Map<number, number[]>();

	for (const d of allDeps) {
		if (!adj.has(d.taskId)) adj.set(d.taskId, []);
		adj.get(d.taskId)!.push(d.dependsOnTaskId);
	}

	// Add the proposed edge
	if (!adj.has(taskId)) adj.set(taskId, []);
	adj.get(taskId)!.push(dependsOnId);

	// DFS cycle detection
	const visited = new Set<number>();
	const inStack = new Set<number>();

	function dfs(node: number): boolean {
		if (inStack.has(node)) return true;
		if (visited.has(node)) return false;
		visited.add(node);
		inStack.add(node);
		for (const neighbor of adj.get(node) || []) {
			if (dfs(neighbor)) return true;
		}
		inStack.delete(node);
		return false;
	}

	return dfs(taskId);
}
