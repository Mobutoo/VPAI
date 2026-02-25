<script lang="ts">
	interface SuggestedAction {
		label: string;
		action_type: string;
		params: Record<string, string>;
	}

	interface Standup {
		generated: boolean;
		title?: string;
		description?: string;
		suggestedActions?: SuggestedAction[];
		createdAt?: string;
	}

	let { standup }: { standup: Standup } = $props();

	/** Lightweight markdown renderer for LiteLLM briefing output.
	 *  Handles: ## h2, ### h3, **bold**, - list items, blank lines as paragraphs.
	 */
	function renderMarkdown(md: string): string {
		if (!md) return '';

		const lines = md.split('\n');
		const html: string[] = [];
		let inList = false;

		for (const raw of lines) {
			const line = raw.trimEnd();

			// Close open list before any non-list line
			if (inList && !line.startsWith('- ') && !line.startsWith('* ')) {
				html.push('</ul>');
				inList = false;
			}

			if (line.startsWith('### ')) {
				html.push(`<h3 class="mt-4 mb-1 text-sm font-semibold" style="color:var(--palais-gold)">${escHtml(line.slice(4))}</h3>`);
			} else if (line.startsWith('## ')) {
				html.push(`<h2 class="mt-5 mb-2 text-base font-semibold" style="color:var(--palais-gold)">${escHtml(line.slice(3))}</h2>`);
			} else if (line.startsWith('# ')) {
				html.push(`<h1 class="mt-5 mb-2 text-lg font-bold" style="color:var(--palais-gold)">${escHtml(line.slice(2))}</h1>`);
			} else if (line.startsWith('- ') || line.startsWith('* ')) {
				if (!inList) { html.push('<ul class="my-1 ml-4 space-y-0.5 list-disc">'); inList = true; }
				html.push(`<li>${inlineMd(line.slice(2))}</li>`);
			} else if (line === '') {
				html.push('<div class="h-2"></div>');
			} else {
				html.push(`<p>${inlineMd(line)}</p>`);
			}
		}

		if (inList) html.push('</ul>');
		return html.join('\n');
	}

	/** Escape HTML special chars */
	function escHtml(s: string): string {
		return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
	}

	/** Inline markdown: **bold**, *italic* */
	function inlineMd(s: string): string {
		return escHtml(s)
			.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
			.replace(/\*(.+?)\*/g, '<em>$1</em>');
	}

	const renderedDescription = $derived(renderMarkdown(standup.description ?? ''));
</script>

{#if standup.generated}
	<section
		class="rounded-lg p-6 relative overflow-hidden"
		style="background: var(--palais-surface); border: 1px solid var(--palais-gold); box-shadow: var(--palais-glow-sm);"
	>
		<!-- Gold accent bar -->
		<div class="absolute top-0 left-0 w-full h-0.5" style="background: var(--palais-gold);"></div>

		<div class="flex items-start justify-between mb-4">
			<h2 class="text-lg font-semibold" style="color: var(--palais-gold); font-family: 'Orbitron', sans-serif;">
				{standup.title}
			</h2>
			{#if standup.createdAt}
				<span class="text-xs tabular-nums" style="color: var(--palais-text-muted);">
					{new Date(standup.createdAt).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })}
				</span>
			{/if}
		</div>

		<div class="text-sm leading-relaxed" style="color: var(--palais-text);">
			<!-- eslint-disable-next-line svelte/no-at-html-tags -->
			{@html renderedDescription}
		</div>

		{#if standup.suggestedActions && standup.suggestedActions.length > 0}
			<div class="flex flex-wrap gap-2 mt-4 pt-4" style="border-top: 1px solid var(--palais-border);">
				{#each standup.suggestedActions as action}
					{#if action.action_type === 'navigate'}
						<a
							href={action.params.url}
							class="px-3 py-1.5 rounded text-xs font-medium transition-all hover:brightness-110"
							style="background: transparent; color: var(--palais-gold); border: 1px solid var(--palais-gold);"
						>
							{action.label}
						</a>
					{:else}
						<button
							class="px-3 py-1.5 rounded text-xs font-medium transition-all hover:brightness-110"
							style="background: transparent; color: var(--palais-amber); border: 1px solid var(--palais-amber);"
						>
							{action.label}
						</button>
					{/if}
				{/each}
			</div>
		{/if}
	</section>
{/if}
