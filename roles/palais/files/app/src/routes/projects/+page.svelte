<script lang="ts">
	import type { PageData } from './$types';

	let { data }: { data: PageData } = $props();

	let showCreate = $state(false);
	let creating = $state(false);
	let newName = $state('');
	let newDesc = $state('');
	let newWorkspaceId = $state(data.workspaces[0]?.id ?? 1);

	async function createProject() {
		if (!newName.trim()) return;
		creating = true;
		try {
			const res = await fetch('/api/v1/projects', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({
					name: newName.trim(),
					description: newDesc.trim() || null,
					workspaceId: newWorkspaceId
				})
			});
			if (res.ok) {
				const project = await res.json();
				window.location.href = `/projects/${project.id}`;
			}
		} finally {
			creating = false;
		}
	}
</script>

<div class="max-w-6xl mx-auto">
	<!-- Header -->
	<div class="flex items-center justify-between mb-8">
		<div>
			<h1 class="text-2xl font-bold" style="font-family: 'Orbitron', sans-serif; color: var(--palais-gold);">
				Projects
			</h1>
			<p class="text-sm mt-1" style="color: var(--palais-text-muted);">
				{data.projects.length} project{data.projects.length !== 1 ? 's' : ''}
			</p>
		</div>
		<button
			onclick={() => (showCreate = !showCreate)}
			class="px-4 py-2 rounded-lg text-sm font-medium transition-all"
			style="background: var(--palais-gold); color: #0A0A0F;"
		>
			+ New Project
		</button>
	</div>

	<!-- Create form -->
	{#if showCreate}
		<div class="rounded-xl p-6 mb-6" style="background: var(--palais-surface); border: 1px solid var(--palais-gold); box-shadow: var(--palais-glow-sm);">
			<h2 class="text-lg font-semibold mb-4" style="color: var(--palais-gold);">New Project</h2>
			<div class="flex flex-col gap-3">
				<input
					bind:value={newName}
					placeholder="Project name"
					class="w-full px-3 py-2 rounded-lg text-sm outline-none"
					style="background: var(--palais-bg); border: 1px solid var(--palais-border); color: var(--palais-text);"
				/>
				<input
					bind:value={newDesc}
					placeholder="Description (optional)"
					class="w-full px-3 py-2 rounded-lg text-sm outline-none"
					style="background: var(--palais-bg); border: 1px solid var(--palais-border); color: var(--palais-text);"
				/>
				{#if data.workspaces.length > 1}
					<select
						bind:value={newWorkspaceId}
						class="w-full px-3 py-2 rounded-lg text-sm outline-none"
						style="background: var(--palais-bg); border: 1px solid var(--palais-border); color: var(--palais-text);"
					>
						{#each data.workspaces as ws}
							<option value={ws.id}>{ws.name}</option>
						{/each}
					</select>
				{/if}
				<div class="flex gap-2">
					<button
						onclick={createProject}
						disabled={creating || !newName.trim()}
						class="px-4 py-2 rounded-lg text-sm font-medium transition-all disabled:opacity-50"
						style="background: var(--palais-gold); color: #0A0A0F;"
					>
						{creating ? 'Creating...' : 'Create'}
					</button>
					<button
						onclick={() => (showCreate = false)}
						class="px-4 py-2 rounded-lg text-sm transition-all"
						style="background: var(--palais-surface-hover); color: var(--palais-text-muted);"
					>
						Cancel
					</button>
				</div>
			</div>
		</div>
	{/if}

	<!-- Projects grid -->
	{#if data.projects.length === 0}
		<div class="text-center py-20" style="color: var(--palais-text-muted);">
			<div class="text-5xl mb-4">⬡</div>
			<p class="text-lg font-medium">No projects yet</p>
			<p class="text-sm mt-1">Create your first project to get started</p>
		</div>
	{:else}
		<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
			{#each data.projects as project}
				<!-- Kuba pattern background for cards -->
				<a
					href="/projects/{project.id}"
					class="block rounded-xl p-5 transition-all hover:scale-[1.01]"
					style="background: var(--palais-surface); border: 1px solid var(--palais-border); text-decoration: none; position: relative; overflow: hidden;"
				>
					<!-- Kuba decorative pattern top border -->
					<div style="position: absolute; top: 0; left: 0; right: 0; height: 3px; background: linear-gradient(90deg, var(--palais-gold) 0%, transparent 50%, var(--palais-gold) 100%);"></div>

					<div class="flex items-start gap-3">
						<div class="text-2xl flex-shrink-0">
							{project.icon || '◈'}
						</div>
						<div class="min-w-0 flex-1">
							<h3 class="font-semibold truncate" style="color: var(--palais-text); font-family: 'Orbitron', sans-serif; font-size: 0.9rem;">
								{project.name}
							</h3>
							{#if project.description}
								<p class="text-xs mt-1 line-clamp-2" style="color: var(--palais-text-muted);">
									{project.description}
								</p>
							{/if}
							<p class="text-xs mt-3" style="color: var(--palais-text-muted);">
								Updated {new Date(project.updatedAt).toLocaleDateString('fr-FR')}
							</p>
						</div>
					</div>

					<!-- Hover gold border -->
					<div class="absolute inset-0 rounded-xl opacity-0 hover:opacity-100 transition-opacity pointer-events-none"
						style="box-shadow: inset 0 0 0 1px var(--palais-gold);"></div>
				</a>
			{/each}
		</div>
	{/if}
</div>
