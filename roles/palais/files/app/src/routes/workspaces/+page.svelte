<script lang="ts">
	import { goto } from '$app/navigation';

	let { data } = $props();

	// ── Stack badge colors ─────────────────────────────────────────
	const stackColors: Record<string, { bg: string; color: string; border: string }> = {
		svelte:     { bg: 'rgba(255, 62, 0, 0.12)',   color: '#FF6B35',              border: 'rgba(255,107,53,0.3)' },
		sveltekit:  { bg: 'rgba(255, 62, 0, 0.12)',   color: '#FF6B35',              border: 'rgba(255,107,53,0.3)' },
		react:      { bg: 'rgba(0, 212, 255, 0.1)',   color: '#4FC3F7',              border: 'rgba(79,195,247,0.3)' },
		nextjs:     { bg: 'rgba(255,255,255,0.07)',   color: 'rgba(255,255,255,0.7)', border: 'rgba(255,255,255,0.15)' },
		node:       { bg: 'rgba(76, 175, 80, 0.1)',   color: '#4CAF50',              border: 'rgba(76,175,80,0.3)' },
		python:     { bg: 'rgba(255, 197, 37, 0.1)',  color: '#FFC525',              border: 'rgba(255,197,37,0.3)' },
		docker:     { bg: 'rgba(0, 150, 199, 0.1)',   color: '#0096C7',              border: 'rgba(0,150,199,0.3)' },
		ansible:    { bg: 'rgba(212, 168, 67, 0.1)',  color: 'var(--palais-gold)',   border: 'rgba(212,168,67,0.3)' },
	};

	function stackStyle(stack: string | null) {
		if (!stack) return null;
		const key = stack.toLowerCase().replace(/[^a-z]/g, '');
		return stackColors[key] ?? { bg: 'rgba(138,138,154,0.1)', color: 'var(--palais-text-muted)', border: 'rgba(138,138,154,0.2)' };
	}

	// ── Deploy status helpers ──────────────────────────────────────
	function deployStatusColor(status: string) {
		switch (status) {
			case 'success':    return 'var(--palais-green)';
			case 'failed':     return 'var(--palais-red)';
			case 'running':    return 'var(--palais-gold)';
			case 'cancelled':  return 'var(--palais-text-muted)';
			case 'rolled_back': return 'var(--palais-amber)';
			default:           return 'var(--palais-text-muted)';
		}
	}

	function deployStatusBg(status: string) {
		switch (status) {
			case 'success':    return 'rgba(76,175,80,0.1)';
			case 'failed':     return 'rgba(229,57,53,0.1)';
			case 'running':    return 'rgba(212,168,67,0.1)';
			default:           return 'rgba(138,138,154,0.08)';
		}
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

	// ── Deploy confirm modal ───────────────────────────────────────
	interface DeployTarget {
		slug: string;
		name: string;
		latestVersion: string | null;
	}

	let deployTarget = $state<DeployTarget | null>(null);
	let deployVersion = $state('');
	let deploying = $state(false);
	let deployError = $state('');

	function openDeploy(ws: { slug: string; name: string; latestVersion: string | null }) {
		deployTarget = { slug: ws.slug, name: ws.name, latestVersion: ws.latestVersion };
		deployVersion = ws.latestVersion ?? '';
		deployError = '';
	}

	function closeDeploy() {
		deployTarget = null;
		deployVersion = '';
		deployError = '';
	}

	async function confirmDeploy() {
		if (!deployTarget || !deployVersion.trim()) {
			deployError = 'Version is required';
			return;
		}
		deploying = true;
		deployError = '';
		try {
			const res = await fetch(`/api/v2/workspaces/${deployTarget.slug}/deploy`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ version: deployVersion.trim() }),
			});
			if (!res.ok) {
				const body = await res.json().catch(() => ({ message: `HTTP ${res.status}` }));
				deployError = body.message ?? `HTTP ${res.status}`;
			} else {
				const body = await res.json();
				closeDeploy();
				// Navigate to deployment detail if id available
				if (body.data?.id) {
					await goto(`/deploy/${body.data.id}`);
				}
			}
		} catch {
			deployError = 'Network error';
		} finally {
			deploying = false;
		}
	}

	const totalWorkspaces = $derived(data.workspaces.length);
	const activeDeployments = $derived(
		data.workspaces.filter((w) => w.latestDeploy?.status === 'running').length
	);
