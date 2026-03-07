<script lang="ts">
	import { goto, invalidateAll } from '$app/navigation';

	let { data } = $props();

	const { deployment, steps } = $derived(data);

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
			default:           return 'rgba(138,138,154,0.15)';
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

	function formatDate(date: Date | null | string): string {
		if (!date) return '—';
		return new Date(date).toLocaleString('fr-FR', {
			day: '2-digit', month: 'short', year: 'numeric',
			hour: '2-digit', minute: '2-digit', second: '2-digit'
		});
	}

	function stepDuration(
		startedAt: Date | null | string,
		completedAt: Date | null | string
	): string {
		if (!startedAt || !completedAt) return '—';
		const ms = new Date(completedAt).getTime() - new Date(startedAt).getTime();
		return formatDuration(ms);
	}

	// ── Expanded output state ──────────────────────────────────────
	let expandedSteps = $state<Set<number>>(new Set());

	function toggleStep(id: number) {
		const next = new Set(expandedSteps);
		if (next.has(id)) {
			next.delete(id);
		} else {
			next.add(id);
		}
		expandedSteps = next;
	}

	// ── Auto-polling for running deployments ───────────────────────
	$effect(() => {
		if (deployment.status !== 'running') return;
		const interval = setInterval(async () => {
			await invalidateAll();
		}, 5000);
		return () => clearInterval(interval);
	});

	// ── Rollback ───────────────────────────────────────────────────
	let rollbackModalOpen = $state(false);
	let rollingBack = $state(false);
	let rollbackError = $state('');

	function openRollback() {
		rollbackError = '';
		rollbackModalOpen = true;
	}

	function closeRollback() {
		rollbackModalOpen = false;
		rollbackError = '';
	}

	async function confirmRollback() {
		if (!deployment.workspaceSlug) {
			rollbackError = 'No workspace slug found';
			return;
		}
		rollingBack = true;
		rollbackError = '';
		try {
			const res = await fetch(`/api/v2/workspaces/${deployment.workspaceSlug}/rollback`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ deploymentId: deployment.id }),
			});
			if (!res.ok) {
				const body = await res.json().catch(() => ({ message: `HTTP ${res.status}` }));
				rollbackError = body.message ?? `HTTP ${res.status}`;
			} else {
				const body = await res.json();
				closeRollback();
				if (body.data?.id) {
					await goto(`/deploy/${body.data.id}`);
				}
			}
		} catch {
			rollbackError = 'Network error';
		} finally {
			rollingBack = false;
		}
	}

	// Progress stats
	const stepStats = $derived({
		total:   steps.length,
		done:    steps.filter((s) => s.status === 'success').length,
		running: steps.filter((s) => s.status === 'running').length,
		failed:  steps.filter((s) => s.status === 'failed').length,
		pending: steps.filter((s) => s.status === 'pending').length,
	});

	const progressPct = $derived(
		stepStats.total > 0
			? Math.round(((stepStats.done + stepStats.failed) / stepStats.total) * 100)
			: 0
	);
</script>

<svelte:head><title>Palais — Deploy #{deployment.id}</title></svelte:head>

