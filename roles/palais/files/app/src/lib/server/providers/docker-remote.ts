import { Client } from 'ssh2';
import { env } from '$env/dynamic/private';

interface ContainerInfo {
    id: string;
    name: string;
    image: string;
    status: string;
    state: string;
    ports: string;
    created: string;
}

interface ContainerStats {
    name: string;
    cpuPercent: number;
    memUsageMb: number;
    memLimitMb: number;
    memPercent: number;
    netIO: string;
    blockIO: string;
}

interface ServerConnection {
    host: string;
    port: number;
    username: string;
    privateKeyPath?: string;
}

function parseServerConnections(): Map<string, ServerConnection> {
    const raw = env.DOCKER_SSH_SERVERS ?? '';
    const servers = new Map<string, ServerConnection>();

    for (const entry of raw.split(',').filter(Boolean)) {
        const [name, host, portStr] = entry.split(':');
        if (name && host) {
            servers.set(name, {
                host,
                port: parseInt(portStr ?? '22', 10),
                username: env.DOCKER_SSH_USER ?? 'mobuone',
                privateKeyPath: env.DOCKER_SSH_KEY_PATH ?? '/data/ssh/deploy-key',
            });
        }
    }

    return servers;
}

async function execSsh(server: ServerConnection, command: string): Promise<string> {
    const { readFileSync } = await import('fs');

    return new Promise((resolve, reject) => {
        const conn = new Client();
        let output = '';
        let errorOutput = '';

        const timeout = setTimeout(() => {
            conn.end();
            reject(new Error(`SSH command timed out after 30s: ${command}`));
        }, 30_000);

        conn.on('ready', () => {
            conn.exec(command, (err, stream) => {
                if (err) {
                    clearTimeout(timeout);
                    conn.end();
                    reject(err);
                    return;
                }

                stream.on('data', (data: Buffer) => { output += data.toString(); });
                stream.stderr.on('data', (data: Buffer) => { errorOutput += data.toString(); });
                stream.on('close', (code: number) => {
                    clearTimeout(timeout);
                    conn.end();
                    if (code !== 0) {
                        reject(new Error(`SSH command failed (exit ${code}): ${errorOutput || output}`));
                    } else {
                        resolve(output.trim());
                    }
                });
            });
        });

        conn.on('error', (err) => {
            clearTimeout(timeout);
            reject(new Error(`SSH connection error to ${server.host}: ${err.message}`));
        });

        conn.connect({
            host: server.host,
            port: server.port,
            username: server.username,
            privateKey: readFileSync(server.privateKeyPath ?? '/data/ssh/deploy-key'),
        });
    });
}

export async function listContainers(serverName: string): Promise<ContainerInfo[]> {
    const servers = parseServerConnections();
    const server = servers.get(serverName);
    if (!server) throw new Error(`Unknown server: ${serverName}`);

    // Use --format json (one JSON object per line, avoids Jinja2 template issues)
    const output = await execSsh(server, 'docker ps -a --format json');

    return output.split('\n').filter(Boolean).map(line => {
        const c = JSON.parse(line);
        return {
            id: c.ID,
            name: c.Names,
            image: c.Image,
            status: c.Status,
            state: c.State,
            ports: c.Ports,
            created: c.CreatedAt,
        };
    });
}

export async function getContainerStats(serverName: string): Promise<ContainerStats[]> {
    const servers = parseServerConnections();
    const server = servers.get(serverName);
    if (!server) throw new Error(`Unknown server: ${serverName}`);

    const output = await execSsh(server, 'docker stats --no-stream --format json');

    return output.split('\n').filter(Boolean).map(line => {
        const s = JSON.parse(line);
        return {
            name: s.Name,
            cpuPercent: parseFloat(s.CPUPerc?.replace('%', '') ?? '0'),
            memUsageMb: parseMemory(s.MemUsage?.split('/')[0]?.trim() ?? '0'),
            memLimitMb: parseMemory(s.MemUsage?.split('/')[1]?.trim() ?? '0'),
            memPercent: parseFloat(s.MemPerc?.replace('%', '') ?? '0'),
            netIO: s.NetIO ?? '0B / 0B',
            blockIO: s.BlockIO ?? '0B / 0B',
        };
    });
}

export async function controlContainer(
    serverName: string,
    containerName: string,
    action: 'start' | 'stop' | 'restart' | 'rm'
): Promise<string> {
    const servers = parseServerConnections();
    const server = servers.get(serverName);
    if (!server) throw new Error(`Unknown server: ${serverName}`);

    return execSsh(server, `docker ${action} ${containerName}`);
}

export async function getContainerLogs(
    serverName: string,
    containerName: string,
    tail: number = 100
): Promise<string> {
    const servers = parseServerConnections();
    const server = servers.get(serverName);
    if (!server) throw new Error(`Unknown server: ${serverName}`);

    return execSsh(server, `docker logs --tail ${tail} --timestamps ${containerName} 2>&1`);
}

export async function getSystemStats(serverName: string): Promise<{
    cpuPercent: number;
    ramUsedMb: number;
    ramTotalMb: number;
    diskUsedGb: number;
    diskTotalGb: number;
    loadAvg1m: number;
}> {
    const servers = parseServerConnections();
    const server = servers.get(serverName);
    if (!server) throw new Error(`Unknown server: ${serverName}`);

    const output = await execSsh(server, [
        "echo CPU=$(top -bn1 | grep 'Cpu(s)' | awk '{print $2}')",
        "free -m | awk '/Mem:/ {print \"RAM_USED=\"$3, \"RAM_TOTAL=\"$2}'",
        "df -BG / | awk 'NR==2 {gsub(/G/,\"\",$3); gsub(/G/,\"\",$2); print \"DISK_USED=\"$3, \"DISK_TOTAL=\"$2}'",
        "cat /proc/loadavg | awk '{print \"LOAD=\"$1}'"
    ].join(' && '));

    const vars: Record<string, string> = {};
    for (const line of output.split('\n')) {
        for (const pair of line.split(' ')) {
            const [k, v] = pair.split('=');
            if (k && v) vars[k] = v;
        }
    }

    return {
        cpuPercent: parseFloat(vars.CPU ?? '0'),
        ramUsedMb: parseInt(vars.RAM_USED ?? '0', 10),
        ramTotalMb: parseInt(vars.RAM_TOTAL ?? '0', 10),
        diskUsedGb: parseFloat(vars.DISK_USED ?? '0'),
        diskTotalGb: parseFloat(vars.DISK_TOTAL ?? '0'),
        loadAvg1m: parseFloat(vars.LOAD ?? '0'),
    };
}

function parseMemory(str: string): number {
    const num = parseFloat(str);
    if (str.includes('GiB')) return num * 1024;
    if (str.includes('MiB')) return num;
    if (str.includes('KiB')) return num / 1024;
    return num;
}

export function getConfiguredServers(): string[] {
    return Array.from(parseServerConnections().keys());
}

export type { ContainerInfo, ContainerStats, ServerConnection };
