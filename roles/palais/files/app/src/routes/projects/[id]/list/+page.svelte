<script lang="ts">
	import type { PageData } from './$types';

	let { data }: { data: PageData } = $props();

	// Filters
	let filterStatus = $state('');
	let filterPriority = $state('');
	let filterAgent = $state('');
	let sortBy = $state<'title' | 'priority' | 'updatedAt'>('updatedAt');
	let sortDir = $state<'asc' | 'desc'>('desc');

	const priorityOrder = { urgent: 4, high: 3, medium: 2, low: 1, none: 0 };
	const priorityColors: Record<string, string> = {
		urgent: 'var(--palais-red)', high: 'var(--palais-amber)',
		medium: 'var(--palais-gold)', low: 'var(--palais-cyan)', none: 'var(--palais-text-muted)'
	};

	let columnMap = $derived(Object.fromEntries(data.columns.map((c) => [c.id, c.name])));
	let agentMap = $derived(Object.fromEntries(data.agents.map((a) => [a.id, a.name])));

	let filteredTasks = $derived(
		data.tasks
			.filter((t) => {
				if (filterStatus && columnMap[t.columnId] !== filterStatus) return false;
				if (filterPriority && t.priority !== filterPriority) return false;
				if (filterAgent && t.assigneeAgentId !== filterAgent) return false;
				return true;
			})
			.sort((a, b) => {
				let cmp = 0;
				if (sortBy === 'title') cmp = a.title.localeCompare(b.title);
				else if (sortBy === 'priority') {
					cmp = (priorityOrder[a.priority ?? 'none'] ?? 0) - (priorityOrder[b.priority ?? 'none'] ?? 0);
				} else {
					cmp = new Date(a.updatedAt).getTime() - new Date(b.updatedAt).getTime();
				}
				return sortDir === 'asc' ? cmp : -cmp;
			})
	);

	function toggleSort(col: typeof sortBy) {
		if (sortBy === col) sortDir = sortDir === 'asc' ? 'desc' : 'asc';
		else { sortBy = col; sortDir = 'asc'; }
	}

	let selectedIds = $state<Set<number>>(new Set());

	function toggleSelect(id: number) {
		const next = new Set(selectedIds);
		if (next.has(id)) next.delete(id);
		else next.add(id);
		selectedIds = next;
	}

	function toggleAll() {
		if (selectedIds.size === filteredTasks.length) selectedIds = new Set();
		else selectedIds = new Set(filteredTasks.map((t) => t.id));
	}
</script>

