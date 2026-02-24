<script lang="ts">
	let { size = 24, class: className = '' }: { size?: number; class?: string } = $props();
</script>

<!-- Akoma: patience/heart — stylized heart shape -->
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
	<path d="M12 20.5C12 20.5 3 14.5 3 9a4.5 4.5 0 0 1 9-1A4.5 4.5 0 0 1 21 9c0 5.5-9 11.5-9 11.5z" />
	<path d="M12 8v4M10 10h4" />
</svg>
