<script lang="ts">
	import { invalidateAll } from '$app/navigation';

	let { data } = $props();

	let syncing = $state(false);
	let syncError = $state('');
	let syncSuccess = $state('');

	function expiryColor(expiryDate: string | Date | null): string {
		if (!expiryDate) return 'var(--palais-text-muted)';
		const days = (new Date(expiryDate).getTime() - Date.now()) / (1000 * 60 * 60 * 24);
		if (days < 30) return 'var(--palais-red)';
		if (days < 60) return 'var(--palais-gold)';
		return 'var(--palais-green)';
	}

	function expiryBg(expiryDate: string | Date | null): string {
		if (!expiryDate) return 'rgba(138,138,154,0.08)';
		const days = (new Date(expiryDate).getTime() - Date.now()) / (1000 * 60 * 60 * 24);
		if (days < 30) return 'rgba(229,57,53,0.1)';
		if (days < 60) return 'rgba(212,168,67,0.1)';
		return 'rgba(76,175,80,0.1)';
	}

	function expiryBorder(expiryDate: string | Date | null): string {
		if (!expiryDate) return 'rgba(138,138,154,0.2)';
		const days = (new Date(expiryDate).getTime() - Date.now()) / (1000 * 60 * 60 * 24);
		if (days < 30) return 'rgba(229,57,53,0.35)';
		if (days < 60) return 'rgba(212,168,67,0.35)';
		return 'rgba(76,175,80,0.3)';
	}

	function fmtExpiry(expiryDate: string | Date | null): string {
		if (!expiryDate) return '—';
		const d = new Date(expiryDate);
		const days = Math.round((d.getTime() - Date.now()) / (1000 * 60 * 60 * 24));
		return `${d.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' })} (${days}d)`;
	}

	function registrarBadgeStyle(registrar: string): { bg: string; color: string; border: string } {
		if (registrar === 'namecheap') {
			return {
				bg: 'rgba(79,195,247,0.1)',
				color: 'var(--palais-cyan)',
				border: 'rgba(79,195,247,0.3)'
			};
		}
		if (registrar === 'ovh') {
			return {
				bg: 'rgba(212,168,67,0.1)',
				color: 'var(--palais-gold)',
				border: 'rgba(212,168,67,0.3)'
			};
		}
		return {
			bg: 'rgba(138,138,154,0.1)',
			color: 'var(--palais-text-muted)',
			border: 'rgba(138,138,154,0.25)'
		};
	}

	function sslColor(status: string | null): string {
		if (!status) return 'var(--palais-text-muted)';
		if (status === 'valid') return 'var(--palais-green)';
		if (status === 'expired') return 'var(--palais-red)';
		return 'var(--palais-gold)';
	}

	async function syncFromNamecheap() {
		syncing = true;
		syncError = '';
		syncSuccess = '';
		try {
			const res = await fetch('/api/v2/domains/sync', { method: 'POST' });
			if (!res.ok) {
				const body = await res.json().catch(() => ({ error: 'Unknown error' }));
				syncError = body.error ?? `HTTP ${res.status}`;
			} else {
				syncSuccess = 'Sync complete';
				await invalidateAll();
				setTimeout(() => { syncSuccess = ''; }, 3000);
			}
		} catch {
			syncError = 'Network error';
		} finally {
			syncing = false;
		}
	}
</script>

<svelte:head><title>Palais — Domains</title></svelte:head>

