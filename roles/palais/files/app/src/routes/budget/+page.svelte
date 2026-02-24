<script lang="ts">
	import { onMount, onDestroy } from 'svelte';

	// ── Data types ────────────────────────────────────────────────────────────
	interface BudgetData {
		today: {
			viaLitellm: number;
			viaDirect: number;
			total: number;
			remaining: number;
			percentUsed: number;
			dailyLimit: number;
		};
		byProvider: Record<string, number>;
		byModel: Array<{ model: string; provider: string; spend: number; tokens: number; requests: number }>;
		burnRatePerHour: number;
		predictedExhaustionAt: string | null;
		history: Array<{ date: string; spend: number }>;
	}

	let data = $state<BudgetData | null>(null);
	let loading = $state(true);
	let ecoMode = $state(false);
	let ecoToggling = $state(false);
	let refreshInterval: ReturnType<typeof setInterval> | null = null;

	async function loadBudget() {
		try {
			const res = await fetch('/api/v1/budget');
			if (res.ok) data = await res.json();
		} catch (e) { console.error(e); }
		loading = false;
	}

	async function toggleEco() {
		ecoToggling = true;
		try {
			await fetch('/api/v1/budget/eco', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ enabled: !ecoMode })
			});
			ecoMode = !ecoMode;
		} catch (e) { console.error(e); }
		ecoToggling = false;
	}

	onMount(() => {
		loadBudget();
		refreshInterval = setInterval(loadBudget, 60_000); // refresh every minute
	});

	onDestroy(() => { if (refreshInterval) clearInterval(refreshInterval); });

	// ── Helpers ───────────────────────────────────────────────────────────────
	function fmtCost(v: number): string {
		return `$${v.toFixed(4)}`;
	}

	function fmtTime(iso: string | null): string {
		if (!iso) return '—';
		const d = new Date(iso);
		return d.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' });
	}

	// Arc SVG for circular gauge (r=52, cx=60, cy=60)
	const R = 52;
	const CX = 60;
	const CY = 65;
	const CIRCUMFERENCE = Math.PI * R; // half-circle

	function arcPath(percent: number, color: string): string {
		// Clamp
		const p = Math.min(100, Math.max(0, percent)) / 100;
		const len = p * CIRCUMFERENCE;
		// Arc starts at left (180°) and sweeps right for fill
		return `
			<circle cx="${CX}" cy="${CY}" r="${R}"
				fill="none"
				stroke="${color}"
				stroke-width="10"
				stroke-dasharray="${len} ${CIRCUMFERENCE - len}"
				stroke-dashoffset="${CIRCUMFERENCE * 0.5}"
				stroke-linecap="round"
				transform="rotate(180 ${CX} ${CY})"
			/>
		`;
	}

	// Provider colors
	const PROVIDER_COLORS: Record<string, string> = {
		litellm: 'var(--palais-cyan)',
		openai: 'var(--palais-green)',
		openrouter: 'var(--palais-amber)',
		anthropic: 'var(--palais-gold)',
		unknown: 'var(--palais-border)'
	};

	// ── Derived chart data ────────────────────────────────────────────────────
	let provEntries = $derived(
		data ? Object.entries(data.byProvider).sort((a, b) => b[1] - a[1]) : []
	);
	let maxProv = $derived(Math.max(0.0001, ...provEntries.map(([, v]) => v)));
	let topModels = $derived(
		data ? [...data.byModel].sort((a, b) => b.spend - a.spend).slice(0, 5) : []
	);

	// History chart: simple SVG line
	function historyPath(history: Array<{ date: string; spend: number }>, maxVal: number): string {
		if (history.length < 2) return '';
		const w = 400;
		const h = 80;
		const pts = history.map((d, i) => {
			const x = (i / (history.length - 1)) * w;
			const y = h - (d.spend / Math.max(maxVal, 0.001)) * h;
			return `${x},${y}`;
		});
		return `M ${pts.join(' L ')}`;
	}
</script>

