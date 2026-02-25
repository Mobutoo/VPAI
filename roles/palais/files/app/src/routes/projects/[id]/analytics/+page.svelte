<script lang="ts">
	import type { PageData } from './$types';

	let { data }: { data: PageData } = $props();
	const { project, analytics: a } = data;

	let completing = $state(false);
	let postMortemResult = $state<string | null>(null);

	async function completeProject() {
		if (!confirm('Clôturer ce projet et générer le post-mortem automatique ?')) return;
		completing = true;
		try {
			const res = await fetch(`/api/v1/projects/${project.id}/complete`, { method: 'POST' });
			if (res.ok) {
				const d = await res.json();
				postMortemResult = d.postMortem;
			}
		} catch (e) { console.error(e); }
		completing = false;
	}

	function fmtTime(s: number): string {
		const h = Math.floor(s / 3600);
		const m = Math.floor((s % 3600) / 60);
		if (h > 0) return `${h}h ${m}m`;
		return `${m}m`;
	}

	function fmtCost(v: number | null): string {
		if (v === null) return '—';
		return `$${v.toFixed(3)}`;
	}

	// Bar chart widths relative to max column time
	const maxColTime = Math.max(1, ...Object.values(a.timeByColumn));
	const colEntries = Object.entries(a.timeByColumn).sort((x, y) => y[1] - x[1]);

	// Cost variance
	const variance = a.totalActual - a.totalEstimated;
	const overBudget = variance > 0;
</script>

