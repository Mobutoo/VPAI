<script lang="ts">
	let {
		name,
		status,
		cpuPercent,
		ramPercent,
		provider
	}: {
		name: string;
		status: string;
		cpuPercent: number;
		ramPercent: number;
		provider: string;
	} = $props();

	const statusColor = $derived(
		status === 'online'
			? 'var(--palais-green)'
			: status === 'offline'
				? 'var(--palais-red)'
				: status === 'busy'
					? 'var(--palais-gold)'
					: '#F59E0B'
	);

	const cpuClamped = $derived(Math.min(100, Math.max(0, cpuPercent)));
	const ramClamped = $derived(Math.min(100, Math.max(0, ramPercent)));
</script>

<div
	class="glass-panel rounded-lg p-3 flex flex-col gap-2"
	style="border: 1px solid rgba(212,168,67,0.1); animation: cardReveal 0.4s ease-out both;"
>
	<!-- Name + status dot row -->
	<div class="flex items-center justify-between gap-2">
		<span
			class="truncate uppercase tracking-[0.15em]"
			style="font-family: 'Orbitron', sans-serif; font-size: 0.5rem; color: var(--palais-text);"
		>{name}</span>
		<span
			class="shrink-0 rounded-full"
			style="
				width: 6px;
				height: 6px;
				background: {statusColor};
				box-shadow: 0 0 6px {statusColor};
				display: inline-block;
			"
			title={status}
		></span>
	</div>

	<!-- CPU bar -->
	<div class="flex flex-col gap-0.5">
		<div class="flex justify-between items-center">
			<span style="font-family: 'Orbitron', sans-serif; font-size: 0.38rem; color: var(--palais-text-muted); letter-spacing: 0.15em;">CPU</span>
			<span style="font-family: 'JetBrains Mono', monospace; font-size: 0.38rem; color: var(--palais-cyan);">{cpuClamped.toFixed(0)}%</span>
		</div>
		<div
			class="rounded-full overflow-hidden"
			style="height: 3px; background: rgba(79,195,247,0.12);"
		>
			<div
				class="h-full rounded-full"
				style="
					width: {cpuClamped}%;
					background: var(--palais-cyan);
					box-shadow: 0 0 4px var(--palais-cyan);
					transition: width 0.6s ease-out;
				"
			></div>
		</div>
	</div>

	<!-- RAM bar -->
	<div class="flex flex-col gap-0.5">
		<div class="flex justify-between items-center">
			<span style="font-family: 'Orbitron', sans-serif; font-size: 0.38rem; color: var(--palais-text-muted); letter-spacing: 0.15em;">RAM</span>
			<span style="font-family: 'JetBrains Mono', monospace; font-size: 0.38rem; color: var(--palais-gold);">{ramClamped.toFixed(0)}%</span>
		</div>
		<div
			class="rounded-full overflow-hidden"
			style="height: 3px; background: rgba(212,168,67,0.12);"
		>
			<div
				class="h-full rounded-full"
				style="
					width: {ramClamped}%;
					background: var(--palais-gold);
					box-shadow: 0 0 4px var(--palais-gold);
					transition: width 0.6s ease-out;
				"
			></div>
		</div>
	</div>

	<!-- Provider badge -->
	<span
		class="self-start uppercase tracking-[0.12em] px-1.5 py-0.5 rounded"
		style="
			font-family: 'JetBrains Mono', monospace;
			font-size: 0.36rem;
			color: var(--palais-text-muted);
			border: 1px solid rgba(212,168,67,0.1);
			background: rgba(212,168,67,0.04);
		"
	>{provider}</span>
</div>
