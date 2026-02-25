<script lang="ts">
	import {
		GyeNyame,
		Dwennimmen,
		Nkyinkyim,
		Sankofa,
		Aya,
		Akoma,
		Fawohodie,
		AnanseNtontan,
		Nyame,
		Bese
	} from '$lib/components/icons';

	let {
		agent,
		index = 0
	}: {
		agent: Record<string, unknown>;
		index?: number;
	} = $props();

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

	// Adinkra watermark: rotate through 10 symbols based on card index
	// Each symbol carries meaning — agents get a symbolic "spirit assignment"
	const adinkraIcons = [GyeNyame, Dwennimmen, Nkyinkyim, Sankofa, Aya, Akoma, Fawohodie, AnanseNtontan, Nyame, Bese];
	const AdinkraIcon = $derived(adinkraIcons[index % adinkraIcons.length]);

	// Status label display
	const statusLabel = $derived(String(agent.status ?? 'unknown'));

	// Card entrance animation delay
	const entranceDelay = $derived(`${index * 60}ms`);
</script>

<!-- eslint-disable-next-line svelte/no-navigation-without-resolve -->
<a
	href="/agents/{agent.id}"
	class="hud-bracket agent-card flex flex-col rounded-xl overflow-hidden transition-all duration-300 hover:-translate-y-0.5 hover:border-[rgba(212,168,67,0.35)]"
	style="
		background: var(--palais-surface);
		border: 1px solid {isBusy ? 'rgba(212,168,67,0.5)' : 'var(--palais-border)'};
		box-shadow: {isBusy ? 'var(--palais-glow-md), 0 0 32px rgba(212,168,67,0.12)' : '0 4px 24px rgba(0,0,0,0.4)'};
		text-decoration: none;
		animation: cardReveal 0.4s ease-out both;
		animation-delay: {entranceDelay};
	"
