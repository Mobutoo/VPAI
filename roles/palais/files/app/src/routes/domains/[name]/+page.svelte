<script lang="ts">
	import { invalidateAll } from '$app/navigation';

	let { data } = $props();

	// ── Inline edit state ──────────────────────────────────────────
	let editingId = $state<number | null>(null);
	let editingValue = $state('');
	let editingSaving = $state(false);
	let editError = $state('');

	function startEdit(record: typeof data.records[0]) {
		editingId = record.id;
		editingValue = record.value;
		editError = '';
	}

	function cancelEdit() {
		editingId = null;
		editingValue = '';
		editError = '';
	}

	async function saveEdit(recordId: number) {
		if (!editingValue.trim()) return;
		editingSaving = true;
		editError = '';
		try {
			const res = await fetch(
				`/api/v2/domains/${encodeURIComponent(data.domain.name)}/dns/${recordId}`,
				{
					method: 'PATCH',
					headers: { 'Content-Type': 'application/json' },
					body: JSON.stringify({ value: editingValue })
				}
			);
			if (!res.ok) {
				const body = await res.json().catch(() => ({ error: 'Unknown error' }));
				editError = body.error ?? `HTTP ${res.status}`;
			} else {
				editingId = null;
				await invalidateAll();
			}
		} catch {
			editError = 'Network error';
		} finally {
			editingSaving = false;
		}
	}

	// ── Add record form state ──────────────────────────────────────
	let addOpen = $state(false);
	let addType = $state('A');
	let addHost = $state('');
	let addValue = $state('');
	let addTtl = $state(1800);
	let addSaving = $state(false);
	let addError = $state('');

	const DNS_TYPES = ['A', 'AAAA', 'CNAME', 'MX', 'TXT', 'NS', 'SRV', 'CAA'];

	function openAddForm() {
		addOpen = true;
		addType = 'A';
		addHost = '';
		addValue = '';
		addTtl = 1800;
		addError = '';
	}

	function closeAddForm() {
		addOpen = false;
		addError = '';
	}

	async function submitAdd() {
		if (!addHost.trim() || !addValue.trim()) {
			addError = 'Host and value are required';
			return;
		}
		addSaving = true;
		addError = '';
		try {
			const res = await fetch(
				`/api/v2/domains/${encodeURIComponent(data.domain.name)}/dns`,
				{
					method: 'POST',
					headers: { 'Content-Type': 'application/json' },
					body: JSON.stringify({
						recordType: addType,
						host: addHost,
						value: addValue,
						ttl: addTtl
					})
				}
			);
			if (!res.ok) {
				const body = await res.json().catch(() => ({ error: 'Unknown error' }));
				addError = body.error ?? `HTTP ${res.status}`;
			} else {
				closeAddForm();
				await invalidateAll();
			}
		} catch {
			addError = 'Network error';
		} finally {
			addSaving = false;
		}
	}

	// ── Delete record state ────────────────────────────────────────
	let deletingId = $state<number | null>(null);
	let confirmDeleteId = $state<number | null>(null);

	async function deleteRecord(recordId: number) {
		deletingId = recordId;
		try {
			const res = await fetch(
				`/api/v2/domains/${encodeURIComponent(data.domain.name)}/dns/${recordId}`,
				{ method: 'DELETE' }
			);
			if (res.ok) {
				confirmDeleteId = null;
				await invalidateAll();
			}
		} catch {
			// silent fail — user can retry
		} finally {
			deletingId = null;
		}
	}

	// ── Formatting helpers ─────────────────────────────────────────
	function expiryColor(expiryDate: string | Date | null): string {
		if (!expiryDate) return 'var(--palais-text-muted)';
		const days = (new Date(expiryDate).getTime() - Date.now()) / (1000 * 60 * 60 * 24);
		if (days < 30) return 'var(--palais-red)';
		if (days < 60) return 'var(--palais-gold)';
		return 'var(--palais-green)';
	}

	function fmtExpiry(expiryDate: string | Date | null): string {
		if (!expiryDate) return '—';
		const d = new Date(expiryDate);
		const days = Math.round((d.getTime() - Date.now()) / (1000 * 60 * 60 * 24));
		return `${d.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' })} (${days}d)`;
	}

	function recordTypeBadge(type: string): { bg: string; color: string } {
		const map: Record<string, { bg: string; color: string }> = {
			A:     { bg: 'rgba(79,195,247,0.12)',  color: 'var(--palais-cyan)' },
			AAAA:  { bg: 'rgba(79,195,247,0.12)',  color: 'var(--palais-cyan)' },
			CNAME: { bg: 'rgba(212,168,67,0.12)',  color: 'var(--palais-gold)' },
			MX:    { bg: 'rgba(76,175,80,0.12)',   color: 'var(--palais-green)' },
			TXT:   { bg: 'rgba(138,138,154,0.12)', color: 'var(--palais-text-muted)' },
			NS:    { bg: 'rgba(232,131,58,0.12)',  color: 'var(--palais-amber)' },
		};
		return map[type] ?? { bg: 'rgba(138,138,154,0.1)', color: 'var(--palais-text-muted)' };
	}

	const inputStyle = `
		width: 100%; padding: 7px 10px;
		background: rgba(0,0,0,0.35); border-radius: 6px;
		border: 1px solid rgba(212,168,67,0.2);
		color: var(--palais-text); font-family: 'JetBrains Mono', monospace; font-size: 0.8rem;
		outline: none;
	`;
