import { ok, err } from '$lib/server/api/response';
import type { RequestHandler } from './$types';
import { Client } from 'ssh2';
import { env } from '$env/dynamic/private';
import { readFileSync } from 'fs';

const DANGEROUS_PATTERNS = [
    'rm -rf /',
    'shutdown',
    'reboot',
    'halt',
    'init 0',
    'init 6',
    'mkfs',
    'dd if=',
    ':(){',
    'fork bomb',
    '> /dev/sda',
    'chmod -R 777 /',
];

function parseServers(): Map<string, { host: string; port: number }> {
    const raw = env.DOCKER_SSH_SERVERS ?? '';
    const map = new Map<string, { host: string; port: number }>();
    for (const entry of raw.split(',').filter(Boolean)) {
        const [name, host, portStr] = entry.split(':');
        if (name && host) {
            map.set(name, { host, port: parseInt(portStr ?? '22', 10) });
        }
    }
    return map;
}

function isSafe(command: string): boolean {
    const lower = command.toLowerCase();
    return !DANGEROUS_PATTERNS.some(p => lower.includes(p));
}

export const POST: RequestHandler = async ({ request }) => {
    try {
        const body = await request.json();
        const { server, command } = body;

        if (!server || !command) {
            return err('Missing required fields: server, command', 400);
        }

        if (typeof command !== 'string' || command.length > 2000) {
            return err('Command must be a string under 2000 characters', 400);
        }

        if (!isSafe(command)) {
            return err('Command rejected for safety', 403);
        }

        const servers = parseServers();
        const serverConfig = servers.get(server);
        if (!serverConfig) {
            return err(`Unknown server: ${server}`, 404);
        }

        const output = await execCommand(serverConfig, command);
        return ok({ output });
    } catch (e) {
        return err(e instanceof Error ? e.message : 'Unknown error');
    }
};

function execCommand(
    server: { host: string; port: number },
    command: string
): Promise<string> {
    return new Promise((resolve, reject) => {
        const conn = new Client();
        let output = '';
        let errorOutput = '';

        const timeout = setTimeout(() => {
            conn.end();
            reject(new Error('Command timed out after 30 seconds'));
        }, 30_000);

        conn.on('ready', () => {
            conn.exec(command, (execErr, stream) => {
                if (execErr) {
                    clearTimeout(timeout);
                    conn.end();
                    reject(execErr);
                    return;
                }

                stream.on('data', (data: Buffer) => { output += data.toString(); });
                stream.stderr.on('data', (data: Buffer) => { errorOutput += data.toString(); });
                stream.on('close', (code: number) => {
                    clearTimeout(timeout);
                    conn.end();
                    if (code !== 0 && errorOutput) {
                        resolve(`[exit ${code}]\n${errorOutput}\n${output}`.trim());
                    } else {
                        resolve(output.trim());
                    }
                });
            });
        });

        conn.on('error', (connErr) => {
            clearTimeout(timeout);
            reject(new Error(`SSH connection error: ${connErr.message}`));
        });

        const keyPath = env.DOCKER_SSH_KEY_PATH ?? '/data/ssh/deploy-key';
        conn.connect({
            host: server.host,
            port: server.port,
            username: env.DOCKER_SSH_USER ?? 'mobuone',
            privateKey: readFileSync(keyPath),
        });
    });
}
