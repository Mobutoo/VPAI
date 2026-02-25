<script lang="ts">
	let { size = 24, class: className = '' }: { size?: number; class?: string } = $props();
</script>

<!-- Bese Saka: creative palette / abundance — diamond with inner gem -->
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
	<path d="M12 3L3 9l9 12 9-12z" />
	<path d="M3 9h18" />
	<path d="M12 3l-4 6 4 9 4-9z" />
</svg>
