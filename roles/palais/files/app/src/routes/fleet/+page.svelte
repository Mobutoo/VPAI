<script lang="ts">
	import ServerCard from '$lib/components/fleet/ServerCard.svelte';
	import ServerDetailModal from '$lib/components/fleet/ServerDetailModal.svelte';

	let { data } = $props();

	type ServerEntry = typeof data.servers[number];

	// ── State ─────────────────────────────────────────────────────────
	let filterProvider = $state<'all' | 'hetzner' | 'ovh' | 'ionos' | 'local'>('all');
	let selectedServer = $state<ServerEntry | null>(null);
	let modalOpen = $state(false);
	let syncingAll = $state(false);
	let syncResult = $state('');

	// ── Derived ───────────────────────────────────────────────────────
	const filteredServers = $derived(
		filterProvider === 'all'
			? data.servers
			: data.servers.filter((s) => s.provider === filterProvider)
	);

	const totalCount = $derived(data.servers.length);

	const onlineCount = $derived(
		data.servers.filter((s) => s.status === 'online').length
	);

	const degradedCount = $derived(
		data.servers.filter((s) => s.status === 'degraded').length
	);

	const offlineCount = $derived(
		data.servers.filter((s) => s.status === 'offline').length
	);

	// ── Actions ───────────────────────────────────────────────────────
	function openDetail(server: ServerEntry) {
		selectedServer = server;
		modalOpen = true;
	}

	function closeModal() {
		modalOpen = false;
		selectedServer = null;
	}

	async function syncAll() {
		if (syncingAll) return;
		syncingAll = true;
		syncResult = '';
		try {
			const res = await fetch('/api/v2/fleet/sync', { method: 'POST' });
			const body = await res.json();
			if (!res.ok) throw new Error(body.error ?? `HTTP ${res.status}`);
			const { synced = 0, total = 0, errors = [] } = body.data ?? {};
			syncResult = `${synced}/${total} synced${errors.length > 0 ? ` — ${errors.length} error(s)` : ''}`;
		} catch (e: unknown) {
			syncResult = e instanceof Error ? e.message : 'Sync failed';
		} finally {
			syncingAll = false;
		}
	}

	const FILTER_TABS: { key: typeof filterProvider; label: string }[] = [
		{ key: 'all',     label: 'ALL' },
		{ key: 'hetzner', label: 'HETZNER' },
		{ key: 'ovh',     label: 'OVH' },
		{ key: 'ionos',   label: 'IONOS' },
		{ key: 'local',   label: 'LOCAL' }
	];

	function filterTabStyle(key: typeof filterProvider) {
		const active = filterProvider === key;
		return `
			font-family: 'Orbitron', sans-serif;
			font-size: 0.55rem;
			font-weight: ${active ? '700' : '500'};
			letter-spacing: 0.18em;
			text-transform: uppercase;
			padding: 5px 14px;
			border-radius: 5px;
			cursor: pointer;
			border: 1px solid ${active ? 'rgba(212,168,67,0.5)' : 'rgba(212,168,67,0.12)'};
			background: ${active ? 'rgba(212,168,67,0.14)' : 'transparent'};
			color: ${active ? 'var(--palais-gold)' : 'var(--palais-text-muted)'};
			transition: all 0.18s ease;
		`;
	}
</script>

<svelte:head><title>Palais — Fleet</title></svelte:head>

