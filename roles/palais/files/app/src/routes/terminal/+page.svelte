<script lang="ts">
	import { onMount, tick } from 'svelte';

	// ── Server list (fetched from /api/v2/fleet) ───────────────────
	type ServerEntry = {
		id: number;
		name: string;
		slug: string;
		status: string | null;
	};

	let servers = $state<ServerEntry[]>([]);
	let serversLoading = $state(true);

	// ── Terminal state ─────────────────────────────────────────────
	type HistoryEntry = {
		id: number;
		server: string;
		command: string;
		output: string | null;
		error: string | null;
		ts: Date;
	};

	let selectedServer = $state('');
	let commandHistory = $state<HistoryEntry[]>([]);
	let currentInput = $state('');
	let isExecuting = $state(false);
	let historyNav = $state(-1); // -1 = not navigating
	let commandBuffer = $state(''); // Stores current draft while navigating

	let outputEl = $state<HTMLDivElement | null>(null);
	let inputEl = $state<HTMLInputElement | null>(null);

	// ── Load server list on mount ──────────────────────────────────
	onMount(async () => {
		try {
			const res = await fetch('/api/v2/fleet');
			if (res.ok) {
				const body = await res.json();
				servers = (body.data ?? []).map((s: ServerEntry & { latestMetric?: unknown }) => ({
					id: s.id,
					name: s.name,
					slug: s.slug,
					status: s.status
				}));
				if (servers.length > 0) {
					selectedServer = servers[0].slug;
				}
			}
		} catch {
			// fallback: empty server list shown in UI
		} finally {
			serversLoading = false;
		}
	});

	// ── Auto-scroll to bottom when history changes ─────────────────
	$effect(() => {
		void commandHistory.length; // track changes
		tick().then(() => {
			if (outputEl) {
				outputEl.scrollTop = outputEl.scrollHeight;
			}
		});
	});

	// ── Execute command ────────────────────────────────────────────
	async function executeCommand() {
		const cmd = currentInput.trim();
		if (!cmd || !selectedServer || isExecuting) return;

		// Clear command
		currentInput = '';
		historyNav = -1;
		commandBuffer = '';
		isExecuting = true;

		// Add pending entry
		const entry: HistoryEntry = {
			id: Date.now(),
			server: selectedServer,
			command: cmd,
			output: null,
			error: null,
			ts: new Date()
		};
		commandHistory = [...commandHistory, entry];

		try {
			const res = await fetch('/api/v2/terminal', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ server: selectedServer, command: cmd })
			});
			const body = await res.json();

			if (res.ok && body.data) {
				commandHistory = commandHistory.map(h =>
					h.id === entry.id
						? { ...h, output: body.data.output ?? '' }
						: h
				);
			} else {
				commandHistory = commandHistory.map(h =>
					h.id === entry.id
						? { ...h, error: body.error ?? `HTTP ${res.status}` }
						: h
				);
			}
		} catch {
			commandHistory = commandHistory.map(h =>
				h.id === entry.id
					? { ...h, error: 'Network error' }
					: h
			);
		} finally {
			isExecuting = false;
		}
	}

	// ── Keyboard shortcuts ─────────────────────────────────────────
	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Enter') {
			e.preventDefault();
			executeCommand();
			return;
		}

		// History navigation with up/down arrows
		const previousCommands = commandHistory.map(h => h.command);
		if (e.key === 'ArrowUp') {
			e.preventDefault();
			if (historyNav === -1) {
				commandBuffer = currentInput;
				historyNav = previousCommands.length - 1;
			} else if (historyNav > 0) {
				historyNav -= 1;
			}
			if (historyNav >= 0) {
				currentInput = previousCommands[historyNav] ?? '';
			}
			return;
		}
		if (e.key === 'ArrowDown') {
			e.preventDefault();
			if (historyNav === -1) return;
			historyNav += 1;
			if (historyNav >= previousCommands.length) {
				historyNav = -1;
				currentInput = commandBuffer;
			} else {
				currentInput = previousCommands[historyNav] ?? '';
			}
			return;
		}

		// Ctrl+L to clear
		if (e.key === 'l' && e.ctrlKey) {
			e.preventDefault();
			commandHistory = [];
			return;
		}
	}

	// ── Formatting ─────────────────────────────────────────────────
	function fmtTime(d: Date): string {
		return d.toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
	}

	function statusDot(status: string | null): string {
		if (status === 'online') return 'var(--palais-green)';
		if (status === 'busy') return 'var(--palais-gold)';
		if (status === 'degraded') return 'var(--palais-amber)';
		return 'rgba(138,138,154,0.5)';
	}

	function clearTerminal() {
		commandHistory = [];
	}
