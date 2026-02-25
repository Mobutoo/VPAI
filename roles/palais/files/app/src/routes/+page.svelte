<script lang="ts">
	import StandupCard from '$lib/components/dashboard/StandupCard.svelte';
	import InsightBanner from '$lib/components/dashboard/InsightBanner.svelte';
	import AgentCard from '$lib/components/agents/AgentCard.svelte';

	let { data } = $props();

	// ── Live clock ──
	let now = $state(new Date());
	$effect(() => {
		const tick = setInterval(() => { now = new Date(); }, 1000);
		return () => clearInterval(tick);
	});

	const timeString = $derived(
		now.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
	);

	const dateString = $derived(
		now.toLocaleDateString('fr-FR', { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' })
	);

	// ── Agent stats ──
	const totalAgents  = $derived(data.agents.length);
	const activeAgents = $derived(data.agents.filter((a: Record<string, unknown>) => a.status === 'idle' || a.status === 'busy').length);
	const busyAgents   = $derived(data.agents.filter((a: Record<string, unknown>) => a.status === 'busy').length);
	const errorAgents  = $derived(data.agents.filter((a: Record<string, unknown>) => a.status === 'error').length);

	// ── Insight lists ──
	const criticalInsights    = $derived((data.insights ?? []).filter((i: Record<string, unknown>) => i.severity === 'critical'));
	const nonCriticalInsights = $derived((data.insights ?? []).filter((i: Record<string, unknown>) => i.severity !== 'critical'));
</script>

<!-- ══════════════════════════════════════════════════════════
     SCANNING LINE — fixed, full-viewport, pointer-events-none
     ══════════════════════════════════════════════════════════ -->
<div class="fixed inset-0 pointer-events-none overflow-hidden z-0" aria-hidden="true">
	<div
		class="absolute w-full h-[2px] bg-gradient-to-r from-transparent via-[var(--palais-gold)] to-transparent"
		style="animation: scanLine 8s ease-in-out infinite; opacity: 0.06;"
	/>
</div>

<!-- ══════════════════════════════════════════════════════════
     MAIN DASHBOARD WRAPPER — hex grid filigrane
     ══════════════════════════════════════════════════════════ -->
<div class="hex-grid-bg space-y-7 relative">

	<!-- ── HEADER ROW ────────────────────────────────────────── -->
	<header
		class="flex items-start justify-between gap-4"
		style="animation: fadeSlideUp 0.5s ease-out both; animation-delay: 0ms;"
	>
		<!-- Left: wordmark + session status row -->
		<div class="flex flex-col gap-2">
			<h1
				class="tracking-[0.18em] font-black leading-none"
				style="
					color: var(--palais-gold);
					font-family: 'Orbitron', sans-serif;
					font-size: clamp(1.1rem, 3vw, 1.6rem);
					text-shadow: 0 0 24px rgba(212,168,67,0.45), 0 0 48px rgba(212,168,67,0.18);
				"
			>
				PALAIS
			</h1>
			<!-- Status summary bar -->
			<div
				class="flex items-center gap-2 flex-wrap"
				style="font-family: 'JetBrains Mono', monospace; font-size: 0.65rem;"
			>
				<span style="color: var(--palais-text-muted); letter-spacing: 0.06em;">SYS</span>
				<span style="color: rgba(212,168,67,0.35);">|</span>
				<span style="color: var(--palais-cyan);">{activeAgents}</span>
				<span style="color: var(--palais-text-muted);">ACTIVE</span>
				<span style="color: rgba(212,168,67,0.35);">|</span>
				<span style="color: var(--palais-gold);">{busyAgents}</span>
				<span style="color: var(--palais-text-muted);">BUSY</span>
				{#if errorAgents > 0}
					<span style="color: rgba(212,168,67,0.35);">|</span>
					<span style="color: var(--palais-red);">{errorAgents}</span>
					<span style="color: var(--palais-text-muted);">ERR</span>
				{/if}
				<span style="color: rgba(212,168,67,0.35);">|</span>
				<span style="color: var(--palais-text-muted);">{totalAgents} TOTAL</span>
			</div>
		</div>

		<!-- Right: live clock HUD element -->
		<div
			class="glass-panel flex flex-col items-end px-3 py-2 rounded-lg shrink-0"
			style="border-color: rgba(212,168,67,0.2);"
		>
			<span
				class="tabular-nums tracking-widest"
				style="
					color: var(--palais-gold);
					font-family: 'JetBrains Mono', monospace;
					font-size: 0.85rem;
					text-shadow: 0 0 12px rgba(212,168,67,0.5);
				"
			>{timeString}<span
					style="animation: blinkCursor 1s step-end infinite; color: var(--palais-gold); opacity: 0.7;"
				>_</span></span>
			<span
				class="uppercase tracking-[0.2em] mt-0.5"
				style="color: var(--palais-text-muted); font-family: 'Orbitron', sans-serif; font-size: 0.45rem;"
			>
				{dateString}
			</span>
		</div>
	</header>

	<!-- ── CRITICAL INSIGHT BANNERS ─────────────────────────── -->
	{#if criticalInsights.length > 0}
		<div
			class="space-y-2"
			style="animation: fadeSlideUp 0.5s ease-out both; animation-delay: 80ms;"
		>
			{#each criticalInsights as insight (insight.id)}
				<InsightBanner {insight} />
			{/each}
		</div>
	{/if}

	<!-- ── DIGITAL STANDUP ──────────────────────────────────── -->
	<section
		style="animation: fadeSlideUp 0.5s ease-out both; animation-delay: 160ms;"
	>
		<!-- HUD section header -->
		<h2
			class="flex items-center gap-2 mb-3"
			style="
				font-family: 'Orbitron', sans-serif;
				font-size: 0.6rem;
				letter-spacing: 0.25em;
				text-transform: uppercase;
				color: var(--palais-gold);
				opacity: 0.7;
			"
		>
			<span style="width: 8px; height: 1px; background: var(--palais-gold); opacity: 0.5; display: inline-block; flex-shrink: 0;"></span>
			BRIEFING DU JOUR
			<span style="flex: 1; height: 1px; background: linear-gradient(to right, rgba(212,168,67,0.3), transparent); display: inline-block;"></span>
		</h2>
		<StandupCard standup={data.standup} />
	</section>

	<!-- ── AGENTS ACTIFS ────────────────────────────────────── -->
	<section
		style="animation: fadeSlideUp 0.5s ease-out both; animation-delay: 240ms;"
	>
		<!-- HUD section header with count badge -->
		<div class="flex items-center gap-3 mb-4">
			<h2
				class="flex items-center gap-2"
				style="
					font-family: 'Orbitron', sans-serif;
					font-size: 0.6rem;
					letter-spacing: 0.25em;
					text-transform: uppercase;
					color: var(--palais-gold);
					opacity: 0.7;
				"
			>
				<span style="width: 8px; height: 1px; background: var(--palais-gold); opacity: 0.5; display: inline-block; flex-shrink: 0;"></span>
				AGENTS ACTIFS
				<span style="flex: 1; height: 1px; background: linear-gradient(to right, rgba(212,168,67,0.3), transparent); display: inline-block; min-width: 40px;"></span>
			</h2>
			<!-- Count badge -->
			<span
				class="tabular-nums px-2 py-0.5 rounded-full"
				style="
					font-family: 'Orbitron', sans-serif;
					font-size: 0.55rem;
					letter-spacing: 0.1em;
					color: var(--palais-gold);
					border: 1px solid rgba(212,168,67,0.35);
					background: rgba(212,168,67,0.06);
					text-shadow: 0 0 8px rgba(212,168,67,0.4);
					line-height: 1.6;
				"
			>{totalAgents}</span>
		</div>

		<div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
			{#each data.agents as agent, i (agent.id)}
				<AgentCard {agent} index={i} />
			{/each}
		</div>
	</section>

	<!-- ── INSIGHTS ─────────────────────────────────────────── -->
	{#if nonCriticalInsights.length > 0}
		<section
			style="animation: fadeSlideUp 0.5s ease-out both; animation-delay: 320ms;"
		>
			<h2
				class="flex items-center gap-2 mb-3"
				style="
					font-family: 'Orbitron', sans-serif;
					font-size: 0.6rem;
					letter-spacing: 0.25em;
					text-transform: uppercase;
					color: var(--palais-gold);
					opacity: 0.7;
				"
			>
				<span style="width: 8px; height: 1px; background: var(--palais-gold); opacity: 0.5; display: inline-block; flex-shrink: 0;"></span>
				INSIGHTS
				<span style="flex: 1; height: 1px; background: linear-gradient(to right, rgba(212,168,67,0.3), transparent); display: inline-block;"></span>
			</h2>
			<div class="space-y-2">
				{#each nonCriticalInsights as insight (insight.id)}
					<InsightBanner {insight} />
				{/each}
			</div>
		</section>
	{/if}

</div>
