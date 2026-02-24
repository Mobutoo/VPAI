<script lang="ts">
	let { size = 24, class: className = '' }: { size?: number; class?: string } = $props();
</script>

<!-- Gye Nyame: omnipotence — stylized cosmic spiral/eye -->
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
	<circle cx="12" cy="12" r="9" />
	<circle cx="12" cy="12" r="4" />
	<path d="M12 3v3M12 18v3M3 12h3M18 12h3" />
	<path d="M12 8c0-1.1.9-2 2-2s2 .9 2 2-.9 2-2 2-2-.9-2-2z" fill="currentColor" stroke="none" />
</svg>
