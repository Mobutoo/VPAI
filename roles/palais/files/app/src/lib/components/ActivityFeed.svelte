<script lang="ts">
	let {
		activities = [],
		maxItems = 20
	}: { activities: Record<string, unknown>[]; maxItems?: number } = $props();
</script>

<div class="space-y-1 max-h-96 overflow-y-auto">
	{#each activities.slice(0, maxItems) as item (item.id)}
		<div
			class="flex items-start gap-3 p-2 rounded text-sm hover:bg-[var(--palais-surface-hover)] transition-colors"
		>
			<span
				class="text-xs tabular-nums whitespace-nowrap mt-0.5 flex-shrink-0"
				style="color: var(--palais-text-muted);"
			>
				{new Date(String(item.createdAt)).toLocaleTimeString('fr-FR', {
					hour: '2-digit',
					minute: '2-digit'
				})}
			</span>
			<div>
				<span style="color: var(--palais-gold);">{item.actorAgentId || 'System'}</span>
				<span style="color: var(--palais-text-muted);"> {item.action} </span>
				<span style="color: var(--palais-text);">{item.entityType} #{item.entityId}</span>
			</div>
		</div>
	{/each}
	{#if activities.length === 0}
		<p class="text-sm text-center py-8" style="color: var(--palais-text-muted);">
			Aucune activité récente
		</p>
	{/if}
</div>
