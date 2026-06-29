const sections = [
  {
    title: "Notifications",
    description: "Events en temps reel de votre infrastructure",
    icon: "\ud83d\udd14",
    href: "/notifications",
  },
  {
    title: "Mes tickets",
    description: "Suivez vos demandes de support",
    icon: "\ud83c\udfab",
    href: "/tickets",
  },
  {
    title: "Documentation",
    description: "Base de connaissance et guides",
    icon: "\ud83d\udcda",
    href: "/docs",
  },
  {
    title: "Recherche",
    description: "Recherche intelligente dans toute la base",
    icon: "\ud83d\udd0d",
    href: "/search",
  },
  {
    title: "Statut",
    description: "Etat des services en temps reel",
    icon: "\ud83d\udcca",
    href: "/status",
  },
  {
    title: "Parametres",
    description: "Preferences de notification",
    icon: "\u2699\ufe0f",
    href: "/settings",
  },
];

export default function Home() {
  return (
    <main
      style={{
        maxWidth: "1200px",
        margin: "0 auto",
        padding: "2rem",
      }}
    >
      <header style={{ marginBottom: "3rem" }}>
        <h1 style={{ fontSize: "2rem", fontWeight: 700 }}>
          Flash Studio — Help Center
        </h1>
        <p style={{ color: "#666", fontSize: "1.1rem" }}>
          Support client, documentation, et statut de vos services
        </p>
      </header>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))",
          gap: "1.5rem",
        }}
      >
        {sections.map((section) => (
          <a
            key={section.href}
            href={section.href}
            style={{
              display: "block",
              padding: "1.5rem",
              border: "1px solid #e5e7eb",
              borderRadius: "12px",
              textDecoration: "none",
              color: "inherit",
              transition: "box-shadow 0.2s",
            }}
          >
            <div style={{ fontSize: "2rem", marginBottom: "0.5rem" }}>
              {section.icon}
            </div>
            <h2 style={{ fontSize: "1.25rem", fontWeight: 600, margin: 0 }}>
              {section.title}
            </h2>
            <p style={{ color: "#666", marginTop: "0.5rem" }}>
              {section.description}
            </p>
          </a>
        ))}
      </div>
    </main>
  );
}
