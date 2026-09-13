import type { Metadata } from "next";
import "./globals.css";
import { OnboardingGate } from "@/components/onboarding-gate";
import { Providers } from "./providers";

export const metadata: Metadata = {
  title: "MiNorte",
  description: "Tu centro financiero inteligente de Banorte",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="es" suppressHydrationWarning>
      <body className="min-h-screen bg-background text-foreground antialiased">
        <Providers>
          <OnboardingGate>{children}</OnboardingGate>
        </Providers>
      </body>
    </html>
  );
}
