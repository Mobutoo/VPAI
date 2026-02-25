import { env } from '$env/dynamic/private';

export interface ChatMessage {
	role: 'system' | 'user' | 'assistant';
	content: string;
}

export async function chatCompletion(messages: ChatMessage[]): Promise<string> {
	const res = await fetch(`${env.LITELLM_URL}/v1/chat/completions`, {
		method: 'POST',
		headers: {
			'Content-Type': 'application/json',
			'Authorization': `Bearer ${env.LITELLM_KEY}`
		},
		body: JSON.stringify({
			model: 'gpt-4o-mini',
			messages,
			max_tokens: 1000
		})
	});

	if (!res.ok) {
		const text = await res.text();
		throw new Error(`LiteLLM error ${res.status}: ${text}`);
	}

	const data = await res.json();
	return data.choices?.[0]?.message?.content ?? '';
}
