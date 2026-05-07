<script lang="ts">
	interface Props {
		message: string;
		onRetry?: () => void;
	}

	let { message, onRetry }: Props = $props();
</script>

<div class="flex flex-col items-center gap-4 py-12 text-center">
	<p class="text-red-600">{message}</p>
	{#if onRetry}
		<button
			onclick={onRetry}
			class="rounded bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700"
		>
			Try Again
		</button>
	{/if}
</div>
