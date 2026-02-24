<script lang="ts">
	let { size = 24, class: className = '' }: { size?: number; class?: string } = $props();
</script>

<!-- Nkyinkyim: adaptability — sinuous S-curve path, cross-like -->
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
	<path d="M4 12c0-2.2 1.8-4 4-4h8c2.2 0 4 1.8 4 4s-1.8 4-4 4H8" />
	<path d="M8 16c-2.2 0-4-1.8-4-4" />
	<path d="M12 4v16M4 8h4M16 16h4" />
</svg>
