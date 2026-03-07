<script lang="ts">
	import { invalidateAll } from '$app/navigation';

	let { data } = $props();

	// ─── Provider color palette ───────────────────────────────────────
	const PROVIDER_COLORS: Record<string, string> = {
		hetzner:    'var(--palais-cyan)',
		ovh:        'var(--palais-gold)',
		ai:         '#F4A261',   // amber
		anthropic:  '#9B7EDE',   // purple
		openai:     '#10B981',   // emerald
		openrouter: '#F4A261',   // amber
		ionos:      '#60A5FA',   // blue
		other:      'var(--palais-text-muted)',
	};

	function providerColor(provider: string): string {
		return PROVIDER_COLORS[provider.toLowerCase()] ?? PROVIDER_COLORS.other;
	}

	// ─── Budget gauge helpers ──────────────────────────────────────────
	const budgetPct = $derived(
		data.summary.budgetEur > 0
			? Math.min((data.summary.totalEur / data.summary.budgetEur) * 100, 100)
			: 0
	);

	function gaugeColor(pct: number): string {
		if (pct >= 90) return 'var(--palais-red)';
		if (pct >= 70) return 'var(--palais-gold)';
		return 'var(--palais-green)';
	}

	const dailyBurnRate = $derived(
		Math.round((data.summary.totalEur / 30) * 100) / 100
	);

	// ─── SVG bar chart for monthly trend ─────────────────────────────
	const CHART_W = 400;
	const CHART_H = 80;
	const BAR_GAP = 6;

	const chartData = $derived(() => {
		const hist = data.monthlyHistory;
		if (hist.length === 0) return { bars: [], maxVal: 0 };

		const maxVal = Math.max(...hist.map((m) => m.total), 0.01);
		const barW = hist.length > 0
			? Math.floor((CHART_W - BAR_GAP * (hist.length - 1)) / hist.length)
			: 0;

		const bars = hist.map((m, i) => {
			const barH = Math.max((m.total / maxVal) * CHART_H, 2);
			const x = i * (barW + BAR_GAP);
			const y = CHART_H - barH;
			// Short month label e.g. "Jan" from "2026-01"
			const [yr, mo] = m.month.split('-');
			const label = new Date(Number(yr), Number(mo) - 1, 1)
				.toLocaleString('en', { month: 'short' });
			return { x, y, w: barW, h: barH, total: m.total, label };
		});

		return { bars, maxVal };
	});

	// ─── Provider stacked bar breakdown ───────────────────────────────
	const providerData = $derived(() => {
		const bp = data.summary.byProvider;
		const total = data.summary.totalEur;
		if (total === 0) return [];
		return Object.entries(bp)
			.sort(([, a], [, b]) => b - a)
			.map(([provider, amount]) => ({
				provider,
				amount: Math.round(amount * 100) / 100,
				pct: Math.round((amount / total) * 1000) / 10,
			}));
	});

	// ─── Add entry form state ──────────────────────────────────────────
	let showForm = $state(false);
	let formProvider = $state('hetzner');
	let formCategory = $state('hosting');
	let formAmount = $state('');
	let formDescription = $state('');
	let formPeriodStart = $state(new Date().toISOString().substring(0, 7) + '-01');
	let formPeriodEnd = $state('');
	let formSubmitting = $state(false);
	let formError = $state('');
	let formSuccess = $state('');

	// Auto-compute period end from start (end of same month)
	$effect(() => {
		if (formPeriodStart) {
			try {
				const d = new Date(formPeriodStart);
				const endOfMonth = new Date(d.getFullYear(), d.getMonth() + 1, 0);
				formPeriodEnd = endOfMonth.toISOString().substring(0, 10);
			} catch {
				// ignore
			}
		}
	});

	async function submitEntry() {
		formError = '';
		formSuccess = '';
		const amount = parseFloat(formAmount);
		if (!formProvider.trim()) { formError = 'Provider is required'; return; }
		if (!formCategory.trim()) { formError = 'Category is required'; return; }
		if (isNaN(amount) || amount <= 0) { formError = 'Amount must be a positive number'; return; }
		if (!formPeriodStart) { formError = 'Period start is required'; return; }
		if (!formPeriodEnd) { formError = 'Period end is required'; return; }

		formSubmitting = true;
		try {
			const res = await fetch('/api/v2/costs/entries', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({
					provider: formProvider.trim().toLowerCase(),
					category: formCategory.trim().toLowerCase(),
					amountEur: amount,
					periodStart: new Date(formPeriodStart).toISOString(),
					periodEnd: new Date(formPeriodEnd).toISOString(),
					description: formDescription.trim() || undefined,
				}),
			});
			const body = await res.json();
			if (!body.success) throw new Error(body.error ?? `HTTP ${res.status}`);
			formSuccess = 'Entry recorded successfully.';
			formAmount = '';
			formDescription = '';
			await invalidateAll();
		} catch (e) {
			formError = e instanceof Error ? e.message : 'Submission failed';
		} finally {
			formSubmitting = false;
		}
	}
