<script lang="ts">
	let { data } = $props();

	// ── Live service state (polled) ────────────────────────────────
	type WazaService = typeof data.services[0];
	let services = $state<WazaService[]>(data.services);
	let togglingSlug = $state<string | null>(null);
	let toggleErrors = $state<Record<string, string>>({});

	// ── Auto-refresh every 30s ─────────────────────────────────────
	$effect(() => {
		const interval = setInterval(async () => {
			try {
				const res = await fetch('/api/v2/waza');
				if (res.ok) {
					const body = await res.json();
					if (body.data) {
						services = body.data;
					}
				}
			} catch {
				// silent — stale data remains
			}
		}, 30_000);

		return () => clearInterval(interval);
	});

	// ── Toggle service start/stop ──────────────────────────────────
	async function toggleService(slug: string, currentStatus: string | null) {
		const action = currentStatus === 'running' ? 'stop' : 'start';
		togglingSlug = slug;
		const { [slug]: _removed, ...rest } = toggleErrors;
		toggleErrors = rest;

		try {
			const res = await fetch(`/api/v2/waza/${slug}`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ action })
			});
			if (res.ok) {
				const body = await res.json();
				if (body.data) {
					services = services.map(s => s.slug === slug ? { ...s, ...body.data } : s);
				}
			} else {
				const body = await res.json().catch(() => ({ error: 'Unknown error' }));
				toggleErrors = { ...toggleErrors, [slug]: body.error ?? `HTTP ${res.status}` };
			}
		} catch {
			toggleErrors = { ...toggleErrors, [slug]: 'Network error' };
		} finally {
			togglingSlug = null;
		}
	}

	// ── Profile switch ─────────────────────────────────────────────
	let profileLoading = $state<string | null>(null);

	async function activateProfile(profileName: string, action: 'start' | 'stop') {
		profileLoading = profileName;
		try {
			const res = await fetch('/api/v2/waza/profiles', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ profile: profileName, action })
			});
			if (res.ok) {
				// Re-fetch fresh state
				const fresh = await fetch('/api/v2/waza');
				if (fresh.ok) {
					const body = await fresh.json();
					if (body.data) services = body.data;
				}
			}
		} catch {
			// silent
		} finally {
			profileLoading = null;
		}
	}

	// ── Helpers ────────────────────────────────────────────────────
	function fmtRam(mb: number | null): string {
		if (!mb) return '—';
		return mb >= 1024 ? `${(mb / 1024).toFixed(1)} GB` : `${mb} MB`;
	}

	function runningCount(): number {
		return services.filter(s => s.status === 'running').length;
	}

	function ramUsedEstimate(): number {
		return services
			.filter(s => s.status === 'running' && s.ramLimitMb)
			.reduce((acc, s) => acc + (s.ramLimitMb ?? 0), 0);
	}

	const totalRamLimit = $derived(
		services.reduce((acc, s) => acc + (s.ramLimitMb ?? 0), 0)
	);
</script>

<svelte:head><title>Palais — Waza</title></svelte:head>

