<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import type { PageData } from './$types';

	let { data }: { data: PageData } = $props();

	// ── State ──────────────────────────────────────────────────────────────────
	let agentList = $state([...data.assignedAgents]);
	let taskList  = $state([...data.missionTasks]);

	// Budget
	let budgetSpent   = $state(0);
	let budgetLimit   = $state(5.0);
	let budgetPercent = $state(0);
	let ecoMode       = $state(false);

	// Pi tools
	let comfyQueue   = $state(0);
	let comfyHistory = $state(0);
	let comfyOk      = $state(false);
	let claudeActive = $state(false);
	let claudeAction = $state<string | null>(null);

	// Real-time feed
	type FeedEvent = {
		id: string;
		ts: number;
		agentId: string | null;
		avatar: string | null;
		text: string;
		previewUrl?: string;
	};
	let events     = $state<FeedEvent[]>([]);
	let feedEl     = $state<HTMLDivElement | undefined>(undefined);
	let userScrolled = $state(false);

	// Modals
	let showReassign  = $state(false);
	let reassignTaskId = $state<number | null>(null);

	// SSE + polling
	let sse: EventSource | null = null;
	let poll: ReturnType<typeof setInterval> | null = null;

	// ── Derived ───────────────────────────────────────────────────────────────
	let activeAgents = $derived(agentList.filter(a => a.status !== 'offline'));
	let doneTasks    = $derived(taskList.filter(t => t.status === 'done').length);
	let progressPercent = $derived(
		taskList.length > 0 ? Math.round((doneTasks / taskList.length) * 100) : 0
	);

	// ── Helpers ───────────────────────────────────────────────────────────────
	function fmtTime(ts: number) {
		return new Date(ts).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
	}

	function addEvent(agentId: string | null, text: string, previewUrl?: string) {
		const agent = agentList.find(a => a.id === agentId);
		events = [...events.slice(-199), {
			id: crypto.randomUUID(), ts: Date.now(),
			agentId, avatar: agent?.avatar_url ?? null, text, previewUrl
		}];
		if (!userScrolled && feedEl) {
			setTimeout(() => { if (feedEl) feedEl.scrollTop = feedEl.scrollHeight; }, 30);
		}
	}

	function statusColor(s: string) {
		return s === 'busy' ? 'var(--palais-amber)' :
		       s === 'error' ? 'var(--palais-red)' :
		       s === 'idle' ? 'var(--palais-cyan)' : 'var(--palais-text-muted)';
	}

	function taskStatusColor(s: string | null) {
		return s === 'done' ? 'var(--palais-green)' :
		       s === 'in-progress' ? 'var(--palais-amber)' :
		       s === 'paused' ? 'var(--palais-text-muted)' : 'var(--palais-border)';
	}

	// ── API calls ─────────────────────────────────────────────────────────────
	async function fetchBudget() {
		try {
			const r = await fetch('/api/v1/budget');
			if (r.ok) {
				const d = await r.json();
				budgetSpent   = d.today?.total ?? 0;
				budgetLimit   = d.today?.dailyLimit ?? 5.0;
				budgetPercent = d.today?.percentUsed ?? 0;
			}
		} catch { /* non-blocking */ }
	}

	async function fetchPiTools() {
		try {
			const r = await fetch('/api/v1/creative/comfyui');
			if (r.ok) {
				comfyOk = true;
				const d = await r.json();
				const q = d.queue?.value;
				const h = d.history?.value;
				comfyQueue   = q ? (q.queue_running?.length ?? 0) + (q.queue_pending?.length ?? 0) : 0;
				comfyHistory = h ? Object.keys(h).length : 0;
			}
		} catch { comfyOk = false; }
	}

	// ── Actions ───────────────────────────────────────────────────────────────
	async function pauseMission() {
		const running = taskList.filter(t => t.status === 'in-progress');
		for (const t of running) {
			await fetch(`/api/v1/tasks/${t.id}`, {
				method: 'PUT',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ status: 'paused' })
			}).catch(() => {});
		}
		taskList = taskList.map(t =>
			t.status === 'in-progress' ? { ...t, status: 'paused' } : t
		);
		addEvent(null, `⏸ Mission pausée — ${running.length} tâche(s) suspendues`);
	}

	async function toggleEcoMode() {
		ecoMode = !ecoMode;
		await fetch('/api/v1/budget/eco', {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ enabled: ecoMode })
		}).catch(() => {});
		addEvent(null, `💡 Eco Mode ${ecoMode ? 'activé' : 'désactivé'}`);
	}

	async function escalate() {
		await fetch('/api/v1/insights', {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({
				type: 'error_pattern',
				severity: 'critical',
				title: `🚨 Escalade War Room — ${data.mission.title}`,
				description: `Mission escaladée manuellement depuis le War Room`,
				entityType: 'mission',
				entityId: data.mission.id,
				missionId: data.mission.id
			})
		}).catch(() => {});
		addEvent(null, '🚨 Escalade créée — notification Telegram envoyée');
	}

	function openReassign(taskId: number) {
		reassignTaskId = taskId;
		showReassign = true;
	}

	// ── Lifecycle ─────────────────────────────────────────────────────────────
	onMount(() => {
		fetchBudget();
		fetchPiTools();

		// SSE — subscribe to OpenClaw agent events
		sse = new EventSource('/api/sse');
		sse.addEventListener('connected', () => {
			addEvent(null, '⚡ War Room connecté — flux temps-réel actif');
		});
		sse.addEventListener('agent', (e) => {
			try {
				const evt = JSON.parse(e.data);
				if (evt.agent_id) {
					agentList = agentList.map(a =>
						a.id === evt.agent_id ? { ...a, status: evt.status ?? a.status } : a
					);
					if (evt.agent_id === 'claude-code') {
						claudeActive = evt.status === 'busy';
						claudeAction = evt.description ?? null;
					}
					addEvent(evt.agent_id, evt.description ?? evt.action ?? 'Activité agent', evt.preview_url);
				}
				if (evt.type === 'token_usage') fetchBudget();
			} catch { /* ignore malformed events */ }
		});
		sse.addEventListener('error', () => {
			addEvent(null, '⚠ Flux SSE interrompu — tentative de reconnexion…');
		});

		// Polling every 10s for non-SSE data
		poll = setInterval(() => {
			fetchBudget();
			fetchPiTools();
		}, 10_000);
	});

	onDestroy(() => {
		sse?.close();
		if (poll) clearInterval(poll);
	});
