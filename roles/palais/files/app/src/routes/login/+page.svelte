<script lang="ts">
	let password = $state('');
	let error = $state('');
	let loading = $state(false);

	async function handleLogin(e: Event) {
		e.preventDefault();
		loading = true;
		error = '';

		const res = await fetch('/api/auth/login', {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ password })
		});

		if (res.ok) {
			window.location.href = '/';
		} else {
			error = 'Invalid password';
		}
		loading = false;
	}
</script>

<div class="min-h-screen flex items-center justify-center" style="background: var(--palais-bg);">
	<div class="w-full max-w-sm p-8 rounded-lg" style="background: var(--palais-surface); border: 1px solid var(--palais-border);">
		<h1 class="text-2xl font-bold text-center mb-8" style="color: var(--palais-gold); font-family: 'Orbitron', sans-serif;">
			PALAIS
		</h1>
		<form onsubmit={handleLogin}>
			<input
				type="password"
				bind:value={password}
				placeholder="Enter password"
				class="w-full px-4 py-3 rounded-md mb-4 outline-none focus:ring-2"
				style="background: var(--palais-bg); color: var(--palais-text); border: 1px solid var(--palais-border);"
			/>
			{#if error}
				<p class="text-sm mb-4" style="color: var(--palais-red);">{error}</p>
			{/if}
			<button
				type="submit"
				disabled={loading}
				class="w-full py-3 rounded-md font-semibold transition-all"
				style="background: var(--palais-gold); color: var(--palais-bg);"
			>
				{loading ? '...' : 'Enter'}
			</button>
		</form>
	</div>
</div>
