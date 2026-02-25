<script lang="ts">
	import type { PageData } from './$types';
	import RichTextEditor from '$lib/components/editor/RichTextEditor.svelte';

	let { data }: { data: PageData } = $props();

	type Idea = typeof data.idea;
	type Version = typeof data.versions[number];

	const STATUSES = ['draft', 'brainstorming', 'planned', 'approved', 'dispatched', 'archived'] as const;
	type Status = (typeof STATUSES)[number];

	const STATUS_COLORS: Record<Status, string> = {
		draft: 'var(--palais-text-muted)',
		brainstorming: 'var(--palais-cyan)',
		planned: 'var(--palais-amber)',
		approved: 'var(--palais-gold)',
		dispatched: '#22c55e',
		archived: 'var(--palais-border)'
	};

	const PRIORITY_COLORS: Record<string, string> = {
		urgent: 'var(--palais-red)', high: 'var(--palais-amber)',
		medium: 'var(--palais-gold)', low: 'var(--palais-cyan)', none: 'var(--palais-text-muted)'
	};

	// Editable state
	let title = $state(data.idea.title);
	let description = $state(data.idea.description ?? '');
	let status = $state(data.idea.status as Status);
	let priority = $state(data.idea.priority ?? 'none');
	let tags = $state([...(data.idea.tags as string[])]);
	let versions = $state([...data.versions]);

	let saving = $state(false);
	let saved = $state(false);
	let newTag = $state('');

	// Version panel state
	let selectedVersionId = $state<number | null>(null);
	let diffA = $state<number | null>(null);
	let diffB = $state<number | null>(null);
	let showDiff = $state(false);

	const selectedVersion = $derived(
		selectedVersionId ? versions.find((v) => v.id === selectedVersionId) ?? null : null
	);

	const versionA = $derived(diffA ? versions.find((v) => v.id === diffA) ?? null : null);
	const versionB = $derived(diffB ? versions.find((v) => v.id === diffB) ?? null : null);

	async function save() {
		saving = true;
		const res = await fetch(`/api/v1/ideas/${data.idea.id}`, {
			method: 'PUT',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ title, description, status, priority, tags })
		});
		if (res.ok) {
			const updated = await res.json();
			// If a new version was created (status changed), reload versions
			if (updated.versionCreated) {
				const vRes = await fetch(`/api/v1/ideas/${data.idea.id}/versions`);
				if (vRes.ok) versions = await vRes.json();
			}
			saved = true;
			setTimeout(() => (saved = false), 2000);
		}
		saving = false;
	}

	function addTag() {
		const t = newTag.trim().toLowerCase();
		if (t && !tags.includes(t)) tags = [...tags, t];
		newTag = '';
	}

	function removeTag(tag: string) {
		tags = tags.filter((t) => t !== tag);
	}

	// Simple JSON diff between two contentSnapshot objects
	type Snapshot = Record<string, unknown>;

	function diffSnapshots(a: Snapshot, b: Snapshot): Array<{ key: string; from: unknown; to: unknown; changed: boolean }> {
		const keys = new Set([...Object.keys(a), ...Object.keys(b)]);
		return [...keys].map((key) => {
			const va = JSON.stringify(a[key]);
			const vb = JSON.stringify(b[key]);
			return { key, from: a[key], to: b[key], changed: va !== vb };
		});
	}

	const diffRows = $derived(
		showDiff && versionA?.contentSnapshot && versionB?.contentSnapshot
			? diffSnapshots(
				versionA.contentSnapshot as Snapshot,
				versionB.contentSnapshot as Snapshot
			)
			: []
	);
</script>

