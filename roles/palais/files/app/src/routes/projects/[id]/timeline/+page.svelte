<script lang="ts">
	import type { PageData } from './$types';
	import GanttChart from '$lib/components/timeline/GanttChart.svelte';

	let { data }: { data: PageData } = $props();
</script>

<div class="flex flex-col h-[calc(100vh-6rem)]">
	<!-- Header -->
	<div class="flex items-center justify-between mb-6 flex-shrink-0">
		<div class="flex items-center gap-3">
			<a href="/projects" class="text-sm transition-colors" style="color: var(--palais-text-muted);">
				← Projects
			</a>
			<span style="color: var(--palais-border);">/</span>
			<a href="/projects/{data.project.id}" class="flex items-center gap-2 text-sm">
				<span class="text-xl">{data.project.icon || '◈'}</span>
				<span style="color: var(--palais-text); font-family: 'Orbitron', sans-serif; font-weight: 700;">
					{data.project.name}
				</span>
			</a>
		</div>
		<div class="flex gap-2">
			<a href="/projects/{data.project.id}"
				class="px-3 py-1.5 rounded-lg text-xs font-medium transition-all"
				style="background: var(--palais-surface-hover); color: var(--palais-text-muted); border: 1px solid var(--palais-border);">
				⬡ Board
			</a>
			<a href="/projects/{data.project.id}/list"
				class="px-3 py-1.5 rounded-lg text-xs font-medium transition-all"
				style="background: var(--palais-surface-hover); color: var(--palais-text-muted); border: 1px solid var(--palais-border);">
				☰ List
			</a>
			<button
				class="px-3 py-1.5 rounded-lg text-xs font-medium"
				style="background: var(--palais-gold); color: #0A0A0F;">
				⏱ Timeline
			</button>
		</div>
	</div>

	<!-- Stats bar -->
	<div class="flex items-center gap-6 mb-4 flex-shrink-0 text-xs" style="color: var(--palais-text-muted);">
		<span>{data.tasks.length} tasks</span>
		<span>{data.dependencies.length} dependencies</span>
		<span style="color: var(--palais-red);">
			◈ {data.criticalPathIds.length} on critical path
		</span>
		<span>{data.tasks.filter((t) => t.startDate && t.endDate).length} with dates</span>
	</div>

	<!-- Gantt chart -->
	<div class="flex-1 overflow-auto rounded-xl p-4"
		style="border: 1px solid var(--palais-border); background: var(--palais-bg);">
		{#if data.tasks.length === 0}
			<div class="flex items-center justify-center h-full text-sm" style="color: var(--palais-text-muted);">
				No tasks in this project yet.
			</div>
		{:else}
			<GanttChart
				tasks={data.tasks}
				dependencies={data.dependencies}
				criticalPathIds={data.criticalPathIds}
				projectId={data.project.id}
			/>
		{/if}
	</div>
</div>
