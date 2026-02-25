<script lang="ts">
	import type { PageData } from './$types';

	let { data }: { data: PageData } = $props();
	const { project } = data;

	type Deliverable = typeof data.deliverables[number];

	let deliverables = $state([...data.deliverables]);
	let uploading = $state(false);
	let dragOver = $state(false);
	let preview = $state<Deliverable | null>(null);
	let uploadTaskId = $state('');

	// File type helpers
	function isImage(mime: string | null): boolean {
		return !!mime?.startsWith('image/');
	}
	function isPDF(mime: string | null): boolean {
		return mime === 'application/pdf';
	}
	function isText(mime: string | null): boolean {
		return !!mime && (mime.startsWith('text/') || mime === 'text/markdown');
	}
	function fileIcon(mime: string | null): string {
		if (!mime) return '📄';
		if (isImage(mime)) return '🖼';
		if (isPDF(mime)) return '📕';
		if (isText(mime)) return '📝';
		if (mime.includes('zip') || mime.includes('tar')) return '📦';
		if (mime.includes('video')) return '🎬';
		if (mime.includes('audio')) return '🎵';
		return '📄';
	}
	function fmtSize(bytes: number | null): string {
		if (!bytes) return '';
		if (bytes < 1024) return `${bytes} B`;
		if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
		return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
	}

	async function uploadFiles(files: FileList | File[]) {
		const taskId = parseInt(uploadTaskId);
		if (isNaN(taskId) || taskId <= 0) {
			alert('Renseignez un Task ID valide pour uploader.');
			return;
		}
		uploading = true;
		for (const file of Array.from(files)) {
			const fd = new FormData();
			fd.append('file', file);
			try {
				const res = await fetch(`/api/v1/tasks/${taskId}/deliverables`, {
					method: 'POST',
					body: fd
				});
				if (res.ok) {
					const entry = await res.json();
					deliverables = [...deliverables, { ...entry, taskTitle: `Task #${taskId}` }];
				}
			} catch (e) { console.error('Upload error:', e); }
		}
		uploading = false;
	}

	function onDrop(e: DragEvent) {
		e.preventDefault();
		dragOver = false;
		if (e.dataTransfer?.files.length) uploadFiles(e.dataTransfer.files);
	}

	function onFileInput(e: Event) {
		const input = e.target as HTMLInputElement;
		if (input.files?.length) uploadFiles(input.files);
	}
</script>

