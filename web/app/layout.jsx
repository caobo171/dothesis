import "./globals.css";
import { AuthProvider } from "./lib/auth-context";

export const metadata = {
  title: "DoThesis — AI Thesis Agent",
  description:
    "Draft master's theses and PhD dissertations with 19 specialized AI agents and 100% verified citations.",
  icons: { icon: "/favicon.png" },
};

export const viewport = {
  width: 1440,
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
