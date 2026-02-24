import postgres from 'postgres';

const DATABASE_URL = process.env.DATABASE_URL;
if (!DATABASE_URL) {
	console.error('DATABASE_URL required');
	process.exit(1);
}

const sql = postgres(DATABASE_URL);

const agentsSeed = [
	{ id: 'concierge', name: 'Mobutoo', persona: "Chef d'orchestre — coordonne, delegue, supervise" },
	{ id: 'builder', name: 'Imhotep', persona: 'Architecte & Ingenieur — code, deploie, construit' },
	{ id: 'writer', name: 'Thot', persona: 'Redacteur & Scribe — contenu, docs, briefings' },
	{ id: 'artist', name: 'Basquiat', persona: 'Directeur Artistique — visuels, design, creative' },
	{ id: 'tutor', name: 'Piccolo', persona: 'Tuteur & Formateur — enseigne, explique, guide' },
	{ id: 'explorer', name: 'R2D2', persona: 'Explorateur & Recherche — explore, analyse, decouvre' },
	{ id: 'marketer', name: 'Marketer', persona: 'Marketing & Growth — campagnes, SEO, social' },
	{ id: 'cfo', name: 'CFO', persona: 'Directeur Financier — budget, couts, optimisation' },
	{ id: 'maintainer', name: 'Maintainer', persona: 'DevOps & Maintenance — infra, monitoring, fixes' },
	{ id: 'messenger', name: 'Hermes', persona: 'Pont inter-systemes — relais, communication, sync' },
];

async function seed() {
	console.log('Seeding agents...');

	// Create default workspace
	const [ws] = await sql`
		INSERT INTO workspaces (name, slug)
		VALUES ('Palais', 'palais')
		ON CONFLICT (slug) DO UPDATE SET name = 'Palais'
		RETURNING id
	`;

	// Seed agents
	for (const agent of agentsSeed) {
		await sql`
			INSERT INTO agents (id, name, persona, status)
			VALUES (${agent.id}, ${agent.name}, ${agent.persona}, 'offline')
			ON CONFLICT (id) DO UPDATE SET
				name = EXCLUDED.name,
				persona = EXCLUDED.persona
		`;
		console.log(`  + ${agent.name} (${agent.id})`);
	}

	console.log(`Seeded ${agentsSeed.length} agents + workspace (id=${ws.id})`);
	await sql.end();
}

seed().catch((err) => {
	console.error('Seed failed:', err);
	process.exit(1);
});
