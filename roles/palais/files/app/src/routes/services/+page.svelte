<script lang="ts">
	import ContainerTable from '$lib/components/services/ContainerTable.svelte';

	let { data } = $props();

	// ─── Server selector ─────────────────────────────────────────────
	let selectedServerId = $state<number | null>(
		data.servers.length > 0 ? data.servers[0].id : null
	);

	// ─── Container list state ─────────────────────────────────────────
	interface ContainerRow {
		name: string;
		image: string;
		status: string;
		state: string;
		cpuPercent: number | null;
		memUsageMb: number | null;
	}

	let containers = $state<ContainerRow[]>([]);
	let loading = $state(false);
	let fetchError = $state('');
	let actionFeedback = $state('');
	let actionError = $state('');

	// ─── Fetch containers when server changes ──────────────────────────
	$effect(() => {
		if (selectedServerId === null) {
			containers = [];
			fetchError = '';
			return;
		}

		const id = selectedServerId;
		loading = true;
		fetchError = '';
		containers = [];

		fetch(`/api/v2/services?serverId=${id}`)
			.then((res) => res.json())
			.then((body) => {
				if (!body.success) throw new Error(body.error ?? 'API error');
				// API returns containers with nested stats
				containers = (body.data ?? []).map((c: Record<string, unknown>) => {
					const stats = c.stats as Record<string, unknown> | null;
					return {
						name: c.name as string,
						image: c.image as string,
						status: c.status as string,
						state: c.state as string,
						cpuPercent: stats ? (stats.cpuPercent as number) : null,
						memUsageMb: stats ? (stats.memUsageMb as number) : null,
					};
				});
			})
			.catch((e: Error) => {
				fetchError = e.message ?? 'Failed to fetch containers';
			})
			.finally(() => {
				loading = false;
			});
	});

	// ─── Derived resource summary ─────────────────────────────────────
	const totalContainers = $derived(containers.length);
	const runningCount = $derived(containers.filter((c) => c.state.toLowerCase() === 'running').length);
	const totalRamMb = $derived(
		containers.reduce((sum, c) => sum + (c.memUsageMb ?? 0), 0)
	);

	function formatRam(mb: number): string {
		if (mb >= 1024) return (mb / 1024).toFixed(1) + ' GiB';
		return mb.toFixed(0) + ' MiB';
	}

	// ─── Container action handler ──────────────────────────────────────
	async function handleContainerAction(containerName: string, action: 'start' | 'stop' | 'restart') {
		if (!selectedServerId) return;
		actionFeedback = '';
		actionError = '';
		try {
			const res = await fetch(
				`/api/v2/services/${selectedServerId}/${encodeURIComponent(containerName)}`,
				{
					method: 'POST',
					headers: { 'Content-Type': 'application/json' },
					body: JSON.stringify({ action }),
				}
			);
			const body = await res.json();
			if (!body.success) throw new Error(body.error ?? `HTTP ${res.status}`);
			actionFeedback = `${action.toUpperCase()} sent to ${containerName}`;

			// Refresh container list after a short delay to let Docker settle
			await new Promise((r) => setTimeout(r, 1200));
			const id = selectedServerId;
			const refreshRes = await fetch(`/api/v2/services?serverId=${id}`);
			const refreshBody = await refreshRes.json();
			if (refreshBody.success) {
				containers = (refreshBody.data ?? []).map((c: Record<string, unknown>) => {
					const stats = c.stats as Record<string, unknown> | null;
					return {
						name: c.name as string,
						image: c.image as string,
						status: c.status as string,
						state: c.state as string,
						cpuPercent: stats ? (stats.cpuPercent as number) : null,
						memUsageMb: stats ? (stats.memUsageMb as number) : null,
					};
				});
			}
		} catch (e) {
			actionError = e instanceof Error ? e.message : 'Action failed';
		}
	}

	const selectedServer = $derived(data.servers.find((s) => s.id === selectedServerId) ?? null);
</script>

<svelte:head><title>Palais — Services</title></svelte:head>