</script>

<!-- ═══════════════════════════════════════════════════════════════════ LAYOUT -->
<div
	class="warroom"
	style="
		margin: -1.5rem;
		height: 100vh;
		display: grid;
		grid-template-columns: 1fr 2fr;
		grid-template-rows: 56px 1fr 80px 200px;
		grid-template-areas: 'header header' 'agents pi' 'timeline timeline' 'feed feed';
		overflow: hidden;
		background: var(--palais-bg);
		font-family: var(--font-body, Inter, sans-serif);
	"
>

	<!-- ═══════════════════════════════════════════════════════════ HEADER BAR -->
	<header style="
		grid-area: header;
		display: flex; align-items: center; gap: 1rem;
		padding: 0 1.25rem;
		background: color-mix(in srgb, var(--palais-surface) 80%, transparent);
		border-bottom: 1px solid var(--palais-border);
		backdrop-filter: blur(8px);
	">
		<!-- Mission name + back link -->
		<a
			href="/missions/{data.mission.id}"
			style="color: var(--palais-text-muted); font-size: 0.75rem; text-decoration: none; white-space: nowrap;"
		>← Mission</a>
		<div style="
			width: 8px; height: 8px; border-radius: 50%;
			background: var(--palais-amber);
			animation: pulse-amber 1.5s ease-in-out infinite;
			flex-shrink: 0;
		"></div>
		<span style="
			font-family: var(--font-display, Orbitron, sans-serif);
			font-size: 0.85rem; font-weight: 600;
			color: var(--palais-gold);
			letter-spacing: 0.08em;
			overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1;
		">WAR ROOM — {data.mission.title.toUpperCase()}</span>

		<!-- Stats chips -->
		<span style="font-size: 0.7rem; color: var(--palais-text-muted); white-space: nowrap;">
			{taskList.length} tâches · {activeAgents.length} agents actifs
		</span>

		<!-- ── Action buttons ── -->
		<div style="display: flex; gap: 0.5rem; flex-shrink: 0;">
			<button
				onclick={pauseMission}
				style="
					padding: 0.3rem 0.75rem; font-size: 0.72rem; font-weight: 600;
					background: color-mix(in srgb, var(--palais-amber) 12%, transparent);
					color: var(--palais-amber); border: 1px solid var(--palais-amber);
					border-radius: 4px; cursor: pointer; letter-spacing: 0.04em;
				"
			>⏸ PAUSE</button>

			<button
				onclick={() => showReassign = true}
				style="
					padding: 0.3rem 0.75rem; font-size: 0.72rem; font-weight: 600;
					background: color-mix(in srgb, var(--palais-cyan) 12%, transparent);
					color: var(--palais-cyan); border: 1px solid var(--palais-cyan);
					border-radius: 4px; cursor: pointer; letter-spacing: 0.04em;
				"
			>↔ RÉASSIGNER</button>

			<button
				onclick={toggleEcoMode}
				style="
					padding: 0.3rem 0.75rem; font-size: 0.72rem; font-weight: 600;
					background: {ecoMode ? 'color-mix(in srgb, var(--palais-green) 20%, transparent)' : 'transparent'};
					color: {ecoMode ? 'var(--palais-green)' : 'var(--palais-text-muted)'};
					border: 1px solid {ecoMode ? 'var(--palais-green)' : 'var(--palais-border)'};
					border-radius: 4px; cursor: pointer; letter-spacing: 0.04em;
					transition: all 0.2s;
				"
			>💡 ECO {ecoMode ? 'ON' : 'OFF'}</button>

			<button
				onclick={escalate}
				style="
					padding: 0.3rem 0.75rem; font-size: 0.72rem; font-weight: 600;
					background: color-mix(in srgb, var(--palais-red) 15%, transparent);
					color: var(--palais-red); border: 1px solid var(--palais-red);
					border-radius: 4px; cursor: pointer; letter-spacing: 0.04em;
				"
			>🚨 ESCALADER</button>
		</div>
	</header>

	<!-- ═══════════════════════════════════════════════════════ ZONE 1: AGENTS -->
	<section style="
		grid-area: agents;
		overflow-y: auto; padding: 1rem;
		border-right: 1px solid var(--palais-border);
		display: flex; flex-direction: column; gap: 0.5rem;
	">
		<div style="
			font-family: var(--font-display, Orbitron, sans-serif);
			font-size: 0.65rem; font-weight: 600; letter-spacing: 0.12em;
			color: var(--palais-text-muted); margin-bottom: 0.5rem;
		">AGENTS VPS</div>

		{#if activeAgents.length === 0}
			<div style="color: var(--palais-text-muted); font-size: 0.8rem; font-style: italic;">
				Aucun agent actif sur cette mission
			</div>
		{/if}

		{#each activeAgents as agent (agent.id)}
			{@const currentTask = taskList.find(t => t.id === agent.currentTaskId)}
			<div style="
				padding: 0.75rem; border-radius: 6px;
				background: var(--palais-surface);
				border: 1px solid {agent.status === 'error' ? 'var(--palais-red)' : agent.status === 'busy' ? 'var(--palais-amber)' : 'var(--palais-border)'};
				transition: border-color 0.3s;
			">
				<div style="display: flex; align-items: center; gap: 0.6rem; margin-bottom: 0.5rem;">
					<!-- Avatar -->
					<div style="
						width: 32px; height: 32px; border-radius: 50%;
						background: color-mix(in srgb, {statusColor(agent.status)} 20%, var(--palais-surface));
						border: 2px solid {statusColor(agent.status)};
						display: flex; align-items: center; justify-content: center;
						font-size: 0.75rem; font-weight: 700; color: {statusColor(agent.status)};
						flex-shrink: 0;
						{agent.status === 'busy' ? 'animation: pulse-border 1.5s ease-in-out infinite;' : ''}
					">
						{agent.name.charAt(0).toUpperCase()}
					</div>
					<div style="flex: 1; min-width: 0;">
						<div style="font-size: 0.8rem; font-weight: 600; color: var(--palais-text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">
							{agent.name}
						</div>
						<div style="font-size: 0.65rem; color: {statusColor(agent.status)}; letter-spacing: 0.06em; text-transform: uppercase;">
							{agent.status}
						</div>
					</div>
					<!-- Spend badge -->
					{#if (agent.totalSpend30d ?? 0) > 0}
						<span style="font-size: 0.65rem; color: var(--palais-text-muted);">
							${(agent.totalSpend30d ?? 0).toFixed(2)}/30j
						</span>
					{/if}
				</div>

				<!-- Current task -->
				{#if currentTask}
					<div style="
						font-size: 0.7rem; color: var(--palais-text-muted);
						white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
						margin-bottom: 0.4rem;
					">
						▶ {currentTask.title}
					</div>
				{:else}
					<div style="font-size: 0.7rem; color: var(--palais-text-muted); margin-bottom: 0.4rem;">idle</div>
				{/if}

				<!-- Spend progress bar (% of daily budget) -->
				{#if budgetLimit > 0}
					{@const agentPct = Math.min(100, ((agent.totalSpend30d ?? 0) / 30 / budgetLimit) * 100)}
					<div style="height: 3px; background: var(--palais-border); border-radius: 2px;">
						<div style="
							height: 100%; border-radius: 2px;
							width: {agentPct}%;
							background: {agentPct > 80 ? 'var(--palais-red)' : 'var(--palais-amber)'};
							transition: width 0.5s;
						"></div>
					</div>
				{/if}
			</div>
		{/each}

		<!-- All mission tasks (compact list) -->
		{#if taskList.length > 0}
			<div style="
				margin-top: 1rem;
				font-family: var(--font-display, Orbitron, sans-serif);
				font-size: 0.6rem; font-weight: 600; letter-spacing: 0.12em;
				color: var(--palais-text-muted);
			">TÂCHES</div>
			{#each taskList as task (task.id)}
				<div style="
					display: flex; align-items: center; gap: 0.5rem;
					font-size: 0.72rem; color: var(--palais-text);
					padding: 0.3rem 0.5rem; border-radius: 4px;
					background: var(--palais-surface);
					border-left: 3px solid {taskStatusColor(task.status)};
				">
					<span style="flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
						{task.title}
					</span>
					<button
						onclick={() => openReassign(task.id)}
						style="
							font-size: 0.6rem; padding: 0.1rem 0.3rem;
							background: transparent; color: var(--palais-text-muted);
							border: 1px solid var(--palais-border); border-radius: 3px; cursor: pointer;
						"
					>↔</button>
				</div>
			{/each}
		{/if}
	</section>

	<!-- ════════════════════════════════════════════════════ ZONE 2: PI TOOLS -->
	<section style="
		grid-area: pi;
		overflow-y: auto; padding: 1rem;
		display: flex; flex-direction: column; gap: 0.75rem;
	">
		<div style="
			font-family: var(--font-display, Orbitron, sans-serif);
			font-size: 0.65rem; font-weight: 600; letter-spacing: 0.12em;
			color: var(--palais-text-muted); margin-bottom: 0.25rem;
		">OUTILS PI</div>

		<div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 0.75rem;">

			<!-- ComfyUI -->
			<div style="
				padding: 0.9rem; border-radius: 8px;
				background: var(--palais-surface);
				border: 1px solid {comfyOk ? 'var(--palais-border)' : 'var(--palais-border)'};
			">
				<div style="display: flex; align-items: center; gap: 0.4rem; margin-bottom: 0.6rem;">
					<div style="
						width: 8px; height: 8px; border-radius: 50%;
						background: {comfyOk ? 'var(--palais-green)' : 'var(--palais-text-muted)'};
					"></div>
					<span style="
						font-family: var(--font-display, Orbitron, sans-serif);
						font-size: 0.65rem; font-weight: 600; letter-spacing: 0.08em;
						color: var(--palais-text);
					">COMFYUI</span>
				</div>
				{#if comfyOk}
					<div style="display: flex; gap: 1.5rem;">
						<div>
							<div style="font-size: 1.5rem; font-weight: 700; color: var(--palais-gold); line-height: 1;">
								{comfyQueue}
							</div>
							<div style="font-size: 0.65rem; color: var(--palais-text-muted);">en queue</div>
						</div>
						<div>
							<div style="font-size: 1.5rem; font-weight: 700; color: var(--palais-cyan); line-height: 1;">
								{comfyHistory}
							</div>
							<div style="font-size: 0.65rem; color: var(--palais-text-muted);">complétés</div>
						</div>
					</div>
					{#if comfyQueue > 0}
						<div style="
							margin-top: 0.5rem; font-size: 0.65rem;
							color: var(--palais-amber);
							animation: pulse-text 1.5s ease-in-out infinite;
						">⚙ Génération en cours…</div>
					{/if}
				{:else}
					<div style="font-size: 0.75rem; color: var(--palais-text-muted); font-style: italic;">Non disponible</div>
				{/if}
			</div>

			<!-- Claude Code -->
			<div style="
				padding: 0.9rem; border-radius: 8px;
				background: var(--palais-surface);
				border: 1px solid {claudeActive ? 'var(--palais-amber)' : 'var(--palais-border)'};
				{claudeActive ? 'animation: border-pulse 2s ease-in-out infinite;' : ''}
			">
				<div style="display: flex; align-items: center; gap: 0.4rem; margin-bottom: 0.6rem;">
					<div style="
						width: 8px; height: 8px; border-radius: 50%;
						background: {claudeActive ? 'var(--palais-amber)' : 'var(--palais-text-muted)'};
						{claudeActive ? 'animation: pulse-amber 1s ease-in-out infinite;' : ''}
					"></div>
					<span style="
						font-family: var(--font-display, Orbitron, sans-serif);
						font-size: 0.65rem; font-weight: 600; letter-spacing: 0.08em;
						color: var(--palais-text);
					">CLAUDE CODE</span>
				</div>
				<div style="font-size: 0.8rem; color: {claudeActive ? 'var(--palais-amber)' : 'var(--palais-text-muted)'};">
					{claudeActive ? 'Session active' : 'Idle'}
				</div>
				{#if claudeAction}
					<div style="
						margin-top: 0.4rem; font-size: 0.65rem;
						color: var(--palais-text-muted);
						overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
					">{claudeAction}</div>
				{/if}
			</div>

			<!-- Remotion -->
			<div style="
				padding: 0.9rem; border-radius: 8px;
				background: var(--palais-surface);
				border: 1px solid var(--palais-border);
				opacity: 0.5;
			">
				<div style="display: flex; align-items: center; gap: 0.4rem; margin-bottom: 0.6rem;">
					<div style="width: 8px; height: 8px; border-radius: 50%; background: var(--palais-text-muted);"></div>
					<span style="
						font-family: var(--font-display, Orbitron, sans-serif);
						font-size: 0.65rem; font-weight: 600; letter-spacing: 0.08em;
						color: var(--palais-text);
					">REMOTION</span>
				</div>
				<div style="font-size: 0.75rem; color: var(--palais-text-muted); font-style: italic;">
					Non configuré
				</div>
			</div>
		</div>
	</section>

	<!-- ══════════════════════════════════════════════ ZONE 3: TIMELINE + BUDGET -->
	<section style="
		grid-area: timeline;
		padding: 0.75rem 1.25rem;
		background: color-mix(in srgb, var(--palais-surface) 60%, transparent);
		border-top: 1px solid var(--palais-border);
		border-bottom: 1px solid var(--palais-border);
		display: flex; flex-direction: column; gap: 0.4rem;
	">
		<!-- Progress + Budget label -->
		<div style="display: flex; justify-content: space-between; align-items: center;">
			<span style="
				font-family: var(--font-display, Orbitron, sans-serif);
				font-size: 0.72rem; font-weight: 600; letter-spacing: 0.08em;
				color: var(--palais-gold);
			">{progressPercent}% COMPLETE</span>

			<span style="font-size: 0.72rem; color: {budgetPercent > 80 ? 'var(--palais-red)' : budgetPercent > 60 ? 'var(--palais-amber)' : 'var(--palais-text-muted)'};">
				BUDGET ${budgetSpent.toFixed(2)} / ${budgetLimit.toFixed(2)}
				{#if budgetPercent > 0}· {budgetPercent.toFixed(0)}%{/if}
			</span>
		</div>

		<!-- Mission progress bar -->
		<div style="height: 6px; background: var(--palais-border); border-radius: 3px; overflow: hidden;">
			<div style="
				height: 100%; border-radius: 3px;
				width: {progressPercent}%;
				background: linear-gradient(90deg, var(--palais-gold), var(--palais-amber));
				transition: width 0.6s ease;
			"></div>
		</div>

		<!-- Per-task segments -->
		<div style="display: flex; gap: 2px; height: 16px;">
			{#each taskList as task (task.id)}
				<div
					title="{task.title} — {task.status ?? 'backlog'}"
					style="
						flex: 1; border-radius: 2px;
						background: {taskStatusColor(task.status)};
						opacity: {task.status === 'paused' ? 0.4 : 0.85};
						{task.status === 'in-progress' ? 'animation: segment-pulse 1.5s ease-in-out infinite;' : ''}
						cursor: default;
					"
				></div>
			{/each}
		</div>

		<!-- Budget bar -->
		{#if budgetLimit > 0}
			<div style="display: flex; align-items: center; gap: 0.5rem;">
				<div style="flex: 1; height: 4px; background: var(--palais-border); border-radius: 2px; overflow: hidden;">
					<div style="
						height: 100%;
						width: {budgetPercent}%;
						background: {budgetPercent > 80 ? 'var(--palais-red)' : budgetPercent > 60 ? 'var(--palais-amber)' : 'var(--palais-green)'};
						transition: width 1s ease;
						border-radius: 2px;
					"></div>
				</div>
				<span style="font-size: 0.6rem; color: var(--palais-text-muted); white-space: nowrap; flex-shrink: 0;">
					BURN
				</span>
			</div>
		{/if}
	</section>

	<!-- ═══════════════════════════════════════════════ ZONE 4: REAL-TIME FEED -->
	<section
		bind:this={feedEl}
		onscroll={() => {
			if (!feedEl) return;
			const atBottom = feedEl.scrollHeight - feedEl.scrollTop - feedEl.clientHeight < 40;
			userScrolled = !atBottom;
		}}
		style="
			grid-area: feed;
			overflow-y: auto; padding: 0.5rem 1.25rem;
			display: flex; flex-direction: column; gap: 0;
		"
	>
		<div style="
			position: sticky; top: 0; z-index: 1;
			font-family: var(--font-display, Orbitron, sans-serif);
			font-size: 0.6rem; font-weight: 600; letter-spacing: 0.12em;
			color: var(--palais-text-muted);
			background: var(--palais-bg);
			padding: 0.3rem 0;
			border-bottom: 1px solid var(--palais-border);
			margin-bottom: 0.3rem;
			display: flex; justify-content: space-between; align-items: center;
		">
			<span>FEED TEMPS-RÉEL</span>
			{#if userScrolled}
				<button
					onclick={() => { if (feedEl) { feedEl.scrollTop = feedEl.scrollHeight; userScrolled = false; } }}
					style="
						font-size: 0.6rem; padding: 0.1rem 0.4rem;
						background: color-mix(in srgb, var(--palais-amber) 15%, transparent);
						color: var(--palais-amber); border: 1px solid var(--palais-amber);
						border-radius: 3px; cursor: pointer;
					"
				>↓ Bas</button>
			{/if}
		</div>

		{#if events.length === 0}
			<div style="font-size: 0.75rem; color: var(--palais-text-muted); font-style: italic; padding: 0.5rem 0;">
				En attente d'événements…
			</div>
		{/if}

		{#each events as event (event.id)}
			<div style="
				display: flex; align-items: flex-start; gap: 0.6rem;
				padding: 0.25rem 0;
				border-bottom: 1px solid color-mix(in srgb, var(--palais-border) 40%, transparent);
				animation: fade-in 0.2s ease;
			">
				<time style="
					font-family: var(--font-mono, JetBrains Mono, monospace);
					font-size: 0.65rem; color: var(--palais-text-muted);
					white-space: nowrap; flex-shrink: 0; margin-top: 1px;
				">{fmtTime(event.ts)}</time>

				<!-- Agent avatar -->
				<div style="
					width: 18px; height: 18px; border-radius: 50%;
					background: color-mix(in srgb, var(--palais-cyan) 20%, var(--palais-surface));
					border: 1px solid var(--palais-border);
					display: flex; align-items: center; justify-content: center;
					font-size: 0.55rem; font-weight: 700; color: var(--palais-cyan);
					flex-shrink: 0; margin-top: 1px;
				">
					{event.agentId ? event.agentId.charAt(0).toUpperCase() : '⚙'}
				</div>

				<span style="font-size: 0.73rem; color: var(--palais-text); flex: 1; line-height: 1.3;">
					{event.text}
				</span>

				{#if event.previewUrl}
					<a
						href={event.previewUrl}
						target="_blank"
						rel="noopener"
						style="
							font-size: 0.65rem; color: var(--palais-cyan);
							text-decoration: none; white-space: nowrap; flex-shrink: 0;
						"
					>[preview]</a>
				{/if}
			</div>
		{/each}
	</section>
</div>

<!-- ═══════════════════════════════════════════════════ REASSIGN MODAL -->
{#if showReassign}
	<!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
	<div
		onclick={() => showReassign = false}
		style="
			position: fixed; inset: 0; z-index: 100;
			background: rgba(0,0,0,0.7);
			display: flex; align-items: center; justify-content: center;
		"
	>
		<!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
		<div
			onclick|stopPropagation
			style="
				background: var(--palais-surface); border: 1px solid var(--palais-border);
				border-radius: 10px; padding: 1.5rem; min-width: 320px;
			"
		>
			<div style="
				font-family: var(--font-display, Orbitron, sans-serif);
				font-size: 0.8rem; font-weight: 600; color: var(--palais-gold);
				margin-bottom: 1rem; letter-spacing: 0.08em;
			">RÉASSIGNER TÂCHE</div>

			<div style="margin-bottom: 0.75rem;">
				<label style="font-size: 0.75rem; color: var(--palais-text-muted);">Tâche</label>
				<select
					bind:value={reassignTaskId}
					style="
						display: block; width: 100%; margin-top: 0.25rem;
						background: var(--palais-bg); color: var(--palais-text);
						border: 1px solid var(--palais-border); border-radius: 4px;
						padding: 0.4rem; font-size: 0.8rem;
					"
				>
					{#each taskList as t}
						<option value={t.id}>{t.title}</option>
					{/each}
				</select>
			</div>

			<div style="display: flex; gap: 0.5rem; justify-content: flex-end;">
				<button
					onclick={() => showReassign = false}
					style="
						padding: 0.35rem 0.9rem; font-size: 0.75rem;
						background: transparent; color: var(--palais-text-muted);
						border: 1px solid var(--palais-border); border-radius: 4px; cursor: pointer;
					"
				>Annuler</button>
				<button
					onclick={async () => {
						if (reassignTaskId) {
							addEvent(null, `↔ Tâche #${reassignTaskId} marquée pour réassignation`);
						}
						showReassign = false;
					}}
					style="
						padding: 0.35rem 0.9rem; font-size: 0.75rem; font-weight: 600;
						background: color-mix(in srgb, var(--palais-cyan) 15%, transparent);
						color: var(--palais-cyan); border: 1px solid var(--palais-cyan);
						border-radius: 4px; cursor: pointer;
					"
				>Confirmer</button>
			</div>
		</div>
	</div>
{/if}

<style>
	@keyframes pulse-amber {
		0%, 100% { opacity: 1; }
		50% { opacity: 0.4; }
	}
	@keyframes pulse-text {
		0%, 100% { opacity: 1; }
		50% { opacity: 0.5; }
	}
	@keyframes segment-pulse {
		0%, 100% { opacity: 0.85; }
		50% { opacity: 0.45; }
	}
	@keyframes fade-in {
		from { opacity: 0; transform: translateY(4px); }
		to   { opacity: 1; transform: translateY(0); }
	}
</style>
