import { env } from '$env/dynamic/private';

const LITELLM_URL = env.LITELLM_URL ?? 'http://litellm:4000';
const LITELLM_KEY = env.LITELLM_KEY ?? '';

/**
 * Fetch total global spend from LiteLLM for today.
 * Returns the total spend amount (snapshot persistence removed in v2).
 */
export async function fetchLiteLLMSpend(): Promise<void> {
	try {
		const headers = {
			Authorization: `Bearer ${LITELLM_KEY}`,
			'Content-Type': 'application/json'
		};

		const now = new Date();
		const startOfDay = new Date(now);
		startOfDay.setHours(0, 0, 0, 0);

		let totalSpend = 0;

		try {
			const res = await fetch(
				`${LITELLM_URL}/global/spend/report?start_date=${startOfDay.toISOString()}&end_date=${now.toISOString()}`,
				{ headers }
			);
			if (res.ok) {
				const data = await res.json();
				if (Array.isArray(data)) {
					for (const item of data) {
						totalSpend += item.spend ?? 0;
					}
				} else if (typeof data === 'object' && data !== null) {
					totalSpend = data.spend ?? data.total_spend ?? 0;
				}
			}
		} catch {
			const res2 = await fetch(`${LITELLM_URL}/spend`, { headers });
			if (res2.ok) {
				const data2 = await res2.json();
				totalSpend = data2.spend ?? data2.total ?? 0;
			}
		}

		console.log(`[Budget] LiteLLM spend today: $${totalSpend.toFixed(4)}`);
	} catch (err) {
		console.error('[Budget] LiteLLM spend fetch error:', err);
	}
}

/**
 * Fetch per-model spend breakdown from LiteLLM spend logs.
 */
export async function getLiteLLMSpendByModel(): Promise<
	Array<{ model: string; provider: string; spend: number; tokens: number; requests: number }>
> {
	try {
		const headers = { Authorization: `Bearer ${LITELLM_KEY}` };
		const now = new Date();
		const startOfDay = new Date(now);
		startOfDay.setHours(0, 0, 0, 0);

		const res = await fetch(
			`${LITELLM_URL}/global/spend/report?start_date=${startOfDay.toISOString()}&end_date=${now.toISOString()}`,
			{ headers }
		);

		if (!res.ok) return [];
		const data = await res.json();
		if (!Array.isArray(data)) return [];

		return data.map((item: Record<string, unknown>) => ({
			model: String(item.model ?? 'unknown'),
			provider: String(item.provider ?? deriveProvider(String(item.model ?? ''))),
			spend: Number(item.spend ?? 0),
			tokens: Number(item.total_tokens ?? 0),
			requests: Number(item.request_count ?? 0)
		}));
	} catch {
		return [];
	}
}

function deriveProvider(model: string): string {
	if (model.startsWith('gpt') || model.startsWith('o1') || model.startsWith('o3')) return 'openai';
	if (model.startsWith('claude')) return 'anthropic';
	if (model.includes('deepseek') || model.includes('qwen') || model.includes('mistral'))
		return 'openrouter';
	return 'unknown';
}
