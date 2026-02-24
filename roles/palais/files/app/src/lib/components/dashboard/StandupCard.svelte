<script lang="ts">
	interface SuggestedAction {
		label: string;
		action_type: string;
		params: Record<string, string>;
	}

	interface Standup {
		generated: boolean;
		title?: string;
		description?: string;
		suggestedActions?: SuggestedAction[];
		createdAt?: string;
	}

	let { standup }: { standup: Standup } = $props();
</script>

{#if standup.generated}
	<section
		class="rounded-lg p-6 relative overflow-hidden"
		style="background: var(--palais-surface); border: 1px solid var(--palais-gold); box-shadow: var(--palais-glow-sm);"
	>
		<!-- Gold accent bar -->
		<div class="absolute top-0 left-0 w-full h-0.5" style="background: var(--palais-gold);"></div>

		<div class="flex items-start justify-between mb-4">
			<h2 class="text-lg font-semibold" style="color: var(--palais-gold); font-family: 'Orbitron', sans-serif;">
				{standup.title}
			</h2>
			{#if standup.createdAt}
				<span class="text-xs tabular-nums" style="color: var(--palais-text-muted);">
					{new Date(standup.createdAt).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })}
				</span>
			{/if}
		</div>

		<div class="text-sm leading-relaxed whitespace-pre-wrap" style="color: var(--palais-text);">
			{standup.description}
		</div>

		{#if standup.suggestedActions && standup.suggestedActions.length > 0}
			<div class="flex flex-wrap gap-2 mt-4 pt-4" style="border-top: 1px solid var(--palais-border);">
				{#each standup.suggestedActions as action}
					{#if action.action_type === 'navigate'}
						<a
							href={action.params.url}
							class="px-3 py-1.5 rounded text-xs font-medium transition-all hover:brightness-110"
							style="background: transparent; color: var(--palais-gold); border: 1px solid var(--palais-gold);"
						>
							{action.label}
						</a>
					{:else}
						<button
							class="px-3 py-1.5 rounded text-xs font-medium transition-all hover:brightness-110"
							style="background: transparent; color: var(--palais-amber); border: 1px solid var(--palais-amber);"
						>
							{action.label}
						</button>
					{/if}
				{/each}
			</div>
		{/if}
	</section>
{/if}
