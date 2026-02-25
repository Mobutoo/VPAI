import { env } from '$env/dynamic/private';
import { db } from './index';
import { nodes, agents } from './schema';

/**
 * Seed the 3 infrastructure nodes.
 * Idempotent — ON CONFLICT DO UPDATE to refresh IPs and descriptions.
 * Called once at startup from hooks.server.ts.
 */
export async function seedNodes(): Promise<void> {
	const nodesSeed = [
		{
			name: 'sese-ai',
			tailscaleIp: env.SESE_AI_TAILSCALE_IP || null,
			localIp: env.SESE_AI_LOCAL_IP || null,
			description: 'OVH VPS 8 Go — Cerveau IA (OpenClaw, LiteLLM, n8n)'
		},
		{
			name: 'rpi5',
			tailscaleIp: env.WORKSTATION_PI_TAILSCALE_IP || null,
			localIp: env.WORKSTATION_PI_LOCAL_IP || null,
			description: 'Raspberry Pi 5 16 Go — Mission Control (Claude Code)'
		},
		{
			name: 'seko-vpn',
			tailscaleIp: env.SEKO_VPN_TAILSCALE_IP || null,
			localIp: env.SEKO_VPN_LOCAL_IP || null,
			description: 'Ionos VPS — Hub VPN Singa (Headscale) + Backup'
		}
	];

	for (const node of nodesSeed) {
		await db
			.insert(nodes)
			.values(node)
			.onConflictDoUpdate({
				target: nodes.name,
				set: {
					tailscaleIp: node.tailscaleIp,
					localIp: node.localIp,
					description: node.description
				}
			});
	}
}

/**
 * Seed agent bio snippets from IDENTITY files.
 * Idempotent — ON CONFLICT DO UPDATE SET bio only (preserves OpenClaw data).
 * Called once at startup from hooks.server.ts.
 */
export async function seedAgentBios(): Promise<void> {
	const bios: { id: string; name: string; bio: string }[] = [
		{
			id: 'main',
			name: 'Général d\'État-Major',
			bio: 'Stratège en chef du Palais. Coordonne les agents, arbitre les priorités, garde le cap. « Ça n\'a pas été facile, cher ami. »'
		},
		{
			id: 'cfo',
			name: 'CFO',
			bio: 'Gardien du budget $5/jour. Surveille chaque token dépensé et déclenche le mode éco avant que les caisses ne sonnent creux.'
		},
		{
			id: 'builder',
			name: 'Imhotep',
			bio: 'Architecte du code. Construit pour durer, documente pour transmettre. « Ce qui est fait, n\'est plus à faire. »'
		},
		{
			id: 'tutor',
			name: 'Piccolo',
			bio: 'Maître de l\'apprentissage. Exige l\'excellence par l\'entraînement. « On s\'entraîne dur pour que l\'examen soit facile. »'
		},
		{
			id: 'artist',
			name: 'JM Basquiat',
			bio: 'Créateur d\'images et de mondes visuels. Saisit l\'émotion avant la technique. « L\'image précède la compréhension. »'
		},
		{
			id: 'messenger',
			name: 'Hermès',
			bio: 'Passeur de messages entre les mondes. Rapide, précis, jamais en retard.'
		},
		{
			id: 'writer',
			name: 'Scribe',
			bio: 'Donne forme aux idées en mots. Transforme le bruit en signal, la pensée en texte.'
		},
		{
			id: 'explorer',
			name: 'Ibn Battuta',
			bio: 'Chercheur insatiable. Parcourt le web, les archives et les API pour ramener la connaissance manquante.'
		},
		{
			id: 'maintainer',
			name: 'Gardien',
			bio: 'Veille sur l\'infrastructure. Détecte les anomalies, corrige les dérives, maintient la flotte en ordre.'
		},
		{
			id: 'concierge',
			name: 'Concierge',
			bio: 'Premier contact, dernier recours. Accueille, oriente, et s\'assure que personne ne reste sans réponse.'
		}
	];

	for (const agent of bios) {
		// Insert stub if not exists, then update bio (preserves OpenClaw-managed fields)
		await db
			.insert(agents)
			.values({ id: agent.id, name: agent.name, bio: agent.bio })
			.onConflictDoUpdate({
				target: agents.id,
				set: { bio: agent.bio }
			});
	}
}
