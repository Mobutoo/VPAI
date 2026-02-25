<script lang="ts">
	import StandupCard from '$lib/components/dashboard/StandupCard.svelte';
	import InsightBanner from '$lib/components/dashboard/InsightBanner.svelte';
	let { data } = $props();
</script>

<div class="space-y-6">
	<!-- Header -->
	<div class="flex items-center justify-between">
		<h1 class="text-2xl font-bold" style="color: var(--palais-gold); font-family: 'Orbitron', sans-serif;">
			PALAIS
		</h1>
		<span class="text-sm tabular-nums" style="color: var(--palais-text-muted);">
			{new Date().toLocaleDateString('fr-FR', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })}
		</span>
	</div>

	<!-- Critical Insight Banners -->
	{#each data.insights.filter(i => i.severity === 'critical') as insight (insight.id)}
		<InsightBanner {insight} />
	{/each}

	<!-- Digital Standup -->
	<StandupCard standup={data.standup} />

	<!-- Agent Grid -->
	<section>
		<h2 class="text-sm font-semibold uppercase tracking-wider mb-4" style="color: var(--palais-text-muted);">
			Agents
		</h2>
		<div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
			{#each data.agents as agent (agent.id)}
				<div class="p-4 rounded-lg transition-all hover:scale-[1.02]"
					style="background: var(--palais-surface); border: 1px solid var(--palais-border);"
					style:box-shadow={agent.status === 'busy' ? 'var(--palais-glow-md)' : 'none'}
					style:border-color={agent.status === 'busy' ? 'var(--palais-gold)' : 'var(--palais-border)'}
				>
					<!-- Avatar placeholder -->
					<div class="w-10 h-10 rounded-full flex items-center justify-center mb-3"
						style="background: linear-gradient(135deg, var(--palais-gold), var(--palais-amber)); color: var(--palais-bg);">
						<span class="text-sm font-bold">{agent.name.substring(0, 2).toUpperCase()}</span>
					</div>
					<h3 class="text-sm font-semibold" style="color: var(--palais-text);">{agent.name}</h3>
					<p class="text-xs mt-1 capitalize"
						style:color={
							agent.status === 'idle' ? 'var(--palais-green)' :
							agent.status === 'busy' ? 'var(--palais-gold)' :
							agent.status === 'error' ? 'var(--palais-red)' :
							'var(--palais-text-muted)'
						}
					>
						{agent.status}
					</p>
				</div>
			{/each}
		</div>
	</section>
</div>
