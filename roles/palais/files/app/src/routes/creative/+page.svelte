<script lang="ts">
	let { data } = $props();

	let prompt = $state('');
	let generating = $state(false);
	let genResult = $state<string | null>(null);
	let genError = $state<string | null>(null);
	let previewUrl = $state<string | null>(null);

	// Queue counts from ComfyUI
	const queueRunning: number = data.queue?.queue_running?.length ?? 0;
	const queuePending: number = data.queue?.queue_pending?.length ?? 0;

	// Quick generate with a simple text-to-image workflow skeleton
	async function generate() {
		if (!prompt.trim()) return;
		generating = true;
		genResult = null;
		genError = null;

		// Minimal ComfyUI API-format workflow (text-to-image placeholder)
		const workflow = {
			'3': {
				class_type: 'KSampler',
				inputs: {
					seed: Math.floor(Math.random() * 1e9),
					steps: 20, cfg: 7, sampler_name: 'euler',
					scheduler: 'normal', denoise: 1,
					model: ['4', 0], positive: ['6', 0], negative: ['7', 0], latent_image: ['5', 0]
				}
			},
			'4': { class_type: 'CheckpointLoaderSimple', inputs: { ckpt_name: 'v1-5-pruned-emaonly.ckpt' } },
			'5': { class_type: 'EmptyLatentImage', inputs: { batch_size: 1, height: 512, width: 512 } },
			'6': { class_type: 'CLIPTextEncode', inputs: { text: prompt, clip: ['4', 1] } },
			'7': { class_type: 'CLIPTextEncode', inputs: { text: 'bad, ugly, blurry', clip: ['4', 1] } },
			'8': { class_type: 'VAEDecode', inputs: { samples: ['3', 0], vae: ['4', 2] } },
			'9': { class_type: 'SaveImage', inputs: { filename_prefix: 'palais', images: ['8', 0] } }
		};

		try {
			const res = await fetch('/api/v1/creative/comfyui', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ workflow })
			});
			const data = await res.json();
			if (!res.ok) throw new Error(data.error ?? 'Unknown error');
			genResult = `Job soumis — prompt_id: ${data.prompt_id}`;
		} catch (err) {
			genError = String(err);
		} finally {
			generating = false;
		}
	}

	function formatBytes(bytes: number | null) {
		if (!bytes) return '—';
		if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
		return `${(bytes / 1048576).toFixed(1)} MB`;
	}
</script>

<svelte:head><title>Palais — Atelier Creatif</title></svelte:head>

