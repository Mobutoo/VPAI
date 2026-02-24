<script lang="ts">
	import AgentCard from '$lib/components/agents/AgentCard.svelte';
	import { connectSSE, onAgentEvent } from '$lib/stores/sse';
	import { onMount } from 'svelte';

	let { data } = $props();
	let agentList = $state(data.agents);

	onMount(() => {
		connectSSE();
		const unsub = onAgentEvent((evt) => {
			if (evt.status) {
				agentList = agentList.map((a) =>
					a.id === evt.agentId ? { ...a, status: evt.status } : a
				);
			}
		});
		return unsub;
	});
</script>

<div class="space-y-6">
	<h1 class="text-2xl font-bold" style="color: var(--palais-gold); font-family: 'Orbitron', sans-serif;">
		Agent Cockpit
	</h1>

	<div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
		{#each agentList as agent (agent.id)}
			<AgentCard {agent} />
		{/each}
	</div>
</div>
