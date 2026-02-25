<script lang="ts">
	import { invalidateAll } from '$app/navigation';

	let { data } = $props();

	// ─── Edit modal state ────────────────────────────────────────────
	interface EditState {
		name: string;
		description: string;
		tailscaleIp: string;
		localIp: string;
	}

	let editNode = $state<EditState | null>(null);
	let saving = $state(false);
	let saveError = $state('');

	function openEdit(node: typeof data.nodes[0]) {
		editNode = {
			name: node.name,
			description: node.description ?? '',
			tailscaleIp: node.tailscaleIp ?? '',
			localIp: node.localIp ?? ''
		};
		saveError = '';
	}

	function closeEdit() {
		editNode = null;
		saveError = '';
	}

	async function saveEdit() {
		if (!editNode) return;
		saving = true;
		saveError = '';
		try {
			const res = await fetch(`/api/v1/health/nodes/${encodeURIComponent(editNode.name)}`, {
				method: 'PATCH',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({
					description: editNode.description,
					tailscaleIp: editNode.tailscaleIp,
					localIp: editNode.localIp
				})
			});
			if (!res.ok) {
				const err = await res.json().catch(() => ({ message: 'Erreur inconnue' }));
				saveError = err.message ?? `HTTP ${res.status}`;
			} else {
				closeEdit();
				await invalidateAll();
			}
		} catch (e) {
			saveError = 'Erreur réseau';
		} finally {
			saving = false;
		}
	}

	// ─── Topology positions ──────────────────────────────────────────
	const POSITION_SLOTS = [
		{ x: 200, y: 80  },
		{ x: 50,  y: 200 },
		{ x: 350, y: 200 },
		{ x: 200, y: 300 }
	];

	const VPN_LINKS = [
		{ from: 'sese-ai', to: 'seko-vpn' },
		{ from: 'rpi5',    to: 'seko-vpn' },
		{ from: 'sese-ai', to: 'rpi5' }
	];

	function nodePos(name: string): { x: number; y: number; label: string } {
		const idx = data.nodes.findIndex((n) => n.name === name);
		const slot = POSITION_SLOTS[idx] ?? { x: 200, y: 140 };
		const node = data.nodes.find((n) => n.name === name);
		return { ...slot, label: node?.description ?? name };
	}

	function statusColor(status: string) {
		return status === 'online'   ? 'var(--palais-green)'      :
		       status === 'offline'  ? 'var(--palais-red)'        :
		       status === 'busy'     ? 'var(--palais-gold)'       :
		       status === 'degraded' ? 'var(--palais-amber)'      : 'var(--palais-text-muted)';
	}

	function statusGlow(status: string) {
		return status === 'online'   ? '0 0 12px 2px rgba(0,255,136,0.4)'   :
		       status === 'busy'     ? '0 0 12px 2px rgba(212,168,67,0.4)'  :
		       status === 'offline'  ? '0 0 8px 2px rgba(255,60,60,0.3)'    :
		       status === 'degraded' ? '0 0 12px 2px rgba(255,165,0,0.35)'  : 'none';
	}

	function cardGlow(status: string) {
		return status === 'online'   ? '0 4px 32px 0 rgba(0,255,136,0.07), 0 1px 0 0 rgba(76,175,80,0.18)'    :
		       status === 'busy'     ? '0 4px 32px 0 rgba(212,168,67,0.09), 0 1px 0 0 rgba(212,168,67,0.22)'  :
		       status === 'offline'  ? '0 4px 32px 0 rgba(255,60,60,0.08), 0 1px 0 0 rgba(229,57,53,0.2)'     :
		       status === 'degraded' ? '0 4px 32px 0 rgba(255,165,0,0.09), 0 1px 0 0 rgba(255,165,0,0.22)'    : 'none';
	}

	function serviceColor(status: string) {
		return status === 'healthy'   ? 'var(--palais-green)' :
		       status === 'unhealthy' ? 'var(--palais-red)'   : 'var(--palais-amber)';
	}

	function gaugeStyle(value: number | null) {
		const pct = Math.min(Math.max(value ?? 0, 0), 100);
		const color = pct > 90 ? 'var(--palais-red)' : pct > 75 ? 'var(--palais-amber)' : 'var(--palais-green)';
		return { width: `${pct}%`, background: color };
	}

	function isBackupStale(lastBackupAt: string | Date | null) {
		if (!lastBackupAt) return true;
		const ms = Date.now() - new Date(lastBackupAt).getTime();
		return ms > 24 * 60 * 60 * 1000;
	}

	function vpnNode(tailscaleIp: string | null) {
		if (!tailscaleIp) return null;
		return data.vpnTopology.find((v) => v.ip === tailscaleIp) ?? null;
	}

	// Status counts
	const onlineCount   = $derived(data.nodes.filter((n) => n.status === 'online').length);
	const busyCount     = $derived(data.nodes.filter((n) => n.status === 'busy').length);
	const offlineCount  = $derived(data.nodes.filter((n) => n.status === 'offline').length);
	const degradedCount = $derived(data.nodes.filter((n) => n.status === 'degraded').length);
