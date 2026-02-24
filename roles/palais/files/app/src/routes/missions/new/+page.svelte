<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';

	// Approved ideas passed via URL search param ideaId (pre-select)
	// or fetched client-side
	let title = $state('');
	let briefText = $state('');
	let selectedIdeaId = $state<number | null>(null);
	let approvedIdeas = $state<Array<{ id: number; title: string }>>([]);
	let creating = $state(false);
	let error = $state('');

	// Pre-fill from idea if ideaId in URL
	import { onMount } from 'svelte';
	onMount(async () => {
		const res = await fetch('/api/v1/ideas?status=approved');
		// Fall back: load all ideas and filter
		const allRes = await fetch('/api/v1/ideas');
		if (allRes.ok) {
			const all = await allRes.json();
			approvedIdeas = all.filter((i: { status: string }) => i.status === 'approved');
		}

		const ideaIdParam = $page.url.searchParams.get('ideaId');
		if (ideaIdParam) {
			selectedIdeaId = parseInt(ideaIdParam);
			const idea = approvedIdeas.find((i) => i.id === selectedIdeaId);
			if (idea && !title) title = idea.title;
		}
	});

	async function create() {
		if (!title.trim()) { error = 'Title is required'; return; }
		creating = true;
		error = '';
		const res = await fetch('/api/v1/missions', {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({
				title: title.trim(),
				briefText: briefText.trim() || null,
				ideaId: selectedIdeaId
			})
		});
		if (res.ok) {
			const mission = await res.json();
			goto(`/missions/${mission.id}`);
		} else {
			const data = await res.json();
			error = data.error ?? 'Failed to create mission';
		}
		creating = false;
	}
</script>

<div class="max-w-2xl mx-auto flex flex-col gap-6">
	<!-- Header -->
	<div class="flex items-center gap-3">
		<a href="/missions" class="text-xs px-2 py-1 rounded"
			style="background: var(--palais-surface); color: var(--palais-text-muted); border: 1px solid var(--palais-border);">
			← Missions
		</a>
		<h1 class="text-xl font-bold" style="font-family: 'Orbitron', sans-serif; color: var(--palais-text);">
			New Mission
		</h1>
	</div>

	<div class="rounded-xl p-6 flex flex-col gap-5"
		style="background: var(--palais-surface); border: 1px solid var(--palais-border);">

		<!-- Title -->
		<div class="flex flex-col gap-1.5">
			<label class="text-xs font-medium" style="color: var(--palais-text-muted);">Mission Title *</label>
			<input
				bind:value={title}
				placeholder="What needs to be built?"
				class="px-3 py-2.5 rounded-lg text-sm outline-none"
				style="background: var(--palais-bg); border: 1px solid var(--palais-border); color: var(--palais-text);"
				onkeydown={(e) => e.key === 'Enter' && create()}
			/>
		</div>

		<!-- From approved idea (optional) -->
		{#if approvedIdeas.length > 0}
			<div class="flex flex-col gap-1.5">
				<label class="text-xs font-medium" style="color: var(--palais-text-muted);">
					From Approved Idea <span style="color: var(--palais-border);">(optional)</span>
				</label>
				<select
					bind:value={selectedIdeaId}
					onchange={() => {
						const idea = approvedIdeas.find((i) => i.id === selectedIdeaId);
						if (idea && !title) title = idea.title;
					}}
					class="px-3 py-2.5 rounded-lg text-sm outline-none"
					style="background: var(--palais-bg); border: 1px solid var(--palais-border); color: var(--palais-text);"
				>
					<option value={null}>— None —</option>
					{#each approvedIdeas as idea}
						<option value={idea.id}>{idea.title}</option>
					{/each}
				</select>
			</div>
		{/if}

		<!-- Brief -->
		<div class="flex flex-col gap-1.5">
			<label class="text-xs font-medium" style="color: var(--palais-text-muted);">
				Mission Brief <span style="color: var(--palais-border);">(optional)</span>
			</label>
			<textarea
				bind:value={briefText}
				rows="5"
				placeholder="Describe the goal, context, and success criteria..."
				class="px-3 py-2.5 rounded-lg text-sm outline-none resize-none"
				style="background: var(--palais-bg); border: 1px solid var(--palais-border); color: var(--palais-text);"
			></textarea>
			<p class="text-xs" style="color: var(--palais-text-muted);">
				The AI will refine this through brainstorming if it's sparse.
			</p>
		</div>

		{#if error}
			<p class="text-xs px-3 py-2 rounded" style="background: color-mix(in srgb, var(--palais-red) 15%, transparent); color: var(--palais-red); border: 1px solid var(--palais-red);">
				{error}
			</p>
		{/if}

		<button
			onclick={create}
			disabled={creating || !title.trim()}
			class="py-2.5 rounded-lg text-sm font-medium disabled:opacity-50 transition-all"
			style="background: var(--palais-gold); color: #0A0A0F;"
		>
			{creating ? 'Creating…' : '🚀 Launch Mission'}
		</button>
	</div>
</div>