</script>

<svelte:head><title>Palais — Costs</title></svelte:head>

<div style="min-height: 100vh; padding: 2rem 0;">

	<!-- ═══════════════════════════════════════════ HUD HEADER ═════ -->
	<header class="flex flex-col gap-3 mb-8">
		<div class="flex items-start justify-between gap-4 flex-wrap">
			<div>
				<p class="text-xs tracking-[0.3em] uppercase mb-1"
					style="color: var(--palais-gold); opacity: 0.6; font-family: 'Orbitron', sans-serif;">
					INFRASTRUCTURE — FINANCIAL CONTROL
				</p>
				<h1 class="text-3xl font-bold tracking-widest"
					style="color: var(--palais-gold); font-family: 'Orbitron', sans-serif; text-shadow: 0 0 24px rgba(212,168,67,0.35);">
					COSTS
				</h1>
			</div>

			<button
				onclick={() => { showForm = !showForm; formError = ''; formSuccess = ''; }}
				style="
					padding: 8px 18px; border-radius: 6px; cursor: pointer;
					background: rgba(212,168,67,0.12); color: var(--palais-gold);
					border: 1px solid rgba(212,168,67,0.35);
					font-family: 'Orbitron', sans-serif; font-size: 0.62rem; letter-spacing: 0.14em;
					transition: all 0.2s; align-self: flex-start;
				"
				onmouseenter={(e) => { const el = e.currentTarget as HTMLElement; el.style.background = 'rgba(212,168,67,0.2)'; el.style.borderColor = 'rgba(212,168,67,0.55)'; }}
				onmouseleave={(e) => { const el = e.currentTarget as HTMLElement; el.style.background = 'rgba(212,168,67,0.12)'; el.style.borderColor = 'rgba(212,168,67,0.35)'; }}
			>
				{showForm ? 'CANCEL' : '+ ADD ENTRY'}
			</button>
		</div>

		<div style="height: 1px; background: linear-gradient(90deg, var(--palais-gold) 0%, rgba(212,168,67,0.08) 100%); opacity: 0.4;"></div>
	</header>

	<!-- ════════════════════════════════════════ SUMMARY ROW ═══════ -->
	<div class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">

		<!-- Total cost card -->
		<div class="glass-panel hud-bracket rounded-xl p-5 md:col-span-1"
			style="border: 1px solid rgba(212,168,67,0.22);">
			<span class="hud-bracket-bottom" style="display: block;">
				<p style="font-family: 'Orbitron', sans-serif; font-size: 0.58rem; letter-spacing: 0.22em; color: rgba(212,168,67,0.5); text-transform: uppercase; margin-bottom: 10px;">
					30-Day Total
				</p>
				<p style="
					font-family: 'Orbitron', sans-serif; font-size: 2.4rem; font-weight: 700;
					color: var(--palais-gold);
					text-shadow: 0 0 24px rgba(212,168,67,0.4);
					line-height: 1;
				">
					{data.summary.totalEur.toFixed(2)}<span style="font-size: 1rem; opacity: 0.6; margin-left: 4px;">EUR</span>
				</p>
				<p class="mt-3" style="font-family: 'JetBrains Mono', monospace; font-size: 0.75rem; color: var(--palais-text-muted);">
					Daily burn: <span style="color: var(--palais-cyan);">{dailyBurnRate.toFixed(2)} EUR/day</span>
				</p>
			</span>
		</div>

		<!-- Budget gauge -->
		<div class="glass-panel hud-bracket rounded-xl p-5"
			style="border: 1px solid rgba(212,168,67,0.18);">
			<span class="hud-bracket-bottom" style="display: block;">
				<div class="flex items-center justify-between mb-3">
					<p style="font-family: 'Orbitron', sans-serif; font-size: 0.58rem; letter-spacing: 0.22em; color: rgba(212,168,67,0.5); text-transform: uppercase;">
						Budget
					</p>
					<span style="
						font-family: 'JetBrains Mono', monospace; font-size: 0.78rem;
						color: {gaugeColor(budgetPct)};
					">{budgetPct.toFixed(1)}%</span>
				</div>

				<!-- Gauge track -->
				<div style="
					height: 10px; border-radius: 5px;
					background: rgba(255,255,255,0.05);
					border: 1px solid rgba(212,168,67,0.12);
					overflow: hidden; margin-bottom: 10px;
				">
					<div style="
						height: 100%; border-radius: 5px;
						width: {budgetPct}%;
						background: {gaugeColor(budgetPct)};
						box-shadow: 0 0 8px {gaugeColor(budgetPct)};
						transition: width 0.6s ease;
					"></div>
				</div>

				<div class="flex justify-between">
					<span style="font-family: 'JetBrains Mono', monospace; font-size: 0.72rem; color: var(--palais-text-muted);">
						{data.summary.totalEur.toFixed(2)} EUR
					</span>
					<span style="font-family: 'JetBrains Mono', monospace; font-size: 0.72rem; color: var(--palais-text-muted);">
						{data.summary.budgetEur.toFixed(0)} EUR limit
					</span>
				</div>

				{#if budgetPct >= 90}
					<p class="mt-2" style="font-family: 'Orbitron', sans-serif; font-size: 0.55rem; letter-spacing: 0.15em; color: var(--palais-red); animation: pulseGold 1.2s ease-in-out infinite;">
						BUDGET CRITICAL
					</p>
				{:else if budgetPct >= 70}
					<p class="mt-2" style="font-family: 'Orbitron', sans-serif; font-size: 0.55rem; letter-spacing: 0.15em; color: var(--palais-gold);">
						BUDGET ELEVATED
					</p>
				{/if}
			</span>
		</div>

		<!-- Provider breakdown -->
		<div class="glass-panel hud-bracket rounded-xl p-5"
			style="border: 1px solid rgba(212,168,67,0.18);">
			<span class="hud-bracket-bottom" style="display: block;">
				<p style="font-family: 'Orbitron', sans-serif; font-size: 0.58rem; letter-spacing: 0.22em; color: rgba(212,168,67,0.5); text-transform: uppercase; margin-bottom: 12px;">
					By Provider
				</p>

				{#if providerData().length === 0}
					<p style="color: var(--palais-text-muted); font-family: 'JetBrains Mono', monospace; font-size: 0.75rem;">No data</p>
				{:else}
					<div class="space-y-2">
						{#each providerData() as row (row.provider)}
							<div>
								<div class="flex justify-between items-baseline mb-1">
									<span style="font-family: 'JetBrains Mono', monospace; font-size: 0.72rem; color: {providerColor(row.provider)};">
										{row.provider}
									</span>
									<span style="font-family: 'JetBrains Mono', monospace; font-size: 0.7rem; color: var(--palais-text-muted);">
										{row.amount.toFixed(2)} EUR
									</span>
								</div>
								<div style="height: 4px; border-radius: 2px; background: rgba(255,255,255,0.05);">
									<div style="
										height: 100%; border-radius: 2px;
										width: {row.pct}%;
										background: {providerColor(row.provider)};
										opacity: 0.8;
										transition: width 0.5s ease;
									"></div>
								</div>
							</div>
						{/each}
					</div>
				{/if}
			</span>
		</div>
	</div>

	<!-- ════════════════════════════════════ MONTHLY TREND CHART ════ -->
	<section class="mb-6">
		<div class="glass-panel hud-bracket rounded-xl p-5"
			style="border: 1px solid rgba(212,168,67,0.18);">
			<span class="hud-bracket-bottom" style="display: block;">
				<p style="font-family: 'Orbitron', sans-serif; font-size: 0.58rem; letter-spacing: 0.22em; color: rgba(212,168,67,0.5); text-transform: uppercase; margin-bottom: 16px;">
					Monthly Trend — Last 6 Months
				</p>

				{#if data.monthlyHistory.length === 0}
					<p style="color: var(--palais-text-muted); font-family: 'JetBrains Mono', monospace; font-size: 0.8rem; text-align: center; padding: 24px 0;">
						<span style="color: rgba(212,168,67,0.3);">// </span>No monthly data available yet.
					</p>
				{:else}
					{@const cd = chartData()}
					<svg
						viewBox="0 0 {CHART_W} {CHART_H + 24}"
						style="width: 100%; max-width: 640px; display: block; overflow: visible;"
						aria-label="Monthly cost trend bar chart"
					>
						<!-- Baseline grid lines -->
						{#each [0.25, 0.5, 0.75, 1.0] as frac}
							<line
								x1="0" y1={CHART_H - frac * CHART_H}
								x2={CHART_W} y2={CHART_H - frac * CHART_H}
								stroke="rgba(212,168,67,0.06)"
								stroke-width="0.8"
							/>
						{/each}

						<!-- Bars -->
						{#each cd.bars as bar, i}
							<!-- Bar glow layer -->
							<rect
								x={bar.x}
								y={bar.y}
								width={bar.w}
								height={bar.h}
								rx="2"
								fill="rgba(212,168,67,0.06)"
								transform="scale(1.08) translate(-{bar.x * 0.04}, 0)"
							/>
							<!-- Bar fill -->
							<rect
								x={bar.x}
								y={bar.y}
								width={bar.w}
								height={bar.h}
								rx="2"
								fill="var(--palais-gold)"
								opacity={i === cd.bars.length - 1 ? '0.9' : '0.55'}
							/>
							<!-- Amount label on top of bar (only if bar is tall enough) -->
							{#if bar.h > 16}
								<text
									x={bar.x + bar.w / 2}
									y={bar.y - 4}
									text-anchor="middle"
									font-size="8"
									font-family="JetBrains Mono, monospace"
									fill="rgba(212,168,67,0.7)"
								>{bar.total.toFixed(0)}</text>
							{/if}
							<!-- Month label below chart -->
							<text
								x={bar.x + bar.w / 2}
								y={CHART_H + 16}
								text-anchor="middle"
								font-size="8"
								font-family="Orbitron, sans-serif"
								fill="rgba(212,168,67,0.45)"
								letter-spacing="0.05em"
							>{bar.label.toUpperCase()}</text>
						{/each}

						<!-- Baseline -->
						<line
							x1="0" y1={CHART_H}
							x2={CHART_W} y2={CHART_H}
							stroke="rgba(212,168,67,0.2)"
							stroke-width="1"
						/>
					</svg>
				{/if}
			</span>
		</div>
	</section>

	<!-- ═══════════════════════════════════════ RECENT ENTRIES ══════ -->
	{#if data.recentEntries.length > 0}
	<section class="mb-6">
		<div class="glass-panel hud-bracket rounded-xl overflow-hidden"
			style="border: 1px solid rgba(212,168,67,0.18);">
			<span class="hud-bracket-bottom" style="display: block;">
				<div class="px-5 py-3" style="border-bottom: 1px solid rgba(212,168,67,0.12);">
					<p style="font-family: 'Orbitron', sans-serif; font-size: 0.58rem; letter-spacing: 0.22em; color: rgba(212,168,67,0.5); text-transform: uppercase;">
						Recent Entries
					</p>
				</div>
				<div class="overflow-x-auto">
					<table style="width: 100%; border-collapse: collapse; font-size: 0.78rem;">
						<thead>
							<tr style="border-bottom: 1px solid rgba(212,168,67,0.1);">
								{#each ['Provider', 'Category', 'Amount (EUR)', 'Period', 'Description'] as col}
									<th style="
										text-align: left; padding: 8px 14px;
										font-family: 'Orbitron', sans-serif; font-size: 0.55rem;
										letter-spacing: 0.15em; color: rgba(212,168,67,0.45);
										text-transform: uppercase; white-space: nowrap;
									">{col}</th>
								{/each}
							</tr>
						</thead>
						<tbody>
							{#each data.recentEntries as entry (entry.id)}
								<tr style="border-bottom: 1px solid rgba(42,42,58,0.5);">
									<td style="padding: 9px 14px; white-space: nowrap;">
										<span style="
											font-family: 'JetBrains Mono', monospace;
											color: {providerColor(entry.provider)};
											font-size: 0.75rem;
										">{entry.provider}</span>
									</td>
									<td style="padding: 9px 14px; white-space: nowrap;">
										<span style="font-family: 'JetBrains Mono', monospace; color: var(--palais-text-muted); font-size: 0.75rem;">{entry.category}</span>
									</td>
									<td style="padding: 9px 14px; white-space: nowrap; text-align: right;">
										<span style="font-family: 'JetBrains Mono', monospace; color: var(--palais-gold); font-size: 0.8rem; font-weight: 500;">
											{entry.amountEur.toFixed(2)}
										</span>
									</td>
									<td style="padding: 9px 14px; white-space: nowrap;">
										<span style="font-family: 'JetBrains Mono', monospace; color: var(--palais-text-muted); font-size: 0.7rem;">
											{entry.periodStart.substring(0, 10)}
										</span>
									</td>
									<td style="padding: 9px 14px; max-width: 200px;">
										<span style="font-family: 'JetBrains Mono', monospace; color: var(--palais-text-muted); font-size: 0.7rem; opacity: 0.7;">
											{entry.description ?? '—'}
										</span>
									</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			</span>
		</div>
	</section>
	{/if}

	<!-- ═══════════════════════════════════════ ADD ENTRY FORM ═════ -->
	{#if showForm}
		<!-- Backdrop -->
		<div
			style="position: fixed; inset: 0; z-index: 100; background: rgba(0,0,0,0.7); backdrop-filter: blur(4px);"
			onclick={() => { showForm = false; }}
			role="presentation"
		></div>

		<div
			class="glass-panel hud-bracket rounded-xl"
			style="
				position: fixed; top: 50%; left: 50%; transform: translate(-50%, -50%);
				z-index: 101; width: min(520px, 95vw); padding: 1.5rem;
				border: 1px solid rgba(212,168,67,0.3);
				box-shadow: 0 8px 64px rgba(0,0,0,0.6), 0 0 0 1px rgba(212,168,67,0.08);
			"
			role="dialog"
			aria-label="Add cost entry"
		>
			<span class="hud-bracket-bottom" style="display: block;">
				<div class="flex items-center justify-between mb-5">
					<h2 style="color: var(--palais-gold); font-family: 'Orbitron', sans-serif; font-size: 0.8rem; letter-spacing: 0.18em; text-transform: uppercase;">
						Add Cost Entry
					</h2>
					<button
						onclick={() => { showForm = false; formError = ''; formSuccess = ''; }}
						style="background: none; border: none; cursor: pointer; color: rgba(212,168,67,0.4); font-size: 1.2rem; padding: 2px 6px;"
					>x</button>
				</div>

				<div class="grid grid-cols-2 gap-4">
					<!-- Provider -->
					<div>
						<label style="display: block; font-family: 'Orbitron', sans-serif; font-size: 0.58rem; letter-spacing: 0.18em; color: rgba(212,168,67,0.5); text-transform: uppercase; margin-bottom: 6px;">
							Provider
						</label>
						<input
							type="text"
							bind:value={formProvider}
							placeholder="hetzner, ovh, ai..."
							style="
								width: 100%; padding: 7px 10px;
								background: rgba(0,0,0,0.35); border-radius: 6px;
								border: 1px solid rgba(212,168,67,0.2);
								color: var(--palais-text); font-family: 'JetBrains Mono', monospace; font-size: 0.8rem;
								outline: none; box-sizing: border-box;
							"
						/>
					</div>

					<!-- Category -->
					<div>
						<label style="display: block; font-family: 'Orbitron', sans-serif; font-size: 0.58rem; letter-spacing: 0.18em; color: rgba(212,168,67,0.5); text-transform: uppercase; margin-bottom: 6px;">
							Category
						</label>
						<input
							type="text"
							bind:value={formCategory}
							placeholder="hosting, ai, domain..."
							style="
								width: 100%; padding: 7px 10px;
								background: rgba(0,0,0,0.35); border-radius: 6px;
								border: 1px solid rgba(212,168,67,0.2);
								color: var(--palais-text); font-family: 'JetBrains Mono', monospace; font-size: 0.8rem;
								outline: none; box-sizing: border-box;
							"
						/>
					</div>

					<!-- Amount -->
					<div>
						<label style="display: block; font-family: 'Orbitron', sans-serif; font-size: 0.58rem; letter-spacing: 0.18em; color: rgba(212,168,67,0.5); text-transform: uppercase; margin-bottom: 6px;">
							Amount (EUR)
						</label>
						<input
							type="number"
							step="0.01"
							min="0"
							bind:value={formAmount}
							placeholder="0.00"
							style="
								width: 100%; padding: 7px 10px;
								background: rgba(0,0,0,0.35); border-radius: 6px;
								border: 1px solid rgba(212,168,67,0.2);
								color: var(--palais-gold); font-family: 'JetBrains Mono', monospace; font-size: 0.8rem;
								outline: none; box-sizing: border-box;
							"
						/>
					</div>

					<!-- Period start -->
					<div>
						<label style="display: block; font-family: 'Orbitron', sans-serif; font-size: 0.58rem; letter-spacing: 0.18em; color: rgba(212,168,67,0.5); text-transform: uppercase; margin-bottom: 6px;">
							Period Start
						</label>
						<input
							type="date"
							bind:value={formPeriodStart}
							style="
								width: 100%; padding: 7px 10px;
								background: rgba(0,0,0,0.35); border-radius: 6px;
								border: 1px solid rgba(212,168,67,0.2);
								color: var(--palais-text); font-family: 'JetBrains Mono', monospace; font-size: 0.8rem;
								outline: none; box-sizing: border-box;
								color-scheme: dark;
							"
						/>
					</div>
				</div>

				<!-- Description (full width) -->
				<div class="mt-4">
					<label style="display: block; font-family: 'Orbitron', sans-serif; font-size: 0.58rem; letter-spacing: 0.18em; color: rgba(212,168,67,0.5); text-transform: uppercase; margin-bottom: 6px;">
						Description (optional)
					</label>
					<input
						type="text"
						bind:value={formDescription}
						placeholder="Monthly VPS invoice, AI tokens..."
						style="
							width: 100%; padding: 7px 10px;
							background: rgba(0,0,0,0.35); border-radius: 6px;
							border: 1px solid rgba(212,168,67,0.2);
							color: var(--palais-text); font-family: 'JetBrains Mono', monospace; font-size: 0.8rem;
							outline: none; box-sizing: border-box;
						"
					/>
				</div>

				{#if formError}
					<p class="mt-3" style="color: var(--palais-red); font-family: 'JetBrains Mono', monospace; font-size: 0.75rem;">
						{formError}
					</p>
				{/if}
				{#if formSuccess}
					<p class="mt-3" style="color: var(--palais-green); font-family: 'JetBrains Mono', monospace; font-size: 0.75rem;">
						{formSuccess}
					</p>
				{/if}

				<div class="flex gap-3 justify-end mt-6">
					<button
						onclick={() => { showForm = false; formError = ''; formSuccess = ''; }}
						style="
							padding: 8px 18px; border-radius: 6px; cursor: pointer;
							background: transparent; color: rgba(212,168,67,0.5);
							border: 1px solid rgba(212,168,67,0.2);
							font-family: 'Orbitron', sans-serif; font-size: 0.62rem; letter-spacing: 0.12em;
						"
					>CANCEL</button>
					<button
						onclick={submitEntry}
						disabled={formSubmitting}
						style="
							padding: 8px 20px; border-radius: 6px; cursor: {formSubmitting ? 'not-allowed' : 'pointer'};
							background: rgba(212,168,67,0.15); color: var(--palais-gold);
							border: 1px solid rgba(212,168,67,0.4);
							font-family: 'Orbitron', sans-serif; font-size: 0.62rem; letter-spacing: 0.12em;
							opacity: {formSubmitting ? '0.5' : '1'};
							transition: all 0.2s;
						"
					>
						{formSubmitting ? 'RECORDING...' : 'RECORD ENTRY'}
					</button>
				</div>
			</span>
		</div>
	{/if}

</div>
