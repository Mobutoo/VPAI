<script lang="ts">
	import type { PageData } from './$types';

	let { data }: { data: PageData } = $props();

	type PlanTask = {
		title: string;
		description: string;
		estimatedCost: number;
		assigneeAgentId: string | null;
		dependencies: string[];
		priority: string;
	};

	type PlanSnapshot = { tasks: PlanTask[] };

	const PRIORITY_COLORS: Record<string, string> = {
		urgent: 'var(--palais-red)', high: 'var(--palais-amber)',
		medium: 'var(--palais-gold)', low: 'var(--palais-cyan)', none: 'var(--palais-text-muted)'
	};

	let mission = $state({ ...data.mission });
	let plan = $state<PlanSnapshot>(
		(data.mission.planSnapshot as PlanSnapshot) ?? { tasks: [] }
	);
	let generating = $state(false);
	let saving = $state(false);
	let saved = $state(false);
	let draggingIndex = $state<number | null>(null);
	let dragOverIndex = $state<number | null>(null);

	const totalCost = $derived(plan.tasks.reduce((s, t) => s + (t.estimatedCost ?? 0), 0));

	async function generatePlan() {
		generating = true;
		const res = await fetch(`/api/v1/missions/${mission.id}/plan`, { method: 'POST' });
		if (res.ok) {
			const updated = await res.json();
			plan = (updated.planSnapshot as PlanSnapshot) ?? { tasks: [] };
			mission = { ...mission, status: updated.status };
		}
		generating = false;
	}

	async function savePlan() {
		saving = true;
		const res = await fetch(`/api/v1/missions/${mission.id}/plan`, {
			method: 'PUT',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify(plan)
		});
		if (res.ok) {
			saved = true;
			setTimeout(() => (saved = false), 2000);
		}
		saving = false;
	}

	function addTask() {
		plan = {
			tasks: [
				...plan.tasks,
				{
					title: 'New Task',
					description: '',
					estimatedCost: 0.05,
					assigneeAgentId: null,
					dependencies: [],
					priority: 'medium'
				}
			]
		};
	}

	function removeTask(index: number) {
		plan = { tasks: plan.tasks.filter((_, i) => i !== index) };
	}

	// Drag reorder
	function onDragStart(index: number) {
		draggingIndex = index;
	}

	function onDragOver(e: DragEvent, index: number) {
		e.preventDefault();
		dragOverIndex = index;
	}

	function onDrop(index: number) {
		if (draggingIndex === null || draggingIndex === index) return;
		const tasks = [...plan.tasks];
		const [moved] = tasks.splice(draggingIndex, 1);
		tasks.splice(index, 0, moved);
		plan = { tasks };
		draggingIndex = null;
		dragOverIndex = null;
	}

	async function approvePlan() {
		await savePlan();
		const res = await fetch(`/api/v1/missions/${mission.id}`, {
			method: 'PUT',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ status: 'approved', totalEstimatedCost: totalCost })
		});
		if (res.ok) mission = { ...mission, status: 'approved', totalEstimatedCost: totalCost };
	}
</script>

