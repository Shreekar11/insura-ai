"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { createClient } from "@/utils/supabase/client";
import { useSyncUser } from "@/hooks/use-users";

export default function AuthSuccessPage() {
  const router = useRouter();
  const [status, setStatus] = useState("Finalizing authentication...");
  const { mutateAsync: syncUser } = useSyncUser();

  useEffect(() => {
    const handleSuccess = async () => {
      const supabase = createClient();
      
      // Get the session that was just established by the callback
      const { data: { session }, error } = await supabase.auth.getSession();

      if (error || !session) {
        console.error("Auth success error:", error);
        router.push("/auth/auth-code-error");
        return;
      }

      try {
        const userData = {
          id: session.user.id,
          email: session.user.email,
          user_metadata: session.user.user_metadata,
        };

        // Store in localStorage as requested
        localStorage.setItem("user_data", JSON.stringify(userData));
        localStorage.setItem("access_token", session.access_token);
        localStorage.setItem("refresh_token", session.refresh_token);

        // Also potentially store in session storage if needed
        sessionStorage.setItem("last_auth_time", new Date().toISOString());

        // Sync user with backend database
        const syncKey = `user_synced_${session.user.id}`;
        const isAlreadySynced = localStorage.getItem(syncKey);

        if (!isAlreadySynced) {
          setStatus("Syncing account details...");
          try {
            await syncUser();
            localStorage.setItem(syncKey, "true");
          } catch (syncErr) {
            console.error("User sync error:", syncErr);
            // We continue even if sync fails
          }
        }

        setStatus("Success! Redirecting you to the dashboard...");
        
        setTimeout(() => {
          router.push("/dashboard");
        }, 800);
      } catch (err) {
        console.error("Storage error:", err);
        router.push("/dashboard");
      }
    };

    handleSuccess();
  }, [router, syncUser]);

  return (
    <div className="flex min-h-screen items-center justify-center bg-background">
      <div className="text-center space-y-4">
        <div className="flex justify-center">
          <div className="h-12 w-12 rounded-full border-4 border-[#0232D4] border-t-transparent animate-spin"></div>
        </div>
        <h2 className="text-xl font-medium text-foreground">{status}</h2>
        <p className="text-sm text-muted-foreground italic">Almost there...</p>
      </div>
    </div>
  );
}
