import "./globals.css";
import { Analytics } from "@vercel/analytics/next";
import VisitTracker from "./VisitTracker";

export const metadata = { title: "Universal SCADA" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <VisitTracker />
        {children}
        <Analytics />
      </body>
    </html>
  );
}
