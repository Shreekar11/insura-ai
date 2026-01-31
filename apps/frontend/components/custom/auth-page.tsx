"use client";

import React, { useState } from "react";
import { Button } from "@/components/ui/button";
import { motion } from "framer-motion";
import Link from "next/link";
import { createClient } from "@/utils/supabase/client";

interface AuthPageProps {
  mode: "sign-in" | "sign-up";
}

export function AuthPage({ mode }: AuthPageProps) {
  const isSignIn = mode === "sign-in";
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const signInWithGoogle = async () => {
    setIsLoading(true);
    setError(null);

    try {
      const supabase = createClient();
      const { error } = await supabase.auth.signInWithOAuth({
        provider: "google",
        options: {
          redirectTo: `${window.location.origin}/auth/callback`,
          queryParams: {
            access_type: "offline",
            prompt: "consent",
          },
        },
      });

      if (error) {
        setError(error.message);
        setIsLoading(false);
      }
      // If successful, the user will be redirected to Google
    } catch (err) {
      setError("An unexpected error occurred. Please try again.");
      setIsLoading(false);
      console.error("Google sign-in error:", err);
    }
  };

  return (
    <div className="flex min-h-screen w-full flex-col lg:flex-row">
      {/* Left Panel */}
      <div className="flex w-full flex-col items-center justify-center p-8 lg:w-[40%] lg:p-12">
        <div className="w-full max-w-sm space-y-8">
          <div className="space-y-2 flex flex-col justify-center items-center text-center lg:text-left">
            <h1 className="text-3xl font-semibold tracking-tight">
              {isSignIn ? "Welcome back" : "Get started"}
            </h1>
            <p className="text-muted-foreground text-sm">
              {isSignIn
                ? "Sign in to your account to continue"
                : "Create an account to start using the platform"}
            </p>
          </div>

          {error && (
            <div className="rounded-md bg-red-50 p-3 text-sm text-red-600">
              {error}
            </div>
          )}

          <Button
            variant="outline"
            className="w-full justify-center gap-3 rounded border shadow-xs transition-all hover:bg-neutral-50 active:scale-95 disabled:opacity-50 disabled:cursor-not-allowed"
            onClick={signInWithGoogle}
            disabled={isLoading}
          >
            {isLoading ? (
              <svg
                className="h-5 w-5 animate-spin text-gray-500"
                xmlns="http://www.w3.org/2000/svg"
                fill="none"
                viewBox="0 0 24 24"
              >
                <circle
                  className="opacity-25"
                  cx="12"
                  cy="12"
                  r="10"
                  stroke="currentColor"
                  strokeWidth="4"
                />
                <path
                  className="opacity-75"
                  fill="currentColor"
                  d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                />
              </svg>
            ) : (
              <svg
                viewBox="0 0 24 24"
                className="h-5 w-5"
                xmlns="http://www.w3.org/2000/svg"
              >
                <path
                  d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
                  fill="#4285F4"
                />
                <path
                  d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
                  fill="#34A853"
                />
                <path
                  d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l3.66-2.84z"
                  fill="#FBBC05"
                />
                <path
                  d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
                  fill="#EA4335"
                />
              </svg>
            )}
            <span>{isLoading ? "Signing in..." : "Continue with Google"}</span>
          </Button>

          <div className="text-center text-sm">
            <span className="text-muted-foreground">
              {isSignIn
                ? "Don't have an account? "
                : "Already have an account? "}
            </span>
            <Link
              href={isSignIn ? "/sign-up" : "/sign-in"}
              className="font-medium text-[#0232D4]/90 hover:text-[#0232D4]/80 underline-offset-4 hover:underline"
            >
              {isSignIn ? "Sign up" : "Sign in"}
            </Link>
          </div>
        </div>
      </div>

      {/* Right Panel */}
      <div
        className="hidden lg:flex w-[60%] flex-col items-center justify-center relative overflow-hidden h-screen"
        style={{
          background:
            "linear-gradient(to bottom, #04091B 0%, #171BB6 40%, #1F49D3 60%, #66A1EE 80%, #DAE5FA 100%)",
        }}
      >
        {/* Ambient Vertical Flickering Lines Layer */}
        <div className="absolute inset-0 pointer-events-none overflow-hidden">
          {[...Array(12)].map((_, i) => (
            <motion.div
              key={i}
              className="absolute top-0 bottom-0 bg-white/10"
              style={{
                width: Math.random() > 0.5 ? "2px" : "3px",
                left: `${Math.random() * 100}%`,
                opacity: 0.1 + Math.random() * 0.5,
              }}
              animate={{
                opacity: [0.1, 0.15, 0.1],
              }}
              transition={{
                duration: 2 + Math.random() * 4,
                repeat: Infinity,
                ease: "easeInOut",
                delay: Math.random() * 3,
              }}
            />
          ))}
        </div>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, ease: "easeOut" }}
          className="relative z-10 w-full max-w-xl px-12"
        >
          <div className="mt-8 text-center text-white/80">
            <h2 className="text-xl font-medium">Build next-gen insurance AI</h2>
            <p className="mt-2 text-sm text-white/60 font-medium">
              Experience the future of automated policy analysis
            </p>
          </div>
        </motion.div>
      </div>
    </div>
  );
}
