<script lang="ts">
	type ServerMetric = {
		cpuPercent: number | null;
		ramUsedMb: number | null;
		ramTotalMb: number | null;
		diskUsedGb: number | null;
		diskTotalGb: number | null;
	} | null;

	type Server = {
		id: number;
		name: string;
		slug: string;
		provider: 'hetzner' | 'ovh' | 'ionos' | 'local';
		serverRole: string;
		location: string | null;
		publicIp: string | null;
		tailscaleIp: string | null;
		status: 'online' | 'offline' | 'busy' | 'degraded';
		cpuCores: number | null;
		ramMb: number | null;
		diskGb: number | null;
		sshPort: number | null;
		latestMetric: ServerMetric;
	};

	let { server, onclick }: { server: Server; onclick?: () => void } = $props();

	// ── Status ────────────────────────────────────────────────────────
	const statusColor = $derived(
		server.status === 'online'
			? 'var(--palais-green)'
			: server.status === 'busy'
				? 'var(--palais-gold)'
				: server.status === 'degraded'
					? '#E8833A'
					: 'var(--palais-red)'
	);

	const statusGlow = $derived(
		server.status === 'online'
			? '0 0 8px 2px rgba(76,175,80,0.55)'
			: server.status === 'busy'
				? '0 0 8px 2px rgba(212,168,67,0.55)'
				: server.status === 'degraded'
					? '0 0 8px 2px rgba(232,131,58,0.5)'
					: '0 0 6px 1px rgba(229,57,53,0.4)'
	);

	const statusPulse = $derived(
		server.status === 'busy' || server.status === 'degraded'
			? 'animation: pulseGold 1.5s ease-in-out infinite;'
			: ''
	);

	// ── Provider badge ─────────────────────────────────────────────────
	const providerStyle = $derived(
		server.provider === 'hetzner'
			? { color: 'var(--palais-cyan)', border: 'rgba(79,195,247,0.35)', bg: 'rgba(79,195,247,0.08)' }
			: server.provider === 'ovh'
				? { color: 'var(--palais-gold)', border: 'rgba(212,168,67,0.35)', bg: 'rgba(212,168,67,0.08)' }
				: server.provider === 'ionos'
					? { color: '#E8833A', border: 'rgba(232,131,58,0.35)', bg: 'rgba(232,131,58,0.08)' }
					: { color: 'var(--palais-green)', border: 'rgba(76,175,80,0.35)', bg: 'rgba(76,175,80,0.08)' }
	);

	// ── Metrics ────────────────────────────────────────────────────────
	const cpuPct = $derived(
		server.latestMetric?.cpuPercent != null
			? Math.min(100, Math.max(0, server.latestMetric.cpuPercent))
			: null
	);

	const ramPct = $derived(
		server.latestMetric?.ramUsedMb != null && server.latestMetric?.ramTotalMb
			? Math.min(100, Math.max(0, (server.latestMetric.ramUsedMb / server.latestMetric.ramTotalMb) * 100))
			: null
	);

	const diskLabel = $derived(
		server.latestMetric?.diskUsedGb != null && server.latestMetric?.diskTotalGb
			? `${server.latestMetric.diskUsedGb.toFixed(0)}/${server.latestMetric.diskTotalGb.toFixed(0)} GB`
			: server.diskGb
				? `— /${server.diskGb} GB`
				: null
	);

	// Card border glow based on status
	const cardBorderColor = $derived(
		server.status === 'online'
			? 'rgba(76,175,80,0.25)'
			: server.status === 'busy'
				? 'rgba(212,168,67,0.3)'
				: server.status === 'degraded'
					? 'rgba(232,131,58,0.25)'
					: 'rgba(229,57,53,0.2)'
	);
</script>

<button
	type="button"
	class="server-card glass-panel hud-bracket rounded-xl"
	style="
		border: 1px solid rgba(212,168,67,0.18);
		border-top-color: var(--palais-gold);
		border-top-width: 2px;
		padding: 1rem;
		width: 100%;
		text-align: left;
		cursor: pointer;
		background: var(--palais-glass-bg);
		transition: box-shadow 200ms ease, border-color 200ms ease, transform 150ms ease;
		animation: cardReveal 0.4s ease-out both;
		display: block;
	"
	onclick={onclick}
	onmouseenter={(e) => {
		const el = e.currentTarget as HTMLElement;
		el.style.boxShadow = `0 8px 32px rgba(0,0,0,0.5), 0 0 0 1px ${cardBorderColor}, inset 0 1px 0 rgba(212,168,67,0.15)`;
		el.style.transform = 'translateY(-1px)';
	}}
	onmouseleave={(e) => {
		const el = e.currentTarget as HTMLElement;
		el.style.boxShadow = '';
		el.style.transform = '';
	}}
