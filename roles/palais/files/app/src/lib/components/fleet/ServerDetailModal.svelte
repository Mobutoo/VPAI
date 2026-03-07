<script lang="ts">
	type ServerMetric = {
		cpuPercent: number | null;
		ramUsedMb: number | null;
		ramTotalMb: number | null;
		diskUsedGb: number | null;
		diskTotalGb: number | null;
		containerCount?: number | null;
		loadAvg1m?: number | null;
		recordedAt?: Date;
	} | null;

	type Server = {
		id: number;
		name: string;
		slug: string;
		provider: string;
		serverRole: string;
		location: string | null;
		publicIp: string | null;
		tailscaleIp: string | null;
		status: string;
		cpuCores: number | null;
		ramMb: number | null;
		diskGb: number | null;
		sshPort: number | null;
		sshUser: string | null;
		os: string | null;
		latestMetric: ServerMetric;
	};

	type Container = {
		id: string;
		name: string;
		image: string;
		status: string;
		state: string;
		cpuPercent?: number;
		memoryUsage?: number;
		memoryLimit?: number;
	};

	let {
		server,
		open,
		onclose
	}: {
		server: Server | null;
		open: boolean;
		onclose: () => void;
	} = $props();

	let containers = $state<Container[]>([]);
	let containersLoading = $state(false);
	let containersError = $state('');
	let syncingMetrics = $state(false);
	let syncMessage = $state('');

	const statusColor = $derived(
		server?.status === 'online' ? 'var(--palais-green)' :
		server?.status === 'busy'   ? 'var(--palais-gold)' :
		server?.status === 'degraded' ? '#E8833A' : 'var(--palais-red)'
	);

	// Fetch containers when panel opens
	$effect(() => {
		if (!open || !server) {
			containers = [];
			containersError = '';
			return;
		}
		containersLoading = true;
		containersError = '';
		fetch(`/api/v2/fleet/${server.id}/containers`)
			.then(async (res) => {
				if (!res.ok) throw new Error(`HTTP ${res.status}`);
				const body = await res.json();
				containers = body.data ?? body ?? [];
			})
			.catch((e: unknown) => {
				containersError = e instanceof Error ? e.message : 'Failed to load containers';
				containers = [];
			})
			.finally(() => {
				containersLoading = false;
			});
	});

	async function syncMetrics() {
		if (!server || syncingMetrics) return;
		syncingMetrics = true;
		syncMessage = '';
		try {
			const res = await fetch('/api/v2/fleet/sync', { method: 'POST' });
			const body = await res.json();
			if (!res.ok) throw new Error(body.error ?? `HTTP ${res.status}`);
			syncMessage = `Synced ${body.data?.synced ?? '?'} server(s)`;
		} catch (e: unknown) {
			syncMessage = e instanceof Error ? e.message : 'Sync failed';
		} finally {
			syncingMetrics = false;
		}
	}

	function roleLabel(role: string): string {
		const labels: Record<string, string> = {
			ai_brain: 'AI Brain',
			vpn_hub: 'VPN Hub',
			workstation: 'Workstation',
			app_prod: 'App Prod',
			storage: 'Storage'
		};
		return labels[role] ?? role;
	}

	function containerStateColor(state: string): string {
		if (state === 'running') return 'var(--palais-green)';
		if (state === 'exited') return 'var(--palais-red)';
		if (state === 'paused') return 'var(--palais-gold)';
		return 'var(--palais-text-muted)';
	}

	function handleBackdropClick(e: MouseEvent) {
		if (e.target === e.currentTarget) onclose();
	}

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Escape') onclose();
	}
</script>

<svelte:window onkeydown={handleKeydown} />

