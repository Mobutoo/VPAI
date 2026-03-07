import { env } from '$env/dynamic/private';

interface DeployRequest {
    workspaceSlug: string;
    version: string;
    targetServer: string;
    playbook: string;
    extraVars?: Record<string, string>;
}

interface DeployCallbackPayload {
    deploymentId: number;
    stepName: string;
    status: 'running' | 'success' | 'failed';
    output?: string;
    error?: string;
}

export async function triggerDeploy(request: DeployRequest): Promise<{ executionId: string }> {
    const webhookBase = env.N8N_WEBHOOK_BASE;
    if (!webhookBase) throw new Error('N8N_WEBHOOK_BASE not configured');

    const url = `${webhookBase}/palais-deploy`;

    const res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            action: 'deploy',
            workspace: request.workspaceSlug,
            version: request.version,
            target: request.targetServer,
            playbook: request.playbook,
            extra_vars: request.extraVars ?? {},
            callback_url: `${env.PALAIS_URL}/api/v2/deploy/callback`,
        }),
    });

    if (!res.ok) {
        const text = await res.text();
        throw new Error(`n8n webhook error ${res.status}: ${text}`);
    }

    const data = await res.json();
    return { executionId: data.executionId ?? data.id ?? 'unknown' };
}

export async function triggerProvision(opts: {
    serverName: string;
    serverType: string;
    location: string;
    image: string;
}): Promise<{ executionId: string }> {
    const webhookBase = env.N8N_WEBHOOK_BASE;
    if (!webhookBase) throw new Error('N8N_WEBHOOK_BASE not configured');

    const url = `${webhookBase}/palais-provision`;

    const res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            action: 'provision',
            server_name: opts.serverName,
            server_type: opts.serverType,
            location: opts.location,
            image: opts.image,
            callback_url: `${env.PALAIS_URL}/api/v2/deploy/callback`,
        }),
    });

    if (!res.ok) {
        const text = await res.text();
        throw new Error(`n8n webhook error ${res.status}: ${text}`);
    }

    const data = await res.json();
    return { executionId: data.executionId ?? data.id ?? 'unknown' };
}

export type { DeployRequest, DeployCallbackPayload };
