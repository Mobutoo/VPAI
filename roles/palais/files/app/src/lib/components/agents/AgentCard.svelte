<script lang="ts">
	let { agent }: { agent: Record<string, unknown> } = $props();

	const statusColor = $derived(
		agent.status === 'idle'    ? 'var(--palais-green)'
		: agent.status === 'busy'  ? 'var(--palais-gold)'
		: agent.status === 'error' ? 'var(--palais-red)'
		:                            'var(--palais-text-muted)'
	);

	const isBusy = $derived(agent.status === 'busy');
	const initials = $derived(
		String(agent.name ?? '')
			.split(' ')
			.map((w: string) => w[0] ?? '')
			.join('')
			.slice(0, 2)
			.toUpperCase()
	);
</script>

<!-- eslint-disable-next-line svelte/no-navigation-without-resolve -->
<a
	href="/agents/{agent.id}"
	class="flex flex-col rounded-xl overflow-hidden transition-all hover:scale-[1.02] hover:shadow-lg"
	style="
		background: var(--palais-surface);
		border: 1px solid {isBusy ? 'var(--palais-gold)' : 'var(--palais-border)'};
		box-shadow: {isBusy ? 'var(--palais-glow-sm)' : 'none'};
		text-decoration: none;
	"
>
	<!-- Photo area (2:3 aspect ratio) with SVG ring overlay -->
	<div class="relative w-full" style="aspect-ratio: 2 / 3; overflow: hidden;">
		<!-- Background / photo -->
		{#if agent.avatar_url}
			<img
				src={String(agent.avatar_url)}
				alt={String(agent.name)}
				class="absolute inset-0 w-full h-full object-cover"
			/>
		{:else}
			<div
				class="absolute inset-0 flex items-center justify-center"
				style="background: linear-gradient(160deg, color-mix(in srgb, {statusColor} 18%, var(--palais-bg)), var(--palais-surface));"
			>
				<span
					class="font-bold"
					style="color: {statusColor}; font-family: 'Orbitron', sans-serif; opacity: 0.7; font-size: clamp(1rem, 4vw, 2rem);"
				>{initials}</span>
			</div>
		{/if}

		<!-- SVG ring — rectangular frame tracing the photo border -->
		<svg
			class="absolute inset-0 w-full h-full pointer-events-none"
			viewBox="0 0 100 150"
			preserveAspectRatio="none"
			xmlns="http://www.w3.org/2000/svg"
		>
			<!-- Base track (always visible, faint) -->
			<rect
				x="2" y="2" width="96" height="146" rx="5"
				fill="none"
				stroke={statusColor}
				stroke-width="2"
				opacity="0.2"
			/>
			<!-- Animated dash ring (bright when busy, solid faint when idle) -->
			<rect
				x="2" y="2" width="96" height="146" rx="5"
				fill="none"
				stroke={statusColor}
				stroke-width="2.5"
				stroke-linecap="round"
				stroke-dasharray={isBusy ? '22 12' : '488 0'}
				stroke-dashoffset="0"
				opacity={isBusy ? '0.9' : '0.35'}
				style={isBusy ? 'animation: ringTrace 2s linear infinite;' : ''}
			/>
		</svg>
	</div>

	<!-- Info section -->
	<div class="p-2.5 flex flex-col gap-1 flex-1">
		<h3 class="text-xs font-semibold truncate" style="color: var(--palais-text);">{agent.name}</h3>
		{#if agent.bio}
			<p
				class="line-clamp-2"
				style="color: var(--palais-text-muted); font-size: 0.6rem; line-height: 1.4;"
			>{agent.bio}</p>
		{:else if agent.persona}
			<p
				class="truncate"
				style="color: var(--palais-text-muted); font-size: 0.6rem;"
			>{agent.persona}</p>
		{/if}
		<div class="flex items-center gap-1.5 mt-auto pt-1">
			<span class="w-1.5 h-1.5 rounded-full flex-shrink-0" style="background: {statusColor};"></span>
			<span class="capitalize" style="color: {statusColor}; font-size: 0.6rem;">{agent.status}</span>
		</div>
	</div>
</a>

<style>
	@keyframes ringTrace {
		from { stroke-dashoffset: 0; }
		to   { stroke-dashoffset: -488; }
	}
</style>
