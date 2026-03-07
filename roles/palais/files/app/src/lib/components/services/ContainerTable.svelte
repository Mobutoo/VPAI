<script lang="ts">
	interface ContainerRow {
		name: string;
		image: string;
		status: string;
		state: string;
		cpuPercent: number | null;
		memUsageMb: number | null;
	}

	interface Props {
		containers: ContainerRow[];
		serverId: number;
		onaction: (containerName: string, action: 'start' | 'stop' | 'restart') => Promise<void>;
	}

	let { containers, serverId, onaction }: Props = $props();

	function statusColor(state: string): string {
		const s = state.toLowerCase();
		if (s === 'running') return 'var(--palais-green)';
		if (s === 'exited' || s === 'dead') return 'var(--palais-red)';
		if (s === 'restarting') return 'var(--palais-gold)';
		if (s === 'paused') return 'var(--palais-text-muted)';
		return 'var(--palais-text-muted)';
	}

	function statusBg(state: string): string {
		const s = state.toLowerCase();
		if (s === 'running') return 'rgba(76,175,80,0.12)';
		if (s === 'exited' || s === 'dead') return 'rgba(229,57,53,0.12)';
		if (s === 'restarting') return 'rgba(212,168,67,0.12)';
		return 'rgba(138,138,154,0.1)';
	}

	function statusBorder(state: string): string {
		const s = state.toLowerCase();
		if (s === 'running') return 'rgba(76,175,80,0.25)';
		if (s === 'exited' || s === 'dead') return 'rgba(229,57,53,0.25)';
		if (s === 'restarting') return 'rgba(212,168,67,0.3)';
		return 'rgba(138,138,154,0.2)';
	}

	function statusLabel(state: string): string {
		return state.toUpperCase();
	}

	function truncateImage(image: string): string {
		// Remove registry prefix if present (e.g. ghcr.io/org/...)
		const parts = image.split('/');
		const last = parts[parts.length - 1] ?? image;
		return last.length > 36 ? last.substring(0, 33) + '...' : last;
	}

	function formatMb(mb: number | null): string {
		if (mb === null) return '—';
		if (mb >= 1024) return (mb / 1024).toFixed(1) + ' GiB';
		return mb.toFixed(0) + ' MiB';
	}

	let actioning = $state<Record<string, boolean>>({});

	async function handleAction(containerName: string, action: 'start' | 'stop' | 'restart') {
		actioning = { ...actioning, [`${containerName}:${action}`]: true };
		try {
			await onaction(containerName, action);
		} finally {
			actioning = { ...actioning, [`${containerName}:${action}`]: false };
		}
	}

	function isActioning(containerName: string): boolean {
		return ['start', 'stop', 'restart'].some((a) => actioning[`${containerName}:${a}`]);
	}
</script>