<div class="flex flex-col gap-6 max-w-5xl mx-auto">
	<!-- Header -->
	<div class="flex items-center gap-3">
		<a href="/projects/{project.id}"
			class="text-sm transition-colors" style="color: var(--palais-text-muted);">← Board</a>
		<span style="color: var(--palais-border);">/</span>
		<h1 class="text-lg font-bold" style="font-family: 'Orbitron', sans-serif; color: var(--palais-text);">
			{project.icon || '◈'} {project.name} — Analytics
		</h1>
		<div class="ml-auto flex gap-2">
			<a href="/projects/{project.id}/deliverables"
				class="px-3 py-1.5 rounded-lg text-xs font-medium"
				style="background: var(--palais-surface); border: 1px solid var(--palais-border); color: var(--palais-text-muted);">
				📎 Livrables
			</a>
			<button
				onclick={completeProject}
				disabled={completing}
				class="px-3 py-1.5 rounded-lg text-xs font-medium disabled:opacity-50"
				style="background: var(--palais-amber); color: #0A0A0F;">
				{completing ? '⏳ Génération…' : '🏁 Clôturer le projet'}
			</button>
		</div>
	</div>

	<!-- KPI Cards -->
	<div class="grid grid-cols-2 md:grid-cols-4 gap-4">
		{@render kpi('⏱ Temps total', fmtTime(a.totalTimeSeconds), 'var(--palais-cyan)')}
		{@render kpi('🔁 Itérations', String(a.totalIterations), 'var(--palais-amber)')}
		{@render kpi('✅ Tâches done', `${a.completedCount}/${a.taskCount}`, 'var(--palais-gold)')}
		{@render kpi(
			overBudget ? '⚠ Sur-coût' : '💰 Économies',
			fmtCost(Math.abs(variance)),
			overBudget ? 'var(--palais-red)' : 'var(--palais-cyan)'
		)}
	</div>

	<!-- Row: Cost chart + Time by column -->
	<div class="grid grid-cols-1 md:grid-cols-2 gap-4">

		<!-- Estimated vs Actual -->
		<div class="rounded-xl p-5" style="background: var(--palais-surface); border: 1px solid var(--palais-border);">
			<p class="text-xs font-semibold mb-4" style="color: var(--palais-gold); font-family: 'Orbitron', sans-serif; letter-spacing: 0.06em;">
				COÛT ESTIMÉ VS RÉEL
			</p>
			<div class="flex flex-col gap-3">
				{@render costBar('Estimé', a.totalEstimated, Math.max(a.totalEstimated, a.totalActual, 0.001), 'var(--palais-border)')}
				{@render costBar('Réel', a.totalActual, Math.max(a.totalEstimated, a.totalActual, 0.001), overBudget ? 'var(--palais-red)' : 'var(--palais-cyan)')}
			</div>
			<p class="text-xs mt-3" style="color: {overBudget ? 'var(--palais-red)' : 'var(--palais-cyan)'};">
				{overBudget ? '+' : '-'}{fmtCost(Math.abs(variance))} vs estimation
			</p>
		</div>

		<!-- Time per column -->
		<div class="rounded-xl p-5" style="background: var(--palais-surface); border: 1px solid var(--palais-border);">
			<p class="text-xs font-semibold mb-4" style="color: var(--palais-gold); font-family: 'Orbitron', sans-serif; letter-spacing: 0.06em;">
				TEMPS PAR COLONNE
			</p>
			{#if colEntries.length === 0}
				<p class="text-xs" style="color: var(--palais-text-muted);">Aucune donnée timer.</p>
			{:else}
				<div class="flex flex-col gap-2">
					{#each colEntries as [col, secs]}
						<div class="flex flex-col gap-1">
							<div class="flex justify-between text-xs">
								<span style="color: var(--palais-text-muted);">{col}</span>
								<span style="color: var(--palais-text);">{fmtTime(secs)}</span>
							</div>
							<div class="h-1 rounded-full overflow-hidden" style="background: var(--palais-bg);">
								<div class="h-full rounded-full" style="width: {Math.round(secs / maxColTime * 100)}%; background: var(--palais-cyan);"></div>
							</div>
						</div>
					{/each}
				</div>
			{/if}
		</div>
	</div>

	<!-- Top expensive tasks -->
	{#if a.topTasks.length > 0}
		<div class="rounded-xl p-5" style="background: var(--palais-surface); border: 1px solid var(--palais-border);">
			<p class="text-xs font-semibold mb-4" style="color: var(--palais-gold); font-family: 'Orbitron', sans-serif; letter-spacing: 0.06em;">
				TOP 3 TÂCHES LES PLUS COÛTEUSES
			</p>
			<div class="flex flex-col gap-2">
				{#each a.topTasks as t, i}
					<div class="flex items-center gap-3 text-xs">
						<span class="font-mono w-4" style="color: var(--palais-text-muted);">#{i + 1}</span>
						<span class="flex-1 truncate" style="color: var(--palais-text);">{t.title}</span>
						<span class="font-mono" style="color: var(--palais-amber);">{fmtCost(t.estimated)}</span>
						<span style="color: var(--palais-border);">→</span>
						<span class="font-mono" style="color: {t.actual && t.estimated && t.actual > t.estimated ? 'var(--palais-red)' : 'var(--palais-cyan)'};">
							{fmtCost(t.actual)}
						</span>
					</div>
				{/each}
			</div>
		</div>
	{/if}

	<!-- Tasks with most iterations -->
	{#if a.taskIterCounts.length > 0}
		<div class="rounded-xl p-5" style="background: var(--palais-surface); border: 1px solid var(--palais-border);">
			<p class="text-xs font-semibold mb-4" style="color: var(--palais-gold); font-family: 'Orbitron', sans-serif; letter-spacing: 0.06em;">
				TÂCHES RÉOUVERTES (ITERATIONS)
			</p>
			<div class="flex flex-col gap-2">
				{#each a.taskIterCounts as t}
					<div class="flex items-center justify-between text-xs">
						<span class="flex-1 truncate" style="color: var(--palais-text);">{t.title}</span>
						<span class="font-mono px-2 py-0.5 rounded"
							style="background: color-mix(in srgb, var(--palais-amber) 15%, transparent); color: var(--palais-amber);">
							{t.iterations}× réouvert
						</span>
					</div>
				{/each}
			</div>
			{#if a.costPerIteration !== null}
				<p class="text-xs mt-3 pt-3" style="border-top: 1px solid var(--palais-border); color: var(--palais-text-muted);">
					Coût moyen / itération : <span style="color: var(--palais-text); font-family: 'JetBrains Mono', monospace;">{fmtCost(a.costPerIteration)}</span>
				</p>
			{/if}
		</div>
	{/if}

	<!-- Post-mortem result (shown after completion) -->
	{#if postMortemResult}
		<div class="rounded-xl p-5" style="background: color-mix(in srgb, var(--palais-gold) 8%, var(--palais-surface)); border: 1px solid var(--palais-gold);">
			<p class="text-xs font-semibold mb-3" style="color: var(--palais-gold); font-family: 'Orbitron', sans-serif; letter-spacing: 0.06em;">
				🏁 POST-MORTEM — MOBUTOO
			</p>
			<pre class="text-xs whitespace-pre-wrap leading-relaxed" style="color: var(--palais-text);">{postMortemResult}</pre>
			<p class="text-xs mt-3 pt-3" style="border-top: 1px solid var(--palais-border); color: var(--palais-text-muted);">
				Rapport sauvegardé dans le Knowledge Graph · Notification Telegram envoyée via n8n
			</p>
		</div>
	{/if}
</div>

{#snippet kpi(label: string, value: string, color: string)}
	<div class="rounded-xl p-4" style="background: var(--palais-surface); border: 1px solid var(--palais-border);">
		<p class="text-xs mb-1" style="color: var(--palais-text-muted);">{label}</p>
		<p class="text-2xl font-bold font-mono" style="color: {color};">{value}</p>
	</div>
{/snippet}

{#snippet costBar(label: string, value: number, max: number, color: string)}
	<div class="flex flex-col gap-1">
		<div class="flex justify-between text-xs">
			<span style="color: var(--palais-text-muted);">{label}</span>
			<span class="font-mono" style="color: var(--palais-text);">{fmtCost(value)}</span>
		</div>
		<div class="h-2 rounded-full overflow-hidden" style="background: var(--palais-bg);">
			<div class="h-full rounded-full transition-all"
				style="width: {Math.round(value / max * 100)}%; background: {color};"></div>
		</div>
	</div>
{/snippet}
