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

<aside class="sidebar-shell fixed left-0 top-0 h-screen w-16 flex flex-col items-center py-4 gap-1 z-50">

	<!-- Kuba textile pattern overlay -->
	<div class="absolute inset-0 kuba-pattern-bg opacity-[0.35] pointer-events-none" aria-hidden="true"></div>

	<!-- Scan line animation -->
	<div class="sidebar-scan-line pointer-events-none" aria-hidden="true"></div>

	<!-- Top gold gradient line -->
	<div class="relative z-10 w-full px-2 mb-1">
		<div class="h-px w-full bg-gradient-to-r from-transparent via-[var(--palais-gold)] to-transparent opacity-40"></div>
	</div>

	<!-- HUD identity ornament: diamond + system label -->
	<div class="relative z-10 flex flex-col items-center mb-3 gap-1">
		<!-- Adinkra-inspired diamond ornament -->
		<div class="sidebar-diamond" aria-hidden="true"></div>
		<!-- System identifier -->
		<div class="sidebar-hud-id">
			<span class="sidebar-bracket">[</span>
			<span class="sidebar-logo-letter">P</span>
			<span class="sidebar-bracket">]</span>
		</div>
		<!-- Blinking cursor line -->
		<div class="sidebar-cursor-blink" aria-hidden="true"></div>
	</div>

	<!-- Nav items -->
	<nav class="flex flex-col items-center gap-1 w-full px-2 flex-1">
		{#each nav as item, i (item.href)}
			{@const active = currentPath === item.href || (item.href !== '/' && currentPath.startsWith(item.href))}
			<!-- eslint-disable-next-line svelte/no-navigation-without-resolve -->
			<a
				href={item.href}
				class="sidebar-nav-item w-10 h-10 flex items-center justify-center rounded-lg transition-all group relative"
				class:sidebar-nav-active={active}
				style:--stagger-delay="{i * 55}ms"
				aria-label={item.label}
				title={item.label}
			>
				<!-- Active left border accent -->
				{#if active}
					<div class="sidebar-active-bar" aria-hidden="true"></div>
				{/if}

				<span class="sidebar-icon-wrap" class:sidebar-icon-active={active}>
					<item.icon size={20} />
				</span>

				<!-- Tooltip -->
				<span class="sidebar-tooltip">
					{item.label}
				</span>
			</a>
		{/each}
	</nav>

	<!-- Bottom gold gradient line -->
	<div class="relative z-10 w-full px-2 mt-1">
		<div class="h-px w-full bg-gradient-to-r from-transparent via-[var(--palais-gold)] to-transparent opacity-20"></div>
		<!-- Tiny version tag -->
		<div class="flex justify-center mt-1">
			<span class="sidebar-version-tag">v1</span>
		</div>
	</div>

</aside>

<style>
/* ── Sidebar shell: liquid glass heavy ──────────────────────────── */
.sidebar-shell {
	background: var(--palais-glass-bg-heavy);
	backdrop-filter: blur(28px) saturate(180%);
	-webkit-backdrop-filter: blur(28px) saturate(180%);
	border-right: 1px solid rgba(212, 168, 67, 0.12);
	box-shadow:
		var(--palais-glass-shadow),
		var(--palais-glass-glow-gold),
		inset -1px 0 0 rgba(212, 168, 67, 0.06);
}

/* ── Scan line that sweeps down periodically ───────────────────── */
/* @keyframes defined in app.css (global): scanLine, pulseGold */
@keyframes sidebarScan {
	0%   { top: -2px;  opacity: 0; }
	5%   { opacity: 1; }
	95%  { opacity: 1; }
	100% { top: 100%;  opacity: 0; }
}

.sidebar-scan-line {
	position: absolute;
	top: 0;
	left: 0;
	right: 0;
	height: 2px;
	background: linear-gradient(
		90deg,
		transparent 0%,
		rgba(212, 168, 67, 0.18) 30%,
		rgba(212, 168, 67, 0.35) 50%,
		rgba(212, 168, 67, 0.18) 70%,
		transparent 100%
	);
	opacity: 0;
	z-index: 20;
	animation: sidebarScan 8s ease-in-out infinite;
	animation-delay: 2s;
	pointer-events: none;
}

/* ── Diamond ornament (Adinkra-inspired geometry) ──────────────── */
.sidebar-diamond {
	width: 8px;
	height: 8px;
	background: var(--palais-gold);
	transform: rotate(45deg);
	opacity: 0.7;
	box-shadow: 0 0 6px rgba(212, 168, 67, 0.5);
	animation: pulseGold 3s ease-in-out infinite;
}

/* ── HUD System Identifier ─────────────────────────────────────── */
.sidebar-hud-id {
	display: flex;
	align-items: center;
	gap: 2px;
}

.sidebar-bracket {
	font-family: 'JetBrains Mono', monospace;
	font-size: 10px;
	color: rgba(212, 168, 67, 0.5);
	line-height: 1;
}

.sidebar-logo-letter {
	font-family: 'Orbitron', sans-serif;
	font-size: 13px;
	font-weight: 700;
	color: var(--palais-gold);
	letter-spacing: 0.12em;
	text-shadow: 0 0 10px rgba(212, 168, 67, 0.5);
}

/* ── Blinking cursor under logo ────────────────────────────────── */
.sidebar-cursor-blink {
	width: 10px;
	height: 1.5px;
	background: var(--palais-gold);
	animation: cursorBlink 1.2s step-end infinite;
	opacity: 0.6;
}

@keyframes cursorBlink {
	0%, 49% { opacity: 0.6; }
	50%, 100% { opacity: 0; }
}

/* ── Nav items: staggered reveal on load ───────────────────────── */
.sidebar-nav-item {
	animation: navItemReveal 0.35s ease-out both;
	animation-delay: var(--stagger-delay, 0ms);
}

@keyframes navItemReveal {
	from {
		opacity: 0;
		transform: translateX(-8px);
	}
	to {
		opacity: 1;
		transform: translateX(0);
	}
}

/* ── Active left border beam ───────────────────────────────────── */
.sidebar-active-bar {
	position: absolute;
	left: 0;
	top: 50%;
	transform: translateY(-50%);
	width: 2px;
	height: 60%;
	background: var(--palais-gold);
	border-radius: 0 2px 2px 0;
	box-shadow: 0 0 8px rgba(212, 168, 67, 0.6), 0 0 16px rgba(212, 168, 67, 0.3);
}

/* ── Active item background: gold light-beam sweep ─────────────── */
.sidebar-nav-active {
	background: linear-gradient(90deg, rgba(212, 168, 67, 0.13) 0%, transparent 100%);
	box-shadow: var(--palais-glow-sm);
}

/* ── Icon wrapper + active/hover glow ──────────────────────────── */
.sidebar-icon-wrap {
	display: flex;
	align-items: center;
	justify-content: center;
	color: var(--palais-text-muted);
	transition: color 200ms ease, filter 200ms ease, transform 150ms ease;
}

.sidebar-icon-active {
	color: var(--palais-gold);
	filter: drop-shadow(0 0 5px rgba(212, 168, 67, 0.55));
}

/* Hover: soft gold glow on icon */
.sidebar-nav-item:not(.sidebar-nav-active):hover .sidebar-icon-wrap {
	color: rgba(212, 168, 67, 0.75);
	filter: drop-shadow(0 0 4px rgba(212, 168, 67, 0.4));
	transform: scale(1.08);
}

/* Hover background: very faint gold tint */
.sidebar-nav-item:not(.sidebar-nav-active):hover {
	background: rgba(212, 168, 67, 0.05);
}

/* ── Tooltip ───────────────────────────────────────────────────── */
.sidebar-tooltip {
	position: absolute;
	left: calc(100% + 10px);
	top: 50%;
	transform: translateY(-50%);
	padding: 4px 8px;
	border-radius: 6px;
	font-size: 11px;
	font-family: 'JetBrains Mono', monospace;
	letter-spacing: 0.05em;
	white-space: nowrap;
	opacity: 0;
	pointer-events: none;
	transition: opacity 150ms ease;
	background: var(--palais-glass-bg-heavy);
	backdrop-filter: blur(12px);
	color: var(--palais-text);
	border: 1px solid rgba(212, 168, 67, 0.18);
	box-shadow: 0 4px 16px rgba(0, 0, 0, 0.4);
	z-index: 100;
}

.sidebar-nav-item:hover .sidebar-tooltip {
	opacity: 1;
}

/* ── Version tag ────────────────────────────────────────────────── */
.sidebar-version-tag {
	font-family: 'JetBrains Mono', monospace;
	font-size: 8px;
	color: rgba(212, 168, 67, 0.3);
	letter-spacing: 0.15em;
}
</style>