<div class="space-y-8">
	<!-- Header -->
	<div class="flex items-center justify-between">
		<h1 class="text-2xl font-bold" style="color: var(--palais-gold); font-family: 'Orbitron', sans-serif;">
			ATELIER CREATIF
		</h1>
		{#if data.comfyError}
			<span class="text-xs px-2 py-1 rounded" style="background: rgba(239,68,68,0.1); color: var(--palais-red);">
				ComfyUI hors ligne
			</span>
		{:else}
			<span class="text-xs px-2 py-1 rounded" style="background: rgba(74,222,128,0.1); color: var(--palais-green);">
				ComfyUI en ligne
			</span>
		{/if}
	</div>

	<div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
		<!-- Left column: Queue + Generate -->
		<div class="space-y-5">
			<!-- Queue status -->
			<section class="rounded-xl p-5 space-y-4"
				style="background: var(--palais-surface); border: 1px solid var(--palais-border);">
				<h2 class="text-xs font-semibold uppercase tracking-widest" style="color: var(--palais-text-muted);">
					File d'attente
				</h2>
				<div class="grid grid-cols-2 gap-3">
					<div class="rounded-lg p-3 text-center" style="background: rgba(0,0,0,0.2);">
						<p class="text-2xl font-bold" style="color: var(--palais-gold);">{queueRunning}</p>
						<p class="text-xs mt-1" style="color: var(--palais-text-muted);">En cours</p>
					</div>
					<div class="rounded-lg p-3 text-center" style="background: rgba(0,0,0,0.2);">
						<p class="text-2xl font-bold" style="color: var(--palais-amber);">{queuePending}</p>
						<p class="text-xs mt-1" style="color: var(--palais-text-muted);">En attente</p>
					</div>
				</div>

				{#if data.status}
					<div class="text-xs space-y-1" style="color: var(--palais-text-muted);">
						{#if data.status.system?.cuda_device_name}
							<p>🎮 {data.status.system.cuda_device_name}</p>
						{/if}
						{#if data.status.system?.ram_total}
							<p>🧠 RAM: {(data.status.system.ram_used / 1073741824).toFixed(1)} / {(data.status.system.ram_total / 1073741824).toFixed(1)} GB</p>
						{/if}
					</div>
				{/if}
			</section>

			<!-- Quick Generate -->
			<section class="rounded-xl p-5 space-y-4"
				style="background: var(--palais-surface); border: 1px solid var(--palais-border);">
				<h2 class="text-xs font-semibold uppercase tracking-widest" style="color: var(--palais-text-muted);">
					Génération rapide
				</h2>
				<textarea
					bind:value={prompt}
					rows="4"
					placeholder="Un portrait cyberpunk sous la pluie..."
					class="w-full text-sm rounded-lg px-3 py-2 resize-none focus:outline-none"
					style="background: rgba(0,0,0,0.3); border: 1px solid var(--palais-border); color: var(--palais-text); font-family: 'Inter', sans-serif;"
				></textarea>
				<button
					onclick={generate}
					disabled={generating || !prompt.trim() || !!data.comfyError}
					class="w-full py-2 px-4 rounded-lg text-sm font-semibold transition-all disabled:opacity-40"
					style="background: linear-gradient(135deg, var(--palais-gold), var(--palais-amber)); color: var(--palais-bg);"
				>
					{generating ? 'Envoi...' : 'Générer'}
				</button>
				{#if genResult}
					<p class="text-xs" style="color: var(--palais-green);">✓ {genResult}</p>
				{/if}
				{#if genError}
					<p class="text-xs" style="color: var(--palais-red);">✗ {genError}</p>
				{/if}
			</section>

			<!-- Recent jobs -->
			{#if data.history.length > 0}
			<section class="rounded-xl p-5 space-y-3"
				style="background: var(--palais-surface); border: 1px solid var(--palais-border);">
				<h2 class="text-xs font-semibold uppercase tracking-widest" style="color: var(--palais-text-muted);">
					Historique ({data.history.length})
				</h2>
				<div class="space-y-2 max-h-48 overflow-y-auto">
					{#each data.history as job}
					<div class="flex items-center justify-between py-1">
						<span class="text-xs font-mono truncate max-w-[120px]" style="color: var(--palais-text-muted);">
							{String(job.id).substring(0, 8)}…
						</span>
						<span class="text-xs" style="color: var(--palais-green);">✓</span>
					</div>
					{/each}
				</div>
			</section>
			{/if}
		</div>

		<!-- Right column: Gallery -->
		<div class="lg:col-span-2">
			<section class="rounded-xl p-5"
				style="background: var(--palais-surface); border: 1px solid var(--palais-border);">
				<h2 class="text-xs font-semibold uppercase tracking-widest mb-4" style="color: var(--palais-text-muted);">
					Galerie — Livrables agents ({data.gallery.length})
				</h2>

				{#if data.gallery.length > 0}
					<div class="grid grid-cols-2 sm:grid-cols-3 gap-3">
						{#each data.gallery as asset}
						<div class="group rounded-lg overflow-hidden cursor-pointer transition-all hover:scale-[1.02]"
							style="background: rgba(0,0,0,0.3); border: 1px solid var(--palais-border);"
							onclick={() => previewUrl = `/dl/${asset.downloadToken}`}
						>
							<!-- Preview thumbnail for images -->
							{#if asset.mimeType?.startsWith('image/')}
								<div class="w-full aspect-square flex items-center justify-center overflow-hidden"
									style="background: rgba(0,0,0,0.2);">
									<img src={`/dl/${asset.downloadToken}`}
										alt={asset.filename}
										class="w-full h-full object-cover"
										loading="lazy"
									/>
								</div>
							{:else}
								<div class="w-full aspect-square flex items-center justify-center"
									style="background: rgba(0,0,0,0.2);">
									<span class="text-3xl">📄</span>
								</div>
							{/if}
							<div class="p-2">
								<p class="text-xs truncate font-mono" style="color: var(--palais-text);">{asset.filename}</p>
								<p class="text-xs mt-0.5" style="color: var(--palais-text-muted);">{formatBytes(asset.sizeBytes)}</p>
							</div>
						</div>
						{/each}
					</div>
				{:else}
					<div class="py-16 text-center">
						<p class="text-sm" style="color: var(--palais-text-muted);">
							Aucun livrable. Les assets générés par les agents apparaîtront ici.
						</p>
					</div>
				{/if}
			</section>
		</div>
	</div>
</div>

<!-- Preview modal -->
{#if previewUrl}
<div
	class="fixed inset-0 z-50 flex items-center justify-center p-8"
	style="background: rgba(0,0,0,0.85);"
	onclick={() => previewUrl = null}
>
	<div class="max-w-2xl w-full" onclick={(e) => e.stopPropagation()}>
		<img src={previewUrl} alt="Preview" class="rounded-xl w-full object-contain max-h-[70vh]"/>
		<div class="flex justify-between items-center mt-4">
			<a href={previewUrl} download
				class="text-xs px-3 py-1.5 rounded-lg"
				style="background: var(--palais-surface); color: var(--palais-text);">
				⬇ Télécharger
			</a>
			<button onclick={() => previewUrl = null}
				class="text-xs px-3 py-1.5 rounded-lg"
				style="background: var(--palais-surface); color: var(--palais-text-muted);">
				Fermer
			</button>
		</div>
	</div>
</div>
{/if}
