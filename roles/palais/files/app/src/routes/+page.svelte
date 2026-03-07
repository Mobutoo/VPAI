<script lang="ts">
	import AgentCard from '$lib/components/agents/AgentCard.svelte';
	import StatCard from '$lib/components/dashboard/StatCard.svelte';
	import MiniServerCard from '$lib/components/dashboard/MiniServerCard.svelte';
	import DeploymentTimeline from '$lib/components/dashboard/DeploymentTimeline.svelte';
	import Aya from '$lib/components/icons/Aya.svelte';
	import Nkyinkyim from '$lib/components/icons/Nkyinkyim.svelte';

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

	// ── Waza service actions ──
	async function toggleWazaService(slug: string, currentStatus: string) {
		const action = currentStatus === 'running' ? 'stop' : 'start';
		await fetch(`/api/v2/waza/${slug}`, {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ action })
		});
	}

	// ── Server metrics helpers ──
	function cpuPercent(server: typeof data.servers[number]): number {
		return server.latestMetric?.cpuPercent ?? 0;
	}

	function ramPercent(server: typeof data.servers[number]): number {
		const m = server.latestMetric;
		if (!m || !m.ramTotalMb || !m.ramUsedMb) return 0;
		return (m.ramUsedMb / m.ramTotalMb) * 100;
	}
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
     MAIN DASHBOARD WRAPPER
     ══════════════════════════════════════════════════════════ -->
