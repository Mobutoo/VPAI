<script lang="ts">
	let { data } = $props();

	type DeployStatus = 'all' | 'running' | 'success' | 'failed' | 'pending';

	// ── Filter state ───────────────────────────────────────────────
	let activeFilter = $state<DeployStatus>('all');

	const filters: { label: string; value: DeployStatus }[] = [
		{ label: 'ALL',     value: 'all' },
		{ label: 'RUNNING', value: 'running' },
		{ label: 'SUCCESS', value: 'success' },
		{ label: 'FAILED',  value: 'failed' },
		{ label: 'PENDING', value: 'pending' },
	];

	const filtered = $derived(
		activeFilter === 'all'
			? data.deployments
			: data.deployments.filter((d) => d.status === activeFilter)
	);

	// ── Counts per filter ──────────────────────────────────────────
	const counts = $derived({
		all:     data.deployments.length,
		running: data.deployments.filter((d) => d.status === 'running').length,
		success: data.deployments.filter((d) => d.status === 'success').length,
		failed:  data.deployments.filter((d) => d.status === 'failed').length,
		pending: data.deployments.filter((d) => d.status === 'pending').length,
	});

	// ── Status helpers ─────────────────────────────────────────────
	function statusColor(status: string): string {
		switch (status) {
			case 'success':    return 'var(--palais-green)';
			case 'failed':     return 'var(--palais-red)';
			case 'running':    return 'var(--palais-gold)';
			case 'rolled_back': return 'var(--palais-amber)';
			case 'cancelled':  return 'var(--palais-text-muted)';
			default:           return 'var(--palais-text-muted)';
		}
	}

	function statusBg(status: string): string {
		switch (status) {
			case 'success':    return 'rgba(76,175,80,0.12)';
			case 'failed':     return 'rgba(229,57,53,0.12)';
			case 'running':    return 'rgba(212,168,67,0.12)';
			case 'rolled_back': return 'rgba(232,131,58,0.12)';
			default:           return 'rgba(138,138,154,0.08)';
		}
	}

	function statusBorder(status: string): string {
		switch (status) {
			case 'success':    return 'rgba(76,175,80,0.3)';
			case 'failed':     return 'rgba(229,57,53,0.3)';
			case 'running':    return 'rgba(212,168,67,0.35)';
			case 'rolled_back': return 'rgba(232,131,58,0.3)';
			default:           return 'rgba(138,138,154,0.18)';
		}
	}

	function formatDuration(ms: number | null): string {
		if (!ms) return '—';
		if (ms < 1000) return `${ms}ms`;
		if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
		const mins = Math.floor(ms / 60000);
		const secs = Math.floor((ms % 60000) / 1000);
		return `${mins}m ${secs}s`;
	}

	function relativeTime(date: Date | null | string): string {
		if (!date) return '—';
		const d = new Date(date);
		const diff = Date.now() - d.getTime();
		const mins = Math.floor(diff / 60000);
		if (mins < 1) return 'just now';
		if (mins < 60) return `${mins}m ago`;
		const hrs = Math.floor(mins / 60);
		if (hrs < 24) return `${hrs}h ago`;
		const days = Math.floor(hrs / 24);
		return `${days}d ago`;
	}

	function filterColor(value: DeployStatus): string {
		switch (value) {
			case 'running': return 'rgba(212,168,67,0.7)';
			case 'success': return 'rgba(76,175,80,0.7)';
			case 'failed':  return 'rgba(229,57,53,0.7)';
			case 'pending': return 'rgba(138,138,154,0.6)';
			default:        return 'rgba(212,168,67,0.5)';
		}
	}
</script>

<svelte:head><title>Palais — Deploy Pipeline</title></svelte:head>