{#if open && server}
	<!-- Backdrop -->
	<div
		style="
			position: fixed; inset: 0; z-index: 200;
			background: rgba(0,0,0,0.6);
			backdrop-filter: blur(3px);
			-webkit-backdrop-filter: blur(3px);
		"
		onclick={handleBackdropClick}
		role="presentation"
	></div>

	<!-- Slide-over panel from right -->
	<aside
		class="glass-panel-heavy"
		style="
			position: fixed;
			top: 0;
			right: 0;
			height: 100vh;
			width: min(520px, 95vw);
			z-index: 201;
			overflow-y: auto;
			border-left: 1px solid rgba(212,168,67,0.25);
			border-top: none;
			border-right: none;
			border-bottom: none;
			box-shadow: -8px 0 64px rgba(0,0,0,0.6), 0 0 0 0.5px rgba(212,168,67,0.1);
			animation: fadeSlideUp 0.25s ease-out both;
			display: flex;
			flex-direction: column;
		"
		role="dialog"
		aria-label="Server detail — {server.name}"
	>
		<!-- ── Header ── -->
		<div
			style="
				padding: 1.25rem 1.5rem 1rem;
				border-bottom: 1px solid rgba(212,168,67,0.15);
				display: flex;
				align-items: center;
				justify-content: space-between;
				gap: 1rem;
				flex-shrink: 0;
			"
		>
			<div>
				<p
					style="
						font-family: 'Orbitron', sans-serif;
						font-size: 0.55rem;
						letter-spacing: 0.3em;
						text-transform: uppercase;
						color: rgba(212,168,67,0.5);
						margin-bottom: 4px;
					"
				>
					SERVER DETAIL
				</p>
				<h2
					style="
						font-family: 'Orbitron', sans-serif;
						font-size: 1.05rem;
						font-weight: 700;
						letter-spacing: 0.12em;
						text-transform: uppercase;
						color: var(--palais-gold);
						text-shadow: 0 0 20px rgba(212,168,67,0.3);
					"
				>
					{server.name}
				</h2>
			</div>

			<!-- Close button -->
			<button
				onclick={onclose}
				style="
					background: rgba(212,168,67,0.06);
					border: 1px solid rgba(212,168,67,0.2);
					border-radius: 6px;
					color: rgba(212,168,67,0.6);
					cursor: pointer;
					width: 32px; height: 32px;
					display: flex; align-items: center; justify-content: center;
					font-size: 1.1rem; line-height: 1;
					transition: all 0.2s;
					flex-shrink: 0;
				"
				onmouseenter={(e) => {
					const el = e.currentTarget as HTMLElement;
					el.style.background = 'rgba(212,168,67,0.14)';
					el.style.color = 'var(--palais-gold)';
				}}
				onmouseleave={(e) => {
					const el = e.currentTarget as HTMLElement;
					el.style.background = 'rgba(212,168,67,0.06)';
					el.style.color = 'rgba(212,168,67,0.6)';
				}}
				aria-label="Close"
			>
				&times;
			</button>
		</div>

		<!-- ── Scrollable body ── -->
		<div style="flex: 1; overflow-y: auto; padding: 1.25rem 1.5rem; display: flex; flex-direction: column; gap: 1.25rem;">

			<!-- Status badge row -->
			<div style="display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap;">
				<span
					style="
						font-family: 'Orbitron', sans-serif;
						font-size: 0.6rem;
						font-weight: 600;
						letter-spacing: 0.15em;
						text-transform: uppercase;
						color: {statusColor};
						background: {statusColor}22;
						border: 1px solid {statusColor}55;
						padding: 3px 10px;
						border-radius: 4px;
					"
				>
					{server.status.toUpperCase()}
				</span>
				<span
					style="
						font-family: 'JetBrains Mono', monospace;
						font-size: 0.55rem;
						color: var(--palais-text-muted);
					"
				>
					{server.slug}
				</span>
			</div>

			<!-- Info grid -->
			<section>
				<p
					style="
						font-family: 'Orbitron', sans-serif;
						font-size: 0.55rem;
						letter-spacing: 0.25em;
						text-transform: uppercase;
						color: rgba(212,168,67,0.5);
						margin-bottom: 0.6rem;
					"
				>
					Configuration
				</p>
				<div
					style="
						display: grid;
						grid-template-columns: 1fr 1fr;
						gap: 0.5rem;
					"
				>
					{#each [
						{ label: 'Provider',    value: server.provider },
						{ label: 'Role',        value: roleLabel(server.serverRole) },
						{ label: 'Location',    value: server.location ?? '—' },
						{ label: 'SSH Port',    value: server.sshPort ? String(server.sshPort) : '22' },
						{ label: 'Tailscale',   value: server.tailscaleIp ?? '—' },
						{ label: 'Public IP',   value: server.publicIp ?? '—' },
						{ label: 'CPU Cores',   value: server.cpuCores ? `${server.cpuCores} vCPU` : '—' },
						{ label: 'RAM',         value: server.ramMb ? `${(server.ramMb / 1024).toFixed(0)} GB` : '—' },
						{ label: 'Disk',        value: server.diskGb ? `${server.diskGb} GB` : '—' },
						{ label: 'OS',          value: server.os ?? '—' },
					] as row}
						<div
							style="
								background: rgba(0,0,0,0.22);
								border: 1px solid rgba(212,168,67,0.08);
								border-radius: 6px;
								padding: 0.45rem 0.6rem;
							"
						>
							<div style="font-family: 'Orbitron', sans-serif; font-size: 0.45rem; letter-spacing: 0.18em; text-transform: uppercase; color: rgba(212,168,67,0.45); margin-bottom: 3px;">
								{row.label}
							</div>
							<div style="font-family: 'JetBrains Mono', monospace; font-size: 0.65rem; color: var(--palais-text);">
								{row.value}
							</div>
						</div>
					{/each}
				</div>
			</section>

			<!-- Latest metrics -->
			{#if server.latestMetric}
				<section>
					<p
						style="
							font-family: 'Orbitron', sans-serif;
							font-size: 0.55rem;
							letter-spacing: 0.25em;
							text-transform: uppercase;
							color: rgba(212,168,67,0.5);
							margin-bottom: 0.6rem;
						"
					>
						Latest Metrics
					</p>
					<div style="display: flex; flex-direction: column; gap: 0.5rem;">
						<!-- CPU -->
						{#if server.latestMetric.cpuPercent != null}
							{@const pct = Math.min(100, Math.max(0, server.latestMetric.cpuPercent))}
							<div>
								<div style="display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 4px;">
									<span style="font-family: 'Orbitron', sans-serif; font-size: 0.5rem; color: var(--palais-text-muted); letter-spacing: 0.15em; text-transform: uppercase;">CPU</span>
									<span style="font-family: 'JetBrains Mono', monospace; font-size: 0.65rem; color: var(--palais-cyan);">{pct.toFixed(1)}%</span>
								</div>
								<div style="height: 4px; background: rgba(79,195,247,0.1); border-radius: 9999px; overflow: hidden;">
									<div style="height: 100%; width: {pct}%; background: var(--palais-cyan); box-shadow: 0 0 6px var(--palais-cyan); border-radius: 9999px; transition: width 0.6s ease-out;"></div>
								</div>
							</div>
						{/if}
						<!-- RAM -->
						{#if server.latestMetric.ramUsedMb != null && server.latestMetric.ramTotalMb}
							{@const ramPct = Math.min(100, (server.latestMetric.ramUsedMb / server.latestMetric.ramTotalMb) * 100)}
							<div>
								<div style="display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 4px;">
									<span style="font-family: 'Orbitron', sans-serif; font-size: 0.5rem; color: var(--palais-text-muted); letter-spacing: 0.15em; text-transform: uppercase;">RAM</span>
									<span style="font-family: 'JetBrains Mono', monospace; font-size: 0.65rem; color: var(--palais-gold);">
										{(server.latestMetric.ramUsedMb / 1024).toFixed(1)} / {(server.latestMetric.ramTotalMb / 1024).toFixed(0)} GB
									</span>
								</div>
								<div style="height: 4px; background: rgba(212,168,67,0.1); border-radius: 9999px; overflow: hidden;">
									<div style="height: 100%; width: {ramPct}%; background: var(--palais-gold); box-shadow: 0 0 6px var(--palais-gold); border-radius: 9999px; transition: width 0.6s ease-out;"></div>
								</div>
							</div>
						{/if}
						<!-- Disk -->
						{#if server.latestMetric.diskUsedGb != null && server.latestMetric.diskTotalGb}
							{@const diskPct = Math.min(100, (server.latestMetric.diskUsedGb / server.latestMetric.diskTotalGb) * 100)}
							<div>
								<div style="display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 4px;">
									<span style="font-family: 'Orbitron', sans-serif; font-size: 0.5rem; color: var(--palais-text-muted); letter-spacing: 0.15em; text-transform: uppercase;">DISK</span>
									<span style="font-family: 'JetBrains Mono', monospace; font-size: 0.65rem; color: var(--palais-text-muted);">
										{server.latestMetric.diskUsedGb.toFixed(1)} / {server.latestMetric.diskTotalGb.toFixed(0)} GB
									</span>
								</div>
								<div style="height: 4px; background: rgba(255,255,255,0.06); border-radius: 9999px; overflow: hidden;">
									<div style="height: 100%; width: {diskPct}%; background: {diskPct > 85 ? 'var(--palais-red)' : diskPct > 70 ? '#E8833A' : 'var(--palais-green)'}; border-radius: 9999px; transition: width 0.6s ease-out;"></div>
								</div>
							</div>
						{/if}
						<!-- Load avg -->
						{#if server.latestMetric.loadAvg1m != null}
							<div style="display: flex; justify-content: space-between; align-items: baseline; padding-top: 4px;">
								<span style="font-family: 'Orbitron', sans-serif; font-size: 0.5rem; color: var(--palais-text-muted); letter-spacing: 0.15em; text-transform: uppercase;">Load 1m</span>
								<span style="font-family: 'JetBrains Mono', monospace; font-size: 0.65rem; color: var(--palais-text-muted);">{server.latestMetric.loadAvg1m.toFixed(2)}</span>
							</div>
						{/if}
					</div>
				</section>
			{/if}

			<!-- Containers section -->
			<section>
				<p
					style="
						font-family: 'Orbitron', sans-serif;
						font-size: 0.55rem;
						letter-spacing: 0.25em;
						text-transform: uppercase;
						color: rgba(212,168,67,0.5);
						margin-bottom: 0.6rem;
					"
				>
					Containers
				</p>

				{#if containersLoading}
					<div style="text-align: center; padding: 1.5rem 0;">
						<span style="font-family: 'JetBrains Mono', monospace; font-size: 0.65rem; color: var(--palais-text-muted); animation: pulseGold 1.2s ease-in-out infinite;">
							// scanning containers...
						</span>
					</div>
				{:else if containersError}
					<div style="background: rgba(229,57,53,0.08); border: 1px solid rgba(229,57,53,0.25); border-radius: 6px; padding: 0.65rem 0.85rem;">
						<span style="font-family: 'JetBrains Mono', monospace; font-size: 0.6rem; color: var(--palais-red);">
							{containersError}
						</span>
					</div>
				{:else if containers.length === 0}
					<div style="padding: 1rem 0; text-align: center;">
						<span style="font-family: 'JetBrains Mono', monospace; font-size: 0.6rem; color: var(--palais-text-muted);">
							// no containers found
						</span>
					</div>
				{:else}
					<div style="display: flex; flex-direction: column; gap: 0.35rem;">
						{#each containers as c (c.id)}
							<div
								style="
									display: flex;
									align-items: center;
									justify-content: space-between;
									gap: 0.5rem;
									background: rgba(0,0,0,0.2);
									border: 1px solid rgba(212,168,67,0.07);
									border-radius: 6px;
									padding: 0.45rem 0.65rem;
								"
							>
								<div style="flex: 1; min-width: 0;">
									<div style="font-family: 'JetBrains Mono', monospace; font-size: 0.6rem; color: var(--palais-text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">
										{c.name.replace(/^\//, '')}
									</div>
									<div style="font-family: 'JetBrains Mono', monospace; font-size: 0.48rem; color: var(--palais-text-muted); margin-top: 2px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">
										{c.image}
									</div>
								</div>
								<span
									style="
										flex-shrink: 0;
										width: 7px; height: 7px;
										border-radius: 50%;
										display: inline-block;
										background: {containerStateColor(c.state)};
										box-shadow: {c.state === 'running' ? '0 0 6px 1px rgba(76,175,80,0.45)' : 'none'};
									"
									title={c.state}
								></span>
							</div>
						{/each}
					</div>
				{/if}
			</section>

			<!-- Sync Metrics button -->
			<div style="padding-top: 0.5rem; border-top: 1px solid rgba(212,168,67,0.1);">
				<button
					onclick={syncMetrics}
					disabled={syncingMetrics}
					style="
						width: 100%;
						padding: 0.65rem 1rem;
						border-radius: 6px;
						cursor: {syncingMetrics ? 'not-allowed' : 'pointer'};
						background: rgba(212,168,67,0.1);
						color: var(--palais-gold);
						border: 1px solid rgba(212,168,67,0.35);
						font-family: 'Orbitron', sans-serif;
						font-size: 0.6rem;
						font-weight: 600;
						letter-spacing: 0.2em;
						text-transform: uppercase;
						transition: all 0.2s;
						opacity: {syncingMetrics ? '0.55' : '1'};
					"
					onmouseenter={(e) => {
						if (!syncingMetrics) {
							const el = e.currentTarget as HTMLElement;
							el.style.background = 'rgba(212,168,67,0.18)';
							el.style.boxShadow = '0 0 16px rgba(212,168,67,0.2)';
						}
					}}
					onmouseleave={(e) => {
						const el = e.currentTarget as HTMLElement;
						el.style.background = 'rgba(212,168,67,0.1)';
						el.style.boxShadow = '';
					}}
				>
					{syncingMetrics ? 'SYNCING...' : 'SYNC METRICS'}
				</button>
				{#if syncMessage}
					<p style="font-family: 'JetBrains Mono', monospace; font-size: 0.58rem; color: var(--palais-text-muted); text-align: center; margin-top: 0.5rem; animation: fadeSlideUp 0.3s ease-out both;">
						{syncMessage}
					</p>
				{/if}
			</div>

		</div><!-- /body -->
	</aside>
{/if}