<div style="min-height: 100vh; padding: 2rem 0;">

	<!-- HUD HEADER -->
	<header class="flex flex-col gap-3 mb-8">
		<div class="flex items-start justify-between gap-4 flex-wrap">
			<div>
				<p class="text-xs tracking-[0.3em] uppercase mb-1"
					style="color: var(--palais-gold); opacity: 0.6; font-family: 'Orbitron', sans-serif;">
					DNS — REGISTRARS
				</p>
				<h1 class="text-3xl font-bold tracking-widest"
					style="color: var(--palais-gold); font-family: 'Orbitron', sans-serif; text-shadow: 0 0 24px rgba(212,168,67,0.35);">
					DOMAINS
				</h1>
			</div>

			<div class="flex items-center gap-3">
				{#if syncError}
					<span class="text-xs font-mono" style="color: var(--palais-red);">
						{syncError}
					</span>
				{/if}
				{#if syncSuccess}
					<span class="text-xs font-mono" style="color: var(--palais-green);">
						{syncSuccess}
					</span>
				{/if}
				<button
					onclick={syncFromNamecheap}
					disabled={syncing}
					style="
						padding: 8px 18px; border-radius: 6px; cursor: pointer;
						background: rgba(79,195,247,0.1); color: var(--palais-cyan);
						border: 1px solid rgba(79,195,247,0.35);
						font-family: 'Orbitron', sans-serif; font-size: 0.65rem; letter-spacing: 0.12em;
						transition: all 0.2s;
						{syncing ? 'opacity: 0.5; cursor: not-allowed;' : ''}
					"
					onmouseenter={(e) => { if (!syncing) { (e.currentTarget as HTMLElement).style.background = 'rgba(79,195,247,0.18)'; (e.currentTarget as HTMLElement).style.boxShadow = '0 0 12px rgba(79,195,247,0.2)'; } }}
					onmouseleave={(e) => { (e.currentTarget as HTMLElement).style.background = 'rgba(79,195,247,0.1)'; (e.currentTarget as HTMLElement).style.boxShadow = 'none'; }}
				>
					{syncing ? 'SYNCING...' : 'SYNC FROM NAMECHEAP'}
				</button>
			</div>
		</div>

		<!-- Gold separator -->
		<div style="height: 1px; background: linear-gradient(90deg, var(--palais-gold) 0%, rgba(212,168,67,0.08) 100%); opacity: 0.4;"></div>
	</header>

	<!-- Domain count stat -->
	<div class="mb-6 flex items-center gap-4">
		<div class="flex items-center gap-2">
			<span class="text-xs uppercase tracking-[0.25em]"
				style="color: rgba(212,168,67,0.5); font-family: 'Orbitron', sans-serif;">
				Total
			</span>
			<span class="text-lg font-bold tabular-nums"
				style="color: var(--palais-gold); font-family: 'JetBrains Mono', monospace;">
				{data.domains.length}
			</span>
		</div>
		{#if data.domains.some(d => d.expiryDate && (new Date(d.expiryDate).getTime() - Date.now()) < 30 * 24 * 60 * 60 * 1000)}
			<span class="px-3 py-1 rounded-full text-xs font-semibold tracking-wider"
				style="background: rgba(229,57,53,0.13); color: var(--palais-red); border: 1px solid rgba(229,57,53,0.3); font-family: 'Orbitron', sans-serif;">
				EXPIRING SOON
			</span>
		{/if}
	</div>

	<!-- Domains table -->
	{#if data.domains.length === 0}
		<div class="glass-panel hud-bracket rounded-xl p-12 text-center"
			style="border: 1px solid rgba(212,168,67,0.18);">
			<span class="hud-bracket-bottom" style="display: block;">
				<p class="text-sm" style="color: var(--palais-text-muted); font-family: 'JetBrains Mono', monospace;">
					<span style="color: rgba(212,168,67,0.4);">// </span>No domains registered.
				</p>
				<p class="text-xs mt-1" style="color: var(--palais-text-muted); opacity: 0.5; font-family: 'JetBrains Mono', monospace;">
					<span style="color: rgba(212,168,67,0.3);">// </span>Sync from Namecheap to populate.
				</p>
			</span>
		</div>
	{:else}
		<div class="glass-panel hud-bracket rounded-xl overflow-hidden"
			style="border: 1px solid rgba(212,168,67,0.18);">
			<span class="hud-bracket-bottom" style="display: block;">
				<table class="w-full text-sm">
					<thead>
						<tr style="background: var(--palais-surface); border-bottom: 1px solid var(--palais-border);">
							<th class="text-left px-4 py-3 text-xs font-semibold uppercase tracking-wider"
								style="color: var(--palais-text-muted); font-family: 'Orbitron', sans-serif; font-size: 0.6rem; letter-spacing: 0.15em;">
								Domain
							</th>
							<th class="text-left px-4 py-3 text-xs font-semibold uppercase tracking-wider"
								style="color: var(--palais-text-muted); font-family: 'Orbitron', sans-serif; font-size: 0.6rem; letter-spacing: 0.15em;">
								Registrar
							</th>
							<th class="text-left px-4 py-3 text-xs font-semibold uppercase tracking-wider"
								style="color: var(--palais-text-muted); font-family: 'Orbitron', sans-serif; font-size: 0.6rem; letter-spacing: 0.15em;">
								Expiry
							</th>
							<th class="text-center px-4 py-3 text-xs font-semibold uppercase tracking-wider"
								style="color: var(--palais-text-muted); font-family: 'Orbitron', sans-serif; font-size: 0.6rem; letter-spacing: 0.15em;">
								Auto-Renew
							</th>
							<th class="text-left px-4 py-3 text-xs font-semibold uppercase tracking-wider"
								style="color: var(--palais-text-muted); font-family: 'Orbitron', sans-serif; font-size: 0.6rem; letter-spacing: 0.15em;">
								SSL
							</th>
						</tr>
					</thead>
					<tbody>
						{#each data.domains as domain, i (domain.id)}
							{@const badge = registrarBadgeStyle(domain.registrar)}
							<tr
								style="
									background: {i % 2 === 0 ? 'var(--palais-bg)' : 'rgba(17,17,24,0.6)'};
									border-bottom: 1px solid rgba(42,42,58,0.6);
									transition: background 0.15s;
								"
								onmouseenter={(e) => { (e.currentTarget as HTMLElement).style.background = 'rgba(212,168,67,0.04)'; }}
								onmouseleave={(e) => { (e.currentTarget as HTMLElement).style.background = i % 2 === 0 ? 'var(--palais-bg)' : 'rgba(17,17,24,0.6)'; }}
							>
								<!-- Domain name — links to detail page -->
								<td class="px-4 py-3">
									<a
										href="/domains/{encodeURIComponent(domain.name)}"
										style="
											color: var(--palais-text);
											text-decoration: none;
											font-family: 'JetBrains Mono', monospace;
											font-size: 0.85rem;
											font-weight: 500;
											transition: color 0.15s;
										"
										onmouseenter={(e) => { (e.currentTarget as HTMLElement).style.color = 'var(--palais-cyan)'; }}
										onmouseleave={(e) => { (e.currentTarget as HTMLElement).style.color = 'var(--palais-text)'; }}
									>
										{domain.name}
									</a>
								</td>

								<!-- Registrar badge -->
								<td class="px-4 py-3">
									<span class="px-2 py-0.5 rounded text-xs font-semibold tracking-wider uppercase"
										style="
											background: {badge.bg};
											color: {badge.color};
											border: 1px solid {badge.border};
											font-family: 'Orbitron', sans-serif;
											font-size: 0.58rem;
											letter-spacing: 0.1em;
										">
										{domain.registrar}
									</span>
								</td>

								<!-- Expiry date with color coding -->
								<td class="px-4 py-3">
									<span class="px-2 py-0.5 rounded text-xs tabular-nums"
										style="
											background: {expiryBg(domain.expiryDate)};
											color: {expiryColor(domain.expiryDate)};
											border: 1px solid {expiryBorder(domain.expiryDate)};
											font-family: 'JetBrains Mono', monospace;
											font-size: 0.75rem;
										">
										{fmtExpiry(domain.expiryDate)}
									</span>
								</td>

								<!-- Auto-renew toggle -->
								<td class="px-4 py-3 text-center">
									<span class="w-2 h-2 rounded-full inline-block"
										style="
											background: {domain.autoRenew ? 'var(--palais-green)' : 'var(--palais-text-muted)'};
											box-shadow: {domain.autoRenew ? '0 0 6px 1px rgba(76,175,80,0.4)' : 'none'};
										"
										title={domain.autoRenew ? 'Auto-renew enabled' : 'Auto-renew disabled'}
									></span>
								</td>

								<!-- SSL status -->
								<td class="px-4 py-3">
									<span class="text-xs font-semibold"
										style="color: {sslColor(domain.sslStatus)}; font-family: 'JetBrains Mono', monospace;">
										{domain.sslStatus ? domain.sslStatus.toUpperCase() : '—'}
									</span>
								</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</span>
		</div>
	{/if}
</div>