<div class="space-y-7 relative">

	<!-- ── HEADER ROW ────────────────────────────────────────── -->
	<header
		class="flex items-start justify-between gap-4"
		style="animation: fadeSlideUp 0.5s ease-out both; animation-delay: 0ms;"
	>
		<!-- Left: wordmark + mission control subtitle -->
		<div class="flex flex-col gap-2">
			<div class="flex flex-col gap-0.5">
				<h1
					class="tracking-[0.18em] font-black leading-none"
					style="
						color: var(--palais-gold);
						font-family: 'Orbitron', sans-serif;
						font-size: clamp(1.1rem, 3vw, 1.6rem);
						text-shadow: 0 0 24px rgba(212,168,67,0.45), 0 0 48px rgba(212,168,67,0.18);
					"
				>
					PALAIS <span style="font-size: 0.65em; opacity: 0.7; letter-spacing: 0.3em;">v2</span>
				</h1>
				<p
					class="tracking-[0.3em] uppercase"
					style="font-family: 'Orbitron', sans-serif; font-size: 0.5rem; color: var(--palais-text-muted); letter-spacing: 0.35em;"
				>
					Mission Control
				</p>
			</div>
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

	<!-- ── ROW 1: STAT CARDS ──────────────────────────────────── -->
	<section
		style="animation: fadeSlideUp 0.5s ease-out both; animation-delay: 60ms;"
	>
		<h2
			class="flex items-center gap-2 mb-4"
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
			OVERVIEW
			<span style="flex: 1; height: 1px; background: linear-gradient(to right, rgba(212,168,67,0.3), transparent); display: inline-block;"></span>
		</h2>

		<div class="grid grid-cols-2 md:grid-cols-4 gap-3">
			<StatCard
				value="{data.onlineCount}/{data.serverCount}"
				label="Servers Online"
				icon={Aya}
				color="var(--palais-cyan)"
			/>
			<StatCard
				value={data.containerCount}
				label="Containers"
				color="var(--palais-gold)"
			/>
			<StatCard
				value="0"
				label="Monthly Cost"
				color="var(--palais-green)"
			/>
			<StatCard
				value={data.activeDeploys}
				label="Active Deploys"
				icon={Nkyinkyim}
				color="var(--palais-gold)"
			/>
		</div>
	</section>

	<!-- ── ROW 2: SERVER HEALTH MINI-GRID ────────────────────── -->
	{#if data.servers.length > 0}
		<section
			style="animation: fadeSlideUp 0.5s ease-out both; animation-delay: 120ms;"
		>
			<h2
				class="flex items-center gap-2 mb-4"
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
				FLEET HEALTH
				<span style="flex: 1; height: 1px; background: linear-gradient(to right, rgba(212,168,67,0.3), transparent); display: inline-block;"></span>
			</h2>

			<div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
				{#each data.servers as server, i (server.id)}
					<MiniServerCard
						name={server.name}
						status={server.status}
						cpuPercent={cpuPercent(server)}
						ramPercent={ramPercent(server)}
						provider={server.provider}
					/>
				{/each}
			</div>
		</section>
	{/if}

	<!-- ── ROW 3: DEPLOYMENT TIMELINE ────────────────────────── -->
	<section
		style="animation: fadeSlideUp 0.5s ease-out both; animation-delay: 180ms;"
	>
		<h2
			class="flex items-center gap-2 mb-4"
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
			RECENT DEPLOYS
			<span style="flex: 1; height: 1px; background: linear-gradient(to right, rgba(212,168,67,0.3), transparent); display: inline-block;"></span>
		</h2>

		<DeploymentTimeline deployments={data.recentDeploys} />
	</section>

	<!-- ── ROW 4: WAZA QUICK-CONTROLS ────────────────────────── -->
	{#if data.wazaServices.length > 0}
		<section
			style="animation: fadeSlideUp 0.5s ease-out both; animation-delay: 240ms;"
		>
			<h2
				class="flex items-center gap-2 mb-4"
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
				WAZA SERVICES
				<span style="flex: 1; height: 1px; background: linear-gradient(to right, rgba(212,168,67,0.3), transparent); display: inline-block;"></span>
			</h2>

			<div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
				{#each data.wazaServices as svc, i (svc.id)}
					<div
						class="glass-panel rounded-lg p-3 flex flex-col gap-2"
						style="
							border: 1px solid rgba(212,168,67,0.1);
							animation: cardReveal 0.4s ease-out both;
							animation-delay: {i * 40}ms;
						"
					>
						<!-- Service name -->
						<span
							class="uppercase tracking-[0.15em] truncate"
							style="font-family: 'Orbitron', sans-serif; font-size: 0.5rem; color: var(--palais-text);"
						>{svc.name}</span>

						<!-- Status badge -->
						<span
							class="self-start px-1.5 py-0.5 rounded uppercase tracking-[0.1em]"
							style="
								font-family: 'JetBrains Mono', monospace;
								font-size: 0.4rem;
								color: {svc.status === 'running' ? 'var(--palais-green)' : svc.status === 'stopped' ? 'var(--palais-text-muted)' : 'var(--palais-gold)'};
								border: 1px solid {svc.status === 'running' ? 'rgba(76,175,80,0.3)' : svc.status === 'stopped' ? 'rgba(255,255,255,0.1)' : 'rgba(212,168,67,0.3)'};
								background: {svc.status === 'running' ? 'rgba(76,175,80,0.08)' : svc.status === 'stopped' ? 'rgba(255,255,255,0.03)' : 'rgba(212,168,67,0.08)'};
							"
						>{svc.status ?? 'unknown'}</span>

						<!-- Toggle button -->
						<button
							onclick={() => toggleWazaService(svc.slug, svc.status ?? 'stopped')}
							class="mt-auto rounded px-2 py-1 uppercase tracking-[0.15em] transition-opacity hover:opacity-80 active:opacity-60"
							style="
								font-family: 'Orbitron', sans-serif;
								font-size: 0.42rem;
								color: {svc.status === 'running' ? 'var(--palais-red)' : 'var(--palais-green)'};
								border: 1px solid {svc.status === 'running' ? 'rgba(229,57,53,0.3)' : 'rgba(76,175,80,0.3)'};
								background: {svc.status === 'running' ? 'rgba(229,57,53,0.06)' : 'rgba(76,175,80,0.06)'};
								cursor: pointer;
							"
						>
							{svc.status === 'running' ? 'Stop' : 'Start'}
						</button>
					</div>
				{/each}
			</div>
		</section>
	{/if}

	<!-- ── AGENTS ACTIFS ────────────────────────────────────────── -->
	<section
		style="animation: fadeSlideUp 0.5s ease-out both; animation-delay: 300ms;"
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

</div>