<div class="space-y-8" style="animation: fadeSlideUp 0.45s ease-out both;">

	<!-- ── BREADCRUMB + HEADER ────────────────────────────────────── -->
	<header class="flex flex-col gap-3">
		<!-- Breadcrumb -->
		<nav style="font-family: 'JetBrains Mono', monospace; font-size: 0.68rem;">
			<a href="/deploy" style="color: rgba(212,168,67,0.5); text-decoration: none;"
				onmouseenter={(e) => { (e.currentTarget as HTMLElement).style.color = 'var(--palais-gold)'; }}
				onmouseleave={(e) => { (e.currentTarget as HTMLElement).style.color = 'rgba(212,168,67,0.5)'; }}
			>DEPLOY PIPELINE</a>
			{#if deployment.workspaceSlug}
				<span style="color: rgba(212,168,67,0.25); margin: 0 6px;">/</span>
				<a href="/workspaces/{deployment.workspaceSlug}"
					style="color: rgba(212,168,67,0.5); text-decoration: none;"
					onmouseenter={(e) => { (e.currentTarget as HTMLElement).style.color = 'var(--palais-gold)'; }}
					onmouseleave={(e) => { (e.currentTarget as HTMLElement).style.color = 'rgba(212,168,67,0.5)'; }}
				>{deployment.workspaceName ?? deployment.workspaceSlug}</a>
			{/if}
			<span style="color: rgba(212,168,67,0.25); margin: 0 6px;">/</span>
			<span style="color: var(--palais-text-muted);">#{deployment.id}</span>
		</nav>

		<div class="flex items-start justify-between gap-4 flex-wrap">
			<div>
				<p
					class="uppercase tracking-[0.35em] mb-1"
					style="color: var(--palais-gold); opacity: 0.5; font-family: 'Orbitron', sans-serif; font-size: 0.5rem;"
				>
					DEPLOYMENT — DETAIL
				</p>
				<h1
					class="font-bold tracking-widest"
					style="
						color: var(--palais-gold);
						font-family: 'Orbitron', sans-serif;
						font-size: clamp(1.1rem, 3vw, 1.6rem);
						text-shadow: 0 0 24px rgba(212,168,67,0.35);
					"
				>
					{deployment.workspaceName?.toUpperCase() ?? 'DEPLOYMENT'}
					<span style="font-size: 0.55em; opacity: 0.5; letter-spacing: 0.2em; font-family: 'JetBrains Mono', monospace;">
						#{deployment.id}
					</span>
				</h1>
			</div>

			<!-- Rollback button (only on success) -->
			{#if deployment.status === 'success' && deployment.workspaceSlug}
				<button
					onclick={openRollback}
					style="
						padding: 7px 16px; border-radius: 6px; cursor: pointer;
						background: rgba(232,131,58,0.1); color: var(--palais-amber);
						border: 1px solid rgba(232,131,58,0.3);
						font-family: 'Orbitron', sans-serif; font-size: 0.58rem; letter-spacing: 0.1em;
						transition: all 0.2s;
					"
					onmouseenter={(e) => {
						const el = e.currentTarget as HTMLElement;
						el.style.background = 'rgba(232,131,58,0.18)';
						el.style.boxShadow = '0 0 14px rgba(232,131,58,0.2)';
					}}
					onmouseleave={(e) => {
						const el = e.currentTarget as HTMLElement;
						el.style.background = 'rgba(232,131,58,0.1)';
						el.style.boxShadow = '';
					}}
				>
					ROLLBACK TO THIS VERSION
				</button>
			{/if}
		</div>

		<div style="height: 1px; background: linear-gradient(90deg, var(--palais-gold) 0%, rgba(212,168,67,0.06) 100%); opacity: 0.35;"></div>
	</header>

	<!-- ── META CARDS ─────────────────────────────────────────────── -->
	<section>
		<h2
			class="flex items-center gap-2 mb-4"
			style="font-family: 'Orbitron', sans-serif; font-size: 0.6rem; letter-spacing: 0.25em; text-transform: uppercase; color: var(--palais-gold); opacity: 0.7;"
		>
			<span style="width: 8px; height: 1px; background: var(--palais-gold); opacity: 0.5; display: inline-block; flex-shrink: 0;"></span>
			OVERVIEW
			<span style="flex: 1; height: 1px; background: linear-gradient(to right, rgba(212,168,67,0.3), transparent); display: inline-block;"></span>
		</h2>

		<div class="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3 mb-4">
			<!-- Status -->
			<div class="glass-panel rounded-lg p-4 md:col-span-2" style="border: 1px solid {statusBorder(deployment.status)};">
				<p style="color: rgba(212,168,67,0.5); font-family: 'Orbitron', sans-serif; font-size: 0.52rem; letter-spacing: 0.18em; text-transform: uppercase; margin-bottom: 8px;">
					STATUS
				</p>
				<span
					class="flex items-center gap-2 px-3 py-1.5 rounded-lg w-fit"
					style="background: {statusBg(deployment.status)}; border: 1px solid {statusBorder(deployment.status)};"
				>
					<span
						class="w-2 h-2 rounded-full"
						style="
							background: {statusColor(deployment.status)};
							{deployment.status === 'running' ? 'animation: pulseGold 1.2s ease-in-out infinite;' : ''}
						"
					></span>
					<span style="color: {statusColor(deployment.status)}; font-family: 'Orbitron', sans-serif; font-size: 0.7rem; letter-spacing: 0.1em; font-weight: 600;">
						{deployment.status.toUpperCase().replace('_', ' ')}
					</span>
				</span>
			</div>

			<!-- Version -->
			<div class="glass-panel rounded-lg p-4" style="border: 1px solid rgba(212,168,67,0.15);">
				<p style="color: rgba(212,168,67,0.5); font-family: 'Orbitron', sans-serif; font-size: 0.52rem; letter-spacing: 0.18em; text-transform: uppercase; margin-bottom: 6px;">
					VERSION
				</p>
				<p style="color: var(--palais-gold); font-family: 'JetBrains Mono', monospace; font-size: 0.9rem; font-weight: 600;">
					{deployment.version ?? '—'}
				</p>
			</div>

			<!-- Type -->
			<div class="glass-panel rounded-lg p-4" style="border: 1px solid rgba(212,168,67,0.15);">
				<p style="color: rgba(212,168,67,0.5); font-family: 'Orbitron', sans-serif; font-size: 0.52rem; letter-spacing: 0.18em; text-transform: uppercase; margin-bottom: 6px;">
					TYPE
				</p>
				<p style="color: {deployment.deployType === 'rollback' ? 'var(--palais-amber)' : 'var(--palais-text-muted)'}; font-family: 'JetBrains Mono', monospace; font-size: 0.82rem; text-transform: uppercase;">
					{deployment.deployType}
				</p>
			</div>

			<!-- Duration -->
			<div class="glass-panel rounded-lg p-4" style="border: 1px solid rgba(212,168,67,0.15);">
				<p style="color: rgba(212,168,67,0.5); font-family: 'Orbitron', sans-serif; font-size: 0.52rem; letter-spacing: 0.18em; text-transform: uppercase; margin-bottom: 6px;">
					DURATION
				</p>
				<p style="color: var(--palais-cyan); font-family: 'JetBrains Mono', monospace; font-size: 0.9rem;">
					{formatDuration(deployment.durationMs)}
				</p>
			</div>

			<!-- Triggered by -->
			<div class="glass-panel rounded-lg p-4" style="border: 1px solid rgba(212,168,67,0.15);">
				<p style="color: rgba(212,168,67,0.5); font-family: 'Orbitron', sans-serif; font-size: 0.52rem; letter-spacing: 0.18em; text-transform: uppercase; margin-bottom: 6px;">
					TRIGGERED BY
				</p>
				<p style="color: var(--palais-text-muted); font-family: 'JetBrains Mono', monospace; font-size: 0.75rem;">
					{deployment.triggeredBy}
				</p>
			</div>
		</div>

		<!-- Timestamps -->
		<div class="grid grid-cols-1 md:grid-cols-2 gap-3">
			<div class="glass-panel rounded-lg px-4 py-3 flex items-center justify-between" style="border: 1px solid rgba(212,168,67,0.1);">
				<span style="color: rgba(212,168,67,0.45); font-family: 'Orbitron', sans-serif; font-size: 0.52rem; letter-spacing: 0.15em; text-transform: uppercase;">
					STARTED
				</span>
				<span style="color: var(--palais-text-muted); font-family: 'JetBrains Mono', monospace; font-size: 0.72rem;">
					{formatDate(deployment.startedAt)}
				</span>
			</div>
			<div class="glass-panel rounded-lg px-4 py-3 flex items-center justify-between" style="border: 1px solid rgba(212,168,67,0.1);">
				<span style="color: rgba(212,168,67,0.45); font-family: 'Orbitron', sans-serif; font-size: 0.52rem; letter-spacing: 0.15em; text-transform: uppercase;">
					COMPLETED
				</span>
				<span style="color: {deployment.completedAt ? 'var(--palais-text-muted)' : 'rgba(212,168,67,0.4)'}; font-family: 'JetBrains Mono', monospace; font-size: 0.72rem;">
					{deployment.completedAt ? formatDate(deployment.completedAt) : deployment.status === 'running' ? 'In progress...' : '—'}
				</span>
			</div>
		</div>

		<!-- Error summary if failed -->
		{#if deployment.errorSummary}
			<div class="mt-3 rounded-lg p-4" style="background: rgba(229,57,53,0.07); border: 1px solid rgba(229,57,53,0.25);">
				<p style="color: rgba(229,57,53,0.8); font-family: 'Orbitron', sans-serif; font-size: 0.55rem; letter-spacing: 0.18em; margin-bottom: 6px;">
					ERROR SUMMARY
				</p>
				<p style="color: var(--palais-red); font-family: 'JetBrains Mono', monospace; font-size: 0.75rem; line-height: 1.5; white-space: pre-wrap;">
					{deployment.errorSummary}
				</p>
			</div>
		{/if}
	</section>

	<!-- ── STEP PROGRESS BAR (if has steps) ───────────────────────── -->
	{#if steps.length > 0}
		<div class="glass-panel rounded-lg px-4 py-3 space-y-2" style="border: 1px solid rgba(212,168,67,0.12);">
			<div class="flex items-center justify-between mb-1">
				<span style="color: rgba(212,168,67,0.5); font-family: 'Orbitron', sans-serif; font-size: 0.52rem; letter-spacing: 0.18em; text-transform: uppercase;">
					PROGRESS
				</span>
				<div class="flex items-center gap-3">
					<span style="color: var(--palais-green); font-family: 'JetBrains Mono', monospace; font-size: 0.65rem;">
						{stepStats.done} done
					</span>
					{#if stepStats.running > 0}
						<span style="color: var(--palais-gold); font-family: 'JetBrains Mono', monospace; font-size: 0.65rem;">
							{stepStats.running} running
						</span>
					{/if}
					{#if stepStats.failed > 0}
						<span style="color: var(--palais-red); font-family: 'JetBrains Mono', monospace; font-size: 0.65rem;">
							{stepStats.failed} failed
						</span>
					{/if}
					<span style="color: var(--palais-gold); font-family: 'JetBrains Mono', monospace; font-size: 0.72rem; font-weight: 600;">
						{progressPct}%
					</span>
				</div>
			</div>
			<div class="h-1.5 rounded-full" style="background: rgba(255,255,255,0.06);">
				<div
					class="h-1.5 rounded-full transition-all"
					style="
						width: {progressPct}%;
						background: {stepStats.failed > 0 ? 'var(--palais-red)' : 'linear-gradient(90deg, var(--palais-gold), rgba(212,168,67,0.6))'};
						box-shadow: {stepStats.failed > 0 ? '0 0 8px rgba(229,57,53,0.4)' : '0 0 8px rgba(212,168,67,0.3)'};
					"
				></div>
			</div>
		</div>
	{/if}

	<!-- ── STEP TIMELINE ──────────────────────────────────────────── -->
	<section>
		<h2
			class="flex items-center gap-2 mb-4"
			style="font-family: 'Orbitron', sans-serif; font-size: 0.6rem; letter-spacing: 0.25em; text-transform: uppercase; color: var(--palais-gold); opacity: 0.7;"
		>
			<span style="width: 8px; height: 1px; background: var(--palais-gold); opacity: 0.5; display: inline-block; flex-shrink: 0;"></span>
			STEP TIMELINE
			{#if steps.length > 0}
				<span
					class="px-2 py-0.5 rounded-full"
					style="font-family: 'Orbitron', sans-serif; font-size: 0.5rem; color: var(--palais-gold); border: 1px solid rgba(212,168,67,0.3); background: rgba(212,168,67,0.06);"
				>
					{steps.length}
				</span>
			{/if}
			<span style="flex: 1; height: 1px; background: linear-gradient(to right, rgba(212,168,67,0.3), transparent); display: inline-block;"></span>
		</h2>

		{#if steps.length === 0}
			<div class="glass-panel rounded-xl p-12 text-center" style="border: 1px solid rgba(212,168,67,0.1);">
				<p style="color: var(--palais-text-muted); font-family: 'JetBrains Mono', monospace; font-size: 0.82rem;">
					<span style="color: rgba(212,168,67,0.4);">// </span>No steps recorded yet.
					{#if deployment.status === 'running'}
						Pipeline is initializing...
					{/if}
				</p>
			</div>
		{:else}
			<div class="relative">
				<!-- Vertical timeline line -->
				<div
					class="absolute left-[19px] top-5 bottom-5 w-px"
					style="background: linear-gradient(to bottom, rgba(212,168,67,0.3), rgba(212,168,67,0.05));"
					aria-hidden="true"
				></div>

				<div class="space-y-2">
					{#each steps as step, i (step.id)}
						{@const isExpanded = expandedSteps.has(step.id)}
						{@const hasOutput = !!(step.output || step.error)}
						{@const stepDur = stepDuration(step.startedAt, step.completedAt)}

						<div
							class="relative"
							style="animation: fadeSlideUp 0.3s ease-out both; animation-delay: {i * 40}ms;"
						>
							<!-- Step indicator dot -->
							<div
								class="absolute left-0 top-3.5 w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0"
								style="
									background: {statusBg(step.status)};
									border: 1.5px solid {statusBorder(step.status)};
									z-index: 2;
								"
								aria-hidden="true"
							>
								{#if step.status === 'running'}
									<!-- Spinning indicator -->
									<div
										style="
											width: 14px; height: 14px;
											border: 2px solid rgba(212,168,67,0.2);
											border-top-color: var(--palais-gold);
											border-radius: 50%;
											animation: spin 0.8s linear infinite;
										"
									></div>
								{:else if step.status === 'success'}
									<!-- Checkmark -->
									<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--palais-green)" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
										<polyline points="20 6 9 17 4 12"/>
									</svg>
								{:else if step.status === 'failed'}
									<!-- X -->
									<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--palais-red)" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
										<line x1="18" y1="6" x2="6" y2="18"/>
										<line x1="6" y1="6" x2="18" y2="18"/>
									</svg>
								{:else}
									<!-- Pending dot -->
									<div style="width: 6px; height: 6px; border-radius: 50%; background: rgba(138,138,154,0.4);"></div>
								{/if}
							</div>

							<!-- Step card -->
							<div
								class="ml-14 glass-panel rounded-lg"
								style="
									border: 1px solid {isExpanded ? statusBorder(step.status) : 'rgba(212,168,67,0.1)'};
									transition: border-color 0.2s;
								"
							>
								<!-- Step header (always visible) -->
								<button
									class="w-full px-4 py-3 text-left"
									style="background: none; border: none; cursor: {hasOutput ? 'pointer' : 'default'};"
									onclick={() => { if (hasOutput) toggleStep(step.id); }}
									disabled={!hasOutput}
								>
									<div class="flex items-center justify-between gap-4">
										<div class="flex items-center gap-3 flex-1 min-w-0">
											<!-- Step number -->
											<span
												class="flex-shrink-0 w-5 h-5 rounded flex items-center justify-center"
												style="background: rgba(212,168,67,0.08); font-family: 'JetBrains Mono', monospace; font-size: 0.55rem; color: rgba(212,168,67,0.5);"
											>
												{step.position + 1}
											</span>

											<!-- Step name -->
											<span style="color: {step.status === 'pending' ? 'rgba(138,138,154,0.5)' : 'var(--palais-text)'}; font-family: 'JetBrains Mono', monospace; font-size: 0.78rem; font-weight: 500;" class="truncate">
												{step.stepName}
											</span>
										</div>

										<div class="flex items-center gap-3 flex-shrink-0">
											<!-- Duration -->
											{#if stepDur !== '—'}
												<span style="color: var(--palais-cyan); font-family: 'JetBrains Mono', monospace; font-size: 0.65rem;">
													{stepDur}
												</span>
											{/if}

											<!-- Status badge -->
											<span
												class="flex items-center gap-1.5 px-2 py-0.5 rounded"
												style="background: {statusBg(step.status)}; border: 1px solid {statusBorder(step.status)};"
											>
												<span
													class="w-1.5 h-1.5 rounded-full"
													style="background: {statusColor(step.status)}; {step.status === 'running' ? 'animation: pulseGold 1.2s ease-in-out infinite;' : ''}"
												></span>
												<span style="color: {statusColor(step.status)}; font-family: 'Orbitron', sans-serif; font-size: 0.48rem; letter-spacing: 0.08em; white-space: nowrap;">
													{step.status.toUpperCase()}
												</span>
											</span>

											<!-- Expand chevron -->
											{#if hasOutput}
												<svg
													width="12" height="12" viewBox="0 0 24 24" fill="none"
													stroke="rgba(212,168,67,0.4)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
													style="transition: transform 0.2s; transform: rotate({isExpanded ? '180deg' : '0deg'});"
													aria-hidden="true"
												>
													<polyline points="6 9 12 15 18 9"/>
												</svg>
											{/if}
										</div>
									</div>
								</button>

								<!-- Expandable output section -->
								{#if isExpanded && hasOutput}
									<div
										style="
											border-top: 1px solid rgba(212,168,67,0.1);
											padding: 0;
											animation: fadeSlideUp 0.2s ease-out both;
										"
									>
										{#if step.error}
											<div class="px-4 py-3" style="border-bottom: {step.output ? '1px solid rgba(212,168,67,0.08)' : 'none'};">
												<p style="color: rgba(229,57,53,0.7); font-family: 'Orbitron', sans-serif; font-size: 0.5rem; letter-spacing: 0.18em; margin-bottom: 6px;">
													ERROR
												</p>
												<pre style="
													color: var(--palais-red);
													font-family: 'JetBrains Mono', monospace;
													font-size: 0.68rem;
													line-height: 1.6;
													white-space: pre-wrap;
													word-break: break-all;
													max-height: 200px;
													overflow-y: auto;
													margin: 0;
												">{step.error}</pre>
											</div>
										{/if}
										{#if step.output}
											<div class="px-4 py-3">
												<p style="color: rgba(212,168,67,0.5); font-family: 'Orbitron', sans-serif; font-size: 0.5rem; letter-spacing: 0.18em; margin-bottom: 6px;">
													OUTPUT
												</p>
												<pre style="
													color: rgba(232,230,227,0.75);
													font-family: 'JetBrains Mono', monospace;
													font-size: 0.68rem;
													line-height: 1.6;
													white-space: pre-wrap;
													word-break: break-all;
													max-height: 300px;
													overflow-y: auto;
													margin: 0;
													background: rgba(0,0,0,0.25);
													padding: 10px;
													border-radius: 6px;
												">{step.output}</pre>
											</div>
										{/if}
									</div>
								{/if}
							</div>
						</div>
					{/each}
				</div>
			</div>
		{/if}
	</section>
</div>

<!-- ══════════════════════════════════════════════════════════
     ROLLBACK MODAL
     ══════════════════════════════════════════════════════════ -->
{#if rollbackModalOpen}
	<div
		style="position: fixed; inset: 0; z-index: 100; background: rgba(0,0,0,0.72); backdrop-filter: blur(4px);"
		onclick={closeRollback}
		role="presentation"
	></div>

	<div
		class="glass-panel hud-bracket rounded-xl"
		style="
			position: fixed; top: 50%; left: 50%; transform: translate(-50%, -50%);
			z-index: 101; width: min(420px, 94vw); padding: 1.75rem;
			border: 1px solid rgba(232,131,58,0.35);
			box-shadow: 0 8px 64px 0 rgba(0,0,0,0.65);
			animation: cardReveal 0.25s ease-out both;
		"
		role="dialog"
		aria-label="Confirm rollback"
	>
		<span class="hud-bracket-bottom" style="display: block;">
			<div class="flex items-center justify-between mb-4">
				<h2 style="color: var(--palais-amber); font-family: 'Orbitron', sans-serif; font-size: 0.9rem; letter-spacing: 0.1em;">
					CONFIRM ROLLBACK
				</h2>
				<button
					onclick={closeRollback}
					style="background: none; border: none; cursor: pointer; color: rgba(232,131,58,0.4); font-size: 1.3rem; line-height: 1; padding: 2px 6px; font-family: 'JetBrains Mono', monospace;"
				>x</button>
			</div>

			<div class="rounded-lg p-3 mb-5" style="background: rgba(232,131,58,0.07); border: 1px solid rgba(232,131,58,0.2);">
				<p style="color: var(--palais-text); font-size: 0.8rem; line-height: 1.5;">
					Roll back <strong style="color: var(--palais-amber);">{deployment.workspaceName}</strong> to
					<strong style="color: var(--palais-gold); font-family: 'JetBrains Mono', monospace;">{deployment.version ?? 'this version'}</strong>
					(deployment #{deployment.id})?
				</p>
				<p style="color: var(--palais-text-muted); font-size: 0.72rem; margin-top: 6px;">
					A new rollback deployment will be created.
				</p>
			</div>

			{#if rollbackError}
				<p style="color: var(--palais-red); font-family: 'JetBrains Mono', monospace; font-size: 0.72rem; margin-bottom: 12px;">
					ERR: {rollbackError}
				</p>
			{/if}

			<div class="flex gap-3 justify-end">
				<button
					onclick={closeRollback}
					disabled={rollingBack}
					style="padding: 8px 18px; border-radius: 6px; cursor: pointer; background: transparent; color: rgba(232,131,58,0.55); border: 1px solid rgba(232,131,58,0.2); font-family: 'Orbitron', sans-serif; font-size: 0.6rem; letter-spacing: 0.12em;"
				>
					CANCEL
				</button>
				<button
					onclick={confirmRollback}
					disabled={rollingBack}
					style="
						padding: 8px 20px; border-radius: 6px; cursor: pointer;
						background: rgba(232,131,58,0.15); color: var(--palais-amber);
						border: 1px solid rgba(232,131,58,0.4);
						font-family: 'Orbitron', sans-serif; font-size: 0.6rem; letter-spacing: 0.12em;
						{rollingBack ? 'opacity: 0.5; cursor: not-allowed;' : ''}
					"
				>
					{rollingBack ? 'ROLLING BACK...' : 'CONFIRM ROLLBACK'}
				</button>
			</div>
		</span>
	</div>
{/if}

<style>
	@keyframes spin {
		to { transform: rotate(360deg); }
	}
</style>
