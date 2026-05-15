"use client";

import { useEffect } from "react";

export default function VisitTracker() {
  useEffect(() => {
    async function trackVisit() {
      try {
        await fetch("/api/track", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            page_url: window.location.href,
            referrer: document.referrer,
            user_agent: navigator.userAgent,
          }),
        });
      } catch {
        // Tracking failure should not break website UI
      }
    }

    trackVisit();
  }, []);

  return null;
}