</script>

<svelte:head><title>Palais — Health</title></svelte:head>

<div style="min-height: 100vh; padding: 2rem 0;">
	<!-- ═══════════════════════════════════════════ HUD HEADER ═════ -->
	<header class="flex flex-col gap-3 mb-8">
		<div class="flex items-start justify-between gap-4 flex-wrap">
			<div>
				<p class="text-xs tracking-[0.3em] uppercase mb-1" style="color: var(--palais-gold); opacity: 0.6; font-family: 'Orbitron', sans-serif;">
					RÉSEAU — SURVEILLANCE
				</p>
				<h1 class="text-3xl font-bold tracking-widest" style="color: var(--palais-gold); font-family: 'Orbitron', sans-serif; text-shadow: 0 0 24px rgba(212,168,67,0.35);">
					INFRASTRUCTURE
				</h1>
			</div>

			<!-- Status summary pills -->
			<div class="flex items-center gap-2 flex-wrap">
				{#if !data.headscaleOk}
					<span class="px-3 py-1 rounded-full text-xs font-semibold tracking-wider"
						style="background: rgba(255,165,0,0.15); color: var(--palais-amber); border: 1px solid rgba(255,165,0,0.4); font-family: 'Orbitron', sans-serif; animation: pulseGold 1.5s ease-in-out infinite;">
						⚠ VPN UNREACHABLE
					</span>
				{:else}
					<span class="px-2 py-0.5 rounded text-xs tracking-wider"
						style="background: rgba(0,255,136,0.06); color: rgba(0,255,136,0.4); border: 1px solid rgba(0,255,136,0.15); font-family: 'JetBrains Mono', monospace; font-size: 0.6rem;">
						● HEADSCALE SYNC
					</span>
				{/if}
				{#if onlineCount > 0}
					<span class="px-3 py-1 rounded-full text-xs font-semibold tracking-wider"
						style="background: rgba(76,175,80,0.13); color: var(--palais-green); border: 1px solid rgba(76,175,80,0.3); font-family: 'Orbitron', sans-serif;">
						{onlineCount} ONLINE
					</span>
				{/if}
				{#if busyCount > 0}
					<span class="px-3 py-1 rounded-full text-xs font-semibold tracking-wider"
						style="background: rgba(212,168,67,0.13); color: var(--palais-gold); border: 1px solid rgba(212,168,67,0.3); font-family: 'Orbitron', sans-serif;">
						{busyCount} BUSY
					</span>
				{/if}
				{#if degradedCount > 0}
					<span class="px-3 py-1 rounded-full text-xs font-semibold tracking-wider"
						style="background: rgba(255,165,0,0.13); color: var(--palais-amber); border: 1px solid rgba(255,165,0,0.3); font-family: 'Orbitron', sans-serif;">
						{degradedCount} DEGRADED
					</span>
				{/if}
				{#if offlineCount > 0}
					<span class="px-3 py-1 rounded-full text-xs font-semibold tracking-wider"
						style="background: rgba(229,57,53,0.13); color: var(--palais-red); border: 1px solid rgba(229,57,53,0.3); font-family: 'Orbitron', sans-serif;">
						{offlineCount} OFFLINE
					</span>
				{/if}
			</div>
		</div>

		<!-- Gold separator line -->
		<div style="height: 1px; background: linear-gradient(90deg, var(--palais-gold) 0%, rgba(212,168,67,0.08) 100%); opacity: 0.4;"></div>
	</header>

	<!-- ═══════════════════════════════════════ VPN TOPOLOGY MAP ═══ -->
	{#if data.nodes.length > 0}
	<section class="mb-8">
		<p class="text-xs font-semibold uppercase tracking-[0.25em] mb-3"
			style="color: var(--palais-gold); opacity: 0.55; font-family: 'Orbitron', sans-serif;">
			Réseau Singa — VPN Mesh
		</p>
		<div class="glass-panel hud-bracket rounded-xl p-4" style="border: 1px solid rgba(212,168,67,0.18);">
			<span class="hud-bracket-bottom" style="display: block;">
				<svg viewBox="0 0 420 340" class="w-full max-w-lg mx-auto" style="height: 220px;">
					<!-- Gold topology lines with animated dashoffset -->
					{#each VPN_LINKS as link}
						{@const from = nodePos(link.from)}
						{@const to   = nodePos(link.to)}
						<line
							x1={from.x} y1={from.y} x2={to.x} y2={to.y}
							stroke="rgba(212,168,67,0.15)"
							stroke-width="1.5"
							stroke-dasharray="4 6"
						>
							<animate
								attributeName="stroke-dashoffset"
								values="0;-10"
								dur="2s"
								repeatCount="indefinite"
							/>
						</line>
					{/each}

					<!-- Nodes -->
					{#each data.nodes as node}
						{@const pos = nodePos(node.name)}
						{@const vpn = vpnNode(node.tailscaleIp)}
						<g transform={`translate(${pos.x}, ${pos.y})`}>
							<!-- Ambient outer glow ring -->
							<circle r="26" fill="none"
								stroke={statusColor(node.status ?? 'offline')}
								stroke-width="0.8"
								opacity="0.25"
							/>
							<!-- Mid ring -->
							<circle r="21" fill="none"
								stroke={statusColor(node.status ?? 'offline')}
								stroke-width="1"
								opacity="0.45"
							/>
							<!-- Node core -->
							<circle r="17"
								fill="var(--palais-surface)"
								stroke={statusColor(node.status ?? 'offline')}
								stroke-width="2"
							/>
							<!-- Node initials -->
							<text
								text-anchor="middle"
								dominant-baseline="middle"
								font-size="10"
								font-weight="bold"
								fill={statusColor(node.status ?? 'offline')}
								font-family="JetBrains Mono, monospace"
							>
								{node.name.substring(0, 2).toUpperCase()}
							</text>
							<!-- Label below -->
							<text
								text-anchor="middle"
								y="34"
								font-size="7.5"
								fill="rgba(212,168,67,0.6)"
								font-family="Orbitron, sans-serif"
								letter-spacing="1"
							>
								{nodePos(node.name).label.toUpperCase().substring(0, 12)}
							</text>
							<!-- VPN active dot -->
							{#if vpn?.online}
								<circle cx="14" cy="-14" r="4" fill="var(--palais-green)" opacity="0.9"/>
								<circle cx="14" cy="-14" r="7" fill="none" stroke="var(--palais-green)" stroke-width="0.8" opacity="0.4"/>
							{/if}
						</g>
					{/each}
				</svg>

				<!-- Legend -->
				<div class="flex gap-6 justify-center mt-3 pt-3"
					style="border-top: 1px solid rgba(212,168,67,0.1);">
					<span class="flex items-center gap-2 text-xs" style="color: rgba(212,168,67,0.5); font-family: 'Orbitron', sans-serif; letter-spacing: 0.08em;">
						<span class="w-2 h-2 rounded-full inline-block" style="background: var(--palais-green); box-shadow: 0 0 6px 1px rgba(0,255,136,0.4);"></span>ONLINE
					</span>
					<span class="flex items-center gap-2 text-xs" style="color: rgba(212,168,67,0.5); font-family: 'Orbitron', sans-serif; letter-spacing: 0.08em;">
						<span class="w-2 h-2 rounded-full inline-block" style="background: var(--palais-gold); box-shadow: 0 0 6px 1px rgba(212,168,67,0.4);"></span>BUSY
					</span>
					<span class="flex items-center gap-2 text-xs" style="color: rgba(212,168,67,0.5); font-family: 'Orbitron', sans-serif; letter-spacing: 0.08em;">
						<span class="w-2 h-2 rounded-full inline-block" style="background: var(--palais-red);"></span>OFFLINE
					</span>
					<span class="flex items-center gap-2 text-xs" style="color: rgba(212,168,67,0.5); font-family: 'Orbitron', sans-serif; letter-spacing: 0.08em;">
						<span class="w-2 h-2 rounded-full inline-block" style="background: var(--palais-green); opacity: 0.55;"></span>VPN SINGA
					</span>
				</div>
			</span>
		</div>
	</section>
	{/if}

	<!-- ══════════════════════════════════════════════ NODE CARDS ═══ -->
	<section>
		<p class="text-xs font-semibold uppercase tracking-[0.25em] mb-4"
			style="color: var(--palais-gold); opacity: 0.55; font-family: 'Orbitron', sans-serif;">
			Noeuds — Holographic Panels
		</p>

		{#if data.nodes.length === 0}
			<div class="col-span-3 text-center py-16">
				<p class="text-sm" style="color: var(--palais-text-muted); font-family: 'JetBrains Mono', monospace;">
					<span style="color: rgba(212,168,67,0.4);">// </span>Aucun noeud enregistré.
				</p>
				<p class="text-xs mt-1" style="color: var(--palais-text-muted); opacity: 0.5; font-family: 'JetBrains Mono', monospace;">
					<span style="color: rgba(212,168,67,0.3);">// </span>Le seed démarre au prochain redémarrage du serveur.
				</p>
			</div>
		{:else}
			<div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5">
				{#each data.nodes as node, i (node.id)}
					{@const backup = node.backup}
					{@const stale  = isBackupStale(backup?.lastBackupAt ?? null)}
					{@const nodeStatus = node.status ?? 'offline'}

					<!-- Node card: glass-panel + hud-bracket -->
					<div
						class="glass-panel hud-bracket rounded-xl p-5 space-y-4"
						style="
							border: 1px solid rgba(212,168,67,0.18);
							box-shadow: {cardGlow(nodeStatus)};
							animation: cardReveal 0.4s ease-out both;
							animation-delay: {i * 80}ms;
						"
					>
						<!-- hud-bracket-bottom inner span -->
						<span class="hud-bracket-bottom" style="display: block;">

							<!-- ── Node header ── -->
							<div class="flex items-start justify-between gap-2 mb-4">
								<div class="flex-1 min-w-0">
									<!-- Node name in Orbitron gold -->
									<h3 class="font-bold text-sm tracking-wider"
										style="color: var(--palais-gold); font-family: 'Orbitron', sans-serif;">
										{node.name.toUpperCase()}
									</h3>
									{#if node.description}
										<p class="text-xs mt-0.5 leading-snug"
											style="color: var(--palais-cyan); font-family: 'JetBrains Mono', monospace;">
											{node.description}
										</p>
									{/if}

									<!-- IPs as HUD readouts -->
									<div class="flex flex-col gap-0.5 mt-2">
										{#if node.localIp}
											<div>
												<span class="text-xs uppercase tracking-widest" style="color: rgba(212,168,67,0.5); font-family: 'Orbitron', sans-serif; font-size: 0.55rem;">LAN</span>
												<span class="block text-xs" style="color: var(--palais-cyan); font-family: 'JetBrains Mono', monospace; margin-top: 1px;">
													{node.localIp}
												</span>
											</div>
										{/if}
										{#if node.tailscaleIp}
											<div class="mt-0.5">
												<span class="text-xs uppercase tracking-widest" style="color: rgba(212,168,67,0.5); font-family: 'Orbitron', sans-serif; font-size: 0.55rem;">VPN</span>
												<span class="block text-xs" style="color: var(--palais-cyan); font-family: 'JetBrains Mono', monospace; margin-top: 1px;">
													{node.tailscaleIp}
												</span>
											</div>
										{/if}
									</div>
								</div>

								<!-- Droite: bouton éditer + badge status + dot -->
								<div class="flex flex-col items-end gap-2 flex-shrink-0">
									<!-- Edit button — SVG pencil icon -->
									<button
										onclick={() => openEdit(node)}
										title="Éditer {node.name}"
										style="
											background: none; border: none; cursor: pointer; padding: 4px;
											color: var(--palais-gold); opacity: 0.45;
											transition: opacity 0.2s, filter 0.2s;
										"
										onmouseenter={(e) => { (e.currentTarget as HTMLElement).style.opacity = '1'; (e.currentTarget as HTMLElement).style.filter = 'drop-shadow(0 0 6px rgba(212,168,67,0.6))'; }}
										onmouseleave={(e) => { (e.currentTarget as HTMLElement).style.opacity = '0.45'; (e.currentTarget as HTMLElement).style.filter = 'none'; }}
									>
										<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none"
											stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
											<path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
											<path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
										</svg>
									</button>
									<!-- Status badge — handles 'degraded' -->
									<span class="text-xs font-semibold capitalize px-2 py-0.5 rounded tracking-wider"
										style="
											background: {nodeStatus === 'online'   ? 'rgba(76,175,80,0.12)'   :
											              nodeStatus === 'busy'     ? 'rgba(212,168,67,0.12)'  :
											              nodeStatus === 'degraded' ? 'rgba(255,165,0,0.12)'   : 'rgba(229,57,53,0.12)'};
											color: {statusColor(nodeStatus)};
											border: 1px solid {nodeStatus === 'online'   ? 'rgba(76,175,80,0.25)'   :
											                    nodeStatus === 'busy'     ? 'rgba(212,168,67,0.25)'  :
											                    nodeStatus === 'degraded' ? 'rgba(255,165,0,0.25)'   : 'rgba(229,57,53,0.25)'};
											font-family: 'Orbitron', sans-serif;
											font-size: 0.6rem;
											letter-spacing: 0.1em;
										"
									>
										{nodeStatus.toUpperCase()}
									</span>
									<!-- Status glow ring dot -->
									<span
										class="w-3 h-3 rounded-full inline-block"
										style="
											background: {statusColor(nodeStatus)};
											box-shadow: {statusGlow(nodeStatus)};
											{(nodeStatus === 'busy' || nodeStatus === 'degraded') ? 'animation: pulseGold 1.5s ease-in-out infinite;' : ''}
										"
									></span>
								</div>
							</div>

							<!-- ── System metrics as HUD readouts ── -->
							{#if node.cpuPercent !== null || node.ramPercent !== null || node.diskPercent !== null}
							<div class="space-y-2 pt-3" style="border-top: 1px solid rgba(212,168,67,0.1);">
								{#each [
									{ label: 'CPU', value: node.cpuPercent  },
									{ label: 'RAM', value: node.ramPercent  },
									{ label: 'DSK', value: node.diskPercent }
								] as metric}
									{#if metric.value !== null}
									<div>
										<div class="flex justify-between items-baseline mb-1">
											<span class="text-xs uppercase tracking-wider" style="color: rgba(212,168,67,0.55); font-family: 'Orbitron', sans-serif; font-size: 0.58rem;">
												{metric.label}
											</span>
											<span class="text-xs" style="color: var(--palais-cyan); font-family: 'JetBrains Mono', monospace;">
												{metric.value?.toFixed(1)}%
											</span>
										</div>
										<div class="h-1 rounded-full" style="background: rgba(255,255,255,0.05);">
											<div
												class="h-1 rounded-full transition-all"
												style={`${Object.entries(gaugeStyle(metric.value)).map(([k,v]) => `${k}:${v}`).join(';')}`}
											></div>
										</div>
									</div>
									{/if}
								{/each}
								{#if node.temperature !== null}
									<div class="flex justify-between items-baseline">
										<span class="text-xs uppercase tracking-wider" style="color: rgba(212,168,67,0.55); font-family: 'Orbitron', sans-serif; font-size: 0.58rem;">TEMP</span>
										<span class="text-xs" style="color: var(--palais-cyan); font-family: 'JetBrains Mono', monospace;">
											{node.temperature?.toFixed(1)} °C
										</span>
									</div>
								{/if}
							</div>
							{/if}

							<!-- ── Services ── -->
							{#if node.services.length > 0}
							<div class="pt-3" style="border-top: 1px solid rgba(212,168,67,0.1);">
								<p class="text-xs font-semibold uppercase tracking-[0.2em] mb-2"
									style="color: rgba(212,168,67,0.5); font-family: 'Orbitron', sans-serif; font-size: 0.58rem;">
									Services
								</p>
								<div class="space-y-1.5">
									{#each node.services as svc}
									<div class="flex items-center justify-between">
										<span class="text-xs" style="color: var(--palais-text); font-family: 'JetBrains Mono', monospace;">{svc.serviceName}</span>
										<div class="flex items-center gap-2">
											{#if svc.responseTimeMs}
												<span class="text-xs" style="color: var(--palais-cyan); font-family: 'JetBrains Mono', monospace;">
													{svc.responseTimeMs}ms
												</span>
											{/if}
											<span
												class="w-2 h-2 rounded-full inline-block"
												style="background: {serviceColor(svc.status ?? 'unknown')}; box-shadow: {serviceColor(svc.status ?? 'unknown') === 'var(--palais-green)' ? '0 0 6px 1px rgba(0,255,136,0.35)' : 'none'};"
											></span>
										</div>
									</div>
									{/each}
								</div>
							</div>
							{/if}

							<!-- ── Backup status ── -->
							{#if backup}
							<div class="rounded-lg p-3 pt-2" style="background: rgba(0,0,0,0.28); border: 1px solid rgba(212,168,67,0.1);">
								<div class="flex items-center justify-between mb-1.5">
									<span class="text-xs font-semibold uppercase tracking-wider"
										style="color: rgba(212,168,67,0.45); font-family: 'Orbitron', sans-serif; font-size: 0.58rem;">
										Backup Zerobyte
									</span>
									<span class="text-xs font-semibold"
										style="color: {(backup.status ?? '') === 'ok' ? 'var(--palais-green)' :
										               (backup.status ?? '') === 'failed' ? 'var(--palais-red)' : 'var(--palais-amber)'}; font-family: 'JetBrains Mono', monospace;">
										{(backup.status ?? 'unknown').toUpperCase()}
									</span>
								</div>
								{#if backup.lastBackupAt}
									<p class="text-xs" style="color: {stale ? 'var(--palais-red)' : 'rgba(212,168,67,0.4)'}; font-family: 'JetBrains Mono', monospace;">
										{new Date(backup.lastBackupAt).toLocaleString('fr-FR')}
										{#if stale}<span style="color: var(--palais-red);"> // &gt; 24h</span>{/if}
									</p>
								{/if}
								{#if backup.sizeBytes}
									<p class="text-xs mt-0.5" style="color: var(--palais-cyan); font-family: 'JetBrains Mono', monospace;">
										{(backup.sizeBytes / 1073741824).toFixed(2)} GB
									</p>
								{/if}
							</div>
							{/if}

							<!-- ── Last seen ── -->
							{#if node.lastSeenAt}
							<div class="flex justify-between items-baseline pt-2" style="border-top: 1px solid rgba(212,168,67,0.07);">
								<span class="text-xs uppercase tracking-wider" style="color: rgba(212,168,67,0.35); font-family: 'Orbitron', sans-serif; font-size: 0.55rem;">
									Dernière vue
								</span>
								<span class="text-xs" style="color: var(--palais-cyan); font-family: 'JetBrains Mono', monospace; opacity: 0.7;">
									{new Date(node.lastSeenAt).toLocaleString('fr-FR')}
								</span>
							</div>
							{/if}

						</span><!-- /hud-bracket-bottom -->
					</div>
				{/each}
			</div>
		{/if}
	</section>

	<!-- ══════════════════════════════════════════ EDIT NODE MODAL ═══ -->
	{#if editNode}
		<!-- Backdrop -->
		<div
			style="position: fixed; inset: 0; z-index: 100; background: rgba(0,0,0,0.72); backdrop-filter: blur(4px);"
			onclick={closeEdit}
			role="presentation"
		></div>

		<!-- Modal panel -->
		<div
			class="glass-panel hud-bracket rounded-xl"
			style="
				position: fixed; top: 50%; left: 50%; transform: translate(-50%, -50%);
				z-index: 101; width: min(480px, 95vw); padding: 1.5rem;
				border: 1px solid rgba(212,168,67,0.3);
				box-shadow: 0 8px 64px 0 rgba(0,0,0,0.6), 0 0 0 1px rgba(212,168,67,0.1);
			"
			role="dialog"
			aria-label="Éditer le node"
		>
			<span class="hud-bracket-bottom" style="display: block;">
				<!-- Modal header -->
				<div class="flex items-center justify-between mb-5">
					<h2 style="color: var(--palais-gold); font-family: 'Orbitron', sans-serif; font-size: 0.85rem; letter-spacing: 0.15em; text-transform: uppercase;">
						Éditer — {editNode.name.toUpperCase()}
					</h2>
					<button
						onclick={closeEdit}
						style="background: none; border: none; cursor: pointer; color: rgba(212,168,67,0.4); font-size: 1.2rem; line-height: 1; padding: 2px 6px;"
					>×</button>
				</div>

				<!-- Fields -->
				<div class="space-y-4">
					<!-- Description -->
					<div>
						<label style="display: block; font-family: 'Orbitron', sans-serif; font-size: 0.6rem; letter-spacing: 0.2em; color: rgba(212,168,67,0.55); text-transform: uppercase; margin-bottom: 6px;">
							Description
						</label>
						<input
							type="text"
							bind:value={editNode.description}
							placeholder="ex: OVH VPS 8 Go — Cerveau IA"
							style="
								width: 100%; padding: 8px 10px;
								background: rgba(0,0,0,0.35); border-radius: 6px;
								border: 1px solid rgba(212,168,67,0.2);
								color: var(--palais-text); font-family: 'JetBrains Mono', monospace; font-size: 0.8rem;
								outline: none; transition: border-color 0.2s;
							"
							onfocus={(e) => { (e.currentTarget as HTMLElement).style.borderColor = 'rgba(212,168,67,0.5)'; }}
							onblur={(e) => { (e.currentTarget as HTMLElement).style.borderColor = 'rgba(212,168,67,0.2)'; }}
						/>
					</div>

					<!-- Tailscale IP -->
					<div>
						<label style="display: block; font-family: 'Orbitron', sans-serif; font-size: 0.6rem; letter-spacing: 0.2em; color: rgba(212,168,67,0.55); text-transform: uppercase; margin-bottom: 6px;">
							IP Tailscale / VPN Singa
						</label>
						<input
							type="text"
							bind:value={editNode.tailscaleIp}
							placeholder="100.x.x.x"
							style="
								width: 100%; padding: 8px 10px;
								background: rgba(0,0,0,0.35); border-radius: 6px;
								border: 1px solid rgba(0,212,255,0.2);
								color: var(--palais-cyan); font-family: 'JetBrains Mono', monospace; font-size: 0.85rem;
								outline: none; transition: border-color 0.2s;
							"
							onfocus={(e) => { (e.currentTarget as HTMLElement).style.borderColor = 'rgba(0,212,255,0.5)'; }}
							onblur={(e) => { (e.currentTarget as HTMLElement).style.borderColor = 'rgba(0,212,255,0.2)'; }}
						/>
					</div>

					<!-- Local IP -->
					<div>
						<label style="display: block; font-family: 'Orbitron', sans-serif; font-size: 0.6rem; letter-spacing: 0.2em; color: rgba(212,168,67,0.55); text-transform: uppercase; margin-bottom: 6px;">
							IP Locale / LAN
						</label>
						<input
							type="text"
							bind:value={editNode.localIp}
							placeholder="192.168.x.x"
							style="
								width: 100%; padding: 8px 10px;
								background: rgba(0,0,0,0.35); border-radius: 6px;
								border: 1px solid rgba(0,212,255,0.2);
								color: var(--palais-cyan); font-family: 'JetBrains Mono', monospace; font-size: 0.85rem;
								outline: none; transition: border-color 0.2s;
							"
							onfocus={(e) => { (e.currentTarget as HTMLElement).style.borderColor = 'rgba(0,212,255,0.5)'; }}
							onblur={(e) => { (e.currentTarget as HTMLElement).style.borderColor = 'rgba(0,212,255,0.2)'; }}
						/>
					</div>
				</div>

				<!-- Error message -->
				{#if saveError}
					<p style="color: var(--palais-red); font-family: 'JetBrains Mono', monospace; font-size: 0.75rem; margin-top: 10px;">
						✗ {saveError}
					</p>
				{/if}

				<!-- Buttons -->
				<div class="flex gap-3 justify-end mt-6">
					<button
						onclick={closeEdit}
						disabled={saving}
						style="
							padding: 8px 18px; border-radius: 6px; cursor: pointer;
							background: transparent; color: rgba(212,168,67,0.6);
							border: 1px solid rgba(212,168,67,0.25);
							font-family: 'Orbitron', sans-serif; font-size: 0.65rem; letter-spacing: 0.12em;
							transition: all 0.2s;
						"
					>
						ANNULER
					</button>
					<button
						onclick={saveEdit}
						disabled={saving}
						style="
							padding: 8px 18px; border-radius: 6px; cursor: pointer;
							background: rgba(212,168,67,0.15); color: var(--palais-gold);
							border: 1px solid rgba(212,168,67,0.4);
							font-family: 'Orbitron', sans-serif; font-size: 0.65rem; letter-spacing: 0.12em;
							transition: all 0.2s;
							{saving ? 'opacity: 0.5; cursor: not-allowed;' : ''}
						"
					>
						{saving ? 'ENREGISTREMENT…' : 'ENREGISTRER'}
					</button>
				</div>
			</span>
		</div>
	{/if}
</div>