<div class="max-w-full">
	<!-- Header -->
	<div class="flex items-center justify-between mb-6">
		<div class="flex items-center gap-3">
			<a href="/projects" class="text-sm transition-colors" style="color: var(--palais-text-muted);">← Projects</a>
			<span style="color: var(--palais-border);">/</span>
			<a href="/projects/{data.project.id}" class="flex items-center gap-2 text-sm">
				<span>{data.project.icon || '◈'}</span>
				<span style="color: var(--palais-text);">{data.project.name}</span>
			</a>
		</div>
		<div class="flex gap-2">
			<a href="/projects/{data.project.id}"
				class="px-3 py-1.5 rounded-lg text-xs font-medium transition-all"
				style="background: var(--palais-surface-hover); color: var(--palais-text-muted); border: 1px solid var(--palais-border);">
				⬡ Board
			</a>
			<button class="px-3 py-1.5 rounded-lg text-xs font-medium"
				style="background: var(--palais-gold); color: #0A0A0F;">
				☰ List
			</button>
		</div>
	</div>

	<!-- Filters -->
	<div class="flex flex-wrap gap-2 mb-4">
		<select bind:value={filterStatus}
			class="px-2 py-1 rounded text-xs outline-none"
			style="background: var(--palais-surface); border: 1px solid var(--palais-border); color: var(--palais-text);">
			<option value="">All columns</option>
			{#each data.columns as col}
				<option value={col.name}>{col.name}</option>
			{/each}
		</select>

		<select bind:value={filterPriority}
			class="px-2 py-1 rounded text-xs outline-none"
			style="background: var(--palais-surface); border: 1px solid var(--palais-border); color: var(--palais-text);">
			<option value="">All priorities</option>
			{#each ['urgent', 'high', 'medium', 'low', 'none'] as p}
				<option value={p}>{p}</option>
			{/each}
		</select>

		<select bind:value={filterAgent}
			class="px-2 py-1 rounded text-xs outline-none"
			style="background: var(--palais-surface); border: 1px solid var(--palais-border); color: var(--palais-text);">
			<option value="">All agents</option>
			{#each data.agents as agent}
				<option value={agent.id}>{agent.name}</option>
			{/each}
		</select>

		<span class="text-xs ml-auto self-center" style="color: var(--palais-text-muted);">
			{filteredTasks.length} task{filteredTasks.length !== 1 ? 's' : ''}
			{#if selectedIds.size > 0} · {selectedIds.size} selected{/if}
		</span>
	</div>

	<!-- Table -->
	<div class="rounded-xl overflow-hidden" style="border: 1px solid var(--palais-border);">
		<table class="w-full text-sm">
			<thead>
				<tr style="background: var(--palais-surface); border-bottom: 2px solid var(--palais-gold);">
					<th class="px-3 py-2 text-left w-8">
						<input type="checkbox"
							checked={selectedIds.size === filteredTasks.length && filteredTasks.length > 0}
							onchange={toggleAll}
							class="rounded" />
					</th>
					<th class="px-3 py-2 text-left cursor-pointer select-none"
						style="color: var(--palais-text-muted); font-size: 0.7rem; letter-spacing: 0.08em; font-family: 'Orbitron', sans-serif;"
						onclick={() => toggleSort('title')}>
						TITLE {sortBy === 'title' ? (sortDir === 'asc' ? '↑' : '↓') : ''}
					</th>
					<th class="px-3 py-2 text-left"
						style="color: var(--palais-text-muted); font-size: 0.7rem; letter-spacing: 0.08em; font-family: 'Orbitron', sans-serif;">
						STATUS
					</th>
					<th class="px-3 py-2 text-left cursor-pointer select-none"
						style="color: var(--palais-text-muted); font-size: 0.7rem; letter-spacing: 0.08em; font-family: 'Orbitron', sans-serif;"
						onclick={() => toggleSort('priority')}>
						PRIORITY {sortBy === 'priority' ? (sortDir === 'asc' ? '↑' : '↓') : ''}
					</th>
					<th class="px-3 py-2 text-left"
						style="color: var(--palais-text-muted); font-size: 0.7rem; letter-spacing: 0.08em; font-family: 'Orbitron', sans-serif;">
						AGENT
					</th>
					<th class="px-3 py-2 text-right"
						style="color: var(--palais-text-muted); font-size: 0.7rem; letter-spacing: 0.08em; font-family: 'Orbitron', sans-serif;">
						CONFIDENCE
					</th>
					<th class="px-3 py-2 text-right"
						style="color: var(--palais-text-muted); font-size: 0.7rem; letter-spacing: 0.08em; font-family: 'Orbitron', sans-serif;">
						COST
					</th>
					<th class="px-3 py-2 text-right cursor-pointer select-none"
						style="color: var(--palais-text-muted); font-size: 0.7rem; letter-spacing: 0.08em; font-family: 'Orbitron', sans-serif;"
						onclick={() => toggleSort('updatedAt')}>
						UPDATED {sortBy === 'updatedAt' ? (sortDir === 'asc' ? '↑' : '↓') : ''}
					</th>
				</tr>
			</thead>
			<tbody>
				{#each filteredTasks as task, i}
					<tr
						class="transition-colors"
						style="
							background: {selectedIds.has(task.id) ? 'color-mix(in srgb, var(--palais-gold) 8%, var(--palais-surface))' : (i % 2 === 0 ? 'var(--palais-surface)' : 'var(--palais-bg)')};
							border-bottom: 1px solid var(--palais-border);
						"
					>
						<td class="px-3 py-2">
							<input type="checkbox"
								checked={selectedIds.has(task.id)}
								onchange={() => toggleSelect(task.id)} />
						</td>
						<td class="px-3 py-2">
							<a href="/projects/{data.project.id}"
								class="hover:underline"
								style="color: var(--palais-text); text-decoration: none; border-left: 3px solid {priorityColors[task.priority ?? 'none']}; padding-left: 8px;">
								{task.title}
							</a>
						</td>
						<td class="px-3 py-2">
							<span class="text-xs px-2 py-0.5 rounded"
								style="background: var(--palais-surface-hover); color: var(--palais-text-muted);">
								{columnMap[task.columnId] ?? '—'}
							</span>
						</td>
						<td class="px-3 py-2">
							{#if task.priority && task.priority !== 'none'}
								<span class="text-xs font-medium"
									style="color: {priorityColors[task.priority]};">
									{task.priority}
								</span>
							{:else}
								<span class="text-xs" style="color: var(--palais-text-muted);">—</span>
							{/if}
						</td>
						<td class="px-3 py-2 text-xs" style="color: var(--palais-text-muted); font-family: 'JetBrains Mono', monospace;">
							{task.assigneeAgentId ? (agentMap[task.assigneeAgentId] ?? task.assigneeAgentId) : '—'}
						</td>
						<td class="px-3 py-2 text-right text-xs font-mono"
							style="color: var(--palais-cyan);">
							{task.confidenceScore !== null ? `${Math.round(task.confidenceScore * 100)}%` : '—'}
						</td>
						<td class="px-3 py-2 text-right text-xs font-mono"
							style="color: var(--palais-gold);">
							{task.actualCost !== null ? `$${task.actualCost.toFixed(3)}` : task.estimatedCost !== null ? `~$${task.estimatedCost.toFixed(3)}` : '—'}
						</td>
						<td class="px-3 py-2 text-right text-xs" style="color: var(--palais-text-muted);">
							{new Date(task.updatedAt).toLocaleDateString('fr-FR')}
						</td>
					</tr>
				{:else}
					<tr>
						<td colspan="8" class="px-3 py-8 text-center text-sm" style="color: var(--palais-text-muted);">
							No tasks match the current filters
						</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>
</div>
