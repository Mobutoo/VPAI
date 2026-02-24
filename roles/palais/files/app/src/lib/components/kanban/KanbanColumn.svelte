<script lang="ts">
	import { createEventDispatcher } from 'svelte';
	import TaskCard from './TaskCard.svelte';

	let {
		column,
		tasks
	}: {
		column: { id: number; name: string; position: number; color: string | null; isFinal: boolean | null };
		tasks: Array<{
			id: number; columnId: number; title: string; priority: string | null;
			assigneeAgentId: string | null; confidenceScore: number | null;
			estimatedCost: number | null; actualCost: number | null; position: number | null;
		}>;
	} = $props();

	const dispatch = createEventDispatcher<{
		moveTask: { taskId: number; toColumnId: number; position: number };
		openTask: number;
		addTask: string;
	}>();

	let isAddingTask = $state(false);
	let newTaskTitle = $state('');
	let isDragOver = $state(false);

	function onDragOver(e: DragEvent) {
		e.preventDefault();
		isDragOver = true;
	}

	function onDragLeave() {
		isDragOver = false;
	}

	function onDrop(e: DragEvent) {
		e.preventDefault();
		isDragOver = false;
		const taskId = parseInt(e.dataTransfer?.getData('taskId') || '0');
		if (!taskId) return;
		dispatch('moveTask', { taskId, toColumnId: column.id, position: tasks.length });
	}

	function addTask() {
		if (!newTaskTitle.trim()) return;
		dispatch('addTask', newTaskTitle.trim());
		newTaskTitle = '';
		isAddingTask = false;
	}

	const accentColor = column.color || 'var(--palais-gold)';
</script>

<div
	class="flex flex-col flex-shrink-0 w-72 rounded-xl overflow-hidden"
	style="background: var(--palais-surface); border: 1px solid {isDragOver ? 'var(--palais-gold)' : 'var(--palais-border)'}; transition: border-color 150ms; box-shadow: {isDragOver ? 'var(--palais-glow-sm)' : 'none'};"
	role="region"
	aria-label="Column: {column.name}"
	ondragover={onDragOver}
	ondragleave={onDragLeave}
	ondrop={onDrop}
>
	<!-- Kuba-pattern column header -->
	<div class="px-4 py-3 flex items-center justify-between" style="
		background: linear-gradient(135deg,
			color-mix(in srgb, {accentColor} 15%, var(--palais-surface)),
			var(--palais-surface)
		);
		border-bottom: 2px solid {accentColor};
		position: relative;
		overflow: hidden;
	">
		<!-- Kuba decorative triangles -->
		<div style="position: absolute; top: 0; right: 0; width: 40px; height: 40px; opacity: 0.1;
			background: repeating-linear-gradient(
				45deg,
				{accentColor},
				{accentColor} 2px,
				transparent 2px,
				transparent 8px
			);">
		</div>

		<div class="flex items-center gap-2">
			<span class="w-2 h-2 rounded-full flex-shrink-0" style="background: {accentColor};"></span>
			<h3 class="font-semibold text-sm" style="font-family: 'Orbitron', sans-serif; color: var(--palais-text); font-size: 0.75rem; letter-spacing: 0.05em;">
				{column.name.toUpperCase()}
			</h3>
		</div>
		<span class="text-xs font-mono px-1.5 py-0.5 rounded"
			style="background: color-mix(in srgb, {accentColor} 20%, transparent); color: {accentColor};">
			{tasks.length}
		</span>
	</div>

	<!-- Task cards -->
	<div class="flex flex-col gap-2 p-2 flex-1 overflow-y-auto min-h-0 max-h-[calc(100vh-220px)]">
		{#each tasks as task (task.id)}
			<TaskCard
				{task}
				on:openTask={() => dispatch('openTask', task.id)}
				on:dragStart={(e) => e.detail.dataTransfer?.setData('taskId', String(task.id))}
			/>
		{/each}

		<!-- Drop zone empty state -->
		{#if isDragOver && tasks.length === 0}
			<div class="rounded-lg border-2 border-dashed h-20 flex items-center justify-center"
				style="border-color: var(--palais-gold); color: var(--palais-gold); font-size: 0.75rem;">
				Drop here
			</div>
		{/if}
	</div>

	<!-- Add task -->
	<div class="p-2 border-t" style="border-color: var(--palais-border);">
		{#if isAddingTask}
			<div class="flex flex-col gap-1">
				<input
					bind:value={newTaskTitle}
					placeholder="Task title..."
					autofocus
					class="w-full px-2 py-1.5 rounded text-sm outline-none"
					style="background: var(--palais-bg); border: 1px solid var(--palais-gold); color: var(--palais-text);"
					onkeydown={(e) => {
						if (e.key === 'Enter') addTask();
						if (e.key === 'Escape') { isAddingTask = false; newTaskTitle = ''; }
					}}
				/>
				<div class="flex gap-1">
					<button onclick={addTask}
						class="flex-1 py-1 rounded text-xs font-medium"
						style="background: var(--palais-gold); color: #0A0A0F;">
						Add
					</button>
					<button onclick={() => { isAddingTask = false; newTaskTitle = ''; }}
						class="px-2 py-1 rounded text-xs"
						style="background: var(--palais-surface-hover); color: var(--palais-text-muted);">
						✕
					</button>
				</div>
			</div>
		{:else}
			<button
				onclick={() => (isAddingTask = true)}
				class="w-full py-1.5 rounded text-xs text-left px-2 transition-colors"
				style="color: var(--palais-text-muted);"
			>
				+ Add task
			</button>
		{/if}
	</div>
</div>