<div class="flex flex-col gap-6 max-w-5xl mx-auto">
	<!-- Header -->
	<div class="flex items-center gap-3">
		<a href="/projects/{project.id}"
			class="text-sm" style="color: var(--palais-text-muted);">← Board</a>
		<span style="color: var(--palais-border);">/</span>
		<h1 class="text-lg font-bold" style="font-family: 'Orbitron', sans-serif; color: var(--palais-text);">
			{project.icon || '◈'} {project.name} — Livrables
		</h1>
		<div class="ml-auto">
			<a href="/projects/{project.id}/analytics"
				class="px-3 py-1.5 rounded-lg text-xs font-medium"
				style="background: var(--palais-surface); border: 1px solid var(--palais-border); color: var(--palais-text-muted);">
				📊 Analytics
			</a>
		</div>
	</div>

	<!-- Upload zone -->
	<div
		ondragover={(e) => { e.preventDefault(); dragOver = true; }}
		ondragleave={() => dragOver = false}
		ondrop={onDrop}
		class="rounded-xl p-6 text-center transition-all"
		style="
			background: {dragOver ? 'color-mix(in srgb, var(--palais-cyan) 10%, var(--palais-surface))' : 'var(--palais-surface)'};
			border: 2px dashed {dragOver ? 'var(--palais-cyan)' : 'var(--palais-border)'};
		"
	>
		<p class="text-2xl mb-2">{uploading ? '⏳' : '📎'}</p>
		{#if uploading}
			<p class="text-sm" style="color: var(--palais-cyan);">Upload en cours…</p>
		{:else}
			<p class="text-sm mb-3" style="color: var(--palais-text-muted);">
				Glissez-déposez des fichiers ici
			</p>
			<div class="flex items-center justify-center gap-2">
				<input
					type="number"
					bind:value={uploadTaskId}
					placeholder="Task ID"
					class="w-24 px-2 py-1 rounded text-xs text-center outline-none"
					style="background: var(--palais-bg); border: 1px solid var(--palais-border); color: var(--palais-text);"
				/>
				<label class="px-3 py-1.5 rounded-lg text-xs font-medium cursor-pointer"
					style="background: var(--palais-gold); color: #0A0A0F;">
					Sélectionner fichiers
					<input type="file" multiple class="hidden" onchange={onFileInput} />
				</label>
			</div>
		{/if}
	</div>

	<!-- Gallery grid -->
	{#if deliverables.length === 0}
		<div class="text-center py-12">
			<p class="text-3xl mb-2">📭</p>
			<p class="text-sm" style="color: var(--palais-text-muted);">Aucun livrable pour ce projet.</p>
		</div>
	{:else}
		<div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
			{#each deliverables as d}
				<!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
				<div
					onclick={() => preview = d}
					class="rounded-xl overflow-hidden cursor-pointer transition-all group"
					style="background: var(--palais-surface); border: 1px solid var(--palais-border);"
				>
					<!-- Preview thumbnail -->
					<div class="relative h-32 flex items-center justify-center overflow-hidden"
						style="background: var(--palais-bg);">
						{#if isImage(d.mimeType)}
							<img src="/dl/{d.downloadToken}" alt={d.filename}
								class="w-full h-full object-cover"
								loading="lazy" />
						{:else}
							<span class="text-4xl">{fileIcon(d.mimeType)}</span>
						{/if}
						<!-- Hover overlay -->
						<div class="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity"
							style="background: rgba(0,0,0,0.5);">
							<span class="text-white text-xs font-medium">🔍 Aperçu</span>
						</div>
					</div>

					<!-- Info -->
					<div class="p-2">
						<p class="text-xs truncate font-medium" style="color: var(--palais-text);">{d.filename}</p>
						<p class="text-xs mt-0.5" style="color: var(--palais-text-muted);">{fmtSize(d.sizeBytes)}</p>
						{#if d.taskTitle}
							<p class="text-xs truncate mt-0.5" style="color: var(--palais-cyan); font-size: 0.6rem;">{d.taskTitle}</p>
						{/if}
					</div>
				</div>
			{/each}
		</div>
	{/if}
</div>

<!-- Preview Modal -->
{#if preview}
	<!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
	<div
		onclick={(e) => { if (e.target === e.currentTarget) preview = null; }}
		class="fixed inset-0 z-50 flex items-center justify-center p-4"
		style="background: rgba(0,0,0,0.8);"
	>
		<div class="rounded-xl overflow-hidden flex flex-col max-w-4xl w-full max-h-[90vh]"
			style="background: var(--palais-surface); border: 1px solid var(--palais-border);">
			<!-- Modal header -->
			<div class="flex items-center gap-3 px-4 py-3 flex-shrink-0"
				style="border-bottom: 1px solid var(--palais-border);">
				<span>{fileIcon(preview.mimeType)}</span>
				<span class="flex-1 text-sm font-medium truncate" style="color: var(--palais-text);">{preview.filename}</span>
				<span class="text-xs" style="color: var(--palais-text-muted);">{fmtSize(preview.sizeBytes)}</span>
				<a href="/dl/{preview.downloadToken}" download={preview.filename}
					class="px-3 py-1 rounded text-xs font-medium"
					style="background: var(--palais-gold); color: #0A0A0F;">
					⬇ Télécharger
				</a>
				<button onclick={() => preview = null}
					class="text-sm px-2" style="color: var(--palais-text-muted);">✕</button>
			</div>

			<!-- Preview content -->
			<div class="flex-1 overflow-auto p-4">
				{#if isImage(preview.mimeType)}
					<img src="/dl/{preview.downloadToken}" alt={preview.filename}
						class="max-w-full max-h-full mx-auto rounded" />
				{:else if isPDF(preview.mimeType)}
					<iframe src="/dl/{preview.downloadToken}" title={preview.filename}
						class="w-full rounded" style="height: 70vh; border: none;"></iframe>
				{:else if isText(preview.mimeType)}
					<iframe src="/dl/{preview.downloadToken}" title={preview.filename}
						class="w-full rounded" style="height: 60vh; border: none; background: var(--palais-bg);"></iframe>
				{:else}
					<div class="text-center py-12">
						<p class="text-5xl mb-4">{fileIcon(preview.mimeType)}</p>
						<p class="text-sm mb-4" style="color: var(--palais-text-muted);">
							Prévisualisation non disponible pour ce type de fichier.
						</p>
						<a href="/dl/{preview.downloadToken}" download={preview.filename}
							class="px-4 py-2 rounded-lg text-sm font-medium"
							style="background: var(--palais-gold); color: #0A0A0F;">
							⬇ Télécharger {preview.filename}
						</a>
					</div>
				{/if}
			</div>
		</div>
	</div>
{/if}
