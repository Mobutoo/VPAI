<script lang="ts">
	let { data } = $props();

	const severityOrder: Record<string, number> = { critical: 0, warning: 1, info: 2 };
	let sorted = $derived(
		[...data.insights].sort((a, b) => (severityOrder[a.severity] ?? 3) - (severityOrder[b.severity] ?? 3))
	);

	const severityColors: Record<string, string> = {
		critical: 'var(--palais-red)',
		warning: 'var(--palais-amber)',
		info: 'var(--palais-cyan)'
	};

	const typeLabels: Record<string, string> = {
		agent_stuck: 'Agent bloqué',
		budget_warning: 'Budget',
		error_pattern: 'Pattern erreur',
		dependency_blocked: 'Dépendance bloquée'
	};

	async function acknowledge(id: number) {
		await fetch(`/api/v1/insights/${id}/acknowledge`, { method: 'PUT' });
		window.location.reload();
	}

	async function executeAction(action: { action_type: string; params: Record<string, unknown> }) {
		if (action.action_type === 'navigate') {
			window.location.href = action.params.url as string;
		} else if (action.action_type === 'webhook') {
			await fetch(action.params.url as string, {
				method: (action.params.method as string) || 'POST'
			});
		}
	}
</script>

<div class="space-y-6">
	<div class="flex items-center justify-between">
		<h1 class="text-2xl font-bold" style="color: var(--palais-gold); font-family: 'Orbitron', sans-serif;">
			INSIGHTS
		</h1>
		<div class="flex items-center gap-4">
			<span class="text-sm" style="color: var(--palais-text-muted);">
				{data.insights.filter(i => !i.acknowledged).length} actif(s)
			</span>
			<a
				href={data.showAcknowledged ? '/insights' : '/insights?showAcknowledged=true'}
				class="text-xs px-3 py-1.5 rounded"
				style="color: var(--palais-gold); border: 1px solid var(--palais-border);"
			>
				{data.showAcknowledged ? 'Masquer acquittés' : 'Afficher tous'}
			</a>
		</div>
	</div>

	{#if sorted.length === 0}
		<div class="text-center py-16" style="color: var(--palais-text-muted);">
			<p class="text-lg">Aucun insight actif</p>
			<p class="text-sm mt-2">Tout est nominal.</p>
		</div>
	{:else}
		<div class="space-y-3">
			{#each sorted as insight (insight.id)}
				<div
					class="rounded-lg p-5 transition-all"
					style="background: var(--palais-surface); border: 1px solid var(--palais-border);"
					style:opacity={insight.acknowledged ? '0.5' : '1'}
				>
					<div class="flex items-start justify-between gap-4">
						<div class="flex-1 min-w-0">
							<div class="flex items-center gap-2 mb-2 flex-wrap">
								<span class="text-xs font-bold uppercase px-2 py-0.5 rounded"
									style:background={severityColors[insight.severity] ?? 'var(--palais-cyan)'}
									style="color: var(--palais-bg);"
								>
									{insight.severity}
								</span>
								<span class="text-xs px-2 py-0.5 rounded"
									style="color: var(--palais-text-muted); border: 1px solid var(--palais-border);"
								>
									{typeLabels[insight.type] ?? insight.type}
								</span>
								<span class="text-xs tabular-nums" style="color: var(--palais-text-muted);">
									{new Date(insight.createdAt).toLocaleString('fr-FR')}
								</span>
							</div>
							<h3 class="text-sm font-semibold mb-1" style="color: var(--palais-text);">
								{insight.title}
							</h3>
							{#if insight.description}
								<p class="text-sm" style="color: var(--palais-text-muted);">
									{insight.description}
								</p>
							{/if}
						</div>
						{#if !insight.acknowledged}
							<button
								onclick={() => acknowledge(insight.id)}
								class="shrink-0 text-xs px-3 py-1.5 rounded transition-colors hover:brightness-110"
								style="color: var(--palais-text-muted); border: 1px solid var(--palais-border);"
							>
								Acquitter
							</button>
						{/if}
					</div>

					<!-- Suggested Actions -->
					{#if insight.suggestedActions && !insight.acknowledged}
						{@const actions = insight.suggestedActions as Array<{label: string; action_type: string; params: Record<string, unknown>}>}
						{#if actions.length > 0}
							<div class="flex flex-wrap gap-2 mt-3 pt-3" style="border-top: 1px solid var(--palais-border);">
								{#each actions as action}
									<button
										onclick={() => executeAction(action)}
										class="px-3 py-1.5 rounded text-xs font-medium transition-all hover:brightness-110"
										style="background: transparent; color: var(--palais-gold); border: 1px solid var(--palais-gold);"
									>
										{action.label}
									</button>
								{/each}
							</div>
						{/if}
					{/if}
				</div>
			{/each}
		</div>
	{/if}
</div>
