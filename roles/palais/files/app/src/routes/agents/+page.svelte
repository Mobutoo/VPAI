<script lang="ts">
	import AgentCard from '$lib/components/agents/AgentCard.svelte';
	import { connectSSE, onAgentEvent } from '$lib/stores/sse';
	import { onMount } from 'svelte';

	let { data } = $props();
	let agentList = $state(data.agents);

	onMount(() => {
		connectSSE();
		const unsub = onAgentEvent((evt) => {
			if (evt.status) {
				agentList = agentList.map((a) =>
					a.id === evt.agentId ? { ...a, status: (evt.status as typeof a.status) ?? a.status } : a
				);
			}
		});
		return unsub;
	});

	// Build name lookup for perf table
	const agentNameMap = $derived(new Map(agentList.map(a => [a.id, a.name])));

	function fmtConf(v: number | null): string {
		if (v === null || v === undefined) return '—';
		return `${(v * 100).toFixed(0)}%`;
	}

	function confColor(v: number | null): string {
		if (v === null || v === undefined) return 'var(--palais-text-muted)';
		return v >= 0.8 ? 'var(--palais-green)' : v >= 0.5 ? 'var(--palais-amber)' : 'var(--palais-red)';
	}

	// Only show agents that have had at least 1 session in 30d
	const activePerf = $derived(data.perf.filter(r => r.sessionCount > 0));
</script>

<div class="space-y-8">
	<h1 class="text-2xl font-bold" style="color: var(--palais-gold); font-family: 'Orbitron', sans-serif;">
		Agent Cockpit
	</h1>

	<!-- Agent cards grid -->
	<div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
		{#each agentList as agent, i (agent.id)}
			<AgentCard {agent} index={i} />
		{/each}
	</div>

	<!-- Performance table (30 days) -->
	<section>
		<h2
			class="text-sm font-semibold uppercase tracking-wider mb-4"
			style="color: var(--palais-text-muted);"
		>
			Performance — 30 derniers jours
		</h2>

		{#if activePerf.length === 0}
			<p class="text-sm py-6 text-center" style="color: var(--palais-text-muted);">
				Aucune session enregistrée dans les 30 derniers jours.
			</p>
		{:else}
			<div class="rounded-xl overflow-hidden" style="border: 1px solid var(--palais-border);">
				<table class="w-full text-sm">
					<thead>
						<tr style="background: var(--palais-surface); border-bottom: 1px solid var(--palais-border);">
							<th class="text-left px-4 py-2.5 text-xs font-semibold uppercase tracking-wider"
								style="color: var(--palais-text-muted);">Agent</th>
							<th class="text-right px-4 py-2.5 text-xs font-semibold uppercase tracking-wider"
								style="color: var(--palais-text-muted);">Sessions</th>
							<th class="text-right px-4 py-2.5 text-xs font-semibold uppercase tracking-wider"
								style="color: var(--palais-text-muted);">Tokens</th>
							<th class="text-right px-4 py-2.5 text-xs font-semibold uppercase tracking-wider"
								style="color: var(--palais-text-muted);">Coût</th>
							<th class="text-right px-4 py-2.5 text-xs font-semibold uppercase tracking-wider"
								style="color: var(--palais-text-muted);">Confiance moy.</th>
							<th class="text-right px-4 py-2.5 text-xs font-semibold uppercase tracking-wider"
								style="color: var(--palais-text-muted);">Erreurs/session</th>
						</tr>
					</thead>
					<tbody>
						{#each activePerf as row, i (row.agentId)}
							<tr
								style="background: {i % 2 === 0 ? 'var(--palais-bg)' : 'var(--palais-surface)'}; border-bottom: 1px solid var(--palais-border);"
							>
								<td class="px-4 py-2.5">
									<a
										href="/agents/{row.agentId}"
										class="font-medium transition-colors"
										style="color: var(--palais-text); text-decoration: none;"
										onmouseenter={(e) => (e.currentTarget.style.color = 'var(--palais-cyan)')}
										onmouseleave={(e) => (e.currentTarget.style.color = 'var(--palais-text)')}
									>
										{agentNameMap.get(row.agentId) ?? row.agentId}
									</a>
								</td>
								<td class="px-4 py-2.5 text-right tabular-nums"
									style="color: var(--palais-text);">{row.sessionCount}</td>
								<td class="px-4 py-2.5 text-right tabular-nums font-mono text-xs"
									style="color: var(--palais-cyan);">{row.totalTokens.toLocaleString()}</td>
								<td class="px-4 py-2.5 text-right tabular-nums font-mono text-xs"
									style="color: var(--palais-amber);">${row.totalCost.toFixed(3)}</td>
								<td class="px-4 py-2.5 text-right tabular-nums font-mono text-xs"
									style="color: {confColor(row.avgConfidence)};">
									{fmtConf(row.avgConfidence)}
								</td>
								<td class="px-4 py-2.5 text-right tabular-nums font-mono text-xs"
									style="color: {row.errorRate > 0.5 ? 'var(--palais-red)' : row.errorRate > 0.1 ? 'var(--palais-amber)' : 'var(--palais-text-muted)'};">
									{row.errorRate > 0 ? row.errorRate.toFixed(2) : '—'}
								</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
		{/if}
	</section>
</div>
