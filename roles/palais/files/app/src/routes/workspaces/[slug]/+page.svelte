<script lang="ts">
	import { goto, invalidateAll } from '$app/navigation';

	let { data } = $props();

	const { workspace, server, deploymentHistory } = $derived(data);

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
			case 'cancelled':  return 'rgba(138,138,154,0.08)';
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

	function formatDate(date: Date | null | string): string {
		if (!date) return '—';
		return new Date(date).toLocaleString('fr-FR', {
			day: '2-digit', month: 'short', year: 'numeric',
			hour: '2-digit', minute: '2-digit'
		});
	}

	// ── Deploy modal ───────────────────────────────────────────────
	let deployModalOpen = $state(false);
	let deployVersion = $state(workspace.latestVersion ?? '');
	let deploying = $state(false);
	let deployError = $state('');

	function openDeployModal() {
		deployVersion = workspace.latestVersion ?? workspace.currentVersion ?? '';
		deployError = '';
		deployModalOpen = true;
	}

	function closeDeployModal() {
		deployModalOpen = false;
		deployError = '';
	}

	async function launchDeploy() {
		if (!deployVersion.trim()) {
			deployError = 'Version is required';
			return;
		}
		deploying = true;
		deployError = '';
		try {
			const res = await fetch(`/api/v2/workspaces/${workspace.slug}/deploy`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ version: deployVersion.trim() }),
			});
			if (!res.ok) {
				const body = await res.json().catch(() => ({ message: `HTTP ${res.status}` }));
				deployError = body.message ?? `HTTP ${res.status}`;
			} else {
				const body = await res.json();
				closeDeployModal();
				if (body.data?.id) {
					await goto(`/deploy/${body.data.id}`);
				} else {
					await invalidateAll();
				}
			}
		} catch {
			deployError = 'Network error';
		} finally {
			deploying = false;
		}
	}

	// ── Rollback ───────────────────────────────────────────────────
	let rollbackTarget = $state<{ id: number; version: string | null } | null>(null);
	let rollingBack = $state(false);
	let rollbackError = $state('');

	function openRollback(deployment: { id: number; version: string | null }) {
		rollbackTarget = { id: deployment.id, version: deployment.version };
		rollbackError = '';
	}

	function closeRollback() {
		rollbackTarget = null;
		rollbackError = '';
	}

	async function confirmRollback() {
		if (!rollbackTarget) return;
		rollingBack = true;
		rollbackError = '';
		try {
			const res = await fetch(`/api/v2/workspaces/${workspace.slug}/rollback`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ deploymentId: rollbackTarget.id }),
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

	const currentDeployRunning = $derived(
		deploymentHistory[0]?.status === 'running'
	);
</script>

<svelte:head><title>Palais — {workspace.name}</title></svelte:head>

<div class="space-y-8" style="animation: fadeSlideUp 0.45s ease-out both;">

	<!-- ── BREADCRUMB + HEADER ────────────────────────────────────── -->
	<header class="flex flex-col gap-3">
		<!-- Breadcrumb -->
		<nav style="font-family: 'JetBrains Mono', monospace; font-size: 0.68rem;">
			<a href="/workspaces" style="color: rgba(212,168,67,0.5); text-decoration: none; transition: color 0.15s;"
				onmouseenter={(e) => { (e.currentTarget as HTMLElement).style.color = 'var(--palais-gold)'; }}
				onmouseleave={(e) => { (e.currentTarget as HTMLElement).style.color = 'rgba(212,168,67,0.5)'; }}
			>WORKSPACES</a>
			<span style="color: rgba(212,168,67,0.25); margin: 0 6px;">/</span>
			<span style="color: var(--palais-text-muted);">{workspace.slug}</span>
		</nav>

		<div class="flex items-start justify-between gap-4 flex-wrap">
			<div>
				<p
					class="uppercase tracking-[0.35em] mb-1"
					style="color: var(--palais-gold); opacity: 0.5; font-family: 'Orbitron', sans-serif; font-size: 0.5rem;"
				>
					WORKSPACE — DETAIL
				</p>
				<h1
					class="font-bold tracking-widest"
					style="
						color: var(--palais-gold);
						font-family: 'Orbitron', sans-serif;
						font-size: clamp(1.2rem, 3vw, 1.75rem);
						text-shadow: 0 0 24px rgba(212,168,67,0.35);
					"
				>
					{workspace.name.toUpperCase()}
				</h1>
				{#if workspace.description}
					<p class="mt-1" style="color: var(--palais-text-muted); font-size: 0.82rem; max-width: 520px;">
						{workspace.description}
					</p>
				{/if}
			</div>

			<!-- Actions -->
			<div class="flex items-center gap-2 flex-wrap">
				{#if workspace.repoUrl}
					<a
						href={workspace.repoUrl}
						target="_blank"
						rel="noopener noreferrer"
						style="
							padding: 7px 14px; border-radius: 6px; text-decoration: none;
							background: transparent;
							color: var(--palais-cyan); border: 1px solid rgba(79,195,247,0.25);
							font-family: 'Orbitron', sans-serif; font-size: 0.58rem; letter-spacing: 0.1em;
							transition: all 0.2s;
						"
						onmouseenter={(e) => {
							const el = e.currentTarget as HTMLElement;
							el.style.background = 'rgba(79,195,247,0.08)';
							el.style.borderColor = 'rgba(79,195,247,0.45)';
						}}
						onmouseleave={(e) => {
							const el = e.currentTarget as HTMLElement;
							el.style.background = 'transparent';
							el.style.borderColor = 'rgba(79,195,247,0.25)';
						}}
					>
						REPO
					</a>
				{/if}

				<button
					onclick={openDeployModal}
					disabled={currentDeployRunning}
					style="
						padding: 7px 18px; border-radius: 6px; cursor: {currentDeployRunning ? 'not-allowed' : 'pointer'};
						background: {currentDeployRunning ? 'rgba(212,168,67,0.06)' : 'rgba(212,168,67,0.15)'};
						color: {currentDeployRunning ? 'rgba(212,168,67,0.35)' : 'var(--palais-gold)'};
						border: 1px solid {currentDeployRunning ? 'rgba(212,168,67,0.15)' : 'rgba(212,168,67,0.4)'};
						font-family: 'Orbitron', sans-serif; font-size: 0.6rem; letter-spacing: 0.12em;
						transition: all 0.2s;
					"
					onmouseenter={(e) => {
						if (!currentDeployRunning) {
							const el = e.currentTarget as HTMLElement;
							el.style.background = 'rgba(212,168,67,0.22)';
							el.style.boxShadow = '0 0 16px rgba(212,168,67,0.22)';
						}
					}}
					onmouseleave={(e) => {
						if (!currentDeployRunning) {
							const el = e.currentTarget as HTMLElement;
							el.style.background = 'rgba(212,168,67,0.15)';
							el.style.boxShadow = '';
						}
					}}
				>
					{currentDeployRunning ? 'DEPLOYING...' : 'DEPLOY'}
				</button>
			</div>
		</div>

		<div style="height: 1px; background: linear-gradient(90deg, var(--palais-gold) 0%, rgba(212,168,67,0.06) 100%); opacity: 0.35;"></div>
	</header>

	<!-- ── INFO CARDS ROW ─────────────────────────────────────────── -->
	<section>
		<h2
			class="flex items-center gap-2 mb-4"
			style="font-family: 'Orbitron', sans-serif; font-size: 0.6rem; letter-spacing: 0.25em; text-transform: uppercase; color: var(--palais-gold); opacity: 0.7;"
		>
			<span style="width: 8px; height: 1px; background: var(--palais-gold); opacity: 0.5; display: inline-block; flex-shrink: 0;"></span>
			WORKSPACE INFO
			<span style="flex: 1; height: 1px; background: linear-gradient(to right, rgba(212,168,67,0.3), transparent); display: inline-block;"></span>
		</h2>

		<div class="grid grid-cols-2 md:grid-cols-4 gap-3">
			<!-- Version card -->
			<div class="glass-panel rounded-lg p-4" style="border: 1px solid rgba(212,168,67,0.15);">
				<p style="color: rgba(212,168,67,0.5); font-family: 'Orbitron', sans-serif; font-size: 0.52rem; letter-spacing: 0.18em; text-transform: uppercase; margin-bottom: 6px;">
					CURRENT VERSION
				</p>
				<p style="color: var(--palais-gold); font-family: 'JetBrains Mono', monospace; font-size: 1rem; font-weight: 600;">
					{workspace.currentVersion ?? '—'}
				</p>
				{#if workspace.latestVersion && workspace.latestVersion !== workspace.currentVersion}
					<p style="color: var(--palais-cyan); font-family: 'JetBrains Mono', monospace; font-size: 0.65rem; margin-top: 3px;">
						latest: {workspace.latestVersion}
					</p>
				{/if}
			</div>

			<!-- Stack card -->
			<div class="glass-panel rounded-lg p-4" style="border: 1px solid rgba(212,168,67,0.15);">
				<p style="color: rgba(212,168,67,0.5); font-family: 'Orbitron', sans-serif; font-size: 0.52rem; letter-spacing: 0.18em; text-transform: uppercase; margin-bottom: 6px;">
					STACK
				</p>
				<p style="color: var(--palais-text); font-family: 'JetBrains Mono', monospace; font-size: 0.85rem;">
					{workspace.stack ?? '—'}
				</p>
			</div>

			<!-- Server card -->
			<div class="glass-panel rounded-lg p-4" style="border: 1px solid rgba(212,168,67,0.15);">
				<p style="color: rgba(212,168,67,0.5); font-family: 'Orbitron', sans-serif; font-size: 0.52rem; letter-spacing: 0.18em; text-transform: uppercase; margin-bottom: 6px;">
					SERVER
				</p>
				{#if server}
					<p style="color: var(--palais-cyan); font-family: 'JetBrains Mono', monospace; font-size: 0.82rem;">
						{server.name}
					</p>
					{#if server.location}
						<p style="color: rgba(138,138,154,0.5); font-family: 'JetBrains Mono', monospace; font-size: 0.62rem; margin-top: 2px;">
							{server.location}
						</p>
					{/if}
				{:else}
					<p style="color: var(--palais-text-muted); font-family: 'JetBrains Mono', monospace; font-size: 0.82rem;">—</p>
				{/if}
			</div>

			<!-- Domain card -->
			<div class="glass-panel rounded-lg p-4" style="border: 1px solid rgba(212,168,67,0.15);">
				<p style="color: rgba(212,168,67,0.5); font-family: 'Orbitron', sans-serif; font-size: 0.52rem; letter-spacing: 0.18em; text-transform: uppercase; margin-bottom: 6px;">
					DOMAIN
				</p>
				{#if workspace.domainPattern}
					<p style="color: var(--palais-text-muted); font-family: 'JetBrains Mono', monospace; font-size: 0.72rem; word-break: break-all;">
						{workspace.domainPattern}
					</p>
				{:else}
					<p style="color: var(--palais-text-muted); font-family: 'JetBrains Mono', monospace; font-size: 0.82rem;">—</p>
				{/if}
			</div>
		</div>
	</section>

	<!-- ── DEPLOYMENT HISTORY TABLE ───────────────────────────────── -->
	<section>
		<h2
			class="flex items-center gap-2 mb-4"
			style="font-family: 'Orbitron', sans-serif; font-size: 0.6rem; letter-spacing: 0.25em; text-transform: uppercase; color: var(--palais-gold); opacity: 0.7;"
		>
			<span style="width: 8px; height: 1px; background: var(--palais-gold); opacity: 0.5; display: inline-block; flex-shrink: 0;"></span>
			DEPLOYMENT HISTORY
			<span
				class="px-2 py-0.5 rounded-full"
				style="font-family: 'Orbitron', sans-serif; font-size: 0.5rem; color: var(--palais-gold); border: 1px solid rgba(212,168,67,0.3); background: rgba(212,168,67,0.06);"
			>
				{deploymentHistory.length}
			</span>
			<span style="flex: 1; height: 1px; background: linear-gradient(to right, rgba(212,168,67,0.3), transparent); display: inline-block;"></span>
		</h2>

		{#if deploymentHistory.length === 0}
			<div class="glass-panel rounded-xl p-12 text-center" style="border: 1px solid rgba(212,168,67,0.1);">
				<p style="color: var(--palais-text-muted); font-family: 'JetBrains Mono', monospace; font-size: 0.82rem;">
					<span style="color: rgba(212,168,67,0.4);">// </span>No deployments yet.
				</p>
			</div>
		{:else}
			<div class="glass-panel rounded-xl overflow-hidden" style="border: 1px solid rgba(212,168,67,0.15);">
				<!-- Table header -->
				<div
					class="grid gap-4 px-5 py-3"
					style="
						grid-template-columns: 80px 1fr 90px 140px 80px 90px;
						background: rgba(212,168,67,0.04);
						border-bottom: 1px solid rgba(212,168,67,0.12);
					"
				>
					{#each ['ID', 'VERSION', 'STATUS', 'STARTED', 'DURATION', 'ACTIONS'] as col}
						<span style="color: rgba(212,168,67,0.5); font-family: 'Orbitron', sans-serif; font-size: 0.52rem; letter-spacing: 0.2em; text-transform: uppercase;">
							{col}
						</span>
					{/each}
				</div>

				<!-- Table rows -->
				{#each deploymentHistory as dep, i (dep.id)}
					<div
						class="grid gap-4 px-5 py-3.5 items-center"
						style="
							grid-template-columns: 80px 1fr 90px 140px 80px 90px;
							border-bottom: {i < deploymentHistory.length - 1 ? '1px solid rgba(212,168,67,0.07)' : 'none'};
							transition: background 0.15s;
							animation: fadeSlideUp 0.3s ease-out both;
							animation-delay: {i * 30}ms;
						"
						onmouseenter={(e) => { (e.currentTarget as HTMLElement).style.background = 'rgba(212,168,67,0.03)'; }}
						onmouseleave={(e) => { (e.currentTarget as HTMLElement).style.background = ''; }}
						role="row"
					>
						<!-- ID -->
						<span style="color: rgba(212,168,67,0.45); font-family: 'JetBrains Mono', monospace; font-size: 0.72rem;">
							#{dep.id}
						</span>

						<!-- Version + type -->
						<div class="flex flex-col gap-0.5 min-w-0">
							<span style="color: var(--palais-text); font-family: 'JetBrains Mono', monospace; font-size: 0.78rem; font-weight: 500;">
								{dep.version ?? '—'}
							</span>
							{#if dep.deployType !== 'update'}
								<span style="color: var(--palais-amber); font-family: 'JetBrains Mono', monospace; font-size: 0.6rem; opacity: 0.75;">
									{dep.deployType}
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
							<span style="color: {statusColor(dep.status)}; font-family: 'Orbitron', sans-serif; font-size: 0.52rem; letter-spacing: 0.08em; white-space: nowrap;">
								{dep.status.toUpperCase().replace('_', ' ')}
							</span>
						</span>

						<!-- Started at -->
						<span style="color: var(--palais-text-muted); font-family: 'JetBrains Mono', monospace; font-size: 0.68rem; white-space: nowrap;">
							{formatDate(dep.startedAt)}
						</span>

						<!-- Duration -->
						<span style="color: var(--palais-cyan); font-family: 'JetBrains Mono', monospace; font-size: 0.72rem;">
							{formatDuration(dep.durationMs)}
						</span>

						<!-- Actions -->
						<div class="flex items-center gap-2">
							<a
								href="/deploy/{dep.id}"
								style="
									color: rgba(212,168,67,0.55); font-family: 'Orbitron', sans-serif;
									font-size: 0.5rem; letter-spacing: 0.1em; text-decoration: none;
									padding: 3px 7px; border-radius: 4px; border: 1px solid rgba(212,168,67,0.2);
									transition: all 0.15s; white-space: nowrap;
								"
								onmouseenter={(e) => {
									const el = e.currentTarget as HTMLElement;
									el.style.color = 'var(--palais-gold)';
									el.style.borderColor = 'rgba(212,168,67,0.4)';
									el.style.background = 'rgba(212,168,67,0.06)';
								}}
								onmouseleave={(e) => {
									const el = e.currentTarget as HTMLElement;
									el.style.color = 'rgba(212,168,67,0.55)';
									el.style.borderColor = 'rgba(212,168,67,0.2)';
									el.style.background = '';
								}}
							>
								VIEW
							</a>

							{#if dep.status === 'success'}
								<button
									onclick={() => openRollback(dep)}
									style="
										color: rgba(232,131,58,0.6); font-family: 'Orbitron', sans-serif;
										font-size: 0.5rem; letter-spacing: 0.08em;
										padding: 3px 7px; border-radius: 4px;
										background: none; border: 1px solid rgba(232,131,58,0.2);
										cursor: pointer; transition: all 0.15s; white-space: nowrap;
									"
									onmouseenter={(e) => {
										const el = e.currentTarget as HTMLElement;
										el.style.color = 'var(--palais-amber)';
										el.style.borderColor = 'rgba(232,131,58,0.4)';
										el.style.background = 'rgba(232,131,58,0.06)';
									}}
									onmouseleave={(e) => {
										const el = e.currentTarget as HTMLElement;
										el.style.color = 'rgba(232,131,58,0.6)';
										el.style.borderColor = 'rgba(232,131,58,0.2)';
										el.style.background = '';
									}}
								>
									ROLLBACK
								</button>
							{/if}
						</div>
					</div>
				{/each}
			</div>
		{/if}
	</section>
</div>

<!-- ══════════════════════════════════════════════════════════
     DEPLOY MODAL
     ══════════════════════════════════════════════════════════ -->
{#if deployModalOpen}
	<div
		style="position: fixed; inset: 0; z-index: 100; background: rgba(0,0,0,0.72); backdrop-filter: blur(4px);"
		onclick={closeDeployModal}
		role="presentation"
	></div>

	<div
		class="glass-panel hud-bracket rounded-xl"
		style="
			position: fixed; top: 50%; left: 50%; transform: translate(-50%, -50%);
			z-index: 101; width: min(440px, 94vw); padding: 1.75rem;
			border: 1px solid rgba(212,168,67,0.32);
			box-shadow: 0 8px 64px 0 rgba(0,0,0,0.65), 0 0 0 1px rgba(212,168,67,0.08);
			animation: cardReveal 0.25s ease-out both;
		"
		role="dialog"
		aria-label="Deploy workspace"
	>
		<span class="hud-bracket-bottom" style="display: block;">
			<div class="flex items-center justify-between mb-5">
				<div>
					<p style="color: rgba(212,168,67,0.5); font-family: 'Orbitron', sans-serif; font-size: 0.5rem; letter-spacing: 0.25em; margin-bottom: 4px;">
						DEPLOY — {workspace.slug.toUpperCase()}
					</p>
					<h2 style="color: var(--palais-gold); font-family: 'Orbitron', sans-serif; font-size: 0.9rem; letter-spacing: 0.1em;">
						LAUNCH DEPLOYMENT
					</h2>
				</div>
				<button
					onclick={closeDeployModal}
					style="background: none; border: none; cursor: pointer; color: rgba(212,168,67,0.4); font-size: 1.3rem; line-height: 1; padding: 2px 6px; font-family: 'JetBrains Mono', monospace;"
				>x</button>
			</div>

			<div class="mb-5">
				<label style="display: block; font-family: 'Orbitron', sans-serif; font-size: 0.58rem; letter-spacing: 0.2em; color: rgba(212,168,67,0.55); text-transform: uppercase; margin-bottom: 8px;">
					VERSION / GIT TAG
				</label>
				<input
					type="text"
					bind:value={deployVersion}
					placeholder="e.g. v1.2.0, main, sha256..."
					style="
						width: 100%; padding: 9px 12px;
						background: rgba(0,0,0,0.35); border-radius: 6px;
						border: 1px solid rgba(212,168,67,0.22);
						color: var(--palais-gold); font-family: 'JetBrains Mono', monospace; font-size: 0.85rem;
						outline: none; transition: border-color 0.2s;
					"
					onfocus={(e) => { (e.currentTarget as HTMLElement).style.borderColor = 'rgba(212,168,67,0.55)'; }}
					onblur={(e) => { (e.currentTarget as HTMLElement).style.borderColor = 'rgba(212,168,67,0.22)'; }}
					onkeydown={(e) => { if (e.key === 'Enter') launchDeploy(); }}
				/>
			</div>

			{#if deployError}
				<p style="color: var(--palais-red); font-family: 'JetBrains Mono', monospace; font-size: 0.72rem; margin-bottom: 12px;">
					ERR: {deployError}
				</p>
			{/if}

			<div class="flex gap-3 justify-end">
				<button
					onclick={closeDeployModal}
					disabled={deploying}
					style="padding: 8px 18px; border-radius: 6px; cursor: pointer; background: transparent; color: rgba(212,168,67,0.55); border: 1px solid rgba(212,168,67,0.2); font-family: 'Orbitron', sans-serif; font-size: 0.6rem; letter-spacing: 0.12em;"
				>
					CANCEL
				</button>
				<button
					onclick={launchDeploy}
					disabled={deploying || !deployVersion.trim()}
					style="
						padding: 8px 20px; border-radius: 6px; cursor: pointer;
						background: rgba(212,168,67,0.15); color: var(--palais-gold);
						border: 1px solid rgba(212,168,67,0.4);
						font-family: 'Orbitron', sans-serif; font-size: 0.6rem; letter-spacing: 0.12em;
						transition: all 0.2s;
						{(deploying || !deployVersion.trim()) ? 'opacity: 0.5; cursor: not-allowed;' : ''}
					"
				>
					{deploying ? 'LAUNCHING...' : 'LAUNCH DEPLOY'}
				</button>
			</div>
		</span>
	</div>
{/if}

<!-- ══════════════════════════════════════════════════════════
     ROLLBACK MODAL
     ══════════════════════════════════════════════════════════ -->
{#if rollbackTarget}
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
					Roll back <strong style="color: var(--palais-amber);">{workspace.name}</strong> to version
					<strong style="color: var(--palais-gold); font-family: 'JetBrains Mono', monospace;">{rollbackTarget.version ?? 'unknown'}</strong>
					(deployment #{rollbackTarget.id})?
				</p>
				<p style="color: var(--palais-text-muted); font-size: 0.72rem; margin-top: 6px;">
					This will trigger a new deployment with the rollback flag.
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