<div class="flex flex-col h-[calc(100vh-6rem)] gap-4">
	<!-- Header -->
	<div class="flex items-center justify-between flex-shrink-0">
		<div class="flex items-center gap-3">
			<a href="/missions/{mission.id}" class="text-xs px-2 py-1 rounded"
				style="background: var(--palais-surface); color: var(--palais-text-muted); border: 1px solid var(--palais-border);">
				← Mission
			</a>
			<h1 class="text-lg font-bold" style="font-family: 'Orbitron', sans-serif; color: var(--palais-text);">
				✏️ Co-Edit Plan
			</h1>
			<span class="text-xs font-mono" style="color: var(--palais-text-muted);">{mission.title}</span>
		</div>
		<div class="flex items-center gap-2">
			{#if plan.tasks.length === 0}
				<button onclick={generatePlan} disabled={generating}
					class="px-3 py-1.5 rounded-lg text-xs font-medium disabled:opacity-50"
					style="background: var(--palais-cyan); color: #0A0A0F;">
					{generating ? '🤖 Generating…' : '🤖 Generate Plan'}
				</button>
			{:else}
				<button onclick={generatePlan} disabled={generating}
					class="px-3 py-1.5 rounded-lg text-xs font-medium disabled:opacity-50"
					style="background: var(--palais-surface); color: var(--palais-text-muted); border: 1px solid var(--palais-border);">
					{generating ? '…' : '↺ Regenerate'}
				</button>
			{/if}
			<button onclick={addTask}
				class="px-3 py-1.5 rounded-lg text-xs font-medium"
				style="background: var(--palais-surface); color: var(--palais-text); border: 1px solid var(--palais-border);">
				+ Task
			</button>
			<button onclick={savePlan} disabled={saving}
				class="px-3 py-1.5 rounded-lg text-xs font-medium disabled:opacity-50"
				style="background: {saved ? 'var(--palais-cyan)' : 'var(--palais-gold)'}; color: #0A0A0F;">
				{saving ? '…' : saved ? '✓ Saved' : 'Save'}
			</button>
			{#if mission.status === 'co_editing' && plan.tasks.length > 0}
				<button onclick={approvePlan}
					class="px-3 py-1.5 rounded-lg text-xs font-medium"
					style="background: #22c55e; color: #0A0A0F;">
					✓ Approve Plan
				</button>
			{/if}
		</div>
	</div>

	<!-- Stats -->
	<div class="flex gap-4 flex-shrink-0 text-xs">
		<span style="color: var(--palais-text-muted);">{plan.tasks.length} tasks</span>
		<span style="color: var(--palais-gold);">Total est. ${totalCost.toFixed(3)}</span>
	</div>

	<!-- Plan table -->
	{#if plan.tasks.length === 0}
		<div class="flex-1 flex flex-col items-center justify-center gap-4">
			{#if generating}
				<p class="text-sm" style="color: var(--palais-cyan);">🤖 Generating plan from brainstorming…</p>
			{:else}
				<p class="text-sm" style="color: var(--palais-text-muted);">No plan yet.</p>
				<button onclick={generatePlan}
					class="px-4 py-2 rounded-lg text-sm font-medium"
					style="background: var(--palais-cyan); color: #0A0A0F;">
					🤖 Generate Plan from Brainstorming
				</button>
			{/if}
		</div>
	{:else}
		<div class="flex-1 overflow-y-auto">
			<table class="w-full text-xs border-collapse">
				<thead class="sticky top-0" style="background: var(--palais-surface);">
					<tr style="border-bottom: 1px solid var(--palais-border);">
						<th class="text-left px-2 py-2 w-6" style="color: var(--palais-text-muted);">#</th>
						<th class="text-left px-2 py-2" style="color: var(--palais-text-muted);">Title</th>
						<th class="text-left px-2 py-2 w-64" style="color: var(--palais-text-muted);">Description</th>
						<th class="text-left px-2 py-2 w-24" style="color: var(--palais-text-muted);">Priority</th>
						<th class="text-right px-2 py-2 w-24" style="color: var(--palais-text-muted);">Est. Cost</th>
						<th class="px-2 py-2 w-8"></th>
					</tr>
				</thead>
				<tbody>
					{#each plan.tasks as task, i}
						<!-- svelte-ignore a11y_no_static_element_interactions -->
						<tr
							draggable={true}
							ondragstart={() => onDragStart(i)}
							ondragover={(e) => onDragOver(e, i)}
							ondrop={() => onDrop(i)}
							class="transition-all"
							style="
								border-bottom: 1px solid var(--palais-border);
								background: {dragOverIndex === i ? 'color-mix(in srgb, var(--palais-gold) 8%, var(--palais-surface))' : draggingIndex === i ? 'var(--palais-surface-hover)' : 'transparent'};
								opacity: {draggingIndex === i ? 0.5 : 1};
								cursor: grab;
							"
						>
							<td class="px-2 py-2" style="color: var(--palais-text-muted);">{i + 1}</td>
							<td class="px-2 py-2">
								<input
									bind:value={task.title}
									class="w-full bg-transparent outline-none border-b border-transparent focus:border-current"
									style="color: var(--palais-text);"
								/>
							</td>
							<td class="px-2 py-2">
								<input
									bind:value={task.description}
									class="w-full bg-transparent outline-none border-b border-transparent focus:border-current text-xs"
									style="color: var(--palais-text-muted);"
									placeholder="Description..."
								/>
							</td>
							<td class="px-2 py-2">
								<select
									bind:value={task.priority}
									class="w-full bg-transparent outline-none text-xs"
									style="color: {PRIORITY_COLORS[task.priority] ?? 'var(--palais-text)'}; border: none; background: transparent;"
								>
									{#each ['none','low','medium','high','urgent'] as p}
										<option value={p} style="background: var(--palais-bg); color: var(--palais-text);">{p}</option>
									{/each}
								</select>
							</td>
							<td class="px-2 py-2 text-right">
								<input
									type="number"
									step="0.001"
									min="0"
									bind:value={task.estimatedCost}
									class="w-20 bg-transparent outline-none text-right border-b border-transparent focus:border-current"
									style="color: var(--palais-gold);"
								/>
							</td>
							<td class="px-2 py-2 text-center">
								<button onclick={() => removeTask(i)}
									class="opacity-40 hover:opacity-100 transition-opacity"
									style="color: var(--palais-red);">
									×
								</button>
							</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	{/if}
</div>
