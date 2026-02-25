<script lang="ts">
	let { data } = $props();

	// ── Span type config ──────────────────────────────────────────────────────
	const SPAN_TYPES: Record<string, { color: string; icon: string; label: string }> = {
		llm_call:   { color: 'var(--palais-cyan)',  icon: '⬡', label: 'LLM'      },
		tool_call:  { color: 'var(--palais-gold)',  icon: '⚙', label: 'Tool'     },
		decision:   { color: 'var(--palais-amber)', icon: '◈', label: 'Decision' },
		delegation: { color: 'var(--palais-green)', icon: '↗', label: 'Delegate' }
	};

	// ── Build tree from flat spans ─────────────────────────────────────────
	type Span = (typeof data.spans)[0];
	type SpanNode = Span & { children: SpanNode[] };

	function buildTree(spans: Span[]): SpanNode[] {
		const map = new Map<number, SpanNode>();
		for (const s of spans) map.set(s.id, { ...s, children: [] });

		const roots: SpanNode[] = [];
		for (const node of map.values()) {
			if (node.parentSpanId && map.has(node.parentSpanId)) {
				map.get(node.parentSpanId)!.children.push(node);
			} else {
				roots.push(node);
			}
		}
		return roots;
	}

	const spanTree = $derived(buildTree(data.spans));

	// ── Collapsed state ───────────────────────────────────────────────────
	let collapsed = $state(new Set<number>());
	let selectedId = $state<number | null>(null);

	function toggleCollapse(id: number) {
		const next = new Set(collapsed);
		next.has(id) ? next.delete(id) : next.add(id);
		collapsed = next;
	}

	// ── Formatters ────────────────────────────────────────────────────────
	function fmtDur(ms: number | null): string {
		if (ms === null || ms === undefined) return '—';
		if (ms < 1000) return `${ms}ms`;
		return `${(ms / 1000).toFixed(2)}s`;
	}

	function fmtTokens(i: number | null, o: number | null): string {
		const ti = i ?? 0;
		const to = o ?? 0;
		if (ti === 0 && to === 0) return '—';
		return `${ti}↑ ${to}↓`;
	}

	function fmtCost(c: number | null): string {
		if (!c) return '';
		return `$${c.toFixed(4)}`;
	}

	function fmtTime(dt: Date | string | null): string {
		if (!dt) return '—';
		return new Date(dt).toLocaleTimeString('fr-FR', { hour12: false });
	}

	function spanConfig(type: string) {
		return SPAN_TYPES[type] ?? { color: 'var(--palais-text-muted)', icon: '○', label: type };
	}

	// ── Selected span detail ──────────────────────────────────────────────
	const selectedSpan = $derived(
		selectedId !== null ? data.spans.find((s) => s.id === selectedId) ?? null : null
	);

	function safeJson(v: unknown): string {
		if (v === null || v === undefined) return '—';
		if (typeof v === 'string') return v;
		try { return JSON.stringify(v, null, 2); } catch { return String(v); }
	}

	// ── Session status color ───────────────────────────────────────────────
	function statusColor(s: string) {
		return s === 'completed' ? 'var(--palais-green)'
			 : s === 'failed'    ? 'var(--palais-red)'
			 :                     'var(--palais-amber)';
	}
</script>

