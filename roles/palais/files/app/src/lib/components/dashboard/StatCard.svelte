<script lang="ts">
	import type { Component } from 'svelte';

	let {
		value,
		label,
		icon: Icon,
		trend,
		color = 'var(--palais-gold)'
	}: {
		value: string | number;
		label: string;
		icon?: Component<{ size: number }>;
		trend?: { value: number; direction: 'up' | 'down' | 'flat' };
		color?: string;
	} = $props();

	const trendColor = $derived(
		trend?.direction === 'up'
			? 'var(--palais-green)'
			: trend?.direction === 'down'
				? 'var(--palais-red)'
				: 'var(--palais-text-muted)'
	);

	const trendPrefix = $derived(
		trend?.direction === 'up' ? '+' : trend?.direction === 'down' ? '-' : ''
	);
</script>

<div
	class="glass-panel rounded-lg p-4 flex flex-col gap-2"
	style="border: 1px solid rgba(212,168,67,0.12); animation: cardReveal 0.4s ease-out both;"
>
	<div class="flex items-center justify-between">
		{#if Icon}
			<span style="color: {color}; opacity: 0.5;">
				<Icon size={18} />
			</span>
		{:else}
			<span></span>
		{/if}
		{#if trend}
			<span
				style="font-family: 'JetBrains Mono', monospace; font-size: 0.6rem; color: {trendColor};"
			>
				{trendPrefix}{trend.value}%
			</span>
		{/if}
	</div>
	<div>
		<span
			class="tabular-nums"
			style="font-family: 'Orbitron', sans-serif; font-size: 1.4rem; font-weight: 700; color: {color}; text-shadow: 0 0 16px {color}40;"
		>{value}</span>
	</div>
	<span
		class="uppercase tracking-[0.2em]"
		style="font-family: 'Orbitron', sans-serif; font-size: 0.45rem; color: var(--palais-text-muted);"
	>{label}</span>
</div>
