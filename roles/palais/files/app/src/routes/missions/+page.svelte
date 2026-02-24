<script lang="ts">
	import type { PageData } from './$types';

	let { data }: { data: PageData } = $props();

	type Mission = typeof data.missions[number];

	const MISSION_STATUSES = [
		'briefing', 'brainstorming', 'planning', 'co_editing',
		'approved', 'executing', 'review', 'completed', 'failed'
	] as const;
	type MissionStatus = (typeof MISSION_STATUSES)[number];

	const STATUS_COLORS: Record<MissionStatus, string> = {
		briefing:     'var(--palais-text-muted)',
		brainstorming:'var(--palais-cyan)',
		planning:     'var(--palais-amber)',
		co_editing:   'var(--palais-gold)',
		approved:     '#22c55e',
		executing:    'var(--palais-red)',
		review:       'var(--palais-amber)',
		completed:    '#22c55e',
		failed:       'var(--palais-red)'
	};

	const STATUS_LABELS: Record<MissionStatus, string> = {
		briefing:     'Briefing',
		brainstorming:'Brainstorming',
		planning:     'Planning',
		co_editing:   'Co-Editing',
		approved:     'Approved',
		executing:    'Executing',
		review:       'Review',
		completed:    'Completed',
		failed:       'Failed'
	};

	let missions = $state([...data.missions]);

	// Group by status for summary
	const statusCounts = $derived(
		MISSION_STATUSES.reduce<Record<string, number>>((acc, s) => {
			acc[s] = missions.filter((m) => m.status === s).length;
			return acc;
		}, {})
	);

	const activeMissions = $derived(
		missions.filter((m) => !['completed', 'failed', 'archived'].includes(m.status))
	);
</script>

<div class="flex flex-col h-[calc(100vh-6rem)] gap-4">
	<!-- Header -->
	<div class="flex items-center justify-between flex-shrink-0">
		<h1 class="text-xl font-bold" style="font-family: 'Orbitron', sans-serif; color: var(--palais-text);">
			🚀 Missions
		</h1>
		<a
			href="/missions/new"
			class="px-3 py-1.5 rounded-lg text-xs font-medium transition-all"
			style="background: var(--palais-gold); color: #0A0A0F;">
			+ New Mission
		</a>
	</div>

	<!-- Status summary bar -->
	<div class="flex gap-2 flex-wrap flex-shrink-0">
		{#each MISSION_STATUSES as s}
			{#if statusCounts[s] > 0}
				<div class="flex items-center gap-1.5 px-3 py-1 rounded-full text-xs"
					style="background: color-mix(in srgb, {STATUS_COLORS[s]} 12%, transparent); border: 1px solid {STATUS_COLORS[s]}; color: {STATUS_COLORS[s]};">
					<span class="font-semibold">{statusCounts[s]}</span>
					<span>{STATUS_LABELS[s]}</span>
				</div>
			{/if}
		{/each}
	</div>

	<!-- Mission list -->
	<div class="flex-1 overflow-y-auto flex flex-col gap-3">
		{#if missions.length === 0}
			<div class="flex flex-col items-center justify-center flex-1 gap-4">
				<p class="text-sm" style="color: var(--palais-text-muted);">No missions yet.</p>
				<a href="/missions/new"
					class="px-4 py-2 rounded-lg text-sm font-medium"
					style="background: var(--palais-gold); color: #0A0A0F;">
					Create your first mission
				</a>
			</div>
		{:else}
			{#each missions as mission}
				<a
					href="/missions/{mission.id}"
					class="block rounded-xl p-4 transition-all hover:border-opacity-60"
					style="background: var(--palais-surface); border: 1px solid var(--palais-border);"
				>
					<div class="flex items-start justify-between gap-4">
						<div class="flex-1 min-w-0">
							<p class="text-sm font-semibold truncate mb-1" style="color: var(--palais-text);">
								{mission.title}
							</p>
							{#if mission.briefText}
								<p class="text-xs line-clamp-2" style="color: var(--palais-text-muted);">
									{mission.briefText}
								</p>
							{/if}
						</div>
						<div class="flex flex-col items-end gap-1.5 flex-shrink-0">
							<span class="px-2 py-0.5 rounded-full text-xs font-medium"
								style="background: color-mix(in srgb, {STATUS_COLORS[mission.status as MissionStatus] ?? 'var(--palais-border)'} 15%, transparent); color: {STATUS_COLORS[mission.status as MissionStatus] ?? 'var(--palais-text-muted)'};">
								{STATUS_LABELS[mission.status as MissionStatus] ?? mission.status}
							</span>
							<span class="text-xs" style="color: var(--palais-text-muted);">
								{new Date(mission.createdAt).toLocaleDateString('fr-FR', { day: '2-digit', month: 'short' })}
							</span>
						</div>
					</div>
					{#if mission.totalEstimatedCost}
						<div class="mt-2 text-xs" style="color: var(--palais-gold);">
							Est. ${mission.totalEstimatedCost.toFixed(3)}
						</div>
					{/if}
				</a>
			{/each}
		{/if}
	</div>
</div>
