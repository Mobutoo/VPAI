<script lang="ts">
	import { createEventDispatcher, onMount } from 'svelte';
	import RichTextEditor from '$lib/components/editor/RichTextEditor.svelte';

	type Task = {
		id: number; columnId: number; title: string; priority: string | null;
		assigneeAgentId: string | null; confidenceScore: number | null;
		estimatedCost: number | null; actualCost: number | null; position: number | null;
		description?: string | null; status?: string | null; agentStatus?: string | null;
	};

	let { task }: { task: Task } = $props();

	const dispatch = createEventDispatcher<{
		close: void;
		updated: Partial<Task>;
	}>();

	let title = $state(task.title);
	let description = $state(task.description ?? '');
	let priority = $state(task.priority ?? 'none');
	let saving = $state(false);
	let comments = $state<Array<{ id: number; content: string; authorType: string; createdAt: string }>>([]);
	let newComment = $state('');
	let postingComment = $state(false);
	let activeTab = $state<'detail' | 'comments' | 'activity'>('detail');

	onMount(async () => {
		const res = await fetch(`/api/v1/tasks/${task.id}/comments`);
		if (res.ok) comments = await res.json();
	});

	async function save() {
		saving = true;
		const updates = { title, description, priority };
		const res = await fetch(`/api/v1/tasks/${task.id}`, {
			method: 'PUT',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify(updates)
		});
		if (res.ok) {
			dispatch('updated', updates);
		}
		saving = false;
	}

	async function postComment() {
		if (!newComment.trim()) return;
		postingComment = true;
		const res = await fetch(`/api/v1/tasks/${task.id}/comments`, {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ content: newComment.trim(), authorType: 'user' })
		});
		if (res.ok) {
			const comment = await res.json();
			comments = [...comments, comment];
			newComment = '';
		}
		postingComment = false;
	}

	const priorityOptions = ['none', 'low', 'medium', 'high', 'urgent'];
	const priorityColors: Record<string, string> = {
		urgent: 'var(--palais-red)', high: 'var(--palais-amber)',
		medium: 'var(--palais-gold)', low: 'var(--palais-cyan)', none: 'var(--palais-text-muted)'
	};
</script>

<!-- Overlay -->
<!-- svelte-ignore a11y_no_static_element_interactions -->
<div
	class="fixed inset-0 z-40"
	style="background: rgba(0,0,0,0.5);"
	onclick={() => dispatch('close')}
	onkeydown={(e) => e.key === 'Escape' && dispatch('close')}
	role="presentation"
></div>

<!-- Slide-out panel -->
<div
	class="fixed right-0 top-0 h-screen z-50 overflow-y-auto flex flex-col"
	style="width: 480px; background: var(--palais-surface); border-left: 1px solid var(--palais-border); box-shadow: -4px 0 24px rgba(0,0,0,0.4);"
