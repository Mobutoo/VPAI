<script lang="ts">
	import type { PageData } from './$types';
	import { tick } from 'svelte';

	let { data }: { data: PageData } = $props();

	type Message = typeof data.conversation[number];

	const STATUS_COLORS: Record<string, string> = {
		briefing:     'var(--palais-text-muted)',
		brainstorming:'var(--palais-cyan)',
		planning:     'var(--palais-amber)',
		co_editing:   'var(--palais-gold)',
		approved:     '#22c55e',
		executing:    'var(--palais-red)',
		review:       'var(--palais-amber)',
		completed:    '#22c55e',
		failed:       'var(--palais-red)'
	};

	const STATUS_LABELS: Record<string, string> = {
		briefing: 'Briefing', brainstorming: 'Brainstorming', planning: 'Planning',
		co_editing: 'Co-Editing', approved: 'Approved', executing: 'Executing',
		review: 'Review', completed: 'Completed', failed: 'Failed'
	};

	let mission = $state({ ...data.mission });
	let messages = $state([...data.conversation]);
	let newMessage = $state('');
	let sending = $state(false);
	let chatEl: HTMLDivElement;

	// Auto-scroll to bottom
	async function scrollToBottom() {
		await tick();
		if (chatEl) chatEl.scrollTop = chatEl.scrollHeight;
	}

	$effect(() => {
		if (messages.length) scrollToBottom();
	});

	async function sendMessage() {
		const content = newMessage.trim();
		if (!content || sending) return;
		sending = true;

		// Optimistic user message
		const optimistic: Message = {
			id: -Date.now(),
			missionId: mission.id,
			role: 'user',
			content,
			memoryRefs: null,
			createdAt: new Date().toISOString() as unknown as Date
		};
		messages = [...messages, optimistic];
		newMessage = '';
		await scrollToBottom();

		const res = await fetch(`/api/v1/missions/${mission.id}/chat`, {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ content })
		});

		if (res.ok) {
			const reply = await res.json();
			// Replace optimistic with real, add assistant reply
			messages = messages.filter((m) => m.id !== optimistic.id).concat(reply);
			// Reload full conversation to get user message with real ID
			const histRes = await fetch(`/api/v1/missions/${mission.id}/chat`);
			if (histRes.ok) messages = await histRes.json();
			// Update mission status
			if (mission.status === 'briefing') mission = { ...mission, status: 'brainstorming' };
		} else {
			// Remove optimistic on error
			messages = messages.filter((m) => m.id !== optimistic.id);
		}
		sending = false;
		await scrollToBottom();
	}

	async function advanceToPlanning() {
		const res = await fetch(`/api/v1/missions/${mission.id}`, {
			method: 'PUT',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ status: 'planning' })
		});
		if (res.ok) mission = { ...mission, status: 'planning' };
	}
</script>