<div style="min-height: 100vh; padding: 2rem 0;">

	<!-- HUD HEADER -->
	<header class="flex flex-col gap-3 mb-8">
		<div class="flex items-start justify-between gap-4 flex-wrap">
			<div>
				<p class="text-xs tracking-[0.3em] uppercase mb-1"
					style="color: var(--palais-gold); opacity: 0.6; font-family: 'Orbitron', sans-serif;">
					WORKSTATION PI — SERVICES
				</p>
				<h1 class="text-3xl font-bold tracking-widest"
					style="color: var(--palais-gold); font-family: 'Orbitron', sans-serif; text-shadow: 0 0 24px rgba(212,168,67,0.35);">
					WAZA
				</h1>
			</div>

			<div class="flex items-center gap-3">
				<span class="px-3 py-1 rounded-full text-xs font-semibold tracking-wider"
					style="background: rgba(76,175,80,0.13); color: var(--palais-green); border: 1px solid rgba(76,175,80,0.3); font-family: 'Orbitron', sans-serif;">
					{runningCount()} / {services.length} RUNNING
				</span>
				<span class="text-xs" style="color: rgba(212,168,67,0.4); font-family: 'JetBrains Mono', monospace;">
					AUTO-REFRESH 30s
				</span>
			</div>
		</div>

		<!-- Gold separator -->
		<div style="height: 1px; background: linear-gradient(90deg, var(--palais-gold) 0%, rgba(212,168,67,0.08) 100%); opacity: 0.4;"></div>
	</header>

	<!-- RAM usage bar (estimated from running services) -->
	{#if totalRamLimit > 0}
		{@const usedMb = ramUsedEstimate()}
		{@const pct = Math.min(100, Math.round((usedMb / totalRamLimit) * 100))}
		{@const barColor = pct > 90 ? 'var(--palais-red)' : pct > 70 ? 'var(--palais-gold)' : 'var(--palais-green)'}
		<div class="glass-panel rounded-xl px-5 py-4 mb-6"
			style="border: 1px solid rgba(212,168,67,0.15);">
			<div class="flex justify-between items-baseline mb-2">
				<span class="text-xs uppercase tracking-wider"
					style="color: rgba(212,168,67,0.55); font-family: 'Orbitron', sans-serif; font-size: 0.6rem; letter-spacing: 0.15em;">
					RAM — Active Services (estimated ceiling)
				</span>
				<span class="tabular-nums"
					style="color: var(--palais-cyan); font-family: 'JetBrains Mono', monospace; font-size: 0.8rem;">
					{fmtRam(usedMb)} / {fmtRam(totalRamLimit)} ({pct}%)
				</span>
			</div>
			<div class="h-1.5 rounded-full" style="background: rgba(255,255,255,0.05);">
				<div class="h-1.5 rounded-full transition-all duration-500"
					style="width: {pct}%; background: {barColor};"></div>
			</div>
		</div>
	{/if}

	<!-- Profile quick-switch row -->
	{#if data.profiles.length > 0}
		<div class="mb-6">
			<p class="text-xs font-semibold uppercase tracking-[0.25em] mb-3"
				style="color: rgba(212,168,67,0.5); font-family: 'Orbitron', sans-serif; font-size: 0.58rem;">
				Profile Quick-Switch
			</p>
			<div class="flex flex-wrap gap-2">
				{#each data.profiles as profile}
					{@const activeCount = services.filter(s => (s.profile ?? 'default') === profile.name && s.status === 'running').length}
					{@const isLoading = profileLoading === profile.name}
					<div class="flex items-center gap-1.5 glass-panel rounded-lg px-3 py-2"
						style="border: 1px solid rgba(212,168,67,0.15);">
						<span class="text-xs font-semibold tracking-wider"
							style="color: var(--palais-text); font-family: 'Orbitron', sans-serif; font-size: 0.62rem; letter-spacing: 0.1em; min-width: 60px;">
							{profile.name.toUpperCase()}
						</span>
						<span class="text-xs tabular-nums"
							style="color: {activeCount > 0 ? 'var(--palais-green)' : 'var(--palais-text-muted)'}; font-family: 'JetBrains Mono', monospace; font-size: 0.7rem; min-width: 28px;">
							{activeCount}/{profile.slugs.length}
						</span>
						<button
							onclick={() => activateProfile(profile.name, 'start')}
							disabled={isLoading}
							title="Start all {profile.name} services"
							style="
								padding: 2px 8px; border-radius: 4px; cursor: pointer;
								background: rgba(76,175,80,0.12); color: var(--palais-green);
								border: 1px solid rgba(76,175,80,0.3);
								font-family: 'Orbitron', sans-serif; font-size: 0.55rem; letter-spacing: 0.08em;
								{isLoading ? 'opacity: 0.5; cursor: not-allowed;' : ''}
							"
						>
							{isLoading ? '...' : 'START'}
						</button>
						<button
							onclick={() => activateProfile(profile.name, 'stop')}
							disabled={isLoading}
							title="Stop all {profile.name} services"
							style="
								padding: 2px 8px; border-radius: 4px; cursor: pointer;
								background: rgba(229,57,53,0.1); color: var(--palais-red);
								border: 1px solid rgba(229,57,53,0.25);
								font-family: 'Orbitron', sans-serif; font-size: 0.55rem; letter-spacing: 0.08em;
								{isLoading ? 'opacity: 0.5; cursor: not-allowed;' : ''}
							"
						>
							{isLoading ? '...' : 'STOP'}
						</button>
					</div>
				{/each}
			</div>
		</div>
	{/if}

	<!-- Service cards grid -->
	{#if services.length === 0}
		<div class="glass-panel hud-bracket rounded-xl p-12 text-center"
			style="border: 1px solid rgba(212,168,67,0.18);">
			<span class="hud-bracket-bottom" style="display: block;">
				<p class="text-sm" style="color: var(--palais-text-muted); font-family: 'JetBrains Mono', monospace;">
					<span style="color: rgba(212,168,67,0.4);">// </span>No Waza services configured.
				</p>
			</span>
		</div>
	{:else}
		<div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
			{#each services as svc, i (svc.id)}
				{@const isRunning = svc.status === 'running'}
				{@const isToggling = togglingSlug === svc.slug}
				{@const cardGlow = isRunning
					? '0 4px 24px 0 rgba(76,175,80,0.07), 0 1px 0 0 rgba(76,175,80,0.18)'
					: '0 4px 16px 0 rgba(0,0,0,0.2)'}

				<div
					class="glass-panel hud-bracket rounded-xl p-4"
					style="
						border: 1px solid {isRunning ? 'rgba(76,175,80,0.2)' : 'rgba(212,168,67,0.13)'};
						box-shadow: {cardGlow};
						animation: cardReveal 0.35s ease-out both;
						animation-delay: {i * 60}ms;
					"
				>
					<span class="hud-bracket-bottom" style="display: block;">

						<!-- Card header -->
						<div class="flex items-start justify-between gap-2 mb-3">
							<div class="flex-1 min-w-0">
								<h3 class="font-bold text-sm tracking-wider truncate"
									style="color: {isRunning ? 'var(--palais-green)' : 'var(--palais-text)'}; font-family: 'Orbitron', sans-serif; font-size: 0.78rem; letter-spacing: 0.1em;">
									{svc.name.toUpperCase()}
								</h3>
								{#if svc.profile}
									<span class="text-xs" style="color: rgba(212,168,67,0.4); font-family: 'JetBrains Mono', monospace; font-size: 0.68rem;">
										{svc.profile}
									</span>
								{/if}
							</div>

							<!-- Status badge -->
							<span class="px-2 py-0.5 rounded text-xs font-semibold flex-shrink-0"
								style="
									background: {isRunning ? 'rgba(76,175,80,0.12)' : 'rgba(138,138,154,0.1)'};
									color: {isRunning ? 'var(--palais-green)' : 'var(--palais-text-muted)'};
									border: 1px solid {isRunning ? 'rgba(76,175,80,0.3)' : 'rgba(138,138,154,0.2)'};
									font-family: 'Orbitron', sans-serif;
									font-size: 0.58rem;
									letter-spacing: 0.1em;
								">
								{(svc.status ?? 'stopped').toUpperCase()}
							</span>
						</div>

						<!-- Service URL -->
						{#if svc.url}
							<a
								href={svc.url}
								target="_blank"
								rel="noopener noreferrer"
								class="block mb-3 truncate"
								style="
									color: var(--palais-cyan); font-family: 'JetBrains Mono', monospace;
									font-size: 0.68rem; text-decoration: none; opacity: {isRunning ? 0.9 : 0.4};
									transition: opacity 0.2s;
								"
								title={svc.url}
							>
								<span style="color: rgba(212,168,67,0.4);">→ </span>{svc.url.replace('https://', '')}
							</a>
						{/if}

						<!-- Resource limits -->
						<div class="flex gap-3 mb-4">
							{#if svc.ramLimitMb}
								<div>
									<span class="text-xs uppercase tracking-wider block"
										style="color: rgba(212,168,67,0.45); font-family: 'Orbitron', sans-serif; font-size: 0.55rem; letter-spacing: 0.12em; margin-bottom: 2px;">RAM</span>
									<span class="tabular-nums text-xs"
										style="color: var(--palais-cyan); font-family: 'JetBrains Mono', monospace; font-size: 0.72rem;">
										{fmtRam(svc.ramLimitMb)}
									</span>
								</div>
							{/if}
							{#if svc.cpuLimit}
								<div>
									<span class="text-xs uppercase tracking-wider block"
										style="color: rgba(212,168,67,0.45); font-family: 'Orbitron', sans-serif; font-size: 0.55rem; letter-spacing: 0.12em; margin-bottom: 2px;">CPU</span>
									<span class="tabular-nums text-xs"
										style="color: var(--palais-cyan); font-family: 'JetBrains Mono', monospace; font-size: 0.72rem;">
										{svc.cpuLimit}x
									</span>
								</div>
							{/if}
							{#if !svc.ramLimitMb && !svc.cpuLimit}
								<span class="text-xs" style="color: rgba(212,168,67,0.3); font-family: 'JetBrains Mono', monospace; font-size: 0.68rem;">
									No limits set
								</span>
							{/if}
						</div>

						<!-- Toggle button -->
						{#if toggleErrors[svc.slug]}
							<p class="text-xs mb-2" style="color: var(--palais-red); font-family: 'JetBrains Mono', monospace; font-size: 0.68rem;">
								{toggleErrors[svc.slug]}
							</p>
						{/if}

						<button
							onclick={() => toggleService(svc.slug, svc.status)}
							disabled={isToggling || togglingSlug !== null}
							style="
								width: 100%; padding: 7px; border-radius: 6px; cursor: pointer;
								background: {isRunning ? 'rgba(229,57,53,0.1)' : 'rgba(76,175,80,0.12)'};
								color: {isRunning ? 'var(--palais-red)' : 'var(--palais-green)'};
								border: 1px solid {isRunning ? 'rgba(229,57,53,0.3)' : 'rgba(76,175,80,0.3)'};
								font-family: 'Orbitron', sans-serif; font-size: 0.62rem; letter-spacing: 0.12em;
								transition: all 0.2s;
								{(isToggling || togglingSlug !== null) ? 'opacity: 0.5; cursor: not-allowed;' : ''}
							"
						>
							{#if isToggling}
								{isRunning ? 'STOPPING...' : 'STARTING...'}
							{:else}
								{isRunning ? 'STOP' : 'START'}
							{/if}
						</button>

					</span>
				</div>
			{/each}
		</div>
	{/if}
</div>
