<script lang="ts">
	let { data } = $props();

	const stats = [
		{ label: 'Tokens 30j', value: data.agent.totalTokens30d?.toLocaleString() || '0' },
		{ label: 'Coût 30j', value: `$${(data.agent.totalSpend30d || 0).toFixed(2)}` },
		{ label: 'Qualité moy.', value: data.agent.avgQualityScore?.toFixed(1) || 'N/A' }
	];

	function statusColor(s: string) {
		return s === 'completed' ? 'var(--palais-green)'
			 : s === 'failed'    ? 'var(--palais-red)'
			 :                     'var(--palais-amber)';
	}

	function confidenceColor(score: number) {
		return score >= 0.8 ? 'var(--palais-green)'
			 : score >= 0.5 ? 'var(--palais-amber)'
			 :                'var(--palais-red)';
	}
</script>

<div class="space-y-6">
	<!-- Header -->
	<div class="flex items-center gap-4">
		<div
			class="w-16 h-16 rounded-full flex items-center justify-center flex-shrink-0"
			style="background: linear-gradient(135deg, var(--palais-gold), var(--palais-amber)); color: var(--palais-bg);"
		>
			{#if data.agent.avatar_url}
				<img
					src={data.agent.avatar_url}
					alt={data.agent.name}
					class="w-16 h-16 rounded-full object-cover"
				/>
			{:else}
				<span class="text-xl font-bold">{data.agent.name.substring(0, 2).toUpperCase()}</span>
			{/if}
		</div>
		<div>
			<h1
				class="text-2xl font-bold"
				style="color: var(--palais-gold); font-family: 'Orbitron', sans-serif;"
			>
				{data.agent.name}
			</h1>
			<p class="text-sm mt-1" style="color: var(--palais-text-muted);">{data.agent.persona}</p>
		</div>
	</div>

	<!-- Stats -->
	<div class="grid grid-cols-3 gap-4">
		{#each stats as stat (stat.label)}
			<div
				class="p-4 rounded-lg"
				style="background: var(--palais-surface); border: 1px solid var(--palais-border);"
			>
				<p class="text-xs" style="color: var(--palais-text-muted);">{stat.label}</p>
				<p class="text-lg font-semibold tabular-nums mt-1" style="color: var(--palais-cyan);">
					{stat.value}
				</p>
			</div>
		{/each}
	</div>

	<!-- Sessions -->
	<section>
		<h2
			class="text-sm font-semibold uppercase tracking-wider mb-4"
			style="color: var(--palais-text-muted);"
		>
			Sessions récentes
		</h2>
		{#if data.sessions.length === 0}
			<p class="text-sm py-8 text-center" style="color: var(--palais-text-muted);">
				Aucune session enregistrée
			</p>
		{:else}
			<div class="space-y-2">
				{#each data.sessions as session (session.id)}
					<a
						href="/agents/{data.agent.id}/traces/{session.id}"
						class="block p-3 rounded-lg session-card"
						style="background: var(--palais-surface); border: 1px solid var(--palais-border); text-decoration: none;"
					>
						<div class="flex items-center justify-between">
							<span class="text-sm" style="color: var(--palais-text);">
								{session.summary || `Session #${session.id}`}
							</span>
							<div class="flex items-center gap-2">
								{#if session.confidenceScore !== null && session.confidenceScore !== undefined}
									<span
										class="text-xs tabular-nums font-mono"
										style="color: {confidenceColor(session.confidenceScore)};"
										title="Score de confiance"
									>
										{(session.confidenceScore * 100).toFixed(0)}%
									</span>
								{/if}
								<span class="text-xs tabular-nums" style="color: {statusColor(session.status)};">
									{session.status}
								</span>
							</div>
						</div>
						<div class="flex gap-4 mt-1 text-xs" style="color: var(--palais-text-muted);">
							{#if session.model}<span>{session.model}</span>{/if}
							<span class="tabular-nums">{session.totalTokens?.toLocaleString() || 0} tokens</span>
							<span class="tabular-nums">${session.totalCost?.toFixed(3) || '0.000'}</span>
							<span class="ml-auto" style="color: var(--palais-cyan); font-size: 0.65rem; opacity: 0.6;">→ trace</span>
						</div>
					</a>
				{/each}
			</div>
		{/if}
	</section>
</div>

<style>
	.session-card {
		transition: border-color 0.15s;
	}
	.session-card:hover {
		border-color: var(--palais-cyan) !important;
	}
</style>