</script>

<svelte:head><title>Palais — Terminal</title></svelte:head>

<div style="min-height: 100vh; padding: 2rem 0; display: flex; flex-direction: column; gap: 0;">

	<!-- HUD HEADER -->
	<header class="flex flex-col gap-3 mb-6">
		<div class="flex items-start justify-between gap-4 flex-wrap">
			<div>
				<p class="text-xs tracking-[0.3em] uppercase mb-1"
					style="color: var(--palais-gold); opacity: 0.6; font-family: 'Orbitron', sans-serif;">
					SSH — REMOTE EXECUTION
				</p>
				<h1 class="text-3xl font-bold tracking-widest"
					style="color: var(--palais-gold); font-family: 'Orbitron', sans-serif; text-shadow: 0 0 24px rgba(212,168,67,0.35);">
					TERMINAL
				</h1>
			</div>

			<!-- Controls -->
			<div class="flex items-center gap-2">
				{#if commandHistory.length > 0}
					<button
						onclick={clearTerminal}
						style="
							padding: 6px 14px; border-radius: 6px; cursor: pointer;
							background: rgba(229,57,53,0.08); color: rgba(229,57,53,0.6);
							border: 1px solid rgba(229,57,53,0.2);
							font-family: 'Orbitron', sans-serif; font-size: 0.6rem; letter-spacing: 0.1em;
							transition: all 0.2s;
						"
						onmouseenter={(e) => { (e.currentTarget as HTMLElement).style.background = 'rgba(229,57,53,0.15)'; (e.currentTarget as HTMLElement).style.color = 'var(--palais-red)'; }}
						onmouseleave={(e) => { (e.currentTarget as HTMLElement).style.background = 'rgba(229,57,53,0.08)'; (e.currentTarget as HTMLElement).style.color = 'rgba(229,57,53,0.6)'; }}
					>
						CLEAR
					</button>
				{/if}
				<span class="text-xs" style="color: rgba(212,168,67,0.35); font-family: 'JetBrains Mono', monospace; font-size: 0.68rem;">
					Ctrl+L to clear
				</span>
			</div>
		</div>

		<!-- Gold separator -->
		<div style="height: 1px; background: linear-gradient(90deg, var(--palais-gold) 0%, rgba(212,168,67,0.08) 100%); opacity: 0.4;"></div>
	</header>

	<!-- Server tab bar -->
	<div class="mb-4">
		{#if serversLoading}
			<div class="flex gap-2">
				{#each [1, 2, 3] as _}
					<div style="width: 90px; height: 32px; border-radius: 6px; background: rgba(212,168,67,0.06); animation: pulseGold 1.5s ease-in-out infinite;"></div>
				{/each}
			</div>
		{:else if servers.length === 0}
			<p class="text-xs" style="color: var(--palais-text-muted); font-family: 'JetBrains Mono', monospace;">
				<span style="color: rgba(212,168,67,0.4);">// </span>No servers found. Add servers via Fleet.
			</p>
		{:else}
			<div class="flex gap-2 flex-wrap">
				{#each servers as server (server.id)}
					{@const isSelected = selectedServer === server.slug}
					<button
						onclick={() => { selectedServer = server.slug; }}
						style="
							padding: 6px 14px; border-radius: 6px; cursor: pointer;
							display: flex; align-items: center; gap: 6px;
							background: {isSelected ? 'rgba(212,168,67,0.15)' : 'rgba(212,168,67,0.05)'};
							color: {isSelected ? 'var(--palais-gold)' : 'var(--palais-text-muted)'};
							border: 1px solid {isSelected ? 'rgba(212,168,67,0.45)' : 'rgba(212,168,67,0.12)'};
							font-family: 'Orbitron', sans-serif; font-size: 0.65rem; letter-spacing: 0.1em;
							transition: all 0.15s;
							{isSelected ? 'box-shadow: 0 0 10px rgba(212,168,67,0.15);' : ''}
						"
					>
						<span class="w-1.5 h-1.5 rounded-full inline-block"
							style="background: {statusDot(server.status)}; box-shadow: {server.status === 'online' ? '0 0 5px rgba(76,175,80,0.5)' : 'none'};"></span>
						{server.name.toUpperCase()}
					</button>
				{/each}
			</div>
		{/if}
	</div>

	<!-- Terminal window -->
	<div class="glass-panel hud-bracket rounded-xl flex flex-col"
		style="
			border: 1px solid rgba(212,168,67,0.18);
			min-height: 480px;
			max-height: calc(100vh - 340px);
			flex: 1;
		">
		<span class="hud-bracket-bottom" style="display: block; height: 100%; display: flex; flex-direction: column;">

			<!-- Terminal title bar -->
			<div class="flex items-center justify-between px-4 py-2"
				style="border-bottom: 1px solid rgba(212,168,67,0.12); background: rgba(0,0,0,0.25);">
				<div class="flex items-center gap-2">
					<div class="flex gap-1.5">
						<span class="w-2.5 h-2.5 rounded-full inline-block" style="background: rgba(229,57,53,0.6);"></span>
						<span class="w-2.5 h-2.5 rounded-full inline-block" style="background: rgba(212,168,67,0.6);"></span>
						<span class="w-2.5 h-2.5 rounded-full inline-block" style="background: rgba(76,175,80,0.6);"></span>
					</div>
					<span class="text-xs" style="color: rgba(212,168,67,0.5); font-family: 'JetBrains Mono', monospace; font-size: 0.7rem; margin-left: 6px;">
						{selectedServer ? `${selectedServer} — SSH` : 'No server selected'}
					</span>
				</div>
				{#if isExecuting}
					<span class="text-xs" style="color: var(--palais-gold); font-family: 'JetBrains Mono', monospace; font-size: 0.68rem; animation: pulseGold 1s ease-in-out infinite;">
						EXECUTING...
					</span>
				{/if}
			</div>

			<!-- Output area -->
			<div
				bind:this={outputEl}
				style="
					flex: 1;
					overflow-y: auto;
					padding: 16px;
					background: rgba(0,0,0,0.45);
					font-family: 'JetBrains Mono', monospace;
					font-size: 0.78rem;
					line-height: 1.6;
					min-height: 360px;
				"
				onclick={() => inputEl?.focus()}
				role="log"
				aria-live="polite"
				aria-label="Terminal output"
			>
				{#if commandHistory.length === 0}
					<!-- Welcome message -->
					<div style="color: rgba(212,168,67,0.4);">
						<p>Palais Terminal — Afrofuturist HUD v2</p>
						<p>Connected to: <span style="color: var(--palais-cyan);">{selectedServer || 'select a server above'}</span></p>
						<p style="margin-top: 8px; color: rgba(212,168,67,0.3);">
							Type a command and press Enter. Use arrow keys for history.
						</p>
						<p style="color: rgba(212,168,67,0.25);">---</p>
					</div>
				{:else}
					{#each commandHistory as entry (entry.id)}
						<!-- Command line -->
						<div class="flex items-baseline gap-2 mt-3" style="first:mt-0">
							<span style="color: rgba(212,168,67,0.5); user-select: none;">[{fmtTime(entry.ts)}]</span>
							<span style="color: rgba(212,168,67,0.6); user-select: none;">{entry.server}</span>
							<span style="color: var(--palais-gold); user-select: none;">$</span>
							<span style="color: var(--palais-text); font-weight: 500;">{entry.command}</span>
						</div>

						<!-- Output or error -->
						{#if entry.output === null && entry.error === null}
							<!-- Loading indicator -->
							<div style="color: rgba(212,168,67,0.4); padding-left: 0; margin-top: 4px;">
								<span style="animation: pulseGold 0.8s ease-in-out infinite;">...</span>
							</div>
						{:else if entry.error}
							<div style="color: var(--palais-red); padding-left: 0; margin-top: 4px; white-space: pre-wrap; word-break: break-all;">
								{entry.error}
							</div>
						{:else if entry.output}
							<div style="color: var(--palais-green); padding-left: 0; margin-top: 4px; white-space: pre-wrap; word-break: break-all;">
								{entry.output}
							</div>
						{:else}
							<div style="color: rgba(76,175,80,0.4); margin-top: 4px; font-size: 0.72rem;">
								(no output)
							</div>
						{/if}
					{/each}
				{/if}
			</div>

			<!-- Command input -->
			<div style="border-top: 1px solid rgba(212,168,67,0.15); background: rgba(0,0,0,0.35);">
				<div class="flex items-center px-4 py-3 gap-3">
					<!-- Prompt indicator -->
					<span style="color: var(--palais-gold); font-family: 'JetBrains Mono', monospace; font-size: 0.85rem; user-select: none; flex-shrink: 0;">
						{selectedServer ? `${selectedServer} $` : '$'}
					</span>

					<!-- Input -->
					<input
						bind:this={inputEl}
						type="text"
						bind:value={currentInput}
						onkeydown={handleKeydown}
						disabled={!selectedServer || isExecuting}
						placeholder={selectedServer ? 'Enter command...' : 'Select a server first'}
						autocomplete="off"
						autocorrect="off"
						autocapitalize="off"
						spellcheck={false}
						style="
							flex: 1;
							background: transparent;
							border: none;
							outline: none;
							color: var(--palais-green);
							font-family: 'JetBrains Mono', monospace;
							font-size: 0.82rem;
							caret-color: var(--palais-gold);
							{(!selectedServer || isExecuting) ? 'opacity: 0.4; cursor: not-allowed;' : ''}
						"
					/>

					<!-- Execute button -->
					<button
						onclick={executeCommand}
						disabled={!selectedServer || isExecuting || !currentInput.trim()}
						style="
							padding: 5px 14px; border-radius: 4px; cursor: pointer; flex-shrink: 0;
							background: rgba(76,175,80,0.12); color: var(--palais-green);
							border: 1px solid rgba(76,175,80,0.3);
							font-family: 'Orbitron', sans-serif; font-size: 0.6rem; letter-spacing: 0.1em;
							transition: all 0.15s;
							{(!selectedServer || isExecuting || !currentInput.trim()) ? 'opacity: 0.3; cursor: not-allowed;' : ''}
						"
						onmouseenter={(e) => { (e.currentTarget as HTMLElement).style.background = 'rgba(76,175,80,0.22)'; }}
						onmouseleave={(e) => { (e.currentTarget as HTMLElement).style.background = 'rgba(76,175,80,0.12)'; }}
					>
						RUN
					</button>
				</div>
			</div>

		</span>
	</div>

	<!-- Hints -->
	<div class="flex gap-6 mt-3 flex-wrap">
		<span class="text-xs" style="color: rgba(212,168,67,0.3); font-family: 'JetBrains Mono', monospace; font-size: 0.65rem;">
			Enter — execute
		</span>
		<span class="text-xs" style="color: rgba(212,168,67,0.3); font-family: 'JetBrains Mono', monospace; font-size: 0.65rem;">
			Up/Down — history
		</span>
		<span class="text-xs" style="color: rgba(212,168,67,0.3); font-family: 'JetBrains Mono', monospace; font-size: 0.65rem;">
			Ctrl+L — clear
		</span>
	</div>
</div>