<div style="min-height: 100vh; padding: 2rem 0;">

	<!-- ═══════════════════════════════════════════ HUD HEADER ═════ -->
	<header class="flex flex-col gap-3 mb-8">
		<div class="flex items-start justify-between gap-4 flex-wrap">
			<div>
				<p class="text-xs tracking-[0.3em] uppercase mb-1"
					style="color: var(--palais-gold); opacity: 0.6; font-family: 'Orbitron', sans-serif;">
					DOCKER — CONTAINER CONTROL
				</p>
				<h1 class="text-3xl font-bold tracking-widest"
					style="color: var(--palais-gold); font-family: 'Orbitron', sans-serif; text-shadow: 0 0 24px rgba(212,168,67,0.35);">
					SERVICES
				</h1>
			</div>

			<!-- Resource summary pills -->
			{#if !loading && containers.length > 0}
				<div class="flex items-center gap-2 flex-wrap">
					<span class="px-3 py-1 rounded-full text-xs font-semibold tracking-wider"
						style="background: rgba(212,168,67,0.1); color: var(--palais-gold); border: 1px solid rgba(212,168,67,0.28); font-family: 'Orbitron', sans-serif;">
						{totalContainers} TOTAL
					</span>
					<span class="px-3 py-1 rounded-full text-xs font-semibold tracking-wider"
						style="background: rgba(76,175,80,0.12); color: var(--palais-green); border: 1px solid rgba(76,175,80,0.28); font-family: 'Orbitron', sans-serif;">
						{runningCount} RUNNING
					</span>
					{#if totalRamMb > 0}
						<span class="px-3 py-1 rounded-full text-xs font-semibold tracking-wider"
							style="background: rgba(79,195,247,0.1); color: var(--palais-cyan); border: 1px solid rgba(79,195,247,0.25); font-family: 'Orbitron', sans-serif;">
							{formatRam(totalRamMb)} RAM
						</span>
					{/if}
				</div>
			{/if}
		</div>

		<!-- Gold separator line -->
		<div style="height: 1px; background: linear-gradient(90deg, var(--palais-gold) 0%, rgba(212,168,67,0.08) 100%); opacity: 0.4;"></div>
	</header>

	<!-- ══════════════════════════════════════ SERVER SELECTOR ═════ -->
	<section class="mb-6">
		<div class="glass-panel hud-bracket rounded-xl p-4" style="border: 1px solid rgba(212,168,67,0.18);">
			<span class="hud-bracket-bottom" style="display: block;">
				<div class="flex items-center gap-4 flex-wrap">
					<label
						for="server-select"
						style="
							font-family: 'Orbitron', sans-serif; font-size: 0.6rem;
							letter-spacing: 0.2em; color: rgba(212,168,67,0.55);
							text-transform: uppercase; white-space: nowrap;
						"
					>Target Server</label>

					{#if data.servers.length === 0}
						<span style="color: var(--palais-text-muted); font-family: 'JetBrains Mono', monospace; font-size: 0.8rem;">
							No servers registered in fleet.
						</span>
					{:else}
						<select
							id="server-select"
							bind:value={selectedServerId}
							style="
								padding: 7px 12px;
								background: rgba(0,0,0,0.4);
								border: 1px solid rgba(212,168,67,0.25);
								border-radius: 6px;
								color: var(--palais-text);
								font-family: 'JetBrains Mono', monospace;
								font-size: 0.82rem;
								cursor: pointer;
								outline: none;
								min-width: 200px;
								transition: border-color 0.2s;
							"
							onfocus={(e) => { (e.currentTarget as HTMLElement).style.borderColor = 'rgba(212,168,67,0.5)'; }}
							onblur={(e) => { (e.currentTarget as HTMLElement).style.borderColor = 'rgba(212,168,67,0.25)'; }}
						>
							{#each data.servers as server (server.id)}
								<option value={server.id} style="background: var(--palais-surface);">
									{server.name} ({server.provider}{server.location ? ' / ' + server.location : ''})
								</option>
							{/each}
						</select>
					{/if}

					{#if selectedServer}
						<span class="px-2 py-0.5 rounded text-xs"
							style="
								background: {selectedServer.status === 'online' ? 'rgba(76,175,80,0.1)' :
								             selectedServer.status === 'offline' ? 'rgba(229,57,53,0.1)' : 'rgba(212,168,67,0.1)'};
								color: {selectedServer.status === 'online' ? 'var(--palais-green)' :
								        selectedServer.status === 'offline' ? 'var(--palais-red)' : 'var(--palais-gold)'};
								border: 1px solid {selectedServer.status === 'online' ? 'rgba(76,175,80,0.25)' :
								                   selectedServer.status === 'offline' ? 'rgba(229,57,53,0.25)' : 'rgba(212,168,67,0.25)'};
								font-family: 'Orbitron', sans-serif; font-size: 0.55rem; letter-spacing: 0.1em;
							"
						>{(selectedServer.status ?? 'unknown').toUpperCase()}</span>
					{/if}
				</div>
			</span>
		</div>
	</section>

	<!-- ════════════════════════════════════════ ACTION FEEDBACK ════ -->
	{#if actionFeedback || actionError}
		<div class="mb-4 px-4 py-2 rounded-lg"
			style="
				background: {actionError ? 'rgba(229,57,53,0.08)' : 'rgba(76,175,80,0.08)'};
				border: 1px solid {actionError ? 'rgba(229,57,53,0.25)' : 'rgba(76,175,80,0.25)'};
				color: {actionError ? 'var(--palais-red)' : 'var(--palais-green)'};
				font-family: 'JetBrains Mono', monospace; font-size: 0.78rem;
			"
		>
			{actionError || actionFeedback}
		</div>
	{/if}

	<!-- ═══════════════════════════════════ CONTAINER TABLE ════════ -->
	<section>
		<div class="glass-panel hud-bracket rounded-xl" style="border: 1px solid rgba(212,168,67,0.18); overflow: hidden;">
			<span class="hud-bracket-bottom" style="display: block;">

				<!-- Table header bar -->
				<div class="flex items-center justify-between px-5 py-3"
					style="border-bottom: 1px solid rgba(212,168,67,0.14);">
					<p style="
						font-family: 'Orbitron', sans-serif; font-size: 0.6rem;
						letter-spacing: 0.2em; color: rgba(212,168,67,0.55);
						text-transform: uppercase;
					">
						{#if selectedServer}
							{selectedServer.name.toUpperCase()} — CONTAINERS
						{:else}
							SELECT A SERVER
						{/if}
					</p>
					{#if loading}
						<span style="
							font-family: 'JetBrains Mono', monospace; font-size: 0.7rem;
							color: rgba(212,168,67,0.5);
							animation: pulseGold 1.2s ease-in-out infinite;
						">LOADING...</span>
					{/if}
				</div>

				<!-- Content area -->
				{#if !selectedServerId}
					<div class="py-16 text-center">
						<p style="color: var(--palais-text-muted); font-family: 'JetBrains Mono', monospace; font-size: 0.85rem;">
							<span style="color: rgba(212,168,67,0.35);">// </span>Select a server above to view containers.
						</p>
					</div>

				{:else if loading}
					<div class="py-16 text-center">
						<p style="color: rgba(212,168,67,0.4); font-family: 'Orbitron', sans-serif; font-size: 0.7rem; letter-spacing: 0.2em;">
							SCANNING CONTAINERS...
						</p>
					</div>

				{:else if fetchError}
					<div class="py-12 px-5">
						<div class="rounded-lg p-4"
							style="background: rgba(229,57,53,0.07); border: 1px solid rgba(229,57,53,0.22);">
							<p style="color: var(--palais-red); font-family: 'JetBrains Mono', monospace; font-size: 0.8rem;">
								Connection error: {fetchError}
							</p>
							<p class="mt-1" style="color: var(--palais-text-muted); font-family: 'JetBrains Mono', monospace; font-size: 0.72rem;">
								Verify SSH connectivity and DOCKER_SSH_SERVERS configuration.
							</p>
						</div>
					</div>

				{:else if containers.length === 0}
					<div class="py-16 text-center">
						<p style="color: var(--palais-text-muted); font-family: 'JetBrains Mono', monospace; font-size: 0.85rem;">
							<span style="color: rgba(212,168,67,0.35);">// </span>No containers found on this server.
						</p>
					</div>

				{:else}
					<ContainerTable
						{containers}
						serverId={selectedServerId}
						onaction={handleContainerAction}
					/>
				{/if}

			</span>
		</div>
	</section>

</div>