>
	<!-- Panel Header -->
	<div class="flex items-center justify-between px-5 py-4 flex-shrink-0"
		style="border-bottom: 1px solid var(--palais-border); background: linear-gradient(135deg, color-mix(in srgb, var(--palais-gold) 8%, var(--palais-surface)), var(--palais-surface));">
		<span class="text-xs font-mono" style="color: var(--palais-text-muted);">Task #{task.id}</span>
		<button
			onclick={() => dispatch('close')}
			class="w-7 h-7 flex items-center justify-center rounded transition-colors"
			style="color: var(--palais-text-muted); background: var(--palais-surface-hover);"
		>✕</button>
	</div>

	<div class="flex-1 p-5 flex flex-col gap-4 overflow-y-auto">
		<!-- Title -->
		<input
			bind:value={title}
			class="w-full text-lg font-semibold outline-none bg-transparent"
			style="color: var(--palais-text); border-bottom: 1px solid var(--palais-border); padding-bottom: 0.5rem; font-family: 'Orbitron', sans-serif; font-size: 1rem;"
		/>

		<!-- Priority -->
		<div class="flex items-center gap-2">
			<span class="text-xs" style="color: var(--palais-text-muted); width: 80px;">Priority</span>
			<div class="flex gap-1">
				{#each priorityOptions as p}
					<button
						onclick={() => (priority = p)}
						class="px-2 py-0.5 rounded text-xs transition-all"
						style="
							background: {priority === p ? `color-mix(in srgb, ${priorityColors[p]} 20%, transparent)` : 'var(--palais-bg)'};
							color: {priority === p ? priorityColors[p] : 'var(--palais-text-muted)'};
							border: 1px solid {priority === p ? priorityColors[p] : 'var(--palais-border)'};
						"
					>{p}</button>
				{/each}
			</div>
		</div>

		<!-- Metrics (read-only) -->
		{#if task.confidenceScore !== null || task.estimatedCost !== null}
			<div class="flex gap-4">
				{#if task.confidenceScore !== null}
					<div>
						<p class="text-xs" style="color: var(--palais-text-muted);">Confidence</p>
						<p class="text-sm font-mono" style="color: var(--palais-cyan);">{Math.round(task.confidenceScore * 100)}%</p>
					</div>
				{/if}
				{#if task.estimatedCost !== null}
					<div>
						<p class="text-xs" style="color: var(--palais-text-muted);">Est. Cost</p>
						<p class="text-sm font-mono" style="color: var(--palais-gold);">${task.estimatedCost.toFixed(3)}</p>
					</div>
				{/if}
				{#if task.actualCost !== null}
					<div>
						<p class="text-xs" style="color: var(--palais-text-muted);">Actual Cost</p>
						<p class="text-sm font-mono" style="color: var(--palais-amber);">${task.actualCost.toFixed(3)}</p>
					</div>
				{/if}
			</div>
		{/if}

		<!-- Tabs -->
		<div class="flex gap-1" style="border-bottom: 1px solid var(--palais-border); padding-bottom: 0;">
			{#each [['detail', 'Description'], ['comments', `Comments (${comments.length})`], ['activity', 'Activity']] as [tab, label]}
				<button
					onclick={() => (activeTab = tab as typeof activeTab)}
					class="px-3 py-1.5 text-xs font-medium transition-all"
					style="
						color: {activeTab === tab ? 'var(--palais-gold)' : 'var(--palais-text-muted)'};
						border-bottom: 2px solid {activeTab === tab ? 'var(--palais-gold)' : 'transparent'};
						margin-bottom: -1px;
					"
				>{label}</button>
			{/each}
		</div>

		<!-- Tab: Description -->
		{#if activeTab === 'detail'}
			<RichTextEditor
				content={description}
				placeholder="Describe this task..."
				onupdate={(html) => (description = html)}
			/>
		{/if}

		<!-- Tab: Comments -->
		{#if activeTab === 'comments'}
			<div class="flex flex-col gap-3">
				{#each comments as comment}
					<div class="rounded-lg p-3" style="background: var(--palais-bg); border: 1px solid var(--palais-border);">
						<div class="flex items-center justify-between mb-1">
							<span class="text-xs font-medium" style="color: var(--palais-gold);">
								{comment.authorType === 'agent' ? '🤖 Agent' : '👤 User'}
							</span>
							<span class="text-xs" style="color: var(--palais-text-muted);">
								{new Date(comment.createdAt).toLocaleString('fr-FR')}
							</span>
						</div>
						<p class="text-sm" style="color: var(--palais-text);">{@html comment.content}</p>
					</div>
				{/each}

				<div class="flex flex-col gap-2">
					<textarea
						bind:value={newComment}
						rows="2"
						placeholder="Add a comment..."
						class="w-full px-3 py-2 rounded-lg text-sm resize-none outline-none"
						style="background: var(--palais-bg); border: 1px solid var(--palais-border); color: var(--palais-text);"
					></textarea>
					<button
						onclick={postComment}
						disabled={postingComment || !newComment.trim()}
						class="self-end px-3 py-1 rounded text-xs font-medium disabled:opacity-50"
						style="background: var(--palais-gold); color: #0A0A0F;"
					>
						{postingComment ? 'Posting...' : 'Post'}
					</button>
				</div>
			</div>
		{/if}

		<!-- Tab: Activity (placeholder) -->
		{#if activeTab === 'activity'}
			<p class="text-sm" style="color: var(--palais-text-muted);">Activity log coming soon.</p>
		{/if}
	</div>

	<!-- Save footer -->
	<div class="px-5 py-3 flex-shrink-0" style="border-top: 1px solid var(--palais-border);">
		<button
			onclick={save}
			disabled={saving}
			class="w-full py-2 rounded-lg text-sm font-medium disabled:opacity-50 transition-all"
			style="background: var(--palais-gold); color: #0A0A0F;"
		>
			{saving ? 'Saving...' : 'Save Changes'}
		</button>
	</div>
</div>