<div class="flex h-[calc(100vh-6rem)] gap-4">
	<!-- Left: Idea Editor -->
	<div class="flex flex-col flex-1 min-w-0 overflow-y-auto gap-4 pr-1">
		<!-- Back + header -->
		<div class="flex items-center gap-3 flex-shrink-0">
			<a href="/ideas" class="text-xs px-2 py-1 rounded"
				style="background: var(--palais-surface); color: var(--palais-text-muted); border: 1px solid var(--palais-border);">
				← Ideas
			</a>
			<span class="text-xs font-mono" style="color: var(--palais-text-muted);">#{data.idea.id}</span>
		</div>

		<!-- Title -->
		<input
			bind:value={title}
			class="w-full text-xl font-bold bg-transparent outline-none"
			style="color: var(--palais-text); font-family: 'Orbitron', sans-serif; border-bottom: 1px solid var(--palais-border); padding-bottom: 0.5rem;"
		/>

		<!-- Status + Priority row -->
		<div class="flex flex-wrap gap-4 items-center flex-shrink-0">
			<div class="flex items-center gap-2">
				<span class="text-xs w-16" style="color: var(--palais-text-muted);">Status</span>
				<div class="flex gap-1 flex-wrap">
					{#each STATUSES as s}
						<button
							onclick={() => (status = s)}
							class="px-2 py-0.5 rounded text-xs transition-all"
							style="
								background: {status === s ? `color-mix(in srgb, ${STATUS_COLORS[s]} 20%, transparent)` : 'var(--palais-bg)'};
								color: {status === s ? STATUS_COLORS[s] : 'var(--palais-text-muted)'};
								border: 1px solid {status === s ? STATUS_COLORS[s] : 'var(--palais-border)'};
							"
						>{s}</button>
					{/each}
				</div>
			</div>

			<div class="flex items-center gap-2">
				<span class="text-xs w-16" style="color: var(--palais-text-muted);">Priority</span>
				<div class="flex gap-1">
					{#each ['none','low','medium','high','urgent'] as p}
						<button
							onclick={() => (priority = p)}
							class="px-2 py-0.5 rounded text-xs transition-all"
							style="
								background: {priority === p ? `color-mix(in srgb, ${PRIORITY_COLORS[p]} 20%, transparent)` : 'var(--palais-bg)'};
								color: {priority === p ? PRIORITY_COLORS[p] : 'var(--palais-text-muted)'};
								border: 1px solid {priority === p ? PRIORITY_COLORS[p] : 'var(--palais-border)'};
							"
						>{p}</button>
					{/each}
				</div>
			</div>
		</div>

		<!-- Tags -->
		<div class="flex items-center gap-2 flex-wrap flex-shrink-0">
			<span class="text-xs w-16" style="color: var(--palais-text-muted);">Tags</span>
			{#each tags as tag}
				<span class="flex items-center gap-1 px-2 py-0.5 rounded text-xs"
					style="background: var(--palais-surface-hover); color: var(--palais-cyan); border: 1px solid var(--palais-border);">
					{tag}
					<button onclick={() => removeTag(tag)} class="opacity-60 hover:opacity-100 leading-none">×</button>
				</span>
			{/each}
			<input
				bind:value={newTag}
				placeholder="+ tag"
				class="px-2 py-0.5 rounded text-xs outline-none w-24"
				style="background: var(--palais-bg); border: 1px solid var(--palais-border); color: var(--palais-text);"
				onkeydown={(e) => e.key === 'Enter' && addTag()}
			/>
		</div>

		<!-- Description editor -->
		<div class="flex-1 min-h-[200px]">
			<p class="text-xs mb-1.5" style="color: var(--palais-text-muted);">Description</p>
			<RichTextEditor
				content={description}
				placeholder="Décrivez l'idée..."
				onupdate={(html) => (description = html)}
			/>
		</div>

		<!-- Save -->
		<div class="flex-shrink-0 pb-4">
			<button
				onclick={save}
				disabled={saving}
				class="px-6 py-2 rounded-lg text-sm font-medium disabled:opacity-50 transition-all"
				style="background: {saved ? 'var(--palais-cyan)' : 'var(--palais-gold)'}; color: #0A0A0F;"
			>
				{saving ? 'Saving…' : saved ? '✓ Saved' : 'Save Changes'}
			</button>
		</div>
	</div>

	<!-- Right: Version History -->
	<div class="flex flex-col flex-shrink-0 overflow-hidden rounded-xl"
		style="width: 280px; background: var(--palais-surface); border: 1px solid var(--palais-border);">

		<!-- Header -->
		<div class="px-4 py-3 flex-shrink-0 flex items-center justify-between"
			style="border-bottom: 1px solid var(--palais-border);">
			<span class="text-xs font-semibold" style="color: var(--palais-gold); font-family: 'Orbitron', sans-serif; letter-spacing: 0.06em;">
				VERSIONS
			</span>
			<span class="text-xs" style="color: var(--palais-text-muted);">{versions.length}</span>
		</div>

		<!-- Diff controls (shown when 2 selected) -->
		{#if diffA && diffB}
			<div class="px-3 py-2 flex-shrink-0 flex items-center gap-2"
				style="border-bottom: 1px solid var(--palais-border); background: var(--palais-bg);">
				<span class="text-xs" style="color: var(--palais-text-muted);">
					v{versions.find(v => v.id === diffA)?.versionNumber} → v{versions.find(v => v.id === diffB)?.versionNumber}
				</span>
				<button
					onclick={() => (showDiff = !showDiff)}
					class="ml-auto px-2 py-0.5 rounded text-xs"
					style="background: var(--palais-amber); color: #0A0A0F;">
					{showDiff ? 'Hide Diff' : 'Diff'}
				</button>
				<button onclick={() => { diffA = null; diffB = null; showDiff = false; }}
					class="text-xs" style="color: var(--palais-text-muted);">✕</button>
			</div>
		{/if}

		<!-- Version list -->
		<div class="flex-1 overflow-y-auto p-2 flex flex-col gap-1.5">
			{#if versions.length === 0}
				<p class="text-xs text-center py-6" style="color: var(--palais-border);">
					No versions yet.<br>Versions are saved on status changes.
				</p>
			{:else}
				{#each [...versions].reverse() as version}
					{@const isSelected = selectedVersionId === version.id}
					{@const isDiffA = diffA === version.id}
					{@const isDiffB = diffB === version.id}
					<!-- svelte-ignore a11y_no_static_element_interactions -->
					<div
						onclick={() => {
							if (selectedVersionId === version.id) {
								selectedVersionId = null;
							} else {
								selectedVersionId = version.id;
							}
						}}
						class="rounded-lg p-2.5 cursor-pointer transition-all"
						style="
							background: {isSelected ? 'var(--palais-surface-hover)' : 'var(--palais-bg)'};
							border: 1px solid {isSelected ? 'var(--palais-gold)' : isDiffA ? 'var(--palais-amber)' : isDiffB ? 'var(--palais-cyan)' : 'var(--palais-border)'};
						"
						onkeydown={(e) => e.key === 'Enter' && (selectedVersionId = version.id)}
						role="button"
						tabindex="0"
					>
						<div class="flex items-center justify-between mb-1">
							<span class="text-xs font-mono font-bold" style="color: var(--palais-gold);">
								v{version.versionNumber}
							</span>
							<span class="text-xs" style="color: var(--palais-text-muted);">
								{version.createdBy === 'agent' ? '🤖' : '👤'}
							</span>
						</div>
						<p class="text-xs" style="color: var(--palais-text-muted);">
							{new Date(version.createdAt).toLocaleString('fr-FR', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })}
						</p>
						{#if (version.contentSnapshot as Record<string, unknown>)?.status}
							<span class="text-xs mt-1 block"
								style="color: {STATUS_COLORS[(version.contentSnapshot as Record<string, unknown>).status as Status] ?? 'var(--palais-text-muted)'};">
								{(version.contentSnapshot as Record<string, unknown>).status as string}
							</span>
						{/if}

						<!-- Diff selector buttons -->
						<div class="flex gap-1 mt-1.5">
							<button
								onclick={(e) => { e.stopPropagation(); diffA = diffA === version.id ? null : version.id; showDiff = false; }}
								class="px-1.5 py-0.5 rounded text-xs"
								style="background: {isDiffA ? 'var(--palais-amber)' : 'var(--palais-surface-hover)'}; color: {isDiffA ? '#0A0A0F' : 'var(--palais-text-muted)'};">
								A
							</button>
							<button
								onclick={(e) => { e.stopPropagation(); diffB = diffB === version.id ? null : version.id; showDiff = false; }}
								class="px-1.5 py-0.5 rounded text-xs"
								style="background: {isDiffB ? 'var(--palais-cyan)' : 'var(--palais-surface-hover)'}; color: {isDiffB ? '#0A0A0F' : 'var(--palais-text-muted)'};">
								B
							</button>
						</div>
					</div>
				{/each}
			{/if}
		</div>

		<!-- Version snapshot view -->
		{#if selectedVersion && !showDiff}
			<div class="flex-shrink-0 border-t p-3 max-h-64 overflow-y-auto"
				style="border-color: var(--palais-border);">
				<p class="text-xs font-semibold mb-2" style="color: var(--palais-gold);">
					Snapshot v{selectedVersion.versionNumber}
				</p>
				{#each Object.entries(selectedVersion.contentSnapshot as Record<string, unknown>) as [key, val]}
					<div class="flex gap-2 text-xs mb-1">
						<span class="w-20 flex-shrink-0" style="color: var(--palais-text-muted);">{key}</span>
						<span style="color: var(--palais-text); word-break: break-all;">
							{Array.isArray(val) ? (val as string[]).join(', ') || '—' : String(val ?? '—')}
						</span>
					</div>
				{/each}
			</div>
		{/if}

		<!-- Diff view -->
		{#if showDiff && diffRows.length > 0}
			<div class="flex-shrink-0 border-t p-3 max-h-64 overflow-y-auto"
				style="border-color: var(--palais-border);">
				<p class="text-xs font-semibold mb-2" style="color: var(--palais-amber);">
					Diff v{versionA?.versionNumber} → v{versionB?.versionNumber}
				</p>
				{#each diffRows as row}
					<div class="text-xs mb-1.5 rounded px-2 py-1"
						style="background: {row.changed ? 'color-mix(in srgb, var(--palais-amber) 8%, transparent)' : 'transparent'}; border-left: 2px solid {row.changed ? 'var(--palais-amber)' : 'var(--palais-border)'};">
						<span class="font-mono" style="color: var(--palais-text-muted);">{row.key}</span>
						{#if row.changed}
							<div class="mt-0.5">
								<span style="color: var(--palais-red);">
									— {Array.isArray(row.from) ? (row.from as string[]).join(', ') || '∅' : String(row.from ?? '∅')}
								</span>
							</div>
							<div>
								<span style="color: #22c55e;">
									+ {Array.isArray(row.to) ? (row.to as string[]).join(', ') || '∅' : String(row.to ?? '∅')}
								</span>
							</div>
						{:else}
							<span class="ml-2" style="color: var(--palais-text-muted);">unchanged</span>
						{/if}
					</div>
				{/each}
			</div>
		{/if}
	</div>
</div>
