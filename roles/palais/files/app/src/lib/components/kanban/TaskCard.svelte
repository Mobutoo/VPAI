<script lang="ts">
	import { createEventDispatcher, onDestroy } from 'svelte';

	let {
		task
	}: {
		task: {
			id: number; columnId: number; title: string; priority: string | null;
			assigneeAgentId: string | null; confidenceScore: number | null;
			estimatedCost: number | null; actualCost: number | null; position: number | null;
			status: string | null;
		};
	} = $props();

	const dispatch = createEventDispatcher<{
		openTask: void;
		dragStart: DragEvent;
	}>();

	const priorityColors: Record<string, string> = {
		urgent: 'var(--palais-red)',
		high: 'var(--palais-amber)',
		medium: 'var(--palais-gold)',
		low: 'var(--palais-cyan)',
		none: 'var(--palais-border)'
	};

	function confidenceBadge(score: number | null) {
		if (score === null) return null;
		if (score >= 0.8) return { color: 'var(--palais-green)', label: `${Math.round(score * 100)}%` };
		if (score >= 0.5) return { color: 'var(--palais-amber)', label: `${Math.round(score * 100)}%` };
		return { color: 'var(--palais-red)', label: `${Math.round(score * 100)}%` };
	}

	let priorityColor = $derived(priorityColors[task.priority ?? 'none'] ?? priorityColors.none);
	let badge = $derived(confidenceBadge(task.confidenceScore));

	// ── Timer ─────────────────────────────────────────────────────────────────
	let timerRunning = $state(false);
	let timerStartedAt: Date | null = null;
	let elapsedSeconds = $state(0);
	let interval: ReturnType<typeof setInterval> | null = null;

	function formatElapsed(s: number): string {
		const h = Math.floor(s / 3600);
		const m = Math.floor((s % 3600) / 60);
		const sec = s % 60;
		if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`;
		return `${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`;
	}

	async function toggleTimer(e: MouseEvent) {
		e.stopPropagation();
		if (timerRunning) {
			// Stop
			await fetch(`/api/v1/tasks/${task.id}/timer`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ action: 'stop' })
			});
			if (interval) { clearInterval(interval); interval = null; }
			timerRunning = false;
			elapsedSeconds = 0;
		} else {
			// Start
			const res = await fetch(`/api/v1/tasks/${task.id}/timer`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ action: 'start' })
			});
			if (res.ok) {
				const entry = await res.json();
				timerStartedAt = new Date(entry.startedAt);
				timerRunning = true;
				elapsedSeconds = 0;
				interval = setInterval(() => {
					elapsedSeconds = Math.round(
						(Date.now() - (timerStartedAt?.getTime() ?? Date.now())) / 1000
					);
				}, 1000);
			}
		}
	}

	onDestroy(() => { if (interval) clearInterval(interval); });

	function onDragStart(e: DragEvent) {
		e.dataTransfer?.setData('taskId', String(task.id));
		dispatch('dragStart', e);
	}
</script>

<!-- svelte-ignore a11y_no_static_element_interactions -->
<div
	draggable="true"
	ondragstart={onDragStart}
	onclick={() => dispatch('openTask')}
	onkeydown={(e) => e.key === 'Enter' && dispatch('openTask')}
	role="button"
	tabindex="0"
	class="rounded-lg p-3 cursor-pointer transition-all select-none"
	style="
		background: var(--palais-bg);
		border: 1px solid var(--palais-border);
		border-left: 3px solid {priorityColor};
		position: relative;
		overflow: hidden;
	"
>
	<!-- Subtle Kuba micro-pattern -->
	<div style="position: absolute; bottom: 0; right: 0; width: 20px; height: 20px; opacity: 0.05;
		background: repeating-linear-gradient(45deg, var(--palais-gold), var(--palais-gold) 1px, transparent 1px, transparent 4px);">
	</div>

	<!-- Title -->
	<p class="text-sm leading-snug mb-2" style="color: var(--palais-text);">
		{task.title}
	</p>

	<!-- Footer badges -->
	<div class="flex items-center gap-2 flex-wrap">
		{#if badge}
			<span class="text-xs font-mono px-1 py-0.5 rounded"
				style="background: color-mix(in srgb, {badge.color} 15%, transparent); color: {badge.color}; font-size: 0.65rem;">
				◎ {badge.label}
			</span>
		{/if}

		{#if task.estimatedCost !== null || task.actualCost !== null}
			<span class="text-xs font-mono" style="color: var(--palais-text-muted); font-size: 0.65rem;">
				${(task.actualCost ?? task.estimatedCost ?? 0).toFixed(3)}
			</span>
		{/if}

		{#if task.assigneeAgentId}
			<span class="text-xs px-1 py-0.5 rounded"
				style="background: var(--palais-surface); color: var(--palais-text-muted); font-size: 0.65rem; font-family: 'JetBrains Mono', monospace;">
				@{task.assigneeAgentId.split('-')[0]}
			</span>
		{/if}

		<!-- Timer control -->
		<div class="ml-auto flex items-center gap-1">
			{#if timerRunning}
				<span class="text-xs font-mono" style="color: var(--palais-cyan); font-size: 0.65rem;">
					{formatElapsed(elapsedSeconds)}
				</span>
			{/if}
			<!-- svelte-ignore a11y_consider_explicit_label -->
			<button
				onclick={toggleTimer}
				title={timerRunning ? 'Stop timer' : 'Start timer'}
				class="rounded p-0.5 transition-colors"
				style="
					background: {timerRunning ? 'color-mix(in srgb, var(--palais-red) 15%, transparent)' : 'transparent'};
					color: {timerRunning ? 'var(--palais-red)' : 'var(--palais-border)'};
					border: none; cursor: pointer; font-size: 0.7rem; line-height: 1;
				"
			>
				{timerRunning ? '⏹' : '⏱'}
			</button>
		</div>
	</div>
</div>
