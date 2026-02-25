<script lang="ts">
	let { data } = $props();

	// Node layout for VPN SVG map (fixed positions)
	const NODE_POSITIONS: Record<string, { x: number; y: number; label: string }> = {
		'sese-ai':  { x: 200, y: 80,  label: 'Sese-AI (VPS)' },
		'rpi5':     { x: 50,  y: 200, label: 'RPi5 (Local)' },
		'seko-vpn': { x: 350, y: 200, label: 'Seko-VPN (Hub)' }
	};

	// VPN links between nodes
	const VPN_LINKS = [
		{ from: 'sese-ai', to: 'seko-vpn' },
		{ from: 'rpi5',    to: 'seko-vpn' },
		{ from: 'sese-ai', to: 'rpi5' }
	];

	function nodePos(name: string) {
		return NODE_POSITIONS[name] ?? { x: 200, y: 140 };
	}

	function statusColor(status: string) {
		return status === 'online' ? 'var(--palais-green)' :
		       status === 'offline' ? 'var(--palais-red)' : 'var(--palais-text-muted)';
	}

	function serviceColor(status: string) {
		return status === 'healthy' ? 'var(--palais-green)' :
		       status === 'unhealthy' ? 'var(--palais-red)' : 'var(--palais-amber)';
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

	// Match VPN topology nodes to our DB nodes by tailscale IP
	function vpnNode(tailscaleIp: string | null) {
		if (!tailscaleIp) return null;
		return data.vpnTopology.find((v) => v.ip === tailscaleIp) ?? null;
	}
</script>

<svelte:head><title>Palais — Health</title></svelte:head>

<div class="space-y-8">
	<!-- Header -->
	<div class="flex items-center justify-between">
		<h1 class="text-2xl font-bold" style="color: var(--palais-gold); font-family: 'Orbitron', sans-serif;">
			INFRASTRUCTURE HEALTH
		</h1>
		<span class="text-xs px-2 py-1 rounded" style="background: var(--palais-surface); color: var(--palais-text-muted);">
			{data.nodes.filter(n => n.status === 'online').length}/{data.nodes.length} nodes online
		</span>
	</div>

	<!-- VPN Topology Map -->
	{#if data.nodes.length > 0}
	<section>
		<h2 class="text-xs font-semibold uppercase tracking-widest mb-3" style="color: var(--palais-text-muted);">
			Réseau VPN
		</h2>
		<div class="rounded-xl p-4" style="background: var(--palais-surface); border: 1px solid var(--palais-border);">
			<svg viewBox="0 0 420 280" class="w-full max-w-lg mx-auto" style="height: 200px;">
				<!-- Links -->
				{#each VPN_LINKS as link}
					{@const from = nodePos(link.from)}
					{@const to = nodePos(link.to)}
					<line
						x1={from.x} y1={from.y} x2={to.x} y2={to.y}
						stroke="rgba(0,255,255,0.25)" stroke-width="1.5" stroke-dasharray="6 3"
					/>
				{/each}

				<!-- Nodes -->
				{#each data.nodes as node}
					{@const pos = nodePos(node.name)}
					{@const vpn = vpnNode(node.tailscaleIp)}
					<g transform={`translate(${pos.x}, ${pos.y})`}>
						<!-- Outer glow ring -->
						<circle r="22" fill="none" stroke={statusColor(node.status)} stroke-width="1" opacity="0.4"/>
						<!-- Node circle -->
						<circle r="18"
							fill="var(--palais-bg)"
							stroke={statusColor(node.status)}
							stroke-width="2"
						/>
						<!-- Node initial -->
						<text text-anchor="middle" dominant-baseline="middle" font-size="10" font-weight="bold"
							fill={statusColor(node.status)} font-family="JetBrains Mono, monospace">
							{node.name.substring(0, 2).toUpperCase()}
						</text>
						<!-- Label -->
						<text text-anchor="middle" y="30" font-size="8" fill="var(--palais-text-muted)" font-family="Inter, sans-serif">
							{NODE_POSITIONS[node.name]?.label ?? node.name}
						</text>
						<!-- VPN online dot -->
						{#if vpn?.online}
							<circle cx="14" cy="-14" r="4" fill="var(--palais-green)"/>
						{/if}
					</g>
				{/each}
			</svg>

			<!-- Legend -->
			<div class="flex gap-4 justify-center mt-2">
				<span class="flex items-center gap-1 text-xs" style="color: var(--palais-text-muted);">
					<span class="w-2 h-2 rounded-full inline-block" style="background: var(--palais-green);"></span>Online
				</span>
				<span class="flex items-center gap-1 text-xs" style="color: var(--palais-text-muted);">
					<span class="w-2 h-2 rounded-full inline-block" style="background: var(--palais-red);"></span>Offline
				</span>
				<span class="flex items-center gap-1 text-xs" style="color: var(--palais-text-muted);">
					<span class="w-2 h-2 rounded-full inline-block" style="background: var(--palais-green); opacity: 0.5;"></span>VPN actif
				</span>
			</div>
		</div>
	</section>
	{/if}

	<!-- Per-node cards -->
	<section>
		<h2 class="text-xs font-semibold uppercase tracking-widest mb-3" style="color: var(--palais-text-muted);">
			Noeuds
		</h2>
		<div class="grid grid-cols-1 md:grid-cols-3 gap-4">
			{#each data.nodes as node (node.id)}
				{@const backup = node.backup}
				{@const stale = isBackupStale(backup?.lastBackupAt ?? null)}
				<div class="rounded-xl p-5 space-y-4"
					style="background: var(--palais-surface); border: 1px solid var(--palais-border);"
					style:border-color={node.status === 'online' ? 'var(--palais-border)' : 'rgba(239,68,68,0.4)'}
				>
					<!-- Node header -->
					<div class="flex items-center justify-between">
						<div>
							<h3 class="font-semibold text-sm font-mono" style="color: var(--palais-text);">{node.name}</h3>
							{#if node.tailscaleIp}
								<p class="text-xs font-mono mt-0.5" style="color: var(--palais-text-muted);">{node.tailscaleIp}</p>
							{/if}
						</div>
						<span class="text-xs font-semibold capitalize px-2 py-0.5 rounded"
							style:background={node.status === 'online' ? 'rgba(74,222,128,0.1)' : 'rgba(239,68,68,0.1)'}
							style:color={statusColor(node.status)}
						>
							{node.status}
						</span>
					</div>

					<!-- System metrics -->
					{#if node.cpuPercent !== null || node.ramPercent !== null || node.diskPercent !== null}
					<div class="space-y-2">
						{#each [
							{ label: 'CPU', value: node.cpuPercent },
							{ label: 'RAM', value: node.ramPercent },
							{ label: 'Disk', value: node.diskPercent }
						] as metric}
							{#if metric.value !== null}
							<div>
								<div class="flex justify-between text-xs mb-1" style="color: var(--palais-text-muted);">
									<span>{metric.label}</span>
									<span>{metric.value?.toFixed(1)}%</span>
								</div>
								<div class="h-1.5 rounded-full" style="background: rgba(255,255,255,0.05);">
									<div class="h-1.5 rounded-full transition-all" style={`${Object.entries(gaugeStyle(metric.value)).map(([k,v]) => `${k}:${v}`).join(';')}`}></div>
								</div>
							</div>
							{/if}
						{/each}
						{#if node.temperature !== null}
							<p class="text-xs" style="color: var(--palais-text-muted);">
								🌡 {node.temperature?.toFixed(1)}°C
							</p>
						{/if}
					</div>
					{/if}

					<!-- Services -->
					{#if node.services.length > 0}
					<div>
						<p class="text-xs font-semibold uppercase tracking-wider mb-2" style="color: var(--palais-text-muted);">Services</p>
						<div class="space-y-1">
							{#each node.services as svc}
							<div class="flex items-center justify-between">
								<span class="text-xs font-mono" style="color: var(--palais-text);">{svc.serviceName}</span>
								<div class="flex items-center gap-2">
									{#if svc.responseTimeMs}
										<span class="text-xs" style="color: var(--palais-text-muted);">{svc.responseTimeMs}ms</span>
									{/if}
									<span class="w-2 h-2 rounded-full inline-block" style:background={serviceColor(svc.status)}></span>
								</div>
							</div>
							{/each}
						</div>
					</div>
					{/if}

					<!-- Backup status -->
					{#if backup}
					<div class="rounded-lg p-3" style="background: rgba(0,0,0,0.2);">
						<div class="flex items-center justify-between mb-1">
							<span class="text-xs font-semibold" style="color: var(--palais-text-muted);">Backup Zerobyte</span>
							<span class="text-xs font-semibold"
								style:color={backup.status === 'ok' ? 'var(--palais-green)' :
								             backup.status === 'failed' ? 'var(--palais-red)' : 'var(--palais-amber)'}>
								{backup.status}
							</span>
						</div>
						{#if backup.lastBackupAt}
							<p class="text-xs" style:color={stale ? 'var(--palais-red)' : 'var(--palais-text-muted)'}>
								Dernier : {new Date(backup.lastBackupAt).toLocaleString('fr-FR')}
								{#if stale} ⚠️ > 24h{/if}
							</p>
						{/if}
						{#if backup.sizeBytes}
							<p class="text-xs mt-0.5" style="color: var(--palais-text-muted);">
								{(backup.sizeBytes / 1073741824).toFixed(2)} GB
							</p>
						{/if}
					</div>
					{/if}

					<!-- Last seen -->
					{#if node.lastSeenAt}
					<p class="text-xs" style="color: var(--palais-text-muted);">
						Vu : {new Date(node.lastSeenAt).toLocaleString('fr-FR')}
					</p>
					{/if}
				</div>
			{/each}

			{#if data.nodes.length === 0}
				<p class="col-span-3 text-center py-12 text-sm" style="color: var(--palais-text-muted);">
					Aucun noeud enregistré. Le seed démarre au prochain redémarrage du serveur.
				</p>
			{/if}
		</div>
	</section>
</div>
