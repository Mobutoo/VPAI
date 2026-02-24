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
		providerStatus: { openrouter: boolean; openai: boolean; anthropic: boolean; openrouterHasBaseline: boolean };
		burnRatePerHour: number;
		predictedExhaustionAt: string | null;
		history: Array<{ date: string; spend: number }>;
	}

	type Period = 'day' | 'week' | 'month';

	let data = $state<BudgetData | null>(null);
	let loading = $state(true);
	let ecoMode = $state(false);
	let ecoToggling = $state(false);
	let period = $state<Period>('day');
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
		refreshInterval = setInterval(loadBudget, 60_000);
	});
	onDestroy(() => { if (refreshInterval) clearInterval(refreshInterval); });

	// ── Helpers ───────────────────────────────────────────────────────────────
	function fmtCost(v: number): string { return `$${v.toFixed(4)}`; }

	function fmtTime(iso: string | null): string {
		if (!iso) return '—';
		return new Date(iso).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' });
	}

	// ── Period-aware gauge data ───────────────────────────────────────────────
	const PERIOD_LABELS: Record<Period, string> = { day: 'JOURNALIER', week: 'HEBDOMADAIRE', month: 'MENSUEL' };
	const PERIOD_MULTIPLIERS: Record<Period, number> = { day: 1, week: 7, month: 30 };

	let periodSpend = $derived((() => {
		if (!data) return 0;
		if (period === 'day') return data.today.total;
		const days = period === 'week' ? 7 : 30;
		const slice = data.history.slice(-days);
		return slice.reduce((s, d) => s + d.spend, 0);
	})());

	let periodLimit = $derived((data?.today.dailyLimit ?? DAILY_LIMIT_FALLBACK) * PERIOD_MULTIPLIERS[period]);
	let periodPercent = $derived(Math.min(100, (periodSpend / Math.max(periodLimit, 0.001)) * 100));
	let periodColor = $derived(
		periodPercent >= 90 ? 'var(--palais-red)' :
		periodPercent >= 70 ? 'var(--palais-amber)' : 'var(--palais-gold)'
	);

	const DAILY_LIMIT_FALLBACK = 5;

	// ── Arc SVG gauge ─────────────────────────────────────────────────────────
	const R = 52, CX = 60, CY = 65;
	const CIRCUMFERENCE = Math.PI * R;

	function arcPath(percent: number, color: string): string {
		const p = Math.min(100, Math.max(0, percent)) / 100;
		const len = p * CIRCUMFERENCE;
		return `<circle cx="${CX}" cy="${CY}" r="${R}"
			fill="none" stroke="${color}" stroke-width="10"
			stroke-dasharray="${len} ${CIRCUMFERENCE - len}"
			stroke-dashoffset="${CIRCUMFERENCE * 0.5}"
			stroke-linecap="round"
			transform="rotate(180 ${CX} ${CY})" />`;
	}

	// ── Provider colors ───────────────────────────────────────────────────────
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

	// ── History chart ─────────────────────────────────────────────────────────
	function historyPath(history: Array<{ date: string; spend: number }>, maxVal: number): string {
		if (history.length < 2) return '';
		const w = 400, h = 80;
		const pts = history.map((d, i) => {
			const x = (i / (history.length - 1)) * w;
			const y = h - (d.spend / Math.max(maxVal, 0.001)) * h;
			return `${x},${y}`;
		});
		return `M ${pts.join(' L ')}`;
	}
</script>

