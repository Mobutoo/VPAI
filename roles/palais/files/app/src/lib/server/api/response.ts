import { json } from '@sveltejs/kit';

interface ApiMeta {
    total?: number;
    page?: number;
    limit?: number;
}

export function ok<T>(data: T, meta?: ApiMeta): Response {
    const body: { success: true; data: T; meta?: ApiMeta } = { success: true, data };
    if (meta) body.meta = meta;
    return json(body);
}

export function err(message: string, code: number = 500): Response {
    return json({ success: false, error: message, code }, { status: code });
}
