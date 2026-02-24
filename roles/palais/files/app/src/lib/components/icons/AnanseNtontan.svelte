<script lang="ts">
	let { size = 24, class: className = '' }: { size?: number; class?: string } = $props();
</script>

<!-- Ananse Ntontan: spider web wisdom — concentric hexagons / web pattern -->
<svg
	width={size}
	height={size}
	viewBox="0 0 24 24"
	fill="none"
	stroke="currentColor"
	stroke-width="1.5"
	stroke-linecap="round"
	stroke-linejoin="round"
	class={className}
>
	<circle cx="12" cy="12" r="1.5" />
	<circle cx="12" cy="12" r="5" />
	<circle cx="12" cy="12" r="9" />
	<path d="M12 3v18M3 12h18" />
	<path d="M5.6 5.6l12.8 12.8M18.4 5.6 5.6 18.4" />
</svg>
