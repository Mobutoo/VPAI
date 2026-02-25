<script lang="ts">
	import { page } from '$app/stores';
	import {
		GyeNyame, Dwennimmen, Nkyinkyim, Sankofa,
		Aya, Akoma, Fawohodie, AnanseNtontan,
		Nyame, Bese
	} from '$lib/components/icons';

	const nav = [
		{ href: '/', label: 'Dashboard', icon: GyeNyame },
		{ href: '/agents', label: 'Agents', icon: Dwennimmen },
		{ href: '/projects', label: 'Projects', icon: Nkyinkyim },
		{ href: '/missions', label: 'Missions', icon: Akoma },
		{ href: '/ideas', label: 'Ideas', icon: Fawohodie },
		{ href: '/memory', label: 'Memory', icon: Sankofa },
		{ href: '/budget', label: 'Budget', icon: Aya },
		{ href: '/insights', label: 'Insights', icon: AnanseNtontan },
		{ href: '/health', label: 'Health', icon: Nyame },
		{ href: '/creative', label: 'Creative', icon: Bese },
	];

	let currentPath = $derived($page.url.pathname);
</script>

<aside class="fixed left-0 top-0 h-screen w-16 flex flex-col items-center py-6 gap-2 z-50"
	style="background: var(--palais-surface); border-right: 1px solid var(--palais-border);">

	<div class="mb-6" style="color: var(--palais-gold);">
		<span class="text-lg font-bold" style="font-family: 'Orbitron', sans-serif;">P</span>
	</div>

	{#each nav as item (item.href)}
		{@const active = currentPath === item.href || (item.href !== '/' && currentPath.startsWith(item.href))}
		<!-- eslint-disable-next-line svelte/no-navigation-without-resolve -->
		<a href={item.href}
			class="w-10 h-10 flex items-center justify-center rounded-lg transition-all group relative"
			style:background={active ? 'var(--palais-gold-glow)' : 'transparent'}
			style:color={active ? 'var(--palais-gold)' : 'var(--palais-text-muted)'}
			style:box-shadow={active ? 'var(--palais-glow-sm)' : 'none'}
		>
			<item.icon size={20} />
			<span class="absolute left-14 px-2 py-1 rounded text-xs opacity-0 group-hover:opacity-100 pointer-events-none whitespace-nowrap transition-opacity"
				style="background: var(--palais-surface); color: var(--palais-text); border: 1px solid var(--palais-border);">
				{item.label}
			</span>
		</a>
	{/each}
</aside>
