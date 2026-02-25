import { env } from '$env/dynamic/private';
import { db } from '$lib/server/db';
import { budgetSnapshots } from '$lib/server/db/schema';

/**
 * Fetch direct provider usage (not routed through LiteLLM).
 * Delta = provider_total - litellm_total = calls made directly.
 */
export async function fetchProviderUsage(): Promise<void> {
	await Promise.allSettled([
		fetchOpenRouterCredits(),
		fetchOpenAIUsage(),
		fetchAnthropicUsage()
	]);
}

// ── OpenRouter ────────────────────────────────────────────────────────────────
// GET /api/v1/auth/key — returns credits_used, limit, etc.
async function fetchOpenRouterCredits(): Promise<void> {
	const key = env.OPENROUTER_API_KEY;
	if (!key) return;

	try {
		const res = await fetch('https://openrouter.ai/api/v1/auth/key', {
			headers: { Authorization: `Bearer ${key}` }
		});
		if (!res.ok) return;

		const data = await res.json();
		// data.data.usage = total credits consumed (USD)
		const usage = data?.data?.usage ?? 0;

		await db.insert(budgetSnapshots).values({
			date: new Date(),
			source: 'openrouter_direct',
			provider: 'openrouter',
			spendAmount: usage,
			tokenCount: 0,
			requestCount: 0
		});
	} catch (err) {
		console.error('[Budget] OpenRouter fetch error:', err);
	}
}

// ── OpenAI ────────────────────────────────────────────────────────────────────
// GET /v1/organization/usage/completions — requires org-level key
async function fetchOpenAIUsage(): Promise<void> {
	const key = env.OPENAI_API_KEY;
	if (!key) return;

	try {
		const now = new Date();
		const startOfDay = new Date(now);
		startOfDay.setHours(0, 0, 0, 0);

		// OpenAI usage API (requires project/org key)
		const res = await fetch(
			`https://api.openai.com/v1/organization/usage/completions?start_time=${Math.floor(startOfDay.getTime() / 1000)}&limit=100`,
			{
				headers: {
					Authorization: `Bearer ${key}`,
					'Content-Type': 'application/json'
				}
			}
		);

		if (!res.ok) return;
		const data = await res.json();

		// Sum up input/output tokens and estimated cost
		let totalInputTokens = 0;
		let totalOutputTokens = 0;
		let requestCount = 0;

		for (const bucket of data?.data ?? []) {
			for (const result of bucket?.results ?? []) {
				totalInputTokens += result.input_tokens ?? 0;
				totalOutputTokens += result.output_tokens ?? 0;
				requestCount += result.num_model_requests ?? 0;
			}
		}

		// Rough cost estimation if no direct cost field (GPT-4o rates)
		const estimatedCost = (totalInputTokens * 0.000005 + totalOutputTokens * 0.000015);

		await db.insert(budgetSnapshots).values({
			date: now,
			source: 'openai_direct',
			provider: 'openai',
			spendAmount: estimatedCost,
			tokenCount: totalInputTokens + totalOutputTokens,
			requestCount
		});
	} catch (err) {
		console.error('[Budget] OpenAI fetch error:', err);
	}
}

// ── Anthropic ─────────────────────────────────────────────────────────────────
// Usage API (if available on account tier)
async function fetchAnthropicUsage(): Promise<void> {
	const key = env.ANTHROPIC_API_KEY;
	if (!key) return;

	try {
		const now = new Date();
		const startOfDay = new Date(now);
		startOfDay.setHours(0, 0, 0, 0);

		const res = await fetch(
			`https://api.anthropic.com/v1/usage?start_date=${startOfDay.toISOString().split('T')[0]}`,
			{
				headers: {
					'x-api-key': key,
					'anthropic-version': '2023-06-01',
					'Content-Type': 'application/json'
				}
			}
		);

		if (!res.ok) return; // Usage API may not be available on all plans
		const data = await res.json();

		let totalTokens = 0;
		let estimatedCost = 0;
		for (const entry of data?.data ?? []) {
			totalTokens += (entry.input_tokens ?? 0) + (entry.output_tokens ?? 0);
			estimatedCost += entry.cost ?? 0;
		}

		if (totalTokens > 0) {
			await db.insert(budgetSnapshots).values({
				date: now,
				source: 'anthropic_direct',
				provider: 'anthropic',
				spendAmount: estimatedCost,
				tokenCount: totalTokens,
				requestCount: 0
			});
		}
	} catch (err) {
		console.error('[Budget] Anthropic fetch error (non-critical):', err);
	}
}
