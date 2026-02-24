<script lang="ts">
	import KanbanColumn from './KanbanColumn.svelte';
	import TaskDetail from './TaskDetail.svelte';

	let {
		columns,
		tasks,
		projectId
	}: {
		columns: Array<{ id: number; name: string; position: number; color: string | null; isFinal: boolean | null }>;
		tasks: Array<{
			id: number; columnId: number; title: string; priority: string | null;
			assigneeAgentId: string | null; confidenceScore: number | null;
			estimatedCost: number | null; actualCost: number | null; position: number | null;
			status: string | null; agentStatus: string | null;
		}>;
		projectId: number;
	} = $props();

	// Local reactive task list (for optimistic updates)
	let localTasks = $state([...tasks]);
	let selectedTaskId = $state<number | null>(null);

	let selectedTask = $derived(selectedTaskId ? localTasks.find(t => t.id === selectedTaskId) ?? null : null);

	function getColumnTasks(columnId: number) {
		return localTasks.filter(t => t.columnId === columnId).sort((a, b) => (a.position ?? 0) - (b.position ?? 0));
	}

	async function moveTask(taskId: number, newColumnId: number, newPosition: number) {
		// Optimistic update
		localTasks = localTasks.map(t =>
			t.id === taskId ? { ...t, columnId: newColumnId, position: newPosition } : t
		);

		await fetch(`/api/v1/tasks/${taskId}`, {
			method: 'PUT',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ columnId: newColumnId, position: newPosition })
		});
	}

	function openTask(taskId: number) {
		selectedTaskId = taskId;
	}

	function closeTask() {
		selectedTaskId = null;
	}

	function onTaskUpdated(taskId: number, updates: Partial<typeof localTasks[0]>) {
		localTasks = localTasks.map(t => t.id === taskId ? { ...t, ...updates } : t);
	}

	async function addTask(columnId: number, title: string) {
		const colTasks = getColumnTasks(columnId);
		const position = colTasks.length;

		const res = await fetch(`/api/v1/projects/${projectId}/tasks`, {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ columnId, title, position })
		});

		if (res.ok) {
			const newTask = await res.json();
			localTasks = [...localTasks, newTask];
		}
	}
</script>

<div class="flex gap-4 overflow-x-auto pb-4 flex-1 min-h-0">
	{#each columns as column (column.id)}
		<KanbanColumn
			{column}
			tasks={getColumnTasks(column.id)}
			on:moveTask={(e) => moveTask(e.detail.taskId, e.detail.toColumnId, e.detail.position)}
			on:openTask={(e) => openTask(e.detail)}
			on:addTask={(e) => addTask(column.id, e.detail)}
		/>
	{/each}
</div>

<!-- Task Detail Panel -->
{#if selectedTask}
	<TaskDetail
		task={selectedTask}
		on:close={closeTask}
		on:updated={(e) => onTaskUpdated(selectedTask!.id, e.detail)}
	/>
{/if}
