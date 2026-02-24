<script lang="ts">
	let { size = 24, class: className = '' }: { size?: number; class?: string } = $props();
</script>

<!-- Sankofa: learn from past — bird looking back, heart shape -->
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
	<path d="M12 20c4.4 0 8-3.6 8-8S16.4 4 12 4 4 7.6 4 12s3.6 8 8 8z" />
	<path d="M9 9c0-1.7 1.3-3 3-3" />
	<path d="M15 9c0-1.7-1.3-3-3-3" />
	<path d="M9 9l3 3 3-3" />
	<circle cx="12" cy="15" r="1.5" fill="currentColor" stroke="none" />
</svg>
