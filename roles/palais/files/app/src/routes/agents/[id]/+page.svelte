<script lang="ts">
	let { data } = $props();

	const agentStatusColor = $derived(
		data.agent.status === 'idle'    ? 'var(--palais-green)'
		: data.agent.status === 'busy'  ? 'var(--palais-gold)'
		: data.agent.status === 'error' ? 'var(--palais-red)'
		:                                 'var(--palais-text-muted)'
	);

	const agentStatusLabel = $derived(
		data.agent.status === 'idle'    ? 'En ligne'
		: data.agent.status === 'busy'  ? 'Actif'
		: data.agent.status === 'error' ? 'Erreur'
		:                                 'Hors ligne'
	);

	const ringAnimating = $derived(data.agent.status === 'busy');

	function sessionStatusColor(s: string) {
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
	<!-- Hero card: image left + activity ring, info right -->
	<div class="agent-hero rounded-2xl overflow-hidden"
		style="background: var(--palais-surface); border: 1px solid var(--palais-border); min-height: 180px;">
		<div class="flex" style="min-height: 180px;">

			<!-- Left: avatar with activity ring -->
			<div class="relative flex-shrink-0 flex items-center justify-center"
				style="width: 180px; background: linear-gradient(135deg, rgba(255,196,0,0.06), rgba(0,255,255,0.04));">
				<!-- SVG ring that wraps around the avatar -->
				<svg class="absolute inset-0 w-full h-full" viewBox="0 0 180 180" xmlns="http://www.w3.org/2000/svg">
					<!-- Base track -->
					<circle cx="90" cy="90" r="76"
						fill="none"
						stroke={agentStatusColor}
						stroke-width="2"
						opacity="0.12"
					/>
					<!-- Animated arc -->
					<circle cx="90" cy="90" r="76"
						fill="none"
						stroke={agentStatusColor}
						stroke-width="3"
						stroke-dasharray="120 358"
						stroke-dashoffset="0"
						stroke-linecap="round"
						opacity={ringAnimating ? '0.9' : '0.5'}
						class={ringAnimating ? 'ring-spin' : ''}
					/>
				</svg>

				<!-- Avatar circle -->
				<div class="w-28 h-28 rounded-full overflow-hidden flex items-center justify-center z-10"
					style="background: linear-gradient(135deg, var(--palais-gold), var(--palais-amber)); color: var(--palais-bg);">
					{#if data.agent.avatar_url}
						<img
							src={data.agent.avatar_url}
							alt={data.agent.name}
							class="w-full h-full object-cover"
						/>
					{:else}
						<span class="text-3xl font-bold" style="font-family: 'Orbitron', sans-serif;">
							{data.agent.name.substring(0, 2).toUpperCase()}
						</span>
					{/if}
				</div>
			</div>

			<!-- Right: info panel -->
			<div class="flex-1 p-6 flex flex-col justify-center gap-2 min-w-0">
				<!-- Status row -->
				<div class="flex items-center gap-2 flex-wrap">
					<span class="w-2.5 h-2.5 rounded-full flex-shrink-0"
						style="background: {agentStatusColor}; box-shadow: 0 0 8px {agentStatusColor};"
						class:pulse-dot={data.agent.status === 'busy'}
					></span>
					<span class="text-xs font-semibold uppercase tracking-wider"
						style="color: {agentStatusColor};">
						{agentStatusLabel}
					</span>
					{#if data.agent.model}
						<span class="text-xs px-2 py-0.5 rounded font-mono"
							style="background: rgba(255,255,255,0.04); color: var(--palais-text-muted); border: 1px solid var(--palais-border);">
							{data.agent.model}
						</span>
					{/if}
				</div>

				<!-- Name -->
				<h1 class="text-2xl font-bold leading-tight"
					style="color: var(--palais-gold); font-family: 'Orbitron', sans-serif;">
					{data.agent.name}
				</h1>

				<!-- Persona / title -->
				{#if data.agent.persona}
					<p class="text-sm font-medium" style="color: var(--palais-text);">
						{data.agent.persona}
					</p>
				{/if}

				<!-- Bio snippet -->
				{#if data.agent.bio}
					<p class="text-sm italic leading-relaxed" style="color: var(--palais-text-muted);">
						{data.agent.bio}
					</p>
				{/if}

				<!-- Stats inline -->
				<div class="flex gap-6 mt-2 flex-wrap">
					<div>
						<p class="text-xs" style="color: var(--palais-text-muted);">Tokens 30j</p>
						<p class="text-base font-semibold tabular-nums" style="color: var(--palais-cyan);">
							{data.agent.totalTokens30d?.toLocaleString() || '0'}
						</p>
					</div>
					<div>
						<p class="text-xs" style="color: var(--palais-text-muted);">Coût 30j</p>
						<p class="text-base font-semibold tabular-nums" style="color: var(--palais-cyan);">
							${(data.agent.totalSpend30d || 0).toFixed(2)}
						</p>
					</div>
					<div>
						<p class="text-xs" style="color: var(--palais-text-muted);">Qualité moy.</p>
						<p class="text-base font-semibold tabular-nums" style="color: var(--palais-cyan);">
							{data.agent.avgQualityScore?.toFixed(1) || 'N/A'}
						</p>
					</div>
				</div>
			</div>
		</div>
	</div>

	<!-- Sessions récentes -->
	<section>
		<h2 class="text-sm font-semibold uppercase tracking-wider mb-4"
			style="color: var(--palais-text-muted);">
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
									<span class="text-xs tabular-nums font-mono"
										style="color: {confidenceColor(session.confidenceScore)};"
										title="Score de confiance">
										{(session.confidenceScore * 100).toFixed(0)}%
									</span>
								{/if}
								<span class="text-xs tabular-nums" style="color: {sessionStatusColor(session.status)};">
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

	/* Activity ring rotation for busy agents */
	.ring-spin {
		animation: ring-rotate 3s linear infinite;
		transform-origin: 90px 90px;
	}

	@keyframes ring-rotate {
		from { transform: rotate(0deg); }
		to   { transform: rotate(360deg); }
	}

	/* Status dot pulse for busy agents */
	.pulse-dot {
		animation: pulse-glow 1.5s ease-in-out infinite;
	}

	@keyframes pulse-glow {
		0%, 100% { opacity: 1; }
		50%       { opacity: 0.35; }
	}
</style>