>
	<span class="hud-bracket-bottom" style="display: block;">

		<!-- ── Header row ── -->
		<div style="display: flex; align-items: flex-start; justify-content: space-between; gap: 0.5rem; margin-bottom: 0.65rem;">
			<div style="flex: 1; min-width: 0;">
				<!-- Server name -->
				<div
					style="
						font-family: 'Orbitron', sans-serif;
						font-size: 0.65rem;
						font-weight: 700;
						letter-spacing: 0.15em;
						text-transform: uppercase;
						color: var(--palais-text);
						white-space: nowrap;
						overflow: hidden;
						text-overflow: ellipsis;
					"
				>
					{server.name}
				</div>

				<!-- Tailscale IP -->
				{#if server.tailscaleIp}
					<div
						style="
							font-family: 'JetBrains Mono', monospace;
							font-size: 0.55rem;
							color: var(--palais-text-muted);
							margin-top: 3px;
							letter-spacing: 0.04em;
						"
					>
						{server.tailscaleIp}
					</div>
				{/if}
			</div>

			<!-- Status dot -->
			<span
				style="
					flex-shrink: 0;
					width: 8px;
					height: 8px;
					border-radius: 50%;
					display: inline-block;
					background: {statusColor};
					box-shadow: {statusGlow};
					margin-top: 2px;
					{statusPulse}
				"
				title={server.status}
			></span>
		</div>

		<!-- ── Provider badge ── -->
		<div style="margin-bottom: 0.75rem;">
			<span
				style="
					display: inline-block;
					font-family: 'JetBrains Mono', monospace;
					font-size: 0.5rem;
					font-weight: 500;
					letter-spacing: 0.12em;
					text-transform: uppercase;
					color: {providerStyle.color};
					border: 1px solid {providerStyle.border};
					background: {providerStyle.bg};
					padding: 2px 7px;
					border-radius: 4px;
				"
			>
				{server.provider}
			</span>
			{#if server.location}
				<span
					style="
						display: inline-block;
						margin-left: 5px;
						font-family: 'JetBrains Mono', monospace;
						font-size: 0.48rem;
						color: var(--palais-text-muted);
						letter-spacing: 0.06em;
					"
				>
					{server.location}
				</span>
			{/if}
		</div>

		<!-- ── CPU gauge ── -->
		<div style="margin-bottom: 0.5rem;">
			<div style="display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 3px;">
				<span style="font-family: 'Orbitron', sans-serif; font-size: 0.45rem; color: var(--palais-text-muted); letter-spacing: 0.18em; text-transform: uppercase;">CPU</span>
				<span style="font-family: 'JetBrains Mono', monospace; font-size: 0.5rem; color: var(--palais-cyan);">
					{cpuPct != null ? `${cpuPct.toFixed(0)}%` : '—'}
				</span>
			</div>
			<div style="height: 3px; background: rgba(79,195,247,0.1); border-radius: 9999px; overflow: hidden;">
				{#if cpuPct != null}
					<div
						style="
							height: 100%;
							width: {cpuPct}%;
							background: var(--palais-cyan);
							box-shadow: 0 0 5px var(--palais-cyan);
							border-radius: 9999px;
							transition: width 0.7s ease-out;
						"
					></div>
				{/if}
			</div>
		</div>

		<!-- ── RAM gauge ── -->
		<div style="margin-bottom: 0.6rem;">
			<div style="display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 3px;">
				<span style="font-family: 'Orbitron', sans-serif; font-size: 0.45rem; color: var(--palais-text-muted); letter-spacing: 0.18em; text-transform: uppercase;">RAM</span>
				<span style="font-family: 'JetBrains Mono', monospace; font-size: 0.5rem; color: var(--palais-gold);">
					{#if server.latestMetric?.ramUsedMb != null && server.latestMetric?.ramTotalMb}
						{(server.latestMetric.ramUsedMb / 1024).toFixed(1)} / {(server.latestMetric.ramTotalMb / 1024).toFixed(0)} GB
					{:else if ramPct != null}
						{ramPct.toFixed(0)}%
					{:else}
						—
					{/if}
				</span>
			</div>
			<div style="height: 3px; background: rgba(212,168,67,0.1); border-radius: 9999px; overflow: hidden;">
				{#if ramPct != null}
					<div
						style="
							height: 100%;
							width: {ramPct}%;
							background: var(--palais-gold);
							box-shadow: 0 0 5px var(--palais-gold);
							border-radius: 9999px;
							transition: width 0.7s ease-out;
						"
					></div>
				{/if}
			</div>
		</div>

		<!-- ── Disk text ── -->
		{#if diskLabel}
			<div style="display: flex; align-items: baseline; gap: 6px; padding-top: 0.4rem; border-top: 1px solid rgba(212,168,67,0.08);">
				<span style="font-family: 'Orbitron', sans-serif; font-size: 0.45rem; color: var(--palais-text-muted); letter-spacing: 0.18em; text-transform: uppercase;">DSK</span>
				<span style="font-family: 'JetBrains Mono', monospace; font-size: 0.5rem; color: var(--palais-text-muted);">{diskLabel}</span>
			</div>
		{/if}

	</span>
</button>

<style>
	.server-card:focus-visible {
		outline: 2px solid var(--palais-gold);
		outline-offset: 2px;
	}
</style>
