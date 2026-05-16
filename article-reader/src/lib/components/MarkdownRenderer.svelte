<script lang="ts">
	import { marked } from 'marked';

	marked.use({
		renderer: {
			link({ href, text }) {
				return `<a href="${href}" target="_blank" rel="noopener noreferrer" class="text-blue-600 underline">${text}</a>`;
			}
		}
	});

	interface Props {
		content: string;
	}

	let { content }: Props = $props();

	let html = $derived(marked.parse(content) as string);
</script>

<div class="prose prose-sm max-w-none text-gray-800">
	<!-- eslint-disable-next-line svelte/no-at-html-tags -->
	{@html html}
</div>