<div class="space-y-8" style="animation: fadeSlideUp 0.45s ease-out both;">

	<!-- ── HUD HEADER ─────────────────────────────────────────────── -->
	<header class="flex flex-col gap-3">
		<div class="flex items-start justify-between gap-4 flex-wrap">
			<div>
				<p
					class="uppercase tracking-[0.35em] mb-1"
					style="color: var(--palais-gold); opacity: 0.5; font-family: 'Orbitron', sans-serif; font-size: 0.5rem;"
				>
					PIPELINE — CI/CD CONTROL
				</p>
				<h1
					class="font-bold tracking-widest"
					style="
						color: var(--palais-gold);
						font-family: 'Orbitron', sans-serif;
						font-size: clamp(1.3rem, 3vw, 1.8rem);
						text-shadow: 0 0 24px rgba(212,168,67,0.35);
					"
				>
					DEPLOY PIPELINE
				</h1>
			</div>

			<!-- Running indicator -->
			{#if counts.running > 0}
				<span
					class="flex items-center gap-2 px-3 py-1.5 rounded-lg"
					style="
						background: rgba(212,168,67,0.1);
						border: 1px solid rgba(212,168,67,0.3);
						animation: pulseGold 1.5s ease-in-out infinite;
					"
				>
					<span class="w-2 h-2 rounded-full" style="background: var(--palais-gold);"></span>
					<span style="color: var(--palais-gold); font-family: 'Orbitron', sans-serif; font-size: 0.6rem; letter-spacing: 0.12em;">
						{counts.running} RUNNING
					</span>
				</span>
			{/if}
		</div>

		<!-- Gold separator -->
		<div style="height: 1px; background: linear-gradient(90deg, var(--palais-gold) 0%, rgba(212,168,67,0.08) 100%); opacity: 0.4;"></div>
	</header>

	<!-- ── FILTER TABS ─────────────────────────────────────────────── -->
	<div class="flex items-center gap-1 flex-wrap">
		{#each filters as filter}
			{@const count = counts[filter.value]}
			{@const isActive = activeFilter === filter.value}
			<button
				onclick={() => { activeFilter = filter.value; }}
				style="
					padding: 5px 12px; border-radius: 6px; cursor: pointer;
					background: {isActive ? 'rgba(212,168,67,0.12)' : 'transparent'};
					color: {isActive ? filterColor(filter.value) : 'rgba(138,138,154,0.5)'};
					border: 1px solid {isActive ? `${filterColor(filter.value).replace('0.7', '0.4').replace('0.5', '0.35')}` : 'rgba(138,138,154,0.12)'};
					font-family: 'Orbitron', sans-serif; font-size: 0.55rem; letter-spacing: 0.15em;
					transition: all 0.18s;
					display: flex; align-items: center; gap: 6px;
				"
				onmouseenter={(e) => {
					if (!isActive) {
						const el = e.currentTarget as HTMLElement;
						el.style.color = filterColor(filter.value);
						el.style.borderColor = filterColor(filter.value).replace('0.7', '0.25').replace('0.5', '0.2');
						el.style.background = 'rgba(212,168,67,0.04)';
					}
				}}
				onmouseleave={(e) => {
					if (!isActive) {
						const el = e.currentTarget as HTMLElement;
						el.style.color = 'rgba(138,138,154,0.5)';
						el.style.borderColor = 'rgba(138,138,154,0.12)';
						el.style.background = 'transparent';
					}
				}}
			>
				{filter.label}
				{#if count > 0}
					<span
						class="rounded-full px-1.5 py-0.5"
						style="
							font-family: 'JetBrains Mono', monospace;
							font-size: 0.5rem;
							background: {isActive ? 'rgba(212,168,67,0.15)' : 'rgba(138,138,154,0.08)'};
							color: {isActive ? filterColor(filter.value) : 'rgba(138,138,154,0.5)'};
						"
					>
						{count}
					</span>
				{/if}
			</button>
		{/each}
	</div>

	<!-- ── DEPLOYMENT LIST ─────────────────────────────────────────── -->
	<section>
		<h2
			class="flex items-center gap-2 mb-4"
			style="font-family: 'Orbitron', sans-serif; font-size: 0.6rem; letter-spacing: 0.25em; text-transform: uppercase; color: var(--palais-gold); opacity: 0.7;"
		>
			<span style="width: 8px; height: 1px; background: var(--palais-gold); opacity: 0.5; display: inline-block; flex-shrink: 0;"></span>
			{activeFilter === 'all' ? 'RECENT DEPLOYMENTS' : `${activeFilter.toUpperCase()} DEPLOYMENTS`}
			<span
				class="px-2 py-0.5 rounded-full"
				style="font-family: 'Orbitron', sans-serif; font-size: 0.5rem; color: var(--palais-gold); border: 1px solid rgba(212,168,67,0.3); background: rgba(212,168,67,0.06);"
			>
				{filtered.length}
			</span>
			<span style="flex: 1; height: 1px; background: linear-gradient(to right, rgba(212,168,67,0.3), transparent); display: inline-block;"></span>
		</h2>

		{#if filtered.length === 0}
			<div class="glass-panel rounded-xl p-14 text-center" style="border: 1px solid rgba(212,168,67,0.1);">
				<p style="color: var(--palais-text-muted); font-family: 'JetBrains Mono', monospace; font-size: 0.82rem;">
					<span style="color: rgba(212,168,67,0.4);">// </span>No {activeFilter === 'all' ? '' : activeFilter + ' '}deployments found.
				</p>
			</div>
		{:else}
			<div class="glass-panel rounded-xl overflow-hidden" style="border: 1px solid rgba(212,168,67,0.15);">
				<!-- Table header -->
				<div
					class="grid gap-4 px-5 py-3"
					style="
						grid-template-columns: 60px 1fr 120px 80px 120px 80px;
						background: rgba(212,168,67,0.04);
						border-bottom: 1px solid rgba(212,168,67,0.12);
					"
				>
					{#each ['ID', 'WORKSPACE / VERSION', 'STATUS', 'TYPE', 'STARTED', 'DURATION'] as col}
						<span style="color: rgba(212,168,67,0.5); font-family: 'Orbitron', sans-serif; font-size: 0.52rem; letter-spacing: 0.2em; text-transform: uppercase;">
							{col}
						</span>
					{/each}
				</div>

				<!-- Rows -->
				{#each filtered as dep, i (dep.id)}
					<a
						href="/deploy/{dep.id}"
						style="
							display: grid;
							grid-template-columns: 60px 1fr 120px 80px 120px 80px;
							gap: 1rem;
							padding: 0.875rem 1.25rem;
							align-items: center;
							text-decoration: none;
							border-bottom: {i < filtered.length - 1 ? '1px solid rgba(212,168,67,0.07)' : 'none'};
							transition: background 0.15s;
							animation: fadeSlideUp 0.3s ease-out both;
							animation-delay: {i * 25}ms;
						"
						onmouseenter={(e) => { (e.currentTarget as HTMLElement).style.background = 'rgba(212,168,67,0.04)'; }}
						onmouseleave={(e) => { (e.currentTarget as HTMLElement).style.background = ''; }}
					>
						<!-- ID -->
						<span style="color: rgba(212,168,67,0.4); font-family: 'JetBrains Mono', monospace; font-size: 0.72rem;">
							#{dep.id}
						</span>

						<!-- Workspace + version -->
						<div class="flex flex-col gap-0.5 min-w-0">
							<span style="color: var(--palais-text); font-family: 'Orbitron', sans-serif; font-size: 0.7rem; letter-spacing: 0.06em; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
								{dep.workspaceName ?? dep.workspaceSlug ?? `ws#${dep.workspaceId}`}
							</span>
							{#if dep.version}
								<span style="color: var(--palais-gold); font-family: 'JetBrains Mono', monospace; font-size: 0.65rem; opacity: 0.8;">
									{dep.version}
								</span>
							{/if}
						</div>

						<!-- Status badge -->
						<span
							class="flex items-center gap-1.5 px-2 py-0.5 rounded w-fit"
							style="
								background: {statusBg(dep.status)};
								border: 1px solid {statusBorder(dep.status)};
							"
						>
							<span
								class="w-1.5 h-1.5 rounded-full flex-shrink-0"
								style="
									background: {statusColor(dep.status)};
									{dep.status === 'running' ? 'animation: pulseGold 1.2s ease-in-out infinite;' : ''}
								"
							></span>
							<span style="color: {statusColor(dep.status)}; font-family: 'Orbitron', sans-serif; font-size: 0.5rem; letter-spacing: 0.08em; white-space: nowrap;">
								{dep.status.toUpperCase().replace('_', ' ')}
							</span>
						</span>

						<!-- Deploy type -->
						<span
							style="
								color: {dep.deployType === 'rollback' ? 'var(--palais-amber)' : 'rgba(138,138,154,0.55)'};
								font-family: 'JetBrains Mono', monospace; font-size: 0.65rem;
								text-transform: uppercase;
							"
						>
							{dep.deployType}
						</span>

						<!-- Started at (relative) -->
						<span style="color: var(--palais-text-muted); font-family: 'JetBrains Mono', monospace; font-size: 0.68rem;">
							{relativeTime(dep.startedAt)}
						</span>

						<!-- Duration -->
						<span style="color: var(--palais-cyan); font-family: 'JetBrains Mono', monospace; font-size: 0.72rem;">
							{formatDuration(dep.durationMs)}
						</span>
					</a>
				{/each}
			</div>
		{/if}
	</section>
</div>