<div class="flex flex-col gap-6 max-w-5xl mx-auto">

	<!-- ── Header ─────────────────────────────────────────────────────────── -->
	<div class="flex items-center justify-between flex-wrap gap-3">
		<h1 class="text-xl font-bold" style="font-family: 'Orbitron', sans-serif; color: var(--palais-text);">
			💰 Budget Intelligence
		</h1>
		<div class="flex items-center gap-4">
			<span class="text-xs" style="color: var(--palais-text-muted);">Actualisation · 1min</span>

			<!-- Eco Mode slide toggle -->
			<div class="flex items-center gap-2">
				<span class="text-xs" style="color: var(--palais-text-muted);">🌿 Eco Mode</span>
				<!-- svelte-ignore a11y_consider_explicit_label -->
				<button
					onclick={toggleEco}
					disabled={ecoToggling}
					title={ecoMode ? 'Eco actif — modèles économiques uniquement' : 'Activer le mode économique'}
					class="relative flex-shrink-0 transition-opacity disabled:opacity-40"
					style="width: 2.5rem; height: 1.375rem; background: {ecoMode ? 'var(--palais-cyan)' : 'var(--palais-border)'}; border-radius: 9999px; border: none; cursor: pointer; transition: background 0.2s;"
				>
					<span
						class="absolute top-0.5 w-4 h-4 rounded-full"
						style="background: white; transition: left 0.2s; left: {ecoMode ? '1.125rem' : '0.125rem'}; box-shadow: 0 1px 3px rgba(0,0,0,0.4);"
					></span>
				</button>
				{#if ecoMode}
					<span class="text-xs font-semibold" style="color: var(--palais-cyan);">ON</span>
				{/if}
			</div>
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
		<!-- ── Main Row: Gauge + Stats ────────────────────────────────────── -->
		<div class="grid grid-cols-1 md:grid-cols-3 gap-4">

			<!-- Circular gauge with period selector -->
			<div class="rounded-xl p-5 flex flex-col items-center gap-3"
				style="background: var(--palais-surface); border: 1px solid var(--palais-border);">

				<!-- Period tabs -->
				<div class="flex rounded-lg overflow-hidden" style="background: var(--palais-bg); border: 1px solid var(--palais-border);">
					{#each (['day', 'week', 'month'] as Period[]) as p}
						<button
							onclick={() => period = p}
							class="px-3 py-1 text-xs font-medium transition-all"
							style="background: {period === p ? 'var(--palais-surface)' : 'transparent'};
								   color: {period === p ? 'var(--palais-gold)' : 'var(--palais-text-muted)'};
								   border: none; cursor: pointer;
								   font-family: 'Orbitron', sans-serif; font-size: 0.6rem; letter-spacing: 0.05em;">
							{p === 'day' ? 'JOUR' : p === 'week' ? 'HEBDO' : 'MOIS'}
						</button>
					{/each}
				</div>

				<!-- Arc gauge -->
				<div class="flex flex-col items-center">
					<svg width="120" height="80" viewBox="0 0 120 80">
						<circle cx={CX} cy={CY} r={R}
							fill="none" stroke="var(--palais-bg)" stroke-width="10"
							stroke-dasharray="{CIRCUMFERENCE} {CIRCUMFERENCE}"
							stroke-dashoffset="{CIRCUMFERENCE * 0.5}"
							stroke-linecap="round"
							transform="rotate(180 {CX} {CY})" />
						{@html arcPath(periodPercent, periodColor)}
					</svg>
					<p class="text-2xl font-bold font-mono -mt-3" style="color: {periodColor};">
						{periodPercent.toFixed(1)}%
					</p>
				</div>

				<!-- Spend / Limit labels -->
				<div class="text-center">
					<p class="text-xs font-mono" style="color: var(--palais-text-muted);">
						{fmtCost(periodSpend)} / {fmtCost(periodLimit)}
					</p>
					<p class="text-xs mt-0.5" style="color: var(--palais-text-muted); font-family: 'Orbitron', sans-serif; font-size: 0.55rem; letter-spacing: 0.08em;">
						{PERIOD_LABELS[period]}
					</p>
					<p class="text-xs mt-0.5" style="color: var(--palais-text-muted); font-size: 0.65rem;">
						Limite : {fmtCost(data.today.dailyLimit)}/jour
					</p>
				</div>
			</div>

			<!-- Summary stat cards (always daily) -->
			<div class="md:col-span-2 grid grid-cols-2 gap-3">
				{@render statCard('Via LiteLLM', fmtCost(data.today.viaLitellm), 'var(--palais-cyan)', 'journalier')}
				{@render statCard('Providers directs', fmtCost(data.today.viaDirect), 'var(--palais-amber)', 'journalier')}
				{@render statCard('Restant aujourd\'hui', fmtCost(data.today.remaining),
					data.today.remaining < 1 ? 'var(--palais-red)' : 'var(--palais-gold)', 'journalier')}
				{@render statCard('Burn rate', `${fmtCost(data.burnRatePerHour)}/h`, 'var(--palais-text-muted)', 'LiteLLM')}
			</div>
		</div>

		<!-- Prediction / stable banner -->
		{#if data.predictedExhaustionAt}
			{@const isToday = new Date(data.predictedExhaustionAt).toDateString() === new Date().toDateString()}
			<div class="rounded-xl p-3 text-center text-sm"
				style="background: color-mix(in srgb, var(--palais-red) 10%, var(--palais-surface));
					   border: 1px solid var(--palais-red); color: var(--palais-red);">
				⚠ Budget journalier épuisé estimé à <strong>{fmtTime(data.predictedExhaustionAt)}</strong>
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

			<!-- By provider -->
			<div class="rounded-xl p-5" style="background: var(--palais-surface); border: 1px solid var(--palais-border);">
				<div class="flex items-center justify-between mb-4">
					<p class="text-xs font-semibold"
						style="color: var(--palais-gold); font-family: 'Orbitron', sans-serif; letter-spacing: 0.06em;">
						PAR PROVIDER · JOURNALIER
					</p>
				</div>
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
						<p class="text-xs" style="color: var(--palais-text-muted);">Aucune donnée aujourd'hui.</p>
					{/if}
				</div>

				<!-- Provider availability notes -->
				<div class="mt-4 pt-3 flex flex-col gap-1" style="border-top: 1px solid var(--palais-border);">
					{#if !data.providerStatus.openai}
						<p class="text-xs" style="color: var(--palais-text-muted); font-size: 0.6rem;">
							⚠ OpenAI — endpoint org requis (<code>sk-org-...</code>), clé projet insuffisante
						</p>
					{/if}
					{#if !data.providerStatus.anthropic}
						<p class="text-xs" style="color: var(--palais-text-muted); font-size: 0.6rem;">
							⚠ Anthropic — API Usage non disponible sur ce plan
						</p>
					{/if}
					{#if data.providerStatus.openrouter && !data.providerStatus.openrouterHasBaseline}
						<p class="text-xs" style="color: var(--palais-text-muted); font-size: 0.6rem;">
							ℹ OpenRouter — delta quotidien disponible dès la 2e journée de tracking
						</p>
					{/if}
				</div>
			</div>

			<!-- By model top 5 -->
			<div class="rounded-xl p-5" style="background: var(--palais-surface); border: 1px solid var(--palais-border);">
				<p class="text-xs font-semibold mb-4"
					style="color: var(--palais-gold); font-family: 'Orbitron', sans-serif; letter-spacing: 0.06em;">
					TOP MODÈLES · LiteLLM
				</p>
				<div class="flex flex-col gap-2">
					{#each topModels as m}
						<div class="flex items-center gap-2 text-xs">
							<span class="w-2 h-2 rounded-full flex-shrink-0"
								style="background: {PROVIDER_COLORS[m.provider] ?? PROVIDER_COLORS.unknown};"></span>
							<span class="flex-1 truncate font-mono" style="color: var(--palais-text-muted); font-size: 0.65rem;">{m.model}</span>
							<span class="font-mono" style="color: var(--palais-text);">{fmtCost(m.spend)}</span>
						</div>
					{/each}
					{#if topModels.length === 0}
						<p class="text-xs" style="color: var(--palais-text-muted);">Aucun appel LiteLLM tracé aujourd'hui.</p>
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
					HISTORIQUE 30 JOURS · JOURNALIER
				</p>
				<div class="relative">
					<svg width="100%" height="80" viewBox="0 0 400 80" preserveAspectRatio="none">
						<line x1="0" y1="{80 - (data.today.dailyLimit / maxHist) * 80}"
							x2="400" y2="{80 - (data.today.dailyLimit / maxHist) * 80}"
							stroke="var(--palais-border)" stroke-dasharray="4 4" stroke-width="1" />
						<path d={historyPath(data.history, maxHist)}
							fill="none" stroke="var(--palais-gold)" stroke-width="2"
							stroke-linejoin="round" stroke-linecap="round" />
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
				<div class="flex gap-6 mt-3 text-xs" style="color: var(--palais-text-muted);">
					<span>Max: <span class="font-mono" style="color: var(--palais-text);">{fmtCost(maxHist)}</span></span>
					<span>Limite/j: <span class="font-mono" style="color: var(--palais-text);">{fmtCost(data.today.dailyLimit)}</span></span>
					<span>Moy/j: <span class="font-mono" style="color: var(--palais-text);">{fmtCost(data.history.reduce((s, d) => s + d.spend, 0) / Math.max(1, data.history.length))}</span></span>
					<span>Total 30j: <span class="font-mono" style="color: var(--palais-text);">{fmtCost(data.history.reduce((s, d) => s + d.spend, 0))}</span></span>
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

{#snippet statCard(label: string, value: string, color: string, sublabel: string)}
	<div class="rounded-xl p-4" style="background: var(--palais-bg); border: 1px solid var(--palais-border);">
		<p class="text-xs mb-1" style="color: var(--palais-text-muted);">{label}</p>
		<p class="text-lg font-bold font-mono" style="color: {color};">{value}</p>
		<p class="text-xs mt-0.5" style="color: var(--palais-border); font-size: 0.6rem; font-family: 'Orbitron', sans-serif; letter-spacing: 0.05em;">{sublabel}</p>
	</div>
{/snippet}
