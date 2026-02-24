<script lang="ts">
	import type { PageData } from './$types';
	import KanbanBoard from '$lib/components/kanban/KanbanBoard.svelte';

	let { data }: { data: PageData } = $props();
</script>

<div class="flex flex-col h-[calc(100vh-6rem)]">
	<!-- Project Header -->
	<div class="flex items-center justify-between mb-6 flex-shrink-0">
		<div class="flex items-center gap-3">
			<a href="/projects" class="text-sm transition-colors" style="color: var(--palais-text-muted);">
				← Projects
			</a>
			<span style="color: var(--palais-border);">/</span>
			<div class="flex items-center gap-2">
				<span class="text-xl">{data.project.icon || '◈'}</span>
				<h1 class="text-xl font-bold" style="font-family: 'Orbitron', sans-serif; color: var(--palais-text);">
					{data.project.name}
				</h1>
			</div>
		</div>
		<div class="flex gap-2">
			<a href="/projects/{data.project.id}/list"
				class="px-3 py-1.5 rounded-lg text-xs font-medium transition-all"
				style="background: var(--palais-surface-hover); color: var(--palais-text-muted); border: 1px solid var(--palais-border);">
				☰ List
			</a>
			<button
				class="px-3 py-1.5 rounded-lg text-xs font-medium transition-all"
				style="background: var(--palais-gold); color: #0A0A0F;">
				⬡ Board
			</button>
		</div>
	</div>

	<!-- Kanban Board -->
	<KanbanBoard
		columns={data.columns}
		tasks={data.tasks}
		projectId={data.project.id}
	/>
</div>