>
	<!-- hud-bracket-bottom needs position:absolute with inset:0 here to span the full card area.
	     The class defines position:relative for standalone use, but we override to absolute
	     so its ::before/::after bottom brackets position relative to the <a> card wrapper. -->
	<span class="hud-bracket-bottom" aria-hidden="true" style="position: absolute; inset: 0; pointer-events: none; z-index: 20;" />

	<!-- Portrait area (2:3 aspect ratio) — full stack, no separate info panel below -->
	<div class="relative w-full" style="aspect-ratio: 2 / 3; overflow: hidden; flex: 1;">

		<!-- ── AVATAR BACKGROUND ── -->
		{#if agent.avatar_url}
			<!-- Photo treatment: slight desaturation + contrast pop, warm vignette -->
			<img
				src={String(agent.avatar_url)}
				alt={String(agent.name)}
				class="absolute inset-0 w-full h-full object-cover"
				style="filter: contrast(1.05) saturate(0.88);"
			/>
			<!-- Vignette overlay for photo mood -->
			<div
				class="absolute inset-0"
				style="background: radial-gradient(ellipse at 50% 40%, transparent 40%, rgba(0,0,0,0.55) 100%);"
			/>
		{:else}
			<!-- Kuba textile base pattern -->
			<div class="absolute inset-0 kuba-pattern-bg" />

			<!-- Radial gold atmospheric glow from center -->
			<div
				class="absolute inset-0"
				style="background: radial-gradient(circle at 50% 42%, rgba(212,168,67,0.14) 0%, rgba(212,168,67,0.04) 45%, transparent 70%);"
			/>

			<!-- Adinkra watermark — large, centered, very faint gold -->
			<div
				class="absolute inset-0 flex items-center justify-center"
				aria-hidden="true"
				style="opacity: 0.07; color: var(--palais-gold);"
			>
				<AdinkraIcon size={80} />
			</div>

			<!-- Gold initials — the agent identifier glyph -->
			<div class="absolute inset-0 flex items-center justify-center">
				<span
					class="relative z-10 font-bold tracking-widest select-none"
					style="
						color: var(--palais-gold);
						font-family: 'Orbitron', sans-serif;
						font-size: clamp(1.25rem, 5vw, 2.25rem);
						text-shadow:
							0 0 16px rgba(212,168,67,0.9),
							0 0 32px rgba(212,168,67,0.55),
							0 0 60px rgba(212,168,67,0.25);
					"
				>{initials}</span>
			</div>
		{/if}

		<!-- ── SVG RING FRAME ── -->
		<svg
			class="absolute inset-0 w-full h-full pointer-events-none"
			viewBox="0 0 100 150"
			preserveAspectRatio="none"
			xmlns="http://www.w3.org/2000/svg"
		>
			<!-- Ambient glow ring — permanent, wide, very soft -->
			<rect
				x="1" y="1" width="98" height="148" rx="6"
				fill="none"
				stroke={statusColor}
				stroke-width="4"
				opacity="0.06"
			/>
			<!-- Base track — always visible, faint -->
			<rect
				x="2" y="2" width="96" height="146" rx="5"
				fill="none"
				stroke={statusColor}
				stroke-width="1.5"
				opacity="0.18"
			/>
			<!-- Animated dash ring — bright when busy, solid faint when idle -->
			<rect
				x="2" y="2" width="96" height="146" rx="5"
				fill="none"
				stroke={statusColor}
				stroke-width="2.5"
				stroke-linecap="round"
				stroke-dasharray={isBusy ? '22 12' : '488 0'}
				stroke-dashoffset="0"
				opacity={isBusy ? '0.9' : '0.32'}
				style={isBusy
					? `animation: ringTrace 2s linear infinite; filter: drop-shadow(0 0 4px ${statusColor});`
					: ''}
			/>
		</svg>

		<!-- ── LIQUID GLASS INFO PANEL (absolute, bottom of portrait) ── -->
		<div
			class="glass-panel absolute bottom-0 left-0 right-0 px-3 py-2.5"
			style="border: none; border-top: 1px solid rgba(212,168,67,0.15); border-radius: 0;"
		>
			<!-- Agent name — mission dossier style -->
			<h3
				class="truncate text-xs font-bold tracking-widest uppercase mb-1"
				style="
					color: var(--palais-text);
					font-family: 'Orbitron', sans-serif;
					font-size: 0.6rem;
					letter-spacing: 0.12em;
				"
			>{agent.name}</h3>

			{#if agent.bio}
				<p
					class="line-clamp-1 mb-1.5"
					style="color: var(--palais-text-muted); font-size: 0.55rem; line-height: 1.35;"
				>{agent.bio}</p>
			{:else if agent.persona}
				<p
					class="truncate mb-1.5"
					style="color: var(--palais-text-muted); font-size: 0.55rem;"
				>{agent.persona}</p>
			{/if}

			<!-- Status line -->
			<div class="flex items-center gap-1.5">
				<!-- Pulsing status dot -->
				<span
					class="w-1.5 h-1.5 rounded-full flex-shrink-0"
					style="background: {statusColor}; box-shadow: 0 0 6px {statusColor}; {isBusy ? 'animation: pulseGold 1.4s ease-in-out infinite;' : ''}"
				/>
				<span
					class="capitalize font-semibold tracking-wider"
					style="
						color: {statusColor};
						font-size: 0.55rem;
						font-family: 'Orbitron', sans-serif;
						text-shadow: 0 0 8px {statusColor};
						letter-spacing: 0.1em;
					"
				>{statusLabel}</span>
			</div>
		</div>

	</div>
</a>

<style>
	@keyframes ringTrace {
		from { stroke-dashoffset: 0; }
		to   { stroke-dashoffset: -488; }
	}

	/* Smooth hover gold border intensification */
	.agent-card:hover {
		box-shadow:
			0 8px 32px rgba(0, 0, 0, 0.5),
			0 0 0 1px rgba(212, 168, 67, 0.2),
			0 0 24px rgba(212, 168, 67, 0.1);
	}
</style>