</script>

<svelte:head><title>Palais — Workspaces</title></svelte:head>

<!-- ══════════════════════════════════════════════════════════
     PAGE WRAPPER
     ══════════════════════════════════════════════════════════ -->
<div class="space-y-8" style="animation: fadeSlideUp 0.45s ease-out both;">

	<!-- ── HUD HEADER ─────────────────────────────────────────────── -->
	<header class="flex flex-col gap-3">
		<div class="flex items-start justify-between gap-4 flex-wrap">
			<div>
				<p
					class="uppercase tracking-[0.35em] mb-1"
					style="color: var(--palais-gold); opacity: 0.55; font-family: 'Orbitron', sans-serif; font-size: 0.5rem;"
				>
					PROJECT REGISTRY — CONTROL PLANE
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
					WORKSPACES
				</h1>
			</div>

			<!-- Stats pills -->
			<div class="flex items-center gap-2 flex-wrap">
				<span
					class="px-3 py-1 rounded-full tracking-wider"
					style="
						background: rgba(212,168,67,0.1);
						color: var(--palais-gold);
						border: 1px solid rgba(212,168,67,0.3);
						font-family: 'Orbitron', sans-serif;
						font-size: 0.6rem;
						letter-spacing: 0.12em;
					"
				>
					{totalWorkspaces} PROJECTS
				</span>
				{#if activeDeployments > 0}
					<span
						class="px-3 py-1 rounded-full tracking-wider"
						style="
							background: rgba(212,168,67,0.1);
							color: var(--palais-gold);
							border: 1px solid rgba(212,168,67,0.35);
							font-family: 'Orbitron', sans-serif;
							font-size: 0.6rem;
							animation: pulseGold 1.5s ease-in-out infinite;
						"
					>
						{activeDeployments} DEPLOYING
					</span>
				{/if}
			</div>
		</div>

		<!-- Gold separator -->
		<div style="height: 1px; background: linear-gradient(90deg, var(--palais-gold) 0%, rgba(212,168,67,0.08) 100%); opacity: 0.4;"></div>
	</header>

	<!-- ── SECTION LABEL ──────────────────────────────────────────── -->
	<div>
		<h2
			class="flex items-center gap-2 mb-5"
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
			ALL WORKSPACES
			<span style="flex: 1; height: 1px; background: linear-gradient(to right, rgba(212,168,67,0.3), transparent); display: inline-block;"></span>
		</h2>

		<!-- ── WORKSPACE GRID ───────────────────────────────────────── -->
		{#if data.workspaces.length === 0}
			<div class="glass-panel rounded-xl p-16 text-center" style="border: 1px solid rgba(212,168,67,0.12);">
				<p style="color: var(--palais-text-muted); font-family: 'JetBrains Mono', monospace; font-size: 0.85rem;">
					<span style="color: rgba(212,168,67,0.4);">// </span>No workspaces registered yet.
				</p>
				<p style="color: rgba(138,138,154,0.5); font-family: 'JetBrains Mono', monospace; font-size: 0.75rem; margin-top: 6px;">
					<span style="color: rgba(212,168,67,0.25);">// </span>POST /api/v2/workspaces to create one.
				</p>
			</div>
		{:else}
			<div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5">
				{#each data.workspaces as ws, i (ws.id)}
					{@const style = stackStyle(ws.stack)}
					{@const deploy = ws.latestDeploy}

					<div
						class="glass-panel hud-bracket rounded-xl p-5 flex flex-col gap-4"
						style="
							border: 1px solid rgba(212,168,67,0.18);
							animation: cardReveal 0.4s ease-out both;
							animation-delay: {i * 60}ms;
							transition: border-color 0.2s, box-shadow 0.2s;
						"
						onmouseenter={(e) => {
							(e.currentTarget as HTMLElement).style.borderColor = 'rgba(212,168,67,0.35)';
							(e.currentTarget as HTMLElement).style.boxShadow = '0 0 24px rgba(212,168,67,0.12)';
						}}
						onmouseleave={(e) => {
							(e.currentTarget as HTMLElement).style.borderColor = 'rgba(212,168,67,0.18)';
							(e.currentTarget as HTMLElement).style.boxShadow = '';
						}}
						role="article"
					>
						<span class="hud-bracket-bottom" style="display: contents;">

							<!-- ── Card header ── -->
							<div class="flex items-start justify-between gap-3">
								<div class="flex-1 min-w-0">
									<a
										href="/workspaces/{ws.slug}"
										class="block"
										style="text-decoration: none;"
									>
										<h3
											class="font-bold tracking-wider truncate"
											style="
												color: var(--palais-gold);
												font-family: 'Orbitron', sans-serif;
												font-size: 0.85rem;
												transition: text-shadow 0.2s;
											"
											onmouseenter={(e) => { (e.currentTarget as HTMLElement).style.textShadow = '0 0 16px rgba(212,168,67,0.6)'; }}
											onmouseleave={(e) => { (e.currentTarget as HTMLElement).style.textShadow = 'none'; }}
										>
											{ws.name.toUpperCase()}
										</h3>
									</a>
									<p style="color: var(--palais-text-muted); font-family: 'JetBrains Mono', monospace; font-size: 0.7rem; margin-top: 2px;">
										/{ws.slug}
									</p>
									{#if ws.description}
										<p class="mt-1 leading-snug line-clamp-2" style="color: var(--palais-text); font-size: 0.75rem; opacity: 0.7;">
											{ws.description}
										</p>
									{/if}
								</div>

								<!-- Stack badge -->
								{#if ws.stack && style}
									<span
										class="flex-shrink-0 px-2 py-0.5 rounded text-xs font-semibold tracking-wider uppercase"
										style="
											background: {style.bg};
											color: {style.color};
											border: 1px solid {style.border};
											font-family: 'JetBrains Mono', monospace;
											font-size: 0.58rem;
											letter-spacing: 0.1em;
											white-space: nowrap;
										"
									>
										{ws.stack}
									</span>
								{/if}
							</div>

							<!-- ── Meta row (server, domain) ── -->
							<div class="space-y-1.5">
								{#if ws.server}
									<div class="flex items-center gap-2">
										<span style="color: rgba(212,168,67,0.45); font-family: 'Orbitron', sans-serif; font-size: 0.55rem; letter-spacing: 0.15em; text-transform: uppercase; width: 48px; flex-shrink: 0;">
											SERVER
										</span>
										<span style="color: var(--palais-cyan); font-family: 'JetBrains Mono', monospace; font-size: 0.72rem;">
											{ws.server.name}
										</span>
									</div>
								{/if}
								{#if ws.domainPattern}
									<div class="flex items-center gap-2">
										<span style="color: rgba(212,168,67,0.45); font-family: 'Orbitron', sans-serif; font-size: 0.55rem; letter-spacing: 0.15em; text-transform: uppercase; width: 48px; flex-shrink: 0;">
											DOMAIN
										</span>
										<span style="color: var(--palais-text-muted); font-family: 'JetBrains Mono', monospace; font-size: 0.72rem;" class="truncate">
											{ws.domainPattern}
										</span>
									</div>
								{/if}
								{#if ws.repoUrl}
									<div class="flex items-center gap-2">
										<span style="color: rgba(212,168,67,0.45); font-family: 'Orbitron', sans-serif; font-size: 0.55rem; letter-spacing: 0.15em; text-transform: uppercase; width: 48px; flex-shrink: 0;">
											REPO
										</span>
										<a
											href={ws.repoUrl}
											target="_blank"
											rel="noopener noreferrer"
											class="truncate"
											style="color: var(--palais-cyan); font-family: 'JetBrains Mono', monospace; font-size: 0.7rem; text-decoration: none; opacity: 0.7; transition: opacity 0.15s;"
											onmouseenter={(e) => { (e.currentTarget as HTMLElement).style.opacity = '1'; }}
											onmouseleave={(e) => { (e.currentTarget as HTMLElement).style.opacity = '0.7'; }}
										>
											{ws.repoUrl.replace('https://github.com/', '')}
										</a>
									</div>
								{/if}
							</div>

							<!-- ── Deploy status row ── -->
							<div
								class="rounded-lg px-3 py-2.5 flex items-center justify-between gap-3"
								style="background: rgba(0,0,0,0.25); border: 1px solid rgba(212,168,67,0.1);"
							>
								<div class="flex flex-col gap-0.5 min-w-0">
									<span style="color: rgba(212,168,67,0.5); font-family: 'Orbitron', sans-serif; font-size: 0.52rem; letter-spacing: 0.18em; text-transform: uppercase;">
										LAST DEPLOY
									</span>
									{#if deploy}
										<div class="flex items-center gap-2 flex-wrap">
											<!-- Status dot + badge -->
											<span
												class="flex items-center gap-1.5 px-2 py-0.5 rounded"
												style="
													background: {deployStatusBg(deploy.status)};
													border: 1px solid {deployStatusColor(deploy.status)}33;
												"
											>
												<span
													class="w-1.5 h-1.5 rounded-full flex-shrink-0"
													style="
														background: {deployStatusColor(deploy.status)};
														{deploy.status === 'running' ? 'animation: pulseGold 1.2s ease-in-out infinite;' : ''}
													"
												></span>
												<span style="color: {deployStatusColor(deploy.status)}; font-family: 'Orbitron', sans-serif; font-size: 0.55rem; letter-spacing: 0.1em;">
													{deploy.status.toUpperCase()}
												</span>
											</span>
											{#if deploy.version}
												<span style="color: var(--palais-text-muted); font-family: 'JetBrains Mono', monospace; font-size: 0.68rem;">
													{deploy.version}
												</span>
											{/if}
											<span style="color: rgba(138,138,154,0.5); font-family: 'JetBrains Mono', monospace; font-size: 0.62rem;">
												{relativeTime(deploy.startedAt)}
											</span>
										</div>
									{:else}
										<span style="color: rgba(138,138,154,0.4); font-family: 'JetBrains Mono', monospace; font-size: 0.7rem;">
											No deployments yet
										</span>
									{/if}
								</div>

								<!-- Version display -->
								{#if ws.currentVersion}
									<span style="color: rgba(212,168,67,0.6); font-family: 'JetBrains Mono', monospace; font-size: 0.7rem; flex-shrink: 0;">
										v{ws.currentVersion}
									</span>
								{/if}
							</div>

							<!-- ── Card footer actions ── -->
							<div class="flex items-center gap-2 pt-1" style="border-top: 1px solid rgba(212,168,67,0.08);">
								<!-- View detail link -->
								<a
									href="/workspaces/{ws.slug}"
									style="
										flex: 1;
										padding: 6px 10px;
										border-radius: 6px;
										text-align: center;
										text-decoration: none;
										background: transparent;
										color: rgba(212,168,67,0.6);
										border: 1px solid rgba(212,168,67,0.2);
										font-family: 'Orbitron', sans-serif;
										font-size: 0.55rem;
										letter-spacing: 0.12em;
										text-transform: uppercase;
										transition: all 0.2s;
									"
									onmouseenter={(e) => {
										const el = e.currentTarget as HTMLElement;
										el.style.background = 'rgba(212,168,67,0.06)';
										el.style.borderColor = 'rgba(212,168,67,0.35)';
										el.style.color = 'var(--palais-gold)';
									}}
									onmouseleave={(e) => {
										const el = e.currentTarget as HTMLElement;
										el.style.background = 'transparent';
										el.style.borderColor = 'rgba(212,168,67,0.2)';
										el.style.color = 'rgba(212,168,67,0.6)';
									}}
								>
									VIEW DETAIL
								</a>

								<!-- Deploy button -->
								<button
									onclick={() => openDeploy(ws)}
									disabled={deploy?.status === 'running'}
									style="
										flex: 1;
										padding: 6px 10px;
										border-radius: 6px;
										cursor: {deploy?.status === 'running' ? 'not-allowed' : 'pointer'};
										background: {deploy?.status === 'running' ? 'rgba(212,168,67,0.04)' : 'rgba(212,168,67,0.12)'};
										color: {deploy?.status === 'running' ? 'rgba(212,168,67,0.35)' : 'var(--palais-gold)'};
										border: 1px solid {deploy?.status === 'running' ? 'rgba(212,168,67,0.15)' : 'rgba(212,168,67,0.35)'};
										font-family: 'Orbitron', sans-serif;
										font-size: 0.55rem;
										letter-spacing: 0.12em;
										text-transform: uppercase;
										transition: all 0.2s;
									"
									onmouseenter={(e) => {
										if (deploy?.status !== 'running') {
											const el = e.currentTarget as HTMLElement;
											el.style.background = 'rgba(212,168,67,0.2)';
											el.style.boxShadow = '0 0 12px rgba(212,168,67,0.2)';
										}
									}}
									onmouseleave={(e) => {
										if (deploy?.status !== 'running') {
											const el = e.currentTarget as HTMLElement;
											el.style.background = 'rgba(212,168,67,0.12)';
											el.style.boxShadow = '';
										}
									}}
								>
									{deploy?.status === 'running' ? 'DEPLOYING...' : 'DEPLOY'}
								</button>
							</div>

						</span>
					</div>
				{/each}
			</div>
		{/if}
	</div>
</div>

<!-- ══════════════════════════════════════════════════════════
     DEPLOY CONFIRM MODAL
     ══════════════════════════════════════════════════════════ -->
{#if deployTarget}
	<!-- Backdrop -->
	<div
		style="position: fixed; inset: 0; z-index: 100; background: rgba(0,0,0,0.72); backdrop-filter: blur(4px);"
		onclick={closeDeploy}
		role="presentation"
	></div>

	<!-- Modal panel -->
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
		aria-label="Confirm deployment"
	>
		<span class="hud-bracket-bottom" style="display: block;">
			<!-- Header -->
			<div class="flex items-center justify-between mb-5">
				<div>
					<p style="color: rgba(212,168,67,0.5); font-family: 'Orbitron', sans-serif; font-size: 0.5rem; letter-spacing: 0.25em; text-transform: uppercase; margin-bottom: 4px;">
						DEPLOY — CONFIRM
					</p>
					<h2 style="color: var(--palais-gold); font-family: 'Orbitron', sans-serif; font-size: 0.9rem; letter-spacing: 0.12em; text-transform: uppercase;">
						{deployTarget.name}
					</h2>
				</div>
				<button
					onclick={closeDeploy}
					style="background: none; border: none; cursor: pointer; color: rgba(212,168,67,0.4); font-size: 1.3rem; line-height: 1; padding: 2px 6px; font-family: 'JetBrains Mono', monospace;"
				>x</button>
			</div>

			<!-- Version input -->
			<div class="mb-5">
				<label style="display: block; font-family: 'Orbitron', sans-serif; font-size: 0.58rem; letter-spacing: 0.2em; color: rgba(212,168,67,0.55); text-transform: uppercase; margin-bottom: 8px;">
					VERSION / TAG
				</label>
				<input
					type="text"
					bind:value={deployVersion}
					placeholder="e.g. v1.2.0 or main"
					style="
						width: 100%; padding: 9px 12px;
						background: rgba(0,0,0,0.35); border-radius: 6px;
						border: 1px solid rgba(212,168,67,0.22);
						color: var(--palais-gold); font-family: 'JetBrains Mono', monospace; font-size: 0.85rem;
						outline: none; transition: border-color 0.2s;
					"
					onfocus={(e) => { (e.currentTarget as HTMLElement).style.borderColor = 'rgba(212,168,67,0.55)'; }}
					onblur={(e) => { (e.currentTarget as HTMLElement).style.borderColor = 'rgba(212,168,67,0.22)'; }}
					onkeydown={(e) => { if (e.key === 'Enter') confirmDeploy(); }}
				/>
			</div>

			<!-- Error -->
			{#if deployError}
				<p style="color: var(--palais-red); font-family: 'JetBrains Mono', monospace; font-size: 0.72rem; margin-bottom: 12px;">
					ERR: {deployError}
				</p>
			{/if}

			<!-- Actions -->
			<div class="flex gap-3 justify-end">
				<button
					onclick={closeDeploy}
					disabled={deploying}
					style="
						padding: 8px 18px; border-radius: 6px; cursor: pointer;
						background: transparent; color: rgba(212,168,67,0.55);
						border: 1px solid rgba(212,168,67,0.2);
						font-family: 'Orbitron', sans-serif; font-size: 0.6rem; letter-spacing: 0.12em;
					"
				>
					CANCEL
				</button>
				<button
					onclick={confirmDeploy}
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
