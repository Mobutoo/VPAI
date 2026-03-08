<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import * as d3 from 'd3-force';
	import { Sankofa } from '$lib/components/icons';

	// ── Types ──────────────────────────────────────────────────────────────────
	interface MemoryNode {
		id: number;
		type: 'episodic' | 'semantic' | 'procedural';
		summary: string;
		entityType: string | null;
		entityId: string | null;
		tags: string[];
		createdAt: string;
		score?: number;
	}

	interface MemoryEdge {
		id: number;
		source: number;
		target: number;
		relation: string;
		weight: number;
	}

	interface GraphNode extends d3.SimulationNodeDatum {
		id: number;
		type: string;
		summary: string;
		tags: string[];
	}

	interface GraphLink extends d3.SimulationLinkDatum<GraphNode> {
		id: number;
		relation: string;
		weight: number;
	}

	interface QdrantCollection {
		name: string;
		pointsCount: number;
		vectorSize: number;
		distance: string;
		status: string;
	}

	interface QdrantPoint {
		id: string | number;
		payload: Record<string, unknown>;
	}

	// ── Tab state ─────────────────────────────────────────────────────────────
	let activeTab = $state<'graph' | 'collections'>('collections');

	// ── Graph state ───────────────────────────────────────────────────────────
	let searchQuery = $state('');
	let searchResults = $state<MemoryNode[]>([]);
	let searching = $state(false);
	let searchError = $state('');

	let recentNodes = $state<MemoryNode[]>([]);
	let loadingRecent = $state(true);

	let selectedNode = $state<MemoryNode | null>(null);
	let selectedNodeDetail = $state<{ edges: MemoryEdge[]; connected: MemoryNode[] } | null>(null);

	// d3 graph
	let svgEl: SVGSVGElement;
	let graphNodes = $state<GraphNode[]>([]);
	let graphLinks = $state<GraphLink[]>([]);
	let simulation: d3.Simulation<GraphNode, GraphLink> | null = null;
	let graphLoading = $state(false);

	// ── Collections state ─────────────────────────────────────────────────────
	let collections = $state<QdrantCollection[]>([]);
	let loadingCollections = $state(true);
	let selectedCollection = $state<string | null>(null);
	let collectionPoints = $state<QdrantPoint[]>([]);
	let loadingPoints = $state(false);
	let nextOffset = $state<string | number | null>(null);
	let selectedPoint = $state<QdrantPoint | null>(null);

	// ── Node colors ────────────────────────────────────────────────────────────
	const NODE_COLORS: Record<string, string> = {
		episodic: 'var(--palais-gold)',
		semantic: 'var(--palais-cyan)',
		procedural: 'var(--palais-amber)'
	};

	const EDGE_COLORS: Record<string, string> = {
		caused_by: 'var(--palais-red)',
		resolved_by: 'var(--palais-green)',
		related_to: 'var(--palais-cyan)',
		learned_from: 'var(--palais-gold)',
		supersedes: 'var(--palais-amber)'
	};

	function collectionStatusColor(status: string): string {
		if (status === 'green') return 'var(--palais-green)';
		if (status === 'yellow') return 'var(--palais-amber)';
		return 'var(--palais-red)';
	}

	// ── Graph data loading ──────────────────────────────────────────────────────
	async function loadRecent() {
		loadingRecent = true;
		try {
			const res = await fetch('/api/v1/memory/nodes?limit=30');
			if (res.ok) recentNodes = await res.json();
		} catch {}
		loadingRecent = false;
	}

	async function search() {
		if (!searchQuery.trim()) { searchResults = []; return; }
		searching = true;
		searchError = '';
		try {
			const res = await fetch('/api/v1/memory/search', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ query: searchQuery, topK: 15, threshold: 0.4 })
			});
			if (!res.ok) { searchError = 'Recherche indisponible (LiteLLM requis)'; return; }
			const data = await res.json();
			searchResults = data.results ?? [];
		} catch {
			searchError = 'Erreur de connexion';
		}
		searching = false;
	}

	async function selectNode(node: MemoryNode) {
		selectedNode = node;
		selectedNodeDetail = null;
		graphLoading = true;
		try {
			const res = await fetch(`/api/v1/memory/graph/${node.id}?depth=2`);
			if (res.ok) {
				const g = await res.json();
				buildGraph(g.nodes, g.edges, node.id);
			}
			const detail = await fetch(`/api/v1/memory/nodes/${node.id}`);
			if (detail.ok) {
				const d = await detail.json();
				selectedNodeDetail = { edges: d.edges, connected: d.connected };
			}
		} catch {}
		graphLoading = false;
	}

	// ── Collections data loading ───────────────────────────────────────────────
	async function loadCollections() {
		loadingCollections = true;
		try {
			const res = await fetch('/api/v1/memory/collections');
			if (res.ok) {
				const data = await res.json();
				collections = (data.collections ?? []).sort(
					(a: QdrantCollection, b: QdrantCollection) => b.pointsCount - a.pointsCount
				);
			}
		} catch {}
		loadingCollections = false;
	}

	async function selectCollection(name: string) {
		selectedCollection = name;
		selectedPoint = null;
		collectionPoints = [];
		nextOffset = null;
		await loadPoints(name);
	}

	async function loadPoints(collection: string, offset?: string | number | null) {
		loadingPoints = true;
		try {
			let url = `/api/v1/memory/collections/${encodeURIComponent(collection)}/points?limit=30`;
			if (offset !== undefined && offset !== null) {
				url += `&offset=${encodeURIComponent(String(offset))}`;
			}
			const res = await fetch(url);
			if (res.ok) {
				const data = await res.json();
				if (offset) {
					collectionPoints = [...collectionPoints, ...(data.points ?? [])];
				} else {
					collectionPoints = data.points ?? [];
				}
				nextOffset = data.nextOffset;
			}
		} catch {}
		loadingPoints = false;
	}

	// ── d3-force graph ─────────────────────────────────────────────────────────
	function buildGraph(nodes: MemoryNode[], edges: MemoryEdge[], rootId: number) {
		if (simulation) simulation.stop();

		const gNodes: GraphNode[] = nodes.map((n) => ({
			id: n.id,
			type: n.type,
			summary: n.summary,
			tags: n.tags ?? [],
			x: n.id === rootId ? 200 : undefined,
			y: n.id === rootId ? 200 : undefined
		}));

		const nodeSet = new Set(gNodes.map((n) => n.id));
		const gLinks: GraphLink[] = edges
			.filter((e) => nodeSet.has(e.source as number) && nodeSet.has(e.target as number))
			.map((e) => ({
				id: e.id,
				source: e.source,
				target: e.target,
				relation: e.relation,
				weight: e.weight
			}));

		graphNodes = gNodes;
		graphLinks = gLinks;

		simulation = d3.forceSimulation(gNodes)
			.force('link', d3.forceLink<GraphNode, GraphLink>(gLinks).id((d) => d.id).distance(90).strength(0.6))
			.force('charge', d3.forceManyBody().strength(-200))
			.force('center', d3.forceCenter(200, 200))
			.force('collision', d3.forceCollide(30))
			.on('tick', () => { graphNodes = [...gNodes]; });
	}

	onMount(() => {
		loadCollections();
		loadRecent();
	});
	onDestroy(() => simulation?.stop());

	function onKeydown(e: KeyboardEvent) {
		if (e.key === 'Enter') search();
	}

	// ── Display helpers ────────────────────────────────────────────────────────
	function relLabel(r: string): string {
		return r.replace(/_/g, ' ');
	}

	function fmtDate(iso: string): string {
		return new Date(iso).toLocaleDateString('fr-FR', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' });
	}

	function payloadPreview(payload: Record<string, unknown>): string {
		const keys = Object.keys(payload);
		const preview = keys.slice(0, 3).map((k) => {
			const v = payload[k];
			const str = typeof v === 'string' ? v : JSON.stringify(v);
			return `${k}: ${(str ?? '').slice(0, 60)}`;
		}).join(' | ');
		return keys.length > 3 ? `${preview} (+${keys.length - 3})` : preview;
	}

	function formatPayloadValue(value: unknown): string {
		if (value === null || value === undefined) return '\u2014';
		if (typeof value === 'string') return value;
		if (typeof value === 'number' || typeof value === 'boolean') return String(value);
		return JSON.stringify(value, null, 2);
	}

	let totalPoints = $derived(collections.reduce((sum, c) => sum + c.pointsCount, 0));
	let displayNodes = $derived(searchResults.length > 0 ? searchResults : recentNodes);
</script>

<div class="flex flex-col gap-6 max-w-6xl mx-auto">

	<!-- Header -->
	<div class="flex items-center justify-between">
		<h1 class="text-xl font-bold flex items-center gap-2" style="font-family: 'Orbitron', sans-serif; color: var(--palais-text);">
			<Sankofa size={20} /> Knowledge Graph
		</h1>
		<span class="text-xs" style="color: var(--palais-text-muted);">
			{collections.length} collections | {totalPoints} points | Qdrant
		</span>
	</div>

	<!-- Tab switcher -->
	<div class="flex gap-1 p-1 rounded-xl" style="background: var(--palais-bg); border: 1px solid var(--palais-border);">
		<button
			onclick={() => activeTab = 'collections'}
			class="flex-1 px-4 py-2 rounded-lg text-xs font-semibold transition-all"
			style="font-family: 'Orbitron', sans-serif; letter-spacing: 0.06em;
				background: {activeTab === 'collections' ? 'var(--palais-surface)' : 'transparent'};
				color: {activeTab === 'collections' ? 'var(--palais-gold)' : 'var(--palais-text-muted)'};
				border: {activeTab === 'collections' ? '1px solid var(--palais-border)' : '1px solid transparent'};
				cursor: pointer;"
		>
			COLLECTIONS QDRANT
		</button>
		<button
			onclick={() => activeTab = 'graph'}
			class="flex-1 px-4 py-2 rounded-lg text-xs font-semibold transition-all"
			style="font-family: 'Orbitron', sans-serif; letter-spacing: 0.06em;
				background: {activeTab === 'graph' ? 'var(--palais-surface)' : 'transparent'};
				color: {activeTab === 'graph' ? 'var(--palais-gold)' : 'var(--palais-text-muted)'};
				border: {activeTab === 'graph' ? '1px solid var(--palais-border)' : '1px solid transparent'};
				cursor: pointer;"
		>
			GRAPHE MEMOIRE
		</button>
	</div>

	{#if activeTab === 'collections'}
		<!-- ═══════════════════ COLLECTIONS TAB ═══════════════════ -->
		<div class="grid grid-cols-1 lg:grid-cols-3 gap-4" style="min-height: 500px;">

			<!-- Collection list -->
			<div class="rounded-xl flex flex-col" style="background: var(--palais-surface); border: 1px solid var(--palais-border); overflow: hidden;">
				<div class="p-4" style="border-bottom: 1px solid var(--palais-border);">
					<p class="text-xs font-semibold" style="color: var(--palais-gold); font-family: 'Orbitron', sans-serif; letter-spacing: 0.06em;">
						COLLECTIONS ({collections.length})
					</p>
				</div>
				<div class="overflow-y-auto flex-1" style="max-height: 520px;">
					{#if loadingCollections}
						<div class="flex justify-center p-8">
							<div class="flex gap-1">
								{#each [0,1,2] as i}
									<div class="w-1.5 h-1.5 rounded-full animate-bounce"
										style="background: var(--palais-gold); animation-delay: {i * 150}ms;"></div>
								{/each}
							</div>
						</div>
					{:else if collections.length === 0}
						<p class="p-4 text-xs text-center" style="color: var(--palais-text-muted);">Aucune collection Qdrant.</p>
					{:else}
						{#each collections as col}
							<!-- svelte-ignore a11y_click_events_have_key_events -->
							<!-- svelte-ignore a11y_no_static_element_interactions -->
							<div
								onclick={() => selectCollection(col.name)}
								class="p-3 cursor-pointer transition-all"
								style="border-bottom: 1px solid var(--palais-border);
									background: {selectedCollection === col.name ? 'color-mix(in srgb, var(--palais-gold) 8%, var(--palais-surface))' : 'transparent'};"
							>
								<div class="flex items-center justify-between mb-1">
									<span class="text-xs font-medium truncate" style="color: var(--palais-text); font-family: 'JetBrains Mono', monospace;">
										{col.name}
									</span>
									<span class="w-2 h-2 rounded-full flex-shrink-0"
										style="background: {collectionStatusColor(col.status)};"></span>
								</div>
								<div class="flex items-center gap-3 text-xs" style="color: var(--palais-text-muted); font-size: 0.6rem;">
									<span>{col.pointsCount} pts</span>
									<span>{col.vectorSize}d</span>
									<span>{col.distance}</span>
								</div>
							</div>
						{/each}
					{/if}
				</div>
			</div>

			<!-- Points list -->
			<div class="rounded-xl flex flex-col" style="background: var(--palais-surface); border: 1px solid var(--palais-border); overflow: hidden;">
				<div class="p-4 flex items-center justify-between" style="border-bottom: 1px solid var(--palais-border);">
					<p class="text-xs font-semibold truncate" style="color: var(--palais-cyan); font-family: 'Orbitron', sans-serif; letter-spacing: 0.06em;">
						{selectedCollection ? `POINTS — ${selectedCollection}` : 'POINTS'}
					</p>
					{#if collectionPoints.length > 0}
						<span class="text-xs flex-shrink-0" style="color: var(--palais-text-muted); font-size: 0.6rem;">
							{collectionPoints.length} affich.
						</span>
					{/if}
				</div>
				<div class="overflow-y-auto flex-1" style="max-height: 460px;">
					{#if !selectedCollection}
						<p class="p-4 text-xs text-center" style="color: var(--palais-text-muted);">Selectionne une collection.</p>
					{:else if loadingPoints && collectionPoints.length === 0}
						<div class="flex justify-center p-8">
							<div class="flex gap-1">
								{#each [0,1,2] as i}
									<div class="w-1.5 h-1.5 rounded-full animate-bounce"
										style="background: var(--palais-cyan); animation-delay: {i * 150}ms;"></div>
								{/each}
							</div>
						</div>
					{:else if collectionPoints.length === 0}
						<p class="p-4 text-xs text-center" style="color: var(--palais-text-muted);">Collection vide.</p>
					{:else}
						{#each collectionPoints as pt}
							<!-- svelte-ignore a11y_click_events_have_key_events -->
							<!-- svelte-ignore a11y_no_static_element_interactions -->
							<div
								onclick={() => selectedPoint = pt}
								class="p-3 cursor-pointer transition-all"
								style="border-bottom: 1px solid var(--palais-border);
									background: {selectedPoint?.id === pt.id ? 'color-mix(in srgb, var(--palais-cyan) 8%, var(--palais-surface))' : 'transparent'};"
							>
								<div class="flex items-start gap-2">
									<span class="w-1.5 h-1.5 rounded-full flex-shrink-0 mt-1.5" style="background: var(--palais-cyan);"></span>
									<div class="flex-1 min-w-0">
										<p class="text-xs truncate" style="color: var(--palais-text-muted); font-family: 'JetBrains Mono', monospace; font-size: 0.6rem;">
											id: {pt.id}
										</p>
										<p class="text-xs leading-snug mt-0.5 truncate" style="color: var(--palais-text);">
											{payloadPreview(pt.payload)}
										</p>
									</div>
								</div>
							</div>
						{/each}
						{#if nextOffset !== null}
							<div class="p-3 text-center">
								<button
									onclick={() => selectedCollection && loadPoints(selectedCollection, nextOffset)}
									disabled={loadingPoints}
									class="px-4 py-1.5 rounded-lg text-xs"
									style="background: var(--palais-bg); color: var(--palais-cyan); border: 1px solid var(--palais-border); cursor: pointer;"
								>
									{loadingPoints ? '...' : 'Charger plus'}
								</button>
							</div>
						{/if}
					{/if}
				</div>
			</div>

			<!-- Point detail -->
			<div class="rounded-xl flex flex-col" style="background: var(--palais-surface); border: 1px solid var(--palais-border); overflow: hidden;">
				<div class="p-4" style="border-bottom: 1px solid var(--palais-border);">
					<p class="text-xs font-semibold" style="color: var(--palais-gold); font-family: 'Orbitron', sans-serif; letter-spacing: 0.06em;">
						DETAIL
					</p>
				</div>
				<div class="p-4 overflow-y-auto flex-1" style="max-height: 460px;">
					{#if !selectedPoint}
						<p class="text-xs" style="color: var(--palais-text-muted);">Selectionne un point.</p>
					{:else}
						<div class="mb-3">
							<span class="text-xs font-mono px-2 py-0.5 rounded"
								style="background: var(--palais-bg); color: var(--palais-cyan); border: 1px solid var(--palais-border); font-size: 0.65rem;">
								{selectedPoint.id}
							</span>
						</div>
						<div class="flex flex-col gap-2.5">
							{#each Object.entries(selectedPoint.payload) as [key, value]}
								<div>
									<p class="text-xs font-semibold mb-0.5" style="color: var(--palais-gold); font-size: 0.6rem; letter-spacing: 0.04em;">
										{key}
									</p>
									{#if typeof value === 'string' && value.length > 120}
										<p class="text-xs leading-relaxed whitespace-pre-wrap break-words" style="color: var(--palais-text); font-size: 0.7rem; max-height: 200px; overflow-y: auto;">
											{value}
										</p>
									{:else}
										<p class="text-xs leading-snug break-words" style="color: var(--palais-text); font-family: 'JetBrains Mono', monospace; font-size: 0.65rem;">
											{formatPayloadValue(value)}
										</p>
									{/if}
								</div>
							{/each}
						</div>
					{/if}
				</div>
			</div>
		</div>

	{:else}
		<!-- ═══════════════════ GRAPH TAB ═══════════════════ -->

		<!-- Search bar -->
		<div class="flex gap-2">
			<div class="flex-1 relative">
				<input
					type="text"
					bind:value={searchQuery}
					onkeydown={onKeydown}
					placeholder="Recherche semantique... (ex: erreur deploiement, task budget)"
					class="w-full px-4 py-2.5 rounded-xl text-sm"
					style="background: var(--palais-surface); border: 1px solid var(--palais-border);
						   color: var(--palais-text); outline: none; font-family: 'JetBrains Mono', monospace;"
				/>
			</div>
			<button
				onclick={search}
				disabled={searching}
				class="px-4 py-2 rounded-xl text-sm font-medium disabled:opacity-50 transition-all"
				style="background: var(--palais-gold); color: #0A0A0F; border: none; cursor: pointer;"
			>
				{searching ? '...' : 'Chercher'}
			</button>
			{#if searchResults.length > 0}
				<button
					onclick={() => { searchResults = []; searchQuery = ''; }}
					class="px-3 py-2 rounded-xl text-sm"
					style="background: var(--palais-surface); color: var(--palais-text-muted); border: 1px solid var(--palais-border); cursor: pointer;"
				>X</button>
			{/if}
		</div>
		{#if searchError}
			<p class="text-xs" style="color: var(--palais-amber);">! {searchError}</p>
		{/if}

		<div class="grid grid-cols-1 lg:grid-cols-3 gap-4" style="min-height: 500px;">

			<!-- Timeline / node list -->
			<div class="rounded-xl flex flex-col" style="background: var(--palais-surface); border: 1px solid var(--palais-border); overflow: hidden;">
				<div class="p-4 flex items-center justify-between" style="border-bottom: 1px solid var(--palais-border);">
					<p class="text-xs font-semibold" style="color: var(--palais-gold); font-family: 'Orbitron', sans-serif; letter-spacing: 0.06em;">
						{searchResults.length > 0 ? `RESULTATS (${searchResults.length})` : 'RECENTS'}
					</p>
				</div>
				<div class="overflow-y-auto flex-1" style="max-height: 480px;">
					{#if loadingRecent && displayNodes.length === 0}
						<div class="flex justify-center p-8">
							<div class="flex gap-1">
								{#each [0,1,2] as i}
									<div class="w-1.5 h-1.5 rounded-full animate-bounce"
										style="background: var(--palais-gold); animation-delay: {i * 150}ms;"></div>
								{/each}
							</div>
						</div>
					{:else if displayNodes.length === 0}
						<p class="p-4 text-xs text-center" style="color: var(--palais-text-muted);">
							Aucun noeud memoire.<br>Les evenements importants sont auto-ingeres.
						</p>
					{:else}
						{#each displayNodes as node}
							<!-- svelte-ignore a11y_click_events_have_key_events -->
							<!-- svelte-ignore a11y_no_static_element_interactions -->
							<div
								onclick={() => selectNode(node)}
								class="p-3 cursor-pointer transition-all"
								style="border-bottom: 1px solid var(--palais-border);
									   background: {selectedNode?.id === node.id ? 'color-mix(in srgb, var(--palais-gold) 8%, var(--palais-surface))' : 'transparent'};"
							>
								<div class="flex items-start gap-2">
									<span class="w-2 h-2 rounded-full flex-shrink-0 mt-1.5"
										style="background: {NODE_COLORS[node.type] ?? 'var(--palais-border)'};">
									</span>
									<div class="flex-1 min-w-0">
										<p class="text-xs leading-snug truncate" style="color: var(--palais-text);">
											{node.summary}
										</p>
										<div class="flex items-center gap-1.5 mt-1 flex-wrap">
											<span class="text-xs" style="color: var(--palais-text-muted); font-size: 0.6rem;">
												{node.type}
											</span>
											{#if node.score !== undefined}
												<span class="font-mono text-xs" style="color: var(--palais-cyan); font-size: 0.6rem;">
													{(node.score * 100).toFixed(0)}%
												</span>
											{/if}
											<span class="text-xs ml-auto" style="color: var(--palais-border); font-size: 0.6rem;">
												{fmtDate(node.createdAt)}
											</span>
										</div>
									</div>
								</div>
							</div>
						{/each}
					{/if}
				</div>
			</div>

			<!-- Force graph -->
			<div class="rounded-xl flex flex-col" style="background: var(--palais-surface); border: 1px solid var(--palais-border); overflow: hidden;">
				<div class="p-4" style="border-bottom: 1px solid var(--palais-border);">
					<p class="text-xs font-semibold" style="color: var(--palais-gold); font-family: 'Orbitron', sans-serif; letter-spacing: 0.06em;">
						GRAPHE VISUEL
					</p>
				</div>
				<div class="flex-1 relative flex items-center justify-center" style="min-height: 400px;">
					{#if !selectedNode}
						<p class="text-xs text-center px-4" style="color: var(--palais-text-muted);">
							Selectionne un noeud<br>pour visualiser le graphe
						</p>
					{:else if graphLoading}
						<div class="flex gap-1">
							{#each [0,1,2] as i}
								<div class="w-2 h-2 rounded-full animate-bounce"
									style="background: var(--palais-cyan); animation-delay: {i * 150}ms;"></div>
							{/each}
						</div>
					{:else if graphNodes.length === 0}
						<p class="text-xs" style="color: var(--palais-text-muted);">Aucune relation trouvee.</p>
					{:else}
						<svg bind:this={svgEl} width="100%" height="400" viewBox="0 0 400 400" style="overflow: visible;">
							{#each graphLinks as link}
								{@const srcId = typeof link.source === "object" ? (link.source as GraphNode).id : (link.source as number)}
								{@const tgtId = typeof link.target === "object" ? (link.target as GraphNode).id : (link.target as number)}
								{@const src = graphNodes.find((n) => n.id === srcId)}
								{@const tgt = graphNodes.find((n) => n.id === tgtId)}
								{#if src?.x !== undefined && tgt?.x !== undefined}
									<line
										x1={src.x} y1={src.y}
										x2={tgt.x} y2={tgt.y}
										stroke={EDGE_COLORS[link.relation] ?? 'var(--palais-border)'}
										stroke-width="{Math.max(1, (link.weight ?? 0.5) * 2)}"
										stroke-opacity="0.5"
									/>
								{/if}
							{/each}
							{#each graphNodes as node}
								{#if node.x !== undefined && node.y !== undefined}
									<g
										transform="translate({node.x},{node.y})"
										style="cursor: pointer;"
										onclick={() => selectNode({ id: node.id, type: node.type as 'episodic' | 'semantic' | 'procedural', summary: node.summary, entityType: null, entityId: null, tags: node.tags, createdAt: '' })}
									>
										<circle
											r={node.id === selectedNode?.id ? 14 : 10}
											fill={NODE_COLORS[node.type] ?? 'var(--palais-border)'}
											fill-opacity={node.id === selectedNode?.id ? 0.9 : 0.7}
											stroke={node.id === selectedNode?.id ? 'white' : 'transparent'}
											stroke-width="1.5"
										/>
										<text
											dy="24"
											text-anchor="middle"
											style="font-size: 0.5rem; fill: var(--palais-text-muted); pointer-events: none;"
										>
											{node.summary.slice(0, 20)}{node.summary.length > 20 ? '...' : ''}
										</text>
									</g>
								{/if}
							{/each}
						</svg>
						<div class="absolute bottom-3 left-3 flex gap-3">
							{#each Object.entries(NODE_COLORS) as [type, color]}
								<div class="flex items-center gap-1">
									<div class="w-2 h-2 rounded-full" style="background: {color};"></div>
									<span style="color: var(--palais-text-muted); font-size: 0.55rem;">{type}</span>
								</div>
							{/each}
						</div>
					{/if}
				</div>
			</div>

			<!-- Detail panel -->
			<div class="rounded-xl flex flex-col" style="background: var(--palais-surface); border: 1px solid var(--palais-border); overflow: hidden;">
				<div class="p-4" style="border-bottom: 1px solid var(--palais-border);">
					<p class="text-xs font-semibold" style="color: var(--palais-gold); font-family: 'Orbitron', sans-serif; letter-spacing: 0.06em;">
						DETAIL
					</p>
				</div>
				<div class="p-4 flex flex-col gap-4 overflow-y-auto" style="max-height: 460px;">
					{#if !selectedNode}
						<p class="text-xs" style="color: var(--palais-text-muted);">Selectionne un noeud.</p>
					{:else}
						<div>
							<div class="flex items-center gap-2 mb-2">
								<span class="w-2.5 h-2.5 rounded-full flex-shrink-0"
									style="background: {NODE_COLORS[selectedNode.type] ?? 'var(--palais-border)'};">
								</span>
								<span class="text-xs font-semibold" style="color: {NODE_COLORS[selectedNode.type]}; font-family: 'Orbitron', sans-serif; font-size: 0.6rem; letter-spacing: 0.06em;">
									{selectedNode.type.toUpperCase()} #{selectedNode.id}
								</span>
							</div>
							<p class="text-xs leading-relaxed" style="color: var(--palais-text);">
								{selectedNode.summary}
							</p>
							{#if selectedNode.entityType}
								<p class="text-xs mt-1" style="color: var(--palais-text-muted); font-size: 0.65rem;">
									{selectedNode.entityType} #{selectedNode.entityId}
								</p>
							{/if}
							{#if selectedNode.tags?.length > 0}
								<div class="flex flex-wrap gap-1 mt-2">
									{#each selectedNode.tags as tag}
										<span class="px-1.5 py-0.5 rounded text-xs"
											style="background: var(--palais-bg); color: var(--palais-text-muted); font-size: 0.6rem; border: 1px solid var(--palais-border);">
											{tag}
										</span>
									{/each}
								</div>
							{/if}
						</div>
						{#if (selectedNodeDetail?.edges?.length ?? 0) > 0}
							<div>
								<p class="text-xs font-semibold mb-2" style="color: var(--palais-text-muted); font-size: 0.65rem; letter-spacing: 0.05em;">RELATIONS</p>
								<div class="flex flex-col gap-1.5">
									{#each selectedNodeDetail!.edges as edge}
										{@const isSource = edge.source === selectedNode.id}
										{@const otherId = isSource ? edge.target : edge.source}
										{@const other = selectedNodeDetail?.connected?.find((n) => n.id === otherId)}
										<div class="flex items-center gap-2 text-xs">
											<span style="color: {EDGE_COLORS[edge.relation] ?? 'var(--palais-border)'}; font-size: 0.6rem; flex-shrink: 0;">
												{isSource ? '->' : '<-'} {relLabel(edge.relation)}
											</span>
											<span class="truncate" style="color: var(--palais-text-muted); font-size: 0.65rem;">
												{other?.summary?.slice(0, 50) ?? `#${otherId}`}
											</span>
										</div>
									{/each}
								</div>
							</div>
						{:else if selectedNodeDetail}
							<p class="text-xs" style="color: var(--palais-text-muted);">Aucune relation.</p>
						{/if}
					{/if}
				</div>
			</div>
		</div>
	{/if}
</div>
