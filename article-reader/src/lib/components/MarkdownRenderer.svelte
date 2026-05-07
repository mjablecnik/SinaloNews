<script lang="ts">
	import { marked } from 'marked';

	interface Props {
		content: string;
	}

	let { content }: Props = $props();

	let html = $derived(marked(content) as string);
</script>

<div class="prose prose-sm max-w-none text-gray-800">
	<!-- eslint-disable-next-line svelte/no-at-html-tags -->
	{@html html}
</div>