</script>

<svelte:head><title>Palais — {data.domain.name}</title></svelte:head>

<div style="min-height: 100vh; padding: 2rem 0;">

	<!-- Breadcrumb -->
	<div class="mb-4">
		<a href="/domains"
			style="color: rgba(212,168,67,0.5); font-family: 'JetBrains Mono', monospace; font-size: 0.75rem; text-decoration: none;"
			onmouseenter={(e) => { (e.currentTarget as HTMLElement).style.color = 'var(--palais-gold)'; }}
			onmouseleave={(e) => { (e.currentTarget as HTMLElement).style.color = 'rgba(212,168,67,0.5)'; }}
		>
			DOMAINS
		</a>
		<span style="color: rgba(212,168,67,0.3); margin: 0 8px; font-family: 'JetBrains Mono', monospace;">/</span>
		<span style="color: var(--palais-gold); font-family: 'JetBrains Mono', monospace; font-size: 0.75rem;">
			{data.domain.name.toUpperCase()}
		</span>
	</div>

	<!-- HUD HEADER -->
	<header class="flex flex-col gap-3 mb-8">
		<div class="flex items-start justify-between gap-4 flex-wrap">
			<div>
				<p class="text-xs tracking-[0.3em] uppercase mb-1"
					style="color: var(--palais-gold); opacity: 0.6; font-family: 'Orbitron', sans-serif;">
					{data.domain.registrar.toUpperCase()} — DNS RECORDS
				</p>
				<h1 class="text-2xl font-bold tracking-wider"
					style="color: var(--palais-gold); font-family: 'Orbitron', sans-serif; text-shadow: 0 0 20px rgba(212,168,67,0.3);">
					{data.domain.name}
				</h1>
				<div class="flex items-center gap-4 mt-2">
					<span class="text-xs" style="color: var(--palais-text-muted); font-family: 'JetBrains Mono', monospace;">
						Expiry:
						<span style="color: {expiryColor(data.domain.expiryDate)};">
							{fmtExpiry(data.domain.expiryDate)}
						</span>
					</span>
					{#if data.domain.autoRenew}
						<span class="px-2 py-0.5 rounded text-xs"
							style="background: rgba(76,175,80,0.1); color: var(--palais-green); border: 1px solid rgba(76,175,80,0.25); font-family: 'Orbitron', sans-serif; font-size: 0.58rem; letter-spacing: 0.1em;">
							AUTO-RENEW
						</span>
					{/if}
					{#if data.domain.sslStatus}
						<span class="px-2 py-0.5 rounded text-xs"
							style="background: rgba(79,195,247,0.1); color: var(--palais-cyan); border: 1px solid rgba(79,195,247,0.25); font-family: 'Orbitron', sans-serif; font-size: 0.58rem; letter-spacing: 0.1em;">
							SSL: {data.domain.sslStatus.toUpperCase()}
						</span>
					{/if}
				</div>
			</div>

			<button
				onclick={openAddForm}
				style="
					padding: 8px 18px; border-radius: 6px; cursor: pointer;
					background: rgba(212,168,67,0.12); color: var(--palais-gold);
					border: 1px solid rgba(212,168,67,0.35);
					font-family: 'Orbitron', sans-serif; font-size: 0.65rem; letter-spacing: 0.12em;
					transition: all 0.2s;
				"
				onmouseenter={(e) => { (e.currentTarget as HTMLElement).style.background = 'rgba(212,168,67,0.2)'; (e.currentTarget as HTMLElement).style.boxShadow = '0 0 12px rgba(212,168,67,0.2)'; }}
				onmouseleave={(e) => { (e.currentTarget as HTMLElement).style.background = 'rgba(212,168,67,0.12)'; (e.currentTarget as HTMLElement).style.boxShadow = 'none'; }}
			>
				+ ADD RECORD
			</button>
		</div>

		<div style="height: 1px; background: linear-gradient(90deg, var(--palais-gold) 0%, rgba(212,168,67,0.08) 100%); opacity: 0.4;"></div>
	</header>

	<!-- DNS Records table -->
	{#if data.records.length === 0}
		<div class="glass-panel hud-bracket rounded-xl p-12 text-center"
			style="border: 1px solid rgba(212,168,67,0.18);">
			<span class="hud-bracket-bottom" style="display: block;">
				<p class="text-sm" style="color: var(--palais-text-muted); font-family: 'JetBrains Mono', monospace;">
					<span style="color: rgba(212,168,67,0.4);">// </span>No DNS records found.
				</p>
			</span>
		</div>
	{:else}
		<div class="glass-panel hud-bracket rounded-xl overflow-hidden mb-4"
			style="border: 1px solid rgba(212,168,67,0.18);">
			<span class="hud-bracket-bottom" style="display: block;">
				<table class="w-full text-sm">
					<thead>
						<tr style="background: var(--palais-surface); border-bottom: 1px solid var(--palais-border);">
							<th class="text-left px-4 py-3 text-xs font-semibold uppercase tracking-wider"
								style="color: var(--palais-text-muted); font-family: 'Orbitron', sans-serif; font-size: 0.6rem; letter-spacing: 0.15em;">Type</th>
							<th class="text-left px-4 py-3 text-xs font-semibold uppercase tracking-wider"
								style="color: var(--palais-text-muted); font-family: 'Orbitron', sans-serif; font-size: 0.6rem; letter-spacing: 0.15em;">Host</th>
							<th class="text-left px-4 py-3 text-xs font-semibold uppercase tracking-wider"
								style="color: var(--palais-text-muted); font-family: 'Orbitron', sans-serif; font-size: 0.6rem; letter-spacing: 0.15em;">Value</th>
							<th class="text-right px-4 py-3 text-xs font-semibold uppercase tracking-wider"
								style="color: var(--palais-text-muted); font-family: 'Orbitron', sans-serif; font-size: 0.6rem; letter-spacing: 0.15em;">TTL</th>
							<th class="text-center px-4 py-3 text-xs font-semibold uppercase tracking-wider"
								style="color: var(--palais-text-muted); font-family: 'Orbitron', sans-serif; font-size: 0.6rem; letter-spacing: 0.15em;">Actions</th>
						</tr>
					</thead>
					<tbody>
						{#each data.records as record, i (record.id)}
							{@const badge = recordTypeBadge(record.recordType)}
							<tr style="
								background: {i % 2 === 0 ? 'var(--palais-bg)' : 'rgba(17,17,24,0.6)'};
								border-bottom: 1px solid rgba(42,42,58,0.6);
							">
								<!-- Type -->
								<td class="px-4 py-3">
									<span class="px-2 py-0.5 rounded text-xs font-bold"
										style="
											background: {badge.bg};
											color: {badge.color};
											border: 1px solid {badge.color}40;
											font-family: 'Orbitron', sans-serif;
											font-size: 0.62rem;
											letter-spacing: 0.08em;
										">
										{record.recordType}
									</span>
								</td>

								<!-- Host -->
								<td class="px-4 py-3">
									<span style="color: var(--palais-text); font-family: 'JetBrains Mono', monospace; font-size: 0.82rem;">
										{record.host}
									</span>
								</td>

								<!-- Value — click to inline edit -->
								<td class="px-4 py-3 max-w-xs">
									{#if editingId === record.id}
										<div class="flex items-center gap-2">
											<input
												type="text"
												bind:value={editingValue}
												style="{inputStyle} max-width: 260px; flex: 1;"
												onfocus={(e) => { (e.currentTarget as HTMLElement).style.borderColor = 'rgba(212,168,67,0.5)'; }}
												onblur={(e) => { (e.currentTarget as HTMLElement).style.borderColor = 'rgba(212,168,67,0.2)'; }}
												onkeydown={(e) => { if (e.key === 'Enter') saveEdit(record.id); if (e.key === 'Escape') cancelEdit(); }}
											/>
											<button
												onclick={() => saveEdit(record.id)}
												disabled={editingSaving}
												style="
													padding: 4px 10px; border-radius: 4px; cursor: pointer;
													background: rgba(76,175,80,0.15); color: var(--palais-green);
													border: 1px solid rgba(76,175,80,0.35);
													font-family: 'Orbitron', sans-serif; font-size: 0.58rem; letter-spacing: 0.1em;
													{editingSaving ? 'opacity: 0.5;' : ''}
												"
											>
												{editingSaving ? '...' : 'SAVE'}
											</button>
											<button
												onclick={cancelEdit}
												style="
													padding: 4px 10px; border-radius: 4px; cursor: pointer;
													background: transparent; color: rgba(212,168,67,0.5);
													border: 1px solid rgba(212,168,67,0.2);
													font-family: 'Orbitron', sans-serif; font-size: 0.58rem;
												"
											>
												X
											</button>
										</div>
										{#if editError}
											<p class="text-xs mt-1" style="color: var(--palais-red); font-family: 'JetBrains Mono', monospace;">
												{editError}
											</p>
										{/if}
									{:else}
										<span
											class="block truncate cursor-pointer transition-colors"
											style="
												color: var(--palais-cyan);
												font-family: 'JetBrains Mono', monospace;
												font-size: 0.78rem;
												max-width: 280px;
											"
											title="Click to edit"
											onclick={() => startEdit(record)}
											onmouseenter={(e) => { (e.currentTarget as HTMLElement).style.color = 'var(--palais-gold)'; }}
											onmouseleave={(e) => { (e.currentTarget as HTMLElement).style.color = 'var(--palais-cyan)'; }}
											role="button"
											tabindex="0"
											onkeydown={(e) => { if (e.key === 'Enter' || e.key === ' ') startEdit(record); }}
										>
											{record.value}
										</span>
									{/if}
								</td>

								<!-- TTL -->
								<td class="px-4 py-3 text-right">
									<span class="tabular-nums" style="color: var(--palais-text-muted); font-family: 'JetBrains Mono', monospace; font-size: 0.75rem;">
										{record.ttl ?? 1800}s
									</span>
								</td>

								<!-- Delete -->
								<td class="px-4 py-3 text-center">
									{#if confirmDeleteId === record.id}
										<div class="flex items-center justify-center gap-2">
											<button
												onclick={() => deleteRecord(record.id)}
												disabled={deletingId === record.id}
												style="
													padding: 3px 8px; border-radius: 4px; cursor: pointer;
													background: rgba(229,57,53,0.15); color: var(--palais-red);
													border: 1px solid rgba(229,57,53,0.4);
													font-family: 'Orbitron', sans-serif; font-size: 0.55rem; letter-spacing: 0.08em;
													{deletingId === record.id ? 'opacity: 0.5;' : ''}
												"
											>
												{deletingId === record.id ? '...' : 'CONFIRM'}
											</button>
											<button
												onclick={() => { confirmDeleteId = null; }}
												style="
													padding: 3px 8px; border-radius: 4px; cursor: pointer;
													background: transparent; color: rgba(212,168,67,0.4);
													border: 1px solid rgba(212,168,67,0.18);
													font-family: 'Orbitron', sans-serif; font-size: 0.55rem;
												"
											>
												X
											</button>
										</div>
									{:else}
										<button
											onclick={() => { confirmDeleteId = record.id; }}
											title="Delete record"
											style="
												background: none; border: none; cursor: pointer; padding: 4px;
												color: rgba(229,57,53,0.35);
												transition: color 0.2s, filter 0.2s;
											"
											onmouseenter={(e) => { (e.currentTarget as HTMLElement).style.color = 'var(--palais-red)'; (e.currentTarget as HTMLElement).style.filter = 'drop-shadow(0 0 5px rgba(229,57,53,0.5))'; }}
											onmouseleave={(e) => { (e.currentTarget as HTMLElement).style.color = 'rgba(229,57,53,0.35)'; (e.currentTarget as HTMLElement).style.filter = 'none'; }}
										>
											<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none"
												stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
												<polyline points="3 6 5 6 21 6"/>
												<path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/>
												<path d="M10 11v6"/>
												<path d="M14 11v6"/>
												<path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/>
											</svg>
										</button>
									{/if}
								</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</span>
		</div>
	{/if}

	<p class="text-xs" style="color: rgba(212,168,67,0.4); font-family: 'JetBrains Mono', monospace;">
		// Click a value cell to edit inline. Changes are pushed to Namecheap.
	</p>
</div>

<!-- ── Add Record Modal ─────────────────────────────────────────── -->
{#if addOpen}
	<div
		style="position: fixed; inset: 0; z-index: 100; background: rgba(0,0,0,0.72); backdrop-filter: blur(4px);"
		onclick={closeAddForm}
		role="presentation"
	></div>

	<div
		class="glass-panel hud-bracket rounded-xl"
		style="
			position: fixed; top: 50%; left: 50%; transform: translate(-50%, -50%);
			z-index: 101; width: min(500px, 95vw); padding: 1.5rem;
			border: 1px solid rgba(212,168,67,0.3);
			box-shadow: 0 8px 64px 0 rgba(0,0,0,0.6), 0 0 0 1px rgba(212,168,67,0.08);
		"
		role="dialog"
		aria-label="Add DNS Record"
	>
		<span class="hud-bracket-bottom" style="display: block;">
			<div class="flex items-center justify-between mb-5">
				<h2 style="color: var(--palais-gold); font-family: 'Orbitron', sans-serif; font-size: 0.85rem; letter-spacing: 0.15em; text-transform: uppercase;">
					Add DNS Record
				</h2>
				<button
					onclick={closeAddForm}
					style="background: none; border: none; cursor: pointer; color: rgba(212,168,67,0.4); font-size: 1.2rem; line-height: 1; padding: 2px 6px;"
				>x</button>
			</div>

			<div class="space-y-4">
				<!-- Type -->
				<div>
					<label style="display: block; font-family: 'Orbitron', sans-serif; font-size: 0.6rem; letter-spacing: 0.2em; color: rgba(212,168,67,0.55); text-transform: uppercase; margin-bottom: 6px;">
						Type
					</label>
					<select
						bind:value={addType}
						style="
							{inputStyle}
							cursor: pointer;
						"
					>
						{#each DNS_TYPES as t}
							<option value={t}>{t}</option>
						{/each}
					</select>
				</div>

				<!-- Host -->
				<div>
					<label style="display: block; font-family: 'Orbitron', sans-serif; font-size: 0.6rem; letter-spacing: 0.2em; color: rgba(212,168,67,0.55); text-transform: uppercase; margin-bottom: 6px;">
						Host
					</label>
					<input
						type="text"
						bind:value={addHost}
						placeholder="@ or subdomain"
						style={inputStyle}
						onfocus={(e) => { (e.currentTarget as HTMLElement).style.borderColor = 'rgba(212,168,67,0.5)'; }}
						onblur={(e) => { (e.currentTarget as HTMLElement).style.borderColor = 'rgba(212,168,67,0.2)'; }}
					/>
				</div>

				<!-- Value -->
				<div>
					<label style="display: block; font-family: 'Orbitron', sans-serif; font-size: 0.6rem; letter-spacing: 0.2em; color: rgba(212,168,67,0.55); text-transform: uppercase; margin-bottom: 6px;">
						Value
					</label>
					<input
						type="text"
						bind:value={addValue}
						placeholder="IP address or target"
						style={inputStyle}
						onfocus={(e) => { (e.currentTarget as HTMLElement).style.borderColor = 'rgba(212,168,67,0.5)'; }}
						onblur={(e) => { (e.currentTarget as HTMLElement).style.borderColor = 'rgba(212,168,67,0.2)'; }}
					/>
				</div>

				<!-- TTL -->
				<div>
					<label style="display: block; font-family: 'Orbitron', sans-serif; font-size: 0.6rem; letter-spacing: 0.2em; color: rgba(212,168,67,0.55); text-transform: uppercase; margin-bottom: 6px;">
						TTL (seconds)
					</label>
					<input
						type="number"
						bind:value={addTtl}
						min="60"
						max="86400"
						style={inputStyle}
						onfocus={(e) => { (e.currentTarget as HTMLElement).style.borderColor = 'rgba(212,168,67,0.5)'; }}
						onblur={(e) => { (e.currentTarget as HTMLElement).style.borderColor = 'rgba(212,168,67,0.2)'; }}
					/>
				</div>
			</div>

			{#if addError}
				<p style="color: var(--palais-red); font-family: 'JetBrains Mono', monospace; font-size: 0.75rem; margin-top: 10px;">
					{addError}
				</p>
			{/if}

			<div class="flex gap-3 justify-end mt-6">
				<button
					onclick={closeAddForm}
					disabled={addSaving}
					style="
						padding: 8px 18px; border-radius: 6px; cursor: pointer;
						background: transparent; color: rgba(212,168,67,0.6);
						border: 1px solid rgba(212,168,67,0.25);
						font-family: 'Orbitron', sans-serif; font-size: 0.65rem; letter-spacing: 0.12em;
					"
				>
					CANCEL
				</button>
				<button
					onclick={submitAdd}
					disabled={addSaving}
					style="
						padding: 8px 18px; border-radius: 6px; cursor: pointer;
						background: rgba(212,168,67,0.15); color: var(--palais-gold);
						border: 1px solid rgba(212,168,67,0.4);
						font-family: 'Orbitron', sans-serif; font-size: 0.65rem; letter-spacing: 0.12em;
						transition: all 0.2s;
						{addSaving ? 'opacity: 0.5; cursor: not-allowed;' : ''}
					"
				>
					{addSaving ? 'ADDING...' : 'ADD RECORD'}
				</button>
			</div>
		</span>
	</div>
{/if}
