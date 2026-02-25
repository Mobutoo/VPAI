<script lang="ts">
	interface Insight {
		id: number;
		type: string;
		severity: string;
		title: string;
		description: string | null;
		suggestedActions: unknown;
		createdAt: string;
	}

	let { insight }: { insight: Insight } = $props();
	let dismissed = $state(false);

	const severityStyles: Record<string, { bg: string; border: string; text: string }> = {
		critical: {
			bg: 'rgba(229, 57, 53, 0.1)',
			border: 'var(--palais-red)',
			text: 'var(--palais-red)'
		},
		warning: {
			bg: 'rgba(232, 131, 58, 0.1)',
			border: 'var(--palais-amber)',
			text: 'var(--palais-amber)'
		},
		info: {
			bg: 'rgba(79, 195, 247, 0.1)',
			border: 'var(--palais-cyan)',
			text: 'var(--palais-cyan)'
		}
	};

	const style = $derived(severityStyles[insight.severity] ?? severityStyles.info);

	async function acknowledge() {
		await fetch(`/api/v1/insights/${insight.id}/acknowledge`, { method: 'PUT' });
		dismissed = true;
	}
</script>

{#if !dismissed}
	<div
		class="rounded-lg px-4 py-3 flex items-center justify-between gap-4"
		style:background={style.bg}
		style:border="1px solid {style.border}"
	>
		<div class="flex items-center gap-3 min-w-0">
			<span class="text-xs font-bold uppercase shrink-0 px-2 py-0.5 rounded"
				style:background={style.border}
				style="color: var(--palais-bg);"
			>
				{insight.severity}
			</span>
			<span class="text-sm truncate" style:color={style.text}>
				{insight.title}
			</span>
		</div>
		<div class="flex items-center gap-2 shrink-0">
			<a href="/insights" class="text-xs underline" style="color: var(--palais-text-muted);">
				Détails
			</a>
			<button
				onclick={acknowledge}
				class="text-xs px-2 py-1 rounded transition-colors"
				style="color: var(--palais-text-muted); border: 1px solid var(--palais-border);"
			>
				OK
			</button>
		</div>
	</div>
{/if}
