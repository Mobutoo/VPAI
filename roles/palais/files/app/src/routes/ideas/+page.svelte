<script lang="ts">
	import type { PageData } from './$types';

	let { data }: { data: PageData } = $props();

	type Idea = typeof data.ideas[number];

	const STATUSES = ['draft', 'brainstorming', 'planned', 'approved', 'dispatched', 'archived'] as const;
	type Status = (typeof STATUSES)[number];

	const STATUS_LABELS: Record<Status, string> = {
		draft: 'Draft',
		brainstorming: 'Brainstorming',
		planned: 'Planned',
		approved: 'Approved',
		dispatched: 'Dispatched',
		archived: 'Archived'
	};

	const STATUS_COLORS: Record<Status, string> = {
		draft: 'var(--palais-text-muted)',
		brainstorming: 'var(--palais-cyan)',
		planned: 'var(--palais-amber)',
		approved: 'var(--palais-gold)',
		dispatched: '#22c55e',
		archived: 'var(--palais-border)'
	};

	const PRIORITY_COLORS: Record<string, string> = {
		urgent: 'var(--palais-red)', high: 'var(--palais-amber)',
		medium: 'var(--palais-gold)', low: 'var(--palais-cyan)', none: 'var(--palais-text-muted)'
	};

	let ideas = $state([...data.ideas]);
	let showNew = $state(false);
	let newTitle = $state('');
	let newPriority = $state('none');
	let creating = $state(false);
	let draggingId = $state<number | null>(null);

	function ideasFor(status: Status) {
		return ideas.filter((i) => i.status === status);
	}

	async function createIdea() {
		if (!newTitle.trim()) return;
		creating = true;
		const res = await fetch('/api/v1/ideas', {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ title: newTitle.trim(), priority: newPriority })
		});
		if (res.ok) {
			const idea = await res.json();
			ideas = [idea, ...ideas];
			newTitle = '';
			newPriority = 'none';
			showNew = false;
		}
		creating = false;
	}

	function onDragStart(e: DragEvent, id: number) {
		draggingId = id;
		e.dataTransfer?.setData('text/plain', String(id));
	}

	function onDragOver(e: DragEvent) {
		e.preventDefault();
	}

	async function onDrop(e: DragEvent, status: Status) {
		e.preventDefault();
		const id = parseInt(e.dataTransfer?.getData('text/plain') ?? '0');
		if (!id) return;
		const idea = ideas.find((i) => i.id === id);
		if (!idea || idea.status === status) return;

		// Optimistic update
		ideas = ideas.map((i) => i.id === id ? { ...i, status } : i);
		draggingId = null;

		await fetch(`/api/v1/ideas/${id}`, {
			method: 'PUT',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ status, createVersion: true })
		});
	}
</script>

<div class="flex flex-col h-[calc(100vh-6rem)]">
	<!-- Header -->
	<div class="flex items-center justify-between mb-6 flex-shrink-0">
		<h1 class="text-xl font-bold" style="font-family: 'Orbitron', sans-serif; color: var(--palais-text);">
			💡 Ideas
		</h1>
		<button
			onclick={() => (showNew = !showNew)}
			class="px-3 py-1.5 rounded-lg text-xs font-medium transition-all"
			style="background: var(--palais-gold); color: #0A0A0F;">
			+ New Idea
		</button>
	</div>

	<!-- New Idea form -->
	{#if showNew}
		<div class="mb-4 flex-shrink-0 p-4 rounded-xl"
			style="background: var(--palais-surface); border: 1px solid var(--palais-gold);">
			<div class="flex gap-3 items-end">
				<input
					bind:value={newTitle}
					placeholder="Idea title..."
					class="flex-1 px-3 py-2 rounded-lg text-sm outline-none"
					style="background: var(--palais-bg); border: 1px solid var(--palais-border); color: var(--palais-text);"
					onkeydown={(e) => e.key === 'Enter' && createIdea()}
				/>
				<select bind:value={newPriority}
					class="px-2 py-2 rounded-lg text-xs outline-none"
					style="background: var(--palais-bg); border: 1px solid var(--palais-border); color: var(--palais-text);">
					{#each ['none','low','medium','high','urgent'] as p}
						<option value={p}>{p}</option>
					{/each}
				</select>
				<button onclick={createIdea} disabled={creating || !newTitle.trim()}
					class="px-4 py-2 rounded-lg text-xs font-medium disabled:opacity-50"
					style="background: var(--palais-gold); color: #0A0A0F;">
					{creating ? '…' : 'Create'}
				</button>
			</div>
		</div>
	{/if}

	<!-- Pipeline columns -->
	<div class="flex gap-3 flex-1 overflow-x-auto overflow-y-hidden pb-2">
		{#each STATUSES as status}
			{@const col = ideasFor(status)}
			<!-- svelte-ignore a11y_no_static_element_interactions -->
			<div
				class="flex flex-col rounded-xl flex-shrink-0"
				style="width: 220px; background: var(--palais-surface); border: 1px solid var(--palais-border);"
				ondragover={onDragOver}
				ondrop={(e) => onDrop(e, status)}
			>
				<!-- Column header -->
				<div class="px-3 py-2.5 flex items-center justify-between flex-shrink-0"
					style="border-bottom: 2px solid {STATUS_COLORS[status]};">
					<span class="text-xs font-semibold" style="color: {STATUS_COLORS[status]}; font-family: 'Orbitron', sans-serif; letter-spacing: 0.06em;">
						{STATUS_LABELS[status]}
					</span>
					<span class="text-xs" style="color: var(--palais-text-muted);">{col.length}</span>
				</div>

				<!-- Cards -->
				<div class="flex-1 p-2 flex flex-col gap-2 overflow-y-auto">
					{#each col as idea (idea.id)}
						<!-- svelte-ignore a11y_no_static_element_interactions -->
						<div
							draggable={true}
							ondragstart={(e) => onDragStart(e, idea.id)}
							class="rounded-lg p-3 cursor-grab active:cursor-grabbing transition-all"
							style="
								background: {draggingId === idea.id ? 'var(--palais-surface-hover)' : 'var(--palais-bg)'};
								border: 1px solid var(--palais-border);
								opacity: {draggingId === idea.id ? '0.5' : '1'};
							"
						>
							<a href="/ideas/{idea.id}" class="block">
								<p class="text-xs font-medium leading-snug mb-1.5"
									style="color: var(--palais-text);">
									{idea.title}
								</p>
								<div class="flex items-center justify-between">
									{#if idea.priority && idea.priority !== 'none'}
										<span class="text-xs" style="color: {PRIORITY_COLORS[idea.priority]};">
											{idea.priority}
										</span>
									{:else}
										<span></span>
									{/if}
									<span class="text-xs" style="color: var(--palais-text-muted);">
										{new Date(idea.updatedAt).toLocaleDateString('fr-FR', { day: '2-digit', month: 'short' })}
									</span>
								</div>
								{#if idea.tags && (idea.tags as string[]).length > 0}
									<div class="flex flex-wrap gap-1 mt-1.5">
										{#each (idea.tags as string[]).slice(0, 3) as tag}
											<span class="text-xs px-1.5 py-0.5 rounded"
												style="background: var(--palais-surface-hover); color: var(--palais-cyan); font-size: 0.6rem;">
												{tag}
											</span>
										{/each}
									</div>
								{/if}
							</a>
						</div>
					{:else}
						<p class="text-xs text-center py-4" style="color: var(--palais-border);">
							Drop here
						</p>
					{/each}
				</div>
			</div>
		{/each}
	</div>
</div>