<div class="trace-layout">
	<!-- ── Back header ─────────────────────────────────────────────────────── -->
	<div class="trace-header">
		<a href="/agents/{data.agent.id}" class="back-link">
			← {data.agent.name}
		</a>
		<div class="session-meta">
			<span class="session-id">Session #{data.session.id}</span>
			{#if data.session.summary}
				<span class="session-summary">{data.session.summary}</span>
			{/if}
			<span class="status-badge" style="color: {statusColor(data.session.status)};">
				{data.session.status}
			</span>
		</div>
	</div>

	<!-- ── Stats bar ──────────────────────────────────────────────────────── -->
	<div class="stats-bar">
		<div class="stat">
			<span class="stat-label">Spans</span>
			<span class="stat-val" style="color: var(--palais-cyan);">{data.stats.spanCount}</span>
		</div>
		<div class="stat">
			<span class="stat-label">Durée</span>
			<span class="stat-val" style="color: var(--palais-gold);">{fmtDur(data.stats.durationMs)}</span>
		</div>
		<div class="stat">
			<span class="stat-label">Tokens</span>
			<span class="stat-val" style="color: var(--palais-cyan);">{(data.stats.totalTokens || 0).toLocaleString()}</span>
		</div>
		<div class="stat">
			<span class="stat-label">Coût</span>
			<span class="stat-val" style="color: var(--palais-amber);">${(data.stats.totalCost || 0).toFixed(4)}</span>
		</div>
		{#if data.stats.errorCount > 0}
			<div class="stat">
				<span class="stat-label">Erreurs</span>
				<span class="stat-val" style="color: var(--palais-red);">{data.stats.errorCount}</span>
			</div>
		{/if}
		{#if data.session.confidenceScore !== null && data.session.confidenceScore !== undefined}
			<div class="stat">
				<span class="stat-label">Confiance</span>
				<span class="stat-val" style="color: var(--palais-green);">
					{(data.session.confidenceScore * 100).toFixed(0)}%
				</span>
			</div>
		{/if}
		{#if data.session.model}
			<div class="stat">
				<span class="stat-label">Modèle</span>
				<span class="stat-val model-name">{data.session.model}</span>
			</div>
		{/if}
	</div>

	<!-- ── Main: tree + detail ─────────────────────────────────────────────── -->
	<div class="main-split">
		<!-- Span tree -->
		<div class="tree-panel">
			{#if data.spans.length === 0}
				<p class="empty-msg">Aucun span enregistré pour cette session.</p>
			{:else}
				<div class="tree-root">
					{#each spanTree as root (root.id)}
						{@render spanNode(root, 0)}
					{/each}
				</div>
			{/if}
		</div>

		<!-- Detail panel -->
		{#if selectedSpan}
			{@const cfg = spanConfig(selectedSpan.type ?? '')}
			<div class="detail-panel">
				<div class="detail-header">
					<span class="detail-icon" style="color: {cfg.color};">{cfg.icon}</span>
					<span class="detail-name" style="color: {cfg.color};">{selectedSpan.name}</span>
					<button class="close-btn" onclick={() => (selectedId = null)}>✕</button>
				</div>

				<div class="detail-body">
					<div class="detail-row">
						<span class="dr-label">Type</span>
						<span class="dr-val" style="color: {spanConfig(selectedSpan.type ?? '').color};">
							{spanConfig(selectedSpan.type ?? '').label}
						</span>
					</div>
					{#if selectedSpan.model}
						<div class="detail-row">
							<span class="dr-label">Modèle</span>
							<span class="dr-val">{selectedSpan.model}</span>
						</div>
					{/if}
					<div class="detail-row">
						<span class="dr-label">Durée</span>
						<span class="dr-val">{fmtDur(selectedSpan.durationMs)}</span>
					</div>
					<div class="detail-row">
						<span class="dr-label">Tokens</span>
						<span class="dr-val">{fmtTokens(selectedSpan.tokensIn, selectedSpan.tokensOut)}</span>
					</div>
					{#if selectedSpan.cost}
						<div class="detail-row">
							<span class="dr-label">Coût</span>
							<span class="dr-val" style="color: var(--palais-amber);">{fmtCost(selectedSpan.cost)}</span>
						</div>
					{/if}
					<div class="detail-row">
						<span class="dr-label">Début</span>
						<span class="dr-val">{fmtTime(selectedSpan.startedAt)}</span>
					</div>
					<div class="detail-row">
						<span class="dr-label">Fin</span>
						<span class="dr-val">{fmtTime(selectedSpan.endedAt)}</span>
					</div>

					{#if selectedSpan.error}
						<div class="detail-section error-section">
							<p class="ds-title" style="color: var(--palais-red);">⚠ Erreur</p>
							<pre class="ds-pre error-pre">{safeJson(selectedSpan.error)}</pre>
						</div>
					{/if}

					{#if selectedSpan.input !== null && selectedSpan.input !== undefined}
						<div class="detail-section">
							<p class="ds-title">Entrée</p>
							<pre class="ds-pre">{safeJson(selectedSpan.input)}</pre>
						</div>
					{/if}

					{#if selectedSpan.output !== null && selectedSpan.output !== undefined}
						<div class="detail-section">
							<p class="ds-title">Sortie</p>
							<pre class="ds-pre">{safeJson(selectedSpan.output)}</pre>
						</div>
					{/if}
				</div>
			</div>
		{/if}
	</div>
</div>

<!-- ── Span node snippet ───────────────────────────────────────────────────── -->
{#snippet spanNode(node: SpanNode, depth: number)}
	{@const cfg = spanConfig(node.type ?? '')}
	{@const hasChildren = node.children.length > 0}
	{@const isCollapsed = collapsed.has(node.id)}
	{@const isSelected = selectedId === node.id}
	{@const hasError = node.error !== null && node.error !== undefined}

	<div class="span-row-wrap" style="--depth: {depth};">
		<!-- Connector line -->
		{#if depth > 0}
			<div class="connector-line" style="color: {cfg.color};"></div>
		{/if}

		<div
			class="span-row {isSelected ? 'selected' : ''} {hasError ? 'has-error' : ''}"
			style="--span-color: {hasError ? 'var(--palais-red)' : cfg.color};"
			role="button"
			tabindex="0"
			onclick={() => (selectedId = isSelected ? null : node.id)}
			onkeydown={(e) => e.key === 'Enter' && (selectedId = isSelected ? null : node.id)}
		>
			<!-- Collapse toggle -->
			{#if hasChildren}
				<button
					class="collapse-btn"
					onclick={(e) => { e.stopPropagation(); toggleCollapse(node.id); }}
					title={isCollapsed ? 'Déplier' : 'Replier'}
				>
					{isCollapsed ? '▶' : '▼'}
				</button>
			{:else}
				<span class="collapse-placeholder"></span>
			{/if}

			<!-- Type icon -->
			<span class="span-icon" style="color: var(--span-color);">{cfg.icon}</span>

			<!-- Name + type badge -->
			<div class="span-info">
				<span class="span-name" style="color: {hasError ? 'var(--palais-red)' : 'var(--palais-text)'};">
					{node.name}
					{#if hasError}<span class="error-dot" title="Erreur"> ●</span>{/if}
				</span>
				<span class="span-type-badge" style="color: var(--span-color);">{cfg.label}</span>
			</div>

			<!-- Metrics -->
			<div class="span-metrics">
				{#if node.model}
					<span class="metric model-chip">{node.model.split('/').pop()}</span>
				{/if}
				{#if (node.tokensIn ?? 0) + (node.tokensOut ?? 0) > 0}
					<span class="metric" style="color: var(--palais-cyan);">
						{fmtTokens(node.tokensIn, node.tokensOut)}
					</span>
				{/if}
				{#if node.cost}
					<span class="metric" style="color: var(--palais-amber);">{fmtCost(node.cost)}</span>
				{/if}
				<span class="metric" style="color: var(--palais-text-muted);">{fmtDur(node.durationMs)}</span>
			</div>
		</div>

		<!-- Children -->
		{#if hasChildren && !isCollapsed}
			<div class="children-wrap">
				{#each node.children as child (child.id)}
					{@render spanNode(child, depth + 1)}
				{/each}
			</div>
		{/if}
	</div>
{/snippet}

<style>
	/* ── Layout ─────────────────────────────────────────────────────────── */
	.trace-layout {
		display: flex;
		flex-direction: column;
		gap: 0;
		height: 100%;
		min-height: 0;
	}

	/* ── Header ─────────────────────────────────────────────────────────── */
	.trace-header {
		display: flex;
		align-items: center;
		gap: 1rem;
		padding: 0 0 0.75rem;
		border-bottom: 1px solid var(--palais-border);
		flex-wrap: wrap;
	}
	.back-link {
		font-size: 0.75rem;
		color: var(--palais-text-muted);
		text-decoration: none;
		transition: color 0.15s;
	}
	.back-link:hover { color: var(--palais-cyan); }

	.session-meta {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		flex: 1;
		flex-wrap: wrap;
	}
	.session-id {
		font-family: 'Orbitron', sans-serif;
		font-size: 0.85rem;
		color: var(--palais-gold);
	}
	.session-summary {
		font-size: 0.8rem;
		color: var(--palais-text);
		flex: 1;
		min-width: 0;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.status-badge {
		font-size: 0.7rem;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}

	/* ── Stats bar ──────────────────────────────────────────────────────── */
	.stats-bar {
		display: flex;
		gap: 1.5rem;
		padding: 0.6rem 0;
		border-bottom: 1px solid var(--palais-border);
		flex-wrap: wrap;
	}
	.stat { display: flex; flex-direction: column; gap: 1px; }
	.stat-label {
		font-size: 0.65rem;
		color: var(--palais-text-muted);
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}
	.stat-val {
		font-size: 0.85rem;
		font-weight: 600;
		font-family: 'Orbitron', monospace;
	}
	.model-name {
		font-family: monospace;
		font-size: 0.75rem;
		color: var(--palais-text-muted);
	}

	/* ── Main split ─────────────────────────────────────────────────────── */
	.main-split {
		display: grid;
		grid-template-columns: 1fr;
		gap: 1rem;
		flex: 1;
		overflow: hidden;
		margin-top: 0.75rem;
	}
	.main-split:has(.detail-panel) {
		grid-template-columns: 1fr 340px;
	}

	/* ── Tree panel ─────────────────────────────────────────────────────── */
	.tree-panel {
		overflow-y: auto;
		overflow-x: auto;
		min-width: 0;
	}
	.tree-root { padding-bottom: 2rem; }

	.empty-msg {
		text-align: center;
		padding: 3rem;
		color: var(--palais-text-muted);
		font-size: 0.85rem;
	}

	/* ── Span row ────────────────────────────────────────────────────────── */
	.span-row-wrap {
		position: relative;
		padding-left: calc(var(--depth) * 1.5rem);
	}

	.connector-line {
		position: absolute;
		left: calc(var(--depth) * 1.5rem - 0.75rem);
		top: 0;
		bottom: 0;
		width: 1px;
		background: repeating-linear-gradient(
			to bottom,
			currentColor 0px,
			currentColor 4px,
			transparent 4px,
			transparent 8px
		);
		opacity: 0.3;
	}

	.span-row {
		display: flex;
		align-items: center;
		gap: 0.4rem;
		padding: 0.35rem 0.5rem;
		border-radius: 6px;
		cursor: pointer;
		transition: background 0.12s, box-shadow 0.12s;
		border: 1px solid transparent;
		margin-bottom: 2px;
		min-width: max-content;
	}
	.span-row:hover {
		background: color-mix(in srgb, var(--span-color) 8%, var(--palais-surface));
		border-color: color-mix(in srgb, var(--span-color) 20%, transparent);
	}
	.span-row.selected {
		background: color-mix(in srgb, var(--span-color) 12%, var(--palais-surface));
		border-color: var(--span-color);
		box-shadow: 0 0 12px color-mix(in srgb, var(--span-color) 30%, transparent);
	}
	.span-row.has-error {
		border-color: color-mix(in srgb, var(--palais-red) 30%, transparent);
	}
	.span-row.has-error.selected {
		box-shadow: 0 0 12px color-mix(in srgb, var(--palais-red) 40%, transparent);
	}

	.collapse-btn {
		background: none;
		border: none;
		color: var(--palais-text-muted);
		cursor: pointer;
		font-size: 0.55rem;
		padding: 0 0.2rem;
		line-height: 1;
		flex-shrink: 0;
		transition: color 0.12s;
	}
	.collapse-btn:hover { color: var(--palais-cyan); }
	.collapse-placeholder { width: 1.2rem; flex-shrink: 0; }

	.span-icon {
		font-size: 0.9rem;
		flex-shrink: 0;
		width: 1.2rem;
		text-align: center;
	}

	.span-info {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		flex: 1;
		min-width: 0;
	}
	.span-name {
		font-size: 0.8rem;
		white-space: nowrap;
	}
	.error-dot { color: var(--palais-red); font-size: 0.6rem; }
	.span-type-badge {
		font-size: 0.65rem;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.04em;
		opacity: 0.75;
		flex-shrink: 0;
	}

	.span-metrics {
		display: flex;
		align-items: center;
		gap: 0.6rem;
		margin-left: auto;
		flex-shrink: 0;
	}
	.metric {
		font-size: 0.7rem;
		font-family: monospace;
		white-space: nowrap;
	}
	.model-chip {
		color: var(--palais-text-muted);
		font-style: italic;
	}

	.children-wrap { /* inherits padding from parent depth */ }

	/* ── Detail panel ────────────────────────────────────────────────────── */
	.detail-panel {
		background: var(--palais-surface);
		border: 1px solid var(--palais-border);
		border-radius: 10px;
		display: flex;
		flex-direction: column;
		overflow: hidden;
		align-self: start;
		max-height: 80vh;
	}

	.detail-header {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		padding: 0.75rem 1rem;
		border-bottom: 1px solid var(--palais-border);
	}
	.detail-icon { font-size: 1.1rem; }
	.detail-name {
		font-size: 0.85rem;
		font-weight: 600;
		flex: 1;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.close-btn {
		background: none;
		border: none;
		color: var(--palais-text-muted);
		cursor: pointer;
		font-size: 0.75rem;
		padding: 0.2rem 0.4rem;
		border-radius: 4px;
		transition: color 0.12s, background 0.12s;
	}
	.close-btn:hover {
		color: var(--palais-text);
		background: var(--palais-border);
	}

	.detail-body {
		overflow-y: auto;
		padding: 0.75rem 1rem;
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}

	.detail-row {
		display: flex;
		align-items: baseline;
		gap: 0.5rem;
	}
	.dr-label {
		font-size: 0.65rem;
		color: var(--palais-text-muted);
		text-transform: uppercase;
		letter-spacing: 0.04em;
		min-width: 4rem;
		flex-shrink: 0;
	}
	.dr-val {
		font-size: 0.8rem;
		color: var(--palais-text);
		font-family: monospace;
	}

	.detail-section {
		margin-top: 0.5rem;
		border-top: 1px solid var(--palais-border);
		padding-top: 0.5rem;
	}
	.ds-title {
		font-size: 0.65rem;
		text-transform: uppercase;
		letter-spacing: 0.04em;
		color: var(--palais-text-muted);
		margin-bottom: 0.35rem;
	}
	.ds-pre {
		font-size: 0.7rem;
		font-family: monospace;
		color: var(--palais-text);
		background: color-mix(in srgb, var(--palais-bg) 60%, transparent);
		border-radius: 6px;
		padding: 0.5rem;
		overflow-x: auto;
		white-space: pre-wrap;
		word-break: break-word;
		max-height: 200px;
		overflow-y: auto;
	}
	.error-section .ds-pre {
		color: var(--palais-red);
		border: 1px solid color-mix(in srgb, var(--palais-red) 30%, transparent);
	}
</style>
