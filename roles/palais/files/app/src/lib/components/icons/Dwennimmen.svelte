<script lang="ts">
	let { size = 24, class: className = '' }: { size?: number; class?: string } = $props();
</script>

<!-- Dwennimmen: humility + strength — ram horns, four-part symmetry -->
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
	<circle cx="12" cy="12" r="2.5" />
	<path d="M12 9.5C12 7 10 5 8 5s-4 2-4 4 1.5 3 3 3" />
	<path d="M12 9.5C12 7 14 5 16 5s4 2 4 4-1.5 3-3 3" />
	<path d="M12 14.5C12 17 10 19 8 19s-4-2-4-4 1.5-3 3-3" />
	<path d="M12 14.5C12 17 14 19 16 19s4-2 4-4-1.5-3-3-3" />
</svg>
