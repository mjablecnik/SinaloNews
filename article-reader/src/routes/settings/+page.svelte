<script lang="ts">
	import { get } from 'svelte/store';
	import { settings } from '$lib/stores/settings';
	import { goto } from '$app/navigation';

	const current = get(settings);
	let minScore = $state(current.minScore);
	let daysBack = $state(current.daysBack);

	function save(e: SubmitEvent) {
		e.preventDefault();
		settings.set({ minScore, daysBack });
		goto('/');
	}
</script>

<main class="container mx-auto max-w-md px-4 py-8">
	<div class="mb-6 flex items-center gap-3">
		<button onclick={() => history.back()} class="text-sm text-gray-500 hover:text-gray-700">
			← Back
		</button>
		<h1 class="text-xl font-bold text-gray-900">Settings</h1>
	</div>

	<form onsubmit={save} class="space-y-6">
		<div>
			<label for="minScore" class="mb-1 block text-sm font-medium text-gray-700">
				Minimum Importance Score: {minScore}
			</label>
			<input
				id="minScore"
				type="range"
				min="0"
				max="10"
				step="1"
				bind:value={minScore}
				class="w-full accent-blue-600"
			/>
			<div class="mt-1 flex justify-between text-xs text-gray-400">
				<span>0</span>
				<span>10</span>
			</div>
		</div>

		<div>
			<label for="daysBack" class="mb-1 block text-sm font-medium text-gray-700">Days Back</label>
			<input
				id="daysBack"
				type="number"
				min="1"
				bind:value={daysBack}
				class="w-full rounded border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
			/>
		</div>

		<button type="submit" class="w-full rounded bg-blue-600 px-4 py-2 text-white hover:bg-blue-700">
			Save Settings
		</button>
	</form>
</main>
