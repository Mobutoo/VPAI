<script lang="ts">
	let { size = 24, class: className = '' }: { size?: number; class?: string } = $props();
</script>

<!-- Fawohodie: freedom — arrows radiating outward, liberation -->
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
	<circle cx="12" cy="12" r="3" />
	<path d="M12 5V3M12 21v-2M5 12H3M21 12h-2" />
	<path d="M7.1 7.1 5.7 5.7M18.3 18.3l-1.4-1.4M16.9 7.1l1.4-1.4M5.7 18.3l1.4-1.4" />
	<path d="M12 9V5l-1.5 2M12 5l1.5 2" />
</svg>
