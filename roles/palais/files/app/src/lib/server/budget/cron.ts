import { fetchLiteLLMSpend } from './litellm';
import { fetchProviderUsage } from './providers';

let litellmTimer: ReturnType<typeof setInterval> | null = null;
let providerTimer: ReturnType<typeof setInterval> | null = null;
let started = false;

const LITELLM_INTERVAL_MS = 15 * 60 * 1000;  // 15 minutes
const PROVIDER_INTERVAL_MS = 60 * 60 * 1000; // 1 hour

/**
 * Start budget cron jobs.
 * Safe to call multiple times — idempotent.
 */
export function startBudgetCron(): void {
	if (started) return;
	started = true;

	console.log('[Budget] Starting cron — LiteLLM every 15min, providers every 1h');

	// Immediate first run
	fetchLiteLLMSpend().catch(console.error);
	fetchProviderUsage().catch(console.error);

	// Recurring
	litellmTimer = setInterval(() => {
		fetchLiteLLMSpend().catch(console.error);
	}, LITELLM_INTERVAL_MS);

	providerTimer = setInterval(() => {
		fetchProviderUsage().catch(console.error);
	}, PROVIDER_INTERVAL_MS);
}

export function stopBudgetCron(): void {
	if (litellmTimer) { clearInterval(litellmTimer); litellmTimer = null; }
	if (providerTimer) { clearInterval(providerTimer); providerTimer = null; }
	started = false;
}
