import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Flash Studio — Help Center",
  description: "Support client, documentation, et statut des services",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="fr">
      <body style={{ margin: 0, fontFamily: "system-ui, sans-serif" }}>
        {children}
      </body>
    </html>
  );
}