<div class="flex flex-col gap-6 max-w-5xl mx-auto">
	<!-- Header -->
	<div class="flex items-center justify-between">
		<h1 class="text-xl font-bold" style="font-family: 'Orbitron', sans-serif; color: var(--palais-text);">
			💰 Budget Intelligence
		</h1>
		<div class="flex items-center gap-3">
			<span class="text-xs" style="color: var(--palais-text-muted);">Actualisation auto · 1min</span>
			<button
				onclick={toggleEco}
				disabled={ecoToggling}
				class="px-3 py-1.5 rounded-lg text-xs font-medium transition-all disabled:opacity-50"
				style="background: {ecoMode ? 'var(--palais-cyan)' : 'var(--palais-surface)'};
					   color: {ecoMode ? '#0A0A0F' : 'var(--palais-text-muted)'};
					   border: 1px solid {ecoMode ? 'var(--palais-cyan)' : 'var(--palais-border)'};">
				{ecoToggling ? '…' : ecoMode ? '🌿 Eco ON' : '🌿 Eco Mode'}
			</button>
		</div>
	</div>

	{#if loading}
		<div class="flex items-center justify-center py-20">
			<div class="flex gap-1">
				{#each [0,1,2] as i}
					<div class="w-2 h-2 rounded-full animate-bounce"
						style="background: var(--palais-gold); animation-delay: {i * 150}ms;"></div>
				{/each}
			</div>
		</div>
	{:else if data}
		<!-- ── Main Row: Gauge + Summary ─────────────────────────────────── -->
		<div class="grid grid-cols-1 md:grid-cols-3 gap-4">

			<!-- Circular gauge -->
			<div class="rounded-xl p-5 flex flex-col items-center justify-center"
				style="background: var(--palais-surface); border: 1px solid var(--palais-border);">
				<svg width="120" height="80" viewBox="0 0 120 80">
					<!-- Background arc -->
					<circle cx={CX} cy={CY} r={R}
						fill="none" stroke="var(--palais-bg)" stroke-width="10"
						stroke-dasharray="{CIRCUMFERENCE} {CIRCUMFERENCE}"
						stroke-dashoffset="{CIRCUMFERENCE * 0.5}"
						stroke-linecap="round"
						transform="rotate(180 {CX} {CY})" />
					<!-- Fill arc -->
					{@html arcPath(data.today.percentUsed,
						data.today.percentUsed >= 90 ? 'var(--palais-red)' :
						data.today.percentUsed >= 70 ? 'var(--palais-amber)' : 'var(--palais-gold)')}
				</svg>
				<p class="text-2xl font-bold font-mono -mt-4"
					style="color: {data.today.percentUsed >= 90 ? 'var(--palais-red)' : data.today.percentUsed >= 70 ? 'var(--palais-amber)' : 'var(--palais-gold)'};">
					{data.today.percentUsed.toFixed(1)}%
				</p>
				<p class="text-xs mt-1" style="color: var(--palais-text-muted);">
					{fmtCost(data.today.total)} / {fmtCost(data.today.dailyLimit)}
				</p>
			</div>

			<!-- Summary stats -->
			<div class="md:col-span-2 grid grid-cols-2 gap-3">
				{@render statCard('Via LiteLLM', fmtCost(data.today.viaLitellm), 'var(--palais-cyan)')}
				{@render statCard('Direct providers', fmtCost(data.today.viaDirect), 'var(--palais-amber)')}
				{@render statCard('Restant', fmtCost(data.today.remaining),
					data.today.remaining < 1 ? 'var(--palais-red)' : 'var(--palais-gold)')}
				{@render statCard('Burn rate', `${fmtCost(data.burnRatePerHour)}/h`, 'var(--palais-text-muted)')}
			</div>
		</div>

		<!-- Prediction banner -->
		{#if data.predictedExhaustionAt}
			{@const isToday = new Date(data.predictedExhaustionAt).toDateString() === new Date().toDateString()}
			<div class="rounded-xl p-3 text-center text-sm"
				style="background: color-mix(in srgb, var(--palais-red) 10%, var(--palais-surface));
					   border: 1px solid var(--palais-red); color: var(--palais-red);">
				⚠ Budget épuisé estimé à <strong>{fmtTime(data.predictedExhaustionAt)}</strong>
				{isToday ? 'aujourd\'hui' : new Date(data.predictedExhaustionAt).toLocaleDateString('fr-FR')}
			</div>
		{:else}
			<div class="rounded-xl p-3 text-center text-xs"
				style="background: var(--palais-surface); border: 1px solid var(--palais-border); color: var(--palais-text-muted);">
				Burn rate insuffisant pour estimer l'épuisement — données insuffisantes ou budget stable.
			</div>
		{/if}

		<!-- ── By Provider + By Model ─────────────────────────────────────── -->
		<div class="grid grid-cols-1 md:grid-cols-2 gap-4">

			<!-- By provider donut-style bar -->
			<div class="rounded-xl p-5" style="background: var(--palais-surface); border: 1px solid var(--palais-border);">
				<p class="text-xs font-semibold mb-4"
					style="color: var(--palais-gold); font-family: 'Orbitron', sans-serif; letter-spacing: 0.06em;">
					PAR PROVIDER
				</p>
						<div class="flex flex-col gap-2">
					{#each provEntries as [prov, spend]}
						<div class="flex flex-col gap-1">
							<div class="flex justify-between text-xs">
								<span style="color: var(--palais-text-muted); text-transform: capitalize;">{prov}</span>
								<span class="font-mono" style="color: var(--palais-text);">{fmtCost(spend)}</span>
							</div>
							<div class="h-1.5 rounded-full overflow-hidden" style="background: var(--palais-bg);">
								<div class="h-full rounded-full transition-all"
									style="width: {Math.round(spend / maxProv * 100)}%;
										   background: {PROVIDER_COLORS[prov] ?? PROVIDER_COLORS.unknown};"></div>
							</div>
						</div>
					{/each}
					{#if provEntries.length === 0}
						<p class="text-xs" style="color: var(--palais-text-muted);">Aucune donnée provider.</p>
					{/if}
				</div>
			</div>

			<!-- By model top 5 -->
			<div class="rounded-xl p-5" style="background: var(--palais-surface); border: 1px solid var(--palais-border);">
				<p class="text-xs font-semibold mb-4"
					style="color: var(--palais-gold); font-family: 'Orbitron', sans-serif; letter-spacing: 0.06em;">
					TOP MODÈLES
				</p>
					<div class="flex flex-col gap-2">
					{#each topModels as m}
						<div class="flex items-center gap-2 text-xs">
							<span class="w-2 h-2 rounded-full flex-shrink-0"
								style="background: {PROVIDER_COLORS[m.provider] ?? PROVIDER_COLORS.unknown};"></span>
							<span class="flex-1 truncate font-mono text-xs" style="color: var(--palais-text-muted); font-size: 0.65rem;">{m.model}</span>
							<span class="font-mono" style="color: var(--palais-text);">{fmtCost(m.spend)}</span>
						</div>
					{/each}
					{#if topModels.length === 0}
						<p class="text-xs" style="color: var(--palais-text-muted);">Pas de données modèle disponibles.</p>
					{/if}
				</div>
			</div>
		</div>

		<!-- ── 30-day history chart ───────────────────────────────────────── -->
		{#if data.history.length > 1}
			{@const maxHist = Math.max(0.001, ...data.history.map((d) => d.spend))}
			<div class="rounded-xl p-5" style="background: var(--palais-surface); border: 1px solid var(--palais-border);">
				<p class="text-xs font-semibold mb-4"
					style="color: var(--palais-gold); font-family: 'Orbitron', sans-serif; letter-spacing: 0.06em;">
					HISTORIQUE 30 JOURS
				</p>
				<div class="relative">
					<svg width="100%" height="80" viewBox="0 0 400 80" preserveAspectRatio="none">
						<!-- Budget limit line -->
						<line x1="0" y1="{80 - (data.today.dailyLimit / maxHist) * 80}"
							x2="400" y2="{80 - (data.today.dailyLimit / maxHist) * 80}"
							stroke="var(--palais-border)" stroke-dasharray="4 4" stroke-width="1" />
						<!-- Spend line -->
						<path d={historyPath(data.history, maxHist)}
							fill="none" stroke="var(--palais-gold)" stroke-width="2"
							stroke-linejoin="round" stroke-linecap="round" />
						<!-- Area fill -->
						{#if data.history.length > 1}
							{@const lastX = 400}
							{@const firstX = 0}
							<path d="{historyPath(data.history, maxHist)} L {lastX},80 L {firstX},80 Z"
								fill="url(#budgetGrad)" opacity="0.15" />
						{/if}
						<defs>
							<linearGradient id="budgetGrad" x1="0" y1="0" x2="0" y2="1">
								<stop offset="0%" stop-color="var(--palais-gold)" />
								<stop offset="100%" stop-color="var(--palais-gold)" stop-opacity="0" />
							</linearGradient>
						</defs>
					</svg>
					<!-- X-axis labels (first, mid, last) -->
					<div class="flex justify-between text-xs mt-1" style="color: var(--palais-text-muted);">
						{#if data.history.length > 0}
							<span>{data.history[0].date.slice(5)}</span>
							{#if data.history.length > 2}
								<span>{data.history[Math.floor(data.history.length / 2)].date.slice(5)}</span>
							{/if}
							<span>{data.history[data.history.length - 1].date.slice(5)}</span>
						{/if}
					</div>
				</div>
				<!-- Stats row -->
				<div class="flex gap-6 mt-3 text-xs" style="color: var(--palais-text-muted);">
					<span>Max: <span class="font-mono" style="color: var(--palais-text);">{fmtCost(maxHist)}</span></span>
					<span>Limite: <span class="font-mono" style="color: var(--palais-text);">{fmtCost(data.today.dailyLimit)}</span></span>
					<span>Avg: <span class="font-mono" style="color: var(--palais-text);">{fmtCost(data.history.reduce((s, d) => s + d.spend, 0) / Math.max(1, data.history.length))}</span></span>
				</div>
			</div>
		{/if}
	{:else}
		<div class="text-center py-12">
			<p class="text-3xl mb-2">📊</p>
			<p class="text-sm" style="color: var(--palais-text-muted);">Erreur de chargement des données budget.</p>
		</div>
	{/if}
</div>

{#snippet statCard(label: string, value: string, color: string)}
	<div class="rounded-xl p-4" style="background: var(--palais-bg); border: 1px solid var(--palais-border);">
		<p class="text-xs mb-1" style="color: var(--palais-text-muted);">{label}</p>
		<p class="text-lg font-bold font-mono" style="color: {color};">{value}</p>
	</div>
{/snippet}
