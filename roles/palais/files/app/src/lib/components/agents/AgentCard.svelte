<script lang="ts">
	let { agent }: { agent: Record<string, unknown> } = $props();

	let statusColor = $derived(
		agent.status === 'idle'
			? 'var(--palais-green)'
			: agent.status === 'busy'
				? 'var(--palais-gold)'
				: agent.status === 'error'
					? 'var(--palais-red)'
					: 'var(--palais-text-muted)'
	);

	let isBusy = $derived(agent.status === 'busy');
</script>

<!-- eslint-disable-next-line svelte/no-navigation-without-resolve -->
<a
	href="/agents/{agent.id}"
	class="block p-4 rounded-lg transition-all hover:scale-[1.02]"
	class:animate-pulse={isBusy}
	style="background: var(--palais-surface); border: 1px solid {isBusy
		? 'var(--palais-gold)'
		: 'var(--palais-border)'};"
	style:box-shadow={isBusy ? 'var(--palais-glow-md)' : 'none'}
>
	<!-- Avatar -->
	<div
		class="w-12 h-12 rounded-full flex items-center justify-center mb-3"
		style="background: linear-gradient(135deg, var(--palais-gold), var(--palais-amber)); color: var(--palais-bg);"
	>
		{#if agent.avatar_url}
			<img
				src={String(agent.avatar_url)}
				alt={String(agent.name)}
				class="w-12 h-12 rounded-full object-cover"
			/>
		{:else}
			<span class="text-sm font-bold">{String(agent.name).substring(0, 2).toUpperCase()}</span>
		{/if}
	</div>

	<h3 class="text-sm font-semibold" style="color: var(--palais-text);">{agent.name}</h3>
	<p class="text-xs truncate" style="color: var(--palais-text-muted);">{agent.persona}</p>

	<div class="flex items-center gap-2 mt-3">
		<span class="w-2 h-2 rounded-full flex-shrink-0" style="background: {statusColor};"></span>
		<span class="text-xs capitalize" style="color: {statusColor};">{agent.status}</span>
	</div>

	{#if agent.totalSpend30d}
		<p class="text-xs mt-2 tabular-nums" style="color: var(--palais-cyan);">
			${Number(agent.totalSpend30d).toFixed(2)} / 30j
		</p>
	{/if}
</a>