<div class="overflow-x-auto">
	<table style="width: 100%; border-collapse: collapse; font-size: 0.8rem;">
		<thead>
			<tr style="border-bottom: 1px solid rgba(212,168,67,0.18);">
				<th style="
					text-align: left; padding: 8px 12px;
					font-family: 'Orbitron', sans-serif; font-size: 0.58rem;
					letter-spacing: 0.18em; color: rgba(212,168,67,0.55);
					text-transform: uppercase; white-space: nowrap;
				">Name</th>
				<th style="
					text-align: left; padding: 8px 12px;
					font-family: 'Orbitron', sans-serif; font-size: 0.58rem;
					letter-spacing: 0.18em; color: rgba(212,168,67,0.55);
					text-transform: uppercase; white-space: nowrap;
				">Image</th>
				<th style="
					text-align: left; padding: 8px 12px;
					font-family: 'Orbitron', sans-serif; font-size: 0.58rem;
					letter-spacing: 0.18em; color: rgba(212,168,67,0.55);
					text-transform: uppercase; white-space: nowrap;
				">Status</th>
				<th style="
					text-align: right; padding: 8px 12px;
					font-family: 'Orbitron', sans-serif; font-size: 0.58rem;
					letter-spacing: 0.18em; color: rgba(212,168,67,0.55);
					text-transform: uppercase; white-space: nowrap;
				">CPU %</th>
				<th style="
					text-align: right; padding: 8px 12px;
					font-family: 'Orbitron', sans-serif; font-size: 0.58rem;
					letter-spacing: 0.18em; color: rgba(212,168,67,0.55);
					text-transform: uppercase; white-space: nowrap;
				">RAM</th>
				<th style="
					text-align: center; padding: 8px 12px;
					font-family: 'Orbitron', sans-serif; font-size: 0.58rem;
					letter-spacing: 0.18em; color: rgba(212,168,67,0.55);
					text-transform: uppercase; white-space: nowrap;
				">Actions</th>
			</tr>
		</thead>
		<tbody>
			{#each containers as c, i (c.name)}
				{@const acting = isActioning(c.name)}
				<tr style="
					border-bottom: 1px solid rgba(42,42,58,0.6);
					background: {i % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.012)'};
					transition: background 0.15s;
					opacity: {acting ? '0.6' : '1'};
				"
					onmouseenter={(e) => { (e.currentTarget as HTMLElement).style.background = 'rgba(212,168,67,0.04)'; }}
					onmouseleave={(e) => { (e.currentTarget as HTMLElement).style.background = i % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.012)'; }}
				>
					<!-- Name -->
					<td style="padding: 10px 12px; white-space: nowrap;">
						<span style="
							font-family: 'JetBrains Mono', monospace;
							color: var(--palais-text);
							font-size: 0.78rem;
						">{c.name}</span>
					</td>

					<!-- Image -->
					<td style="padding: 10px 12px; max-width: 200px;">
						<span
							title={c.image}
							style="
								font-family: 'JetBrains Mono', monospace;
								color: var(--palais-text-muted);
								font-size: 0.72rem;
							"
						>{truncateImage(c.image)}</span>
					</td>

					<!-- Status badge -->
					<td style="padding: 10px 12px; white-space: nowrap;">
						<span style="
							display: inline-flex; align-items: center; gap: 6px;
							padding: 2px 8px; border-radius: 4px;
							background: {statusBg(c.state)};
							border: 1px solid {statusBorder(c.state)};
						">
							<span style="
								display: inline-block; width: 6px; height: 6px; border-radius: 50%;
								background: {statusColor(c.state)};
								box-shadow: {c.state.toLowerCase() === 'running' ? '0 0 5px 1px rgba(76,175,80,0.5)' :
								             c.state.toLowerCase() === 'restarting' ? '0 0 5px 1px rgba(212,168,67,0.5)' : 'none'};
								{c.state.toLowerCase() === 'restarting' ? 'animation: pulseGold 1.2s ease-in-out infinite;' : ''}
							"></span>
							<span style="
								font-family: 'Orbitron', sans-serif;
								font-size: 0.55rem; letter-spacing: 0.1em;
								color: {statusColor(c.state)};
							">{statusLabel(c.state)}</span>
						</span>
					</td>

					<!-- CPU % -->
					<td style="padding: 10px 12px; text-align: right; white-space: nowrap;">
						{#if c.cpuPercent !== null}
							<span style="
								font-family: 'JetBrains Mono', monospace;
								font-size: 0.78rem;
								color: {c.cpuPercent > 80 ? 'var(--palais-red)' :
								         c.cpuPercent > 50 ? 'var(--palais-gold)' : 'var(--palais-cyan)'};
							">{c.cpuPercent.toFixed(1)}%</span>
						{:else}
							<span style="color: var(--palais-text-muted); font-family: 'JetBrains Mono', monospace; font-size: 0.75rem;">—</span>
						{/if}
					</td>

					<!-- RAM -->
					<td style="padding: 10px 12px; text-align: right; white-space: nowrap;">
						<span style="
							font-family: 'JetBrains Mono', monospace;
							font-size: 0.78rem;
							color: var(--palais-cyan);
						">{formatMb(c.memUsageMb)}</span>
					</td>

					<!-- Action buttons -->
					<td style="padding: 10px 12px; text-align: center; white-space: nowrap;">
						<div style="display: inline-flex; gap: 4px; align-items: center;">
							<!-- Start -->
							<button
								onclick={() => handleAction(c.name, 'start')}
								disabled={acting}
								title="Start {c.name}"
								style="
									padding: 3px 8px; border-radius: 4px; cursor: {acting ? 'not-allowed' : 'pointer'};
									background: rgba(76,175,80,0.1); color: var(--palais-green);
									border: 1px solid rgba(76,175,80,0.25);
									font-family: 'Orbitron', sans-serif; font-size: 0.55rem; letter-spacing: 0.1em;
									transition: all 0.15s;
									opacity: {acting ? '0.4' : '1'};
								"
								onmouseenter={(e) => { if (!acting) { const el = e.currentTarget as HTMLElement; el.style.background = 'rgba(76,175,80,0.2)'; el.style.borderColor = 'rgba(76,175,80,0.45)'; } }}
								onmouseleave={(e) => { const el = e.currentTarget as HTMLElement; el.style.background = 'rgba(76,175,80,0.1)'; el.style.borderColor = 'rgba(76,175,80,0.25)'; }}
							>S</button>

							<!-- Stop -->
							<button
								onclick={() => handleAction(c.name, 'stop')}
								disabled={acting}
								title="Stop {c.name}"
								style="
									padding: 3px 8px; border-radius: 4px; cursor: {acting ? 'not-allowed' : 'pointer'};
									background: rgba(229,57,53,0.1); color: var(--palais-red);
									border: 1px solid rgba(229,57,53,0.25);
									font-family: 'Orbitron', sans-serif; font-size: 0.55rem; letter-spacing: 0.1em;
									transition: all 0.15s;
									opacity: {acting ? '0.4' : '1'};
								"
								onmouseenter={(e) => { if (!acting) { const el = e.currentTarget as HTMLElement; el.style.background = 'rgba(229,57,53,0.2)'; el.style.borderColor = 'rgba(229,57,53,0.45)'; } }}
								onmouseleave={(e) => { const el = e.currentTarget as HTMLElement; el.style.background = 'rgba(229,57,53,0.1)'; el.style.borderColor = 'rgba(229,57,53,0.25)'; }}
							>P</button>

							<!-- Restart -->
							<button
								onclick={() => handleAction(c.name, 'restart')}
								disabled={acting}
								title="Restart {c.name}"
								style="
									padding: 3px 8px; border-radius: 4px; cursor: {acting ? 'not-allowed' : 'pointer'};
									background: rgba(212,168,67,0.1); color: var(--palais-gold);
									border: 1px solid rgba(212,168,67,0.25);
									font-family: 'Orbitron', sans-serif; font-size: 0.55rem; letter-spacing: 0.1em;
									transition: all 0.15s;
									opacity: {acting ? '0.4' : '1'};
								"
								onmouseenter={(e) => { if (!acting) { const el = e.currentTarget as HTMLElement; el.style.background = 'rgba(212,168,67,0.2)'; el.style.borderColor = 'rgba(212,168,67,0.45)'; } }}
								onmouseleave={(e) => { const el = e.currentTarget as HTMLElement; el.style.background = 'rgba(212,168,67,0.1)'; el.style.borderColor = 'rgba(212,168,67,0.25)'; }}
							>R</button>
						</div>
					</td>
				</tr>
			{/each}
		</tbody>
	</table>
</div>