<div style="min-height: 100vh; padding: 2rem 0;">

	<!-- ══════════════════════════════════════════ HUD HEADER ═══════ -->
	<header style="margin-bottom: 2rem;">
		<div style="display: flex; align-items: flex-start; justify-content: space-between; gap: 1rem; flex-wrap: wrap; margin-bottom: 0.75rem;">
			<div>
				<p
					style="
						font-family: 'Orbitron', sans-serif;
						font-size: 0.55rem;
						letter-spacing: 0.35em;
						text-transform: uppercase;
						color: rgba(212,168,67,0.55);
						margin-bottom: 4px;
					"
				>
					INFRASTRUCTURE — FLEET
				</p>
				<h1
					style="
						font-family: 'Orbitron', sans-serif;
						font-size: 1.75rem;
						font-weight: 800;
						letter-spacing: 0.15em;
						text-transform: uppercase;
						color: var(--palais-gold);
						text-shadow: 0 0 28px rgba(212,168,67,0.35);
						position: relative;
					"
				>
					FLEET OVERVIEW
					<!-- Scan-line accent bar -->
					<span
						style="
							display: block;
							position: absolute;
							bottom: -6px;
							left: 0;
							height: 2px;
							width: 60%;
							background: linear-gradient(90deg, var(--palais-gold) 0%, transparent 100%);
							opacity: 0.5;
						"
					></span>
				</h1>
			</div>

			<!-- Sync All button -->
			<div style="display: flex; flex-direction: column; align-items: flex-end; gap: 6px; flex-shrink: 0;">
				<button
					onclick={syncAll}
					disabled={syncingAll}
					style="
						font-family: 'Orbitron', sans-serif;
						font-size: 0.58rem;
						font-weight: 600;
						letter-spacing: 0.2em;
						text-transform: uppercase;
						padding: 8px 20px;
						border-radius: 6px;
						cursor: {syncingAll ? 'not-allowed' : 'pointer'};
						background: rgba(212,168,67,0.1);
						color: var(--palais-gold);
						border: 1px solid rgba(212,168,67,0.4);
						transition: all 0.2s;
						opacity: {syncingAll ? '0.6' : '1'};
					"
					onmouseenter={(e) => {
						if (!syncingAll) {
							const el = e.currentTarget as HTMLElement;
							el.style.background = 'rgba(212,168,67,0.2)';
							el.style.boxShadow = '0 0 20px rgba(212,168,67,0.25)';
						}
					}}
					onmouseleave={(e) => {
						const el = e.currentTarget as HTMLElement;
						el.style.background = 'rgba(212,168,67,0.1)';
						el.style.boxShadow = '';
					}}
				>
					{syncingAll ? 'SYNCING...' : 'SYNC ALL'}
				</button>
				{#if syncResult}
					<span style="font-family: 'JetBrains Mono', monospace; font-size: 0.55rem; color: var(--palais-text-muted); animation: fadeSlideUp 0.3s ease-out both;">
						{syncResult}
					</span>
				{/if}
			</div>
		</div>

		<!-- Gold separator -->
		<div style="height: 1px; background: linear-gradient(90deg, var(--palais-gold) 0%, rgba(212,168,67,0.04) 100%); opacity: 0.35; margin-top: 1rem;"></div>
	</header>

	<!-- ═════════════════════════════════ STATS SUMMARY BAR ══════════ -->
	<div
		class="glass-panel"
		style="
			display: flex;
			align-items: center;
			gap: 0;
			border-radius: 8px;
			border: 1px solid rgba(212,168,67,0.14);
			margin-bottom: 1.75rem;
			overflow: hidden;
		"
	>
		{#each [
			{ label: 'TOTAL',    value: totalCount,    color: 'var(--palais-text)',     bg: 'transparent' },
			{ label: 'ONLINE',   value: onlineCount,   color: 'var(--palais-green)',    bg: 'rgba(76,175,80,0.06)' },
			{ label: 'DEGRADED', value: degradedCount, color: '#E8833A',               bg: 'rgba(232,131,58,0.06)' },
			{ label: 'OFFLINE',  value: offlineCount,  color: 'var(--palais-red)',      bg: 'rgba(229,57,53,0.06)' },
		] as stat, i}
			<div
				style="
					flex: 1;
					padding: 0.75rem 1rem;
					background: {stat.bg};
					border-right: {i < 3 ? '1px solid rgba(212,168,67,0.08)' : 'none'};
					display: flex;
					flex-direction: column;
					align-items: center;
					gap: 3px;
				"
			>
				<span
					style="
						font-family: 'Orbitron', sans-serif;
						font-size: 1.2rem;
						font-weight: 700;
						color: {stat.color};
						font-variant-numeric: tabular-nums;
					"
				>
					{stat.value}
				</span>
				<span
					style="
						font-family: 'Orbitron', sans-serif;
						font-size: 0.45rem;
						letter-spacing: 0.22em;
						text-transform: uppercase;
						color: rgba(212,168,67,0.4);
					"
				>
					{stat.label}
				</span>
			</div>
		{/each}
	</div>

	<!-- ═════════════════════════════════ PROVIDER FILTER TABS ═══════ -->
	<div style="display: flex; gap: 0.4rem; flex-wrap: wrap; margin-bottom: 1.5rem;">
		{#each FILTER_TABS as tab}
			<button
				type="button"
				style={filterTabStyle(tab.key)}
				onclick={() => { filterProvider = tab.key; }}
				onmouseenter={(e) => {
					if (filterProvider !== tab.key) {
						const el = e.currentTarget as HTMLElement;
						el.style.borderColor = 'rgba(212,168,67,0.28)';
						el.style.color = 'var(--palais-text)';
					}
				}}
				onmouseleave={(e) => {
					if (filterProvider !== tab.key) {
						const el = e.currentTarget as HTMLElement;
						el.style.borderColor = 'rgba(212,168,67,0.12)';
						el.style.color = 'var(--palais-text-muted)';
					}
				}}
			>
				{tab.label}
			</button>
		{/each}
	</div>

	<!-- ═══════════════════════════════════════ SERVER CARD GRID ═════ -->
	{#if filteredServers.length === 0}
		<div
			class="glass-panel"
			style="
				border: 1px solid rgba(212,168,67,0.1);
				border-radius: 10px;
				padding: 3rem 2rem;
				text-align: center;
			"
		>
			<p style="font-family: 'JetBrains Mono', monospace; font-size: 0.7rem; color: var(--palais-text-muted);">
				<span style="color: rgba(212,168,67,0.4);">// </span>No servers found for provider: {filterProvider}
			</p>
		</div>
	{:else}
		<div
			style="
				display: grid;
				grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
				gap: 0.85rem;
			"
		>
			{#each filteredServers as server, i (server.id)}
				<div style="animation: cardReveal 0.4s ease-out both; animation-delay: {i * 60}ms;">
					<ServerCard
						{server}
						onclick={() => openDetail(server)}
					/>
				</div>
			{/each}
		</div>
	{/if}

</div>

<!-- ═══════════════════════════════════ SERVER DETAIL MODAL ══════════ -->
<ServerDetailModal
	server={selectedServer as any}
	open={modalOpen}
	onclose={closeModal}
/>
