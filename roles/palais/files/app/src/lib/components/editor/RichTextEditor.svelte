<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { Editor } from '@tiptap/core';
	import StarterKit from '@tiptap/starter-kit';
	import Placeholder from '@tiptap/extension-placeholder';

	let {
		content = '',
		placeholder = 'Écrivez ici...',
		onupdate
	}: {
		content?: string;
		placeholder?: string;
		onupdate?: (html: string) => void;
	} = $props();

	let element: HTMLDivElement;
	let editor: Editor | undefined;

	onMount(() => {
		editor = new Editor({
			element,
			extensions: [
				StarterKit,
				Placeholder.configure({ placeholder })
			],
			content,
			onUpdate: ({ editor: e }) => {
				onupdate?.(e.getHTML());
			}
		});
	});

	onDestroy(() => {
		editor?.destroy();
	});
</script>

<div
	bind:this={element}
	class="prose prose-invert max-w-none min-h-[100px] p-3 rounded-lg outline-none"
	style="background: var(--palais-bg); border: 1px solid var(--palais-border); color: var(--palais-text); font-family: 'Inter', sans-serif; font-size: 0.875rem;"
></div>

<style>
	:global(.ProseMirror p.is-editor-empty:first-child::before) {
		content: attr(data-placeholder);
		float: left;
		color: var(--palais-text-muted);
		pointer-events: none;
		height: 0;
	}
	:global(.ProseMirror) {
		outline: none;
	}
	:global(.ProseMirror p) {
		margin: 0.25rem 0;
	}
	:global(.ProseMirror ul, .ProseMirror ol) {
		padding-left: 1.5rem;
	}
	:global(.ProseMirror code) {
		background: rgba(212, 168, 67, 0.1);
		color: var(--palais-gold);
		padding: 0.1em 0.3em;
		border-radius: 3px;
		font-family: 'JetBrains Mono', monospace;
		font-size: 0.85em;
	}
	:global(.ProseMirror pre) {
		background: var(--palais-bg);
		border: 1px solid var(--palais-border);
		border-radius: 6px;
		padding: 0.75rem;
		font-family: 'JetBrains Mono', monospace;
		font-size: 0.8rem;
	}
</style>
