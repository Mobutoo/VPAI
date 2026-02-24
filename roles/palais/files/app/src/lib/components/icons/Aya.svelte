<script lang="ts">
	let { size = 24, class: className = '' }: { size?: number; class?: string } = $props();
</script>

<!-- Aya: endurance — fern fronds, vertical growth -->
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
	<path d="M12 20V4" />
	<path d="M12 16c-3 0-5-2-5-5" />
	<path d="M12 12c-3 0-5-2-5-5" />
	<path d="M12 16c3 0 5-2 5-5" />
	<path d="M12 12c3 0 5-2 5-5" />
	<path d="M12 8c0-2 0-3 0-4" />
</svg>
