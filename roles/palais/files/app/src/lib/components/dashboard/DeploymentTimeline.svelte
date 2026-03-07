<script lang="ts">
	let {
		deployments
	}: {
		deployments: Array<{
			id: number;
			workspaceName: string | null;
			version: string | null;
			status: string;
			startedAt: Date | string;
		}>;
	} = $props();

	function relativeTime(date: Date | string): string {
		const d = typeof date === 'string' ? new Date(date) : date;
		const diff = Date.now() - d.getTime();
		const mins = Math.floor(diff / 60000);
		if (mins < 1) return 'just now';
		if (mins < 60) return `${mins}m ago`;
		const hrs = Math.floor(mins / 60);
		if (hrs < 24) return `${hrs}h ago`;
		const days = Math.floor(hrs / 24);
		return `${days}d ago`;
	}

	function statusColor(status: string): string {
		switch (status) {
			case 'success': return 'var(--palais-green)';
			case 'failed': return 'var(--palais-red)';
			case 'running': return 'var(--palais-gold)';
			default: return 'var(--palais-text-muted)';
		}
	}

	function statusLabel(status: string): string {
		switch (status) {
			case 'success': return 'OK';
			case 'failed': return 'FAIL';
			case 'running': return 'RUN';
			case 'pending': return 'WAIT';
			case 'cancelled': return 'SKIP';
			case 'rolled_back': return 'BACK';
			default: return status.slice(0, 4).toUpperCase();
		}
	}
</script>

<div class="glass-panel rounded-lg p-4" style="border: 1px solid rgba(212,168,67,0.1);">
	{#if deployments.length === 0}
		<p
			style="font-family: 'JetBrains Mono', monospace; font-size: 0.6rem; color: var(--palais-text-muted); text-align: center; padding: 1rem 0;"
		>
			NO DEPLOYMENTS YET
		</p>
	{:else}
		<div class="flex flex-col" style="position: relative;">
			<!-- Vertical timeline line -->
			<div
				class="absolute"
				style="
					left: 5px;
					top: 6px;
					bottom: 6px;
					width: 1px;
					background: linear-gradient(to bottom, rgba(212,168,67,0.4), rgba(212,168,67,0.05));
				"
				aria-hidden="true"
			></div>

			{#each deployments as deploy, i (deploy.id)}
				<div
					class="flex items-start gap-3 py-2"
					style="animation: fadeSlideUp 0.4s ease-out both; animation-delay: {i * 60}ms;"
				>
					<!-- Status dot -->
					<div class="shrink-0 relative" style="z-index: 1; padding-top: 2px;">
						<span
							class="rounded-full block"
							style="
								width: 11px;
								height: 11px;
								background: {statusColor(deploy.status)};
								box-shadow: 0 0 8px {statusColor(deploy.status)};
								border: 1px solid var(--palais-bg);
							"
							title={deploy.status}
						></span>
					</div>

					<!-- Content -->
					<div class="flex-1 min-w-0">
						<div class="flex items-center justify-between gap-2 flex-wrap">
							<!-- Workspace name -->
							<span
								class="truncate"
								style="font-family: 'Orbitron', sans-serif; font-size: 0.5rem; letter-spacing: 0.12em; color: var(--palais-text); text-transform: uppercase;"
							>
								{deploy.workspaceName ?? 'unknown'}
							</span>
							<!-- Relative time -->
							<span
								style="font-family: 'JetBrains Mono', monospace; font-size: 0.5rem; color: var(--palais-text-muted); white-space: nowrap; flex-shrink: 0;"
							>
								{relativeTime(deploy.startedAt)}
							</span>
						</div>
						<div class="flex items-center gap-2 mt-0.5">
							<!-- Version badge -->
							{#if deploy.version}
								<span
									class="px-1.5 py-0.5 rounded"
									style="
										font-family: 'JetBrains Mono', monospace;
										font-size: 0.42rem;
										color: var(--palais-cyan);
										border: 1px solid rgba(79,195,247,0.2);
										background: rgba(79,195,247,0.06);
										letter-spacing: 0.06em;
									"
								>{deploy.version}</span>
							{/if}
							<!-- Status badge -->
							<span
								class="px-1.5 py-0.5 rounded"
								style="
									font-family: 'JetBrains Mono', monospace;
									font-size: 0.4rem;
									color: {statusColor(deploy.status)};
									border: 1px solid {statusColor(deploy.status)}33;
									background: {statusColor(deploy.status)}0D;
									letter-spacing: 0.1em;
								"
							>{statusLabel(deploy.status)}</span>
						</div>
					</div>
				</div>
				{#if i < deployments.length - 1}
					<div style="height: 1px; background: rgba(212,168,67,0.05); margin-left: 20px;"></div>
				{/if}
			{/each}
		</div>
	{/if}
</div>