<div class="flex h-[calc(100vh-6rem)] gap-4">
	<!-- Left: Chat panel -->
	<div class="flex flex-col flex-1 min-w-0 rounded-xl overflow-hidden"
		style="background: var(--palais-surface); border: 1px solid var(--palais-border);">

		<!-- Header -->
		<div class="flex items-center gap-3 px-5 py-3 flex-shrink-0"
			style="border-bottom: 1px solid var(--palais-border); background: linear-gradient(135deg, color-mix(in srgb, var(--palais-gold) 8%, var(--palais-surface)), var(--palais-surface));">
			<a href="/missions" class="text-xs" style="color: var(--palais-text-muted);">← Missions</a>
			<div class="flex-1 min-w-0">
				<h1 class="text-sm font-bold truncate" style="color: var(--palais-text); font-family: 'Orbitron', sans-serif;">
					{mission.title}
				</h1>
			</div>
			<span class="px-2 py-0.5 rounded-full text-xs flex-shrink-0"
				style="background: color-mix(in srgb, {STATUS_COLORS[mission.status] ?? 'var(--palais-border)'} 15%, transparent); color: {STATUS_COLORS[mission.status] ?? 'var(--palais-text-muted)'};">
				{STATUS_LABELS[mission.status] ?? mission.status}
			</span>
		</div>

		<!-- Brief (if set) -->
		{#if mission.briefText && messages.length === 0}
			<div class="mx-4 my-3 p-3 rounded-lg text-xs flex-shrink-0"
				style="background: var(--palais-bg); border: 1px solid var(--palais-border); color: var(--palais-text-muted);">
				<span class="font-medium" style="color: var(--palais-text);">Brief: </span>{mission.briefText}
			</div>
		{/if}

		<!-- Messages -->
		<div bind:this={chatEl} class="flex-1 overflow-y-auto p-4 flex flex-col gap-3">
			{#if messages.length === 0}
				<div class="flex flex-col items-center justify-center flex-1 gap-3 text-center">
					<p class="text-2xl">🤖</p>
					<p class="text-sm" style="color: var(--palais-text-muted);">
						Start the brainstorming session.<br>
						<span class="text-xs">The AI will help clarify your mission one question at a time.</span>
					</p>
				</div>
			{:else}
				{#each messages as msg}
					<div class="flex {msg.role === 'user' ? 'justify-end' : 'justify-start'}">
						<div class="max-w-[80%] rounded-xl px-4 py-2.5 text-sm"
							style="
								background: {msg.role === 'user' ? 'color-mix(in srgb, var(--palais-gold) 20%, var(--palais-surface))' : 'var(--palais-bg)'};
								border: 1px solid {msg.role === 'user' ? 'var(--palais-gold)' : 'var(--palais-border)'};
								color: var(--palais-text);
							"
						>
							{#if msg.role === 'assistant'}
								<span class="text-xs font-medium block mb-1" style="color: var(--palais-cyan);">🤖 Planificateur</span>
							{/if}
							<p style="white-space: pre-wrap; line-height: 1.5;">{msg.content}</p>
							<p class="text-xs mt-1" style="color: var(--palais-text-muted);">
								{new Date(msg.createdAt).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })}
							</p>
						</div>
					</div>
				{/each}
				{#if sending}
					<div class="flex justify-start">
						<div class="rounded-xl px-4 py-2.5"
							style="background: var(--palais-bg); border: 1px solid var(--palais-border);">
							<span class="text-xs" style="color: var(--palais-text-muted);">🤖 thinking…</span>
						</div>
					</div>
				{/if}
			{/if}
		</div>

		<!-- Input -->
		<div class="flex-shrink-0 p-4 flex gap-2" style="border-top: 1px solid var(--palais-border);">
			<textarea
				bind:value={newMessage}
				rows="2"
				placeholder="Répondez ou posez une question..."
				class="flex-1 px-3 py-2 rounded-lg text-sm resize-none outline-none"
				style="background: var(--palais-bg); border: 1px solid var(--palais-border); color: var(--palais-text);"
				onkeydown={(e) => {
					if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
				}}
			></textarea>
			<button
				onclick={sendMessage}
				disabled={sending || !newMessage.trim()}
				class="px-4 py-2 rounded-lg text-sm font-medium disabled:opacity-50 self-end"
				style="background: var(--palais-gold); color: #0A0A0F; white-space: nowrap;"
			>
				{sending ? '…' : 'Send'}
			</button>
		</div>
	</div>

	<!-- Right: Mission info + actions -->
	<div class="flex flex-col gap-3 flex-shrink-0" style="width: 260px;">

		<!-- Info card -->
		<div class="rounded-xl p-4 flex flex-col gap-3"
			style="background: var(--palais-surface); border: 1px solid var(--palais-border);">
			<p class="text-xs font-semibold" style="color: var(--palais-gold); font-family: 'Orbitron', sans-serif; letter-spacing: 0.06em;">
				MISSION INFO
			</p>
			<div class="text-xs flex flex-col gap-1.5">
				<div class="flex justify-between">
					<span style="color: var(--palais-text-muted);">ID</span>
					<span class="font-mono" style="color: var(--palais-text);">#{mission.id}</span>
				</div>
				<div class="flex justify-between">
					<span style="color: var(--palais-text-muted);">Created</span>
					<span style="color: var(--palais-text);">
						{new Date(mission.createdAt).toLocaleDateString('fr-FR', { day: '2-digit', month: 'short' })}
					</span>
				</div>
				{#if mission.totalEstimatedCost}
					<div class="flex justify-between">
						<span style="color: var(--palais-text-muted);">Est. Cost</span>
						<span class="font-mono" style="color: var(--palais-gold);">${mission.totalEstimatedCost.toFixed(3)}</span>
					</div>
				{/if}
				<div class="flex justify-between">
					<span style="color: var(--palais-text-muted);">Messages</span>
					<span style="color: var(--palais-text);">{messages.length}</span>
				</div>
			</div>
		</div>

		<!-- Status flow -->
		<div class="rounded-xl p-4" style="background: var(--palais-surface); border: 1px solid var(--palais-border);">
			<p class="text-xs font-semibold mb-3" style="color: var(--palais-gold); font-family: 'Orbitron', sans-serif; letter-spacing: 0.06em;">
				FLOW
			</p>
			{#each ['briefing','brainstorming','planning','co_editing','approved','executing','completed'] as s}
				{@const current = mission.status === s}
				{@const passed = ['briefing','brainstorming','planning','co_editing','approved','executing','completed'].indexOf(mission.status) > ['briefing','brainstorming','planning','co_editing','approved','executing','completed'].indexOf(s)}
				<div class="flex items-center gap-2 mb-1.5">
					<div class="w-2 h-2 rounded-full flex-shrink-0"
						style="background: {current ? STATUS_COLORS[s] : passed ? '#22c55e' : 'var(--palais-border)'};">
					</div>
					<span class="text-xs" style="color: {current ? STATUS_COLORS[s] : passed ? 'var(--palais-text-muted)' : 'var(--palais-border)'};">
						{STATUS_LABELS[s]}
					</span>
				</div>
			{/each}
		</div>

		<!-- Actions -->
		{#if mission.status === 'brainstorming' && messages.length >= 4}
			<button
				onclick={advanceToPlanning}
				class="w-full py-2 rounded-lg text-xs font-medium transition-all"
				style="background: var(--palais-amber); color: #0A0A0F;">
				→ Move to Planning
			</button>
		{/if}

		{#if mission.status === 'co_editing'}
			<a
				href="/missions/{mission.id}/plan"
				class="block text-center w-full py-2 rounded-lg text-xs font-medium"
				style="background: var(--palais-gold); color: #0A0A0F;">
				✏️ Edit Plan
			</a>
		{/if}
	</div>
</div>
