"use client";

import Link from "next/link";
import Image from "next/image";
import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Menu, X, ArrowRight, Sparkle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { LineShadowText } from "@/components/ui/line-shadow-text";

import productPlaceholder from "../public/assets/product-landing.png";

const GradientBackground = () => (
  <div
    className="absolute inset-0 z-0 pointer-events-none overflow-hidden w-full h-full"
    style={{
      background:
        "linear-gradient(to bottom, #DAE5FA 0%, #66A1EE 35%, #1F49D3 55%, #171BB6 75%, #04091B 100%)",
    }}
  >
    {/* Ambient Vertical Flickering Lines Layer */}
    <div className="absolute inset-0 pointer-events-none">
      {[...Array(20)].map((_, i) => (
        <motion.div
          key={i}
          className="absolute top-0 bottom-0 bg-blue-100/20"
          style={{
            width: Math.random() > 0.5 ? "2px" : "3px",
            left: `${Math.random() * 100}%`,
            opacity: 0.1 + Math.random() * 0.3,
          }}
          animate={{
            opacity: [0.1, 0.4, 0.1],
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
  </div>
);

export default function Home() {
  const [isScrolled, setIsScrolled] = useState(false);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);

  useEffect(() => {
    const handleScroll = () => {
      setIsScrolled(window.scrollY > 10);
    };

    window.addEventListener("scroll", handleScroll);
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  return (
    <div className="relative min-h-screen w-full selection:bg-blue-500/30 font-sans text-[#2B2C36] overflow-x-hidden">
      <GradientBackground />

      {/* Header */}
      <header
        className={`relative w-full z-50 ${
          isScrolled
            ? "py-3 bg-white/5 border-b border-white/10"
            : "py-6 bg-transparent"
        }`}
      >
        <div className="max-w-5xl mx-auto px-6 md:px-8">
          <nav className="flex items-center justify-between">
            {/* Logo */}
            <Link href="/" className="flex items-center gap-1 group">
              <Sparkle className="size-5 text-[#2B2C36]" />
              <span className="text-xl font-bold tracking-tight text-[#2B2C36]">
                InsuraAI
              </span>
            </Link>

            <div className="flex items-center justify-end gap-4">
              {/* Mobile Menu Button */}
              <Button
                variant="ghost"
                size="icon"
                className="md:hidden text-[#2B2C36]"
                onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
              >
                {isMobileMenuOpen ? <X size={24} /> : <Menu size={24} />}
              </Button>
            </div>

            <div className="hidden md:flex">
              <div className="hidden md:flex items-center space-x-2">
                <Link href="/sign-in">
                  <Button
                    variant="ghost"
                    className="text-[#2B2C36] rounded-sm hover:text-[#2B2C36] hover:bg-gray-100"
                  >
                    Log in
                  </Button>
                </Link>
                <Link href="/sign-up">
                  <Button
                    variant="default"
                    className="bg-[#0232D4]/90 rounded-sm text-white hover:bg-[#0232D4]/80"
                  >
                    Sign up
                  </Button>
                </Link>
              </div>
            </div>
          </nav>

          {/* Mobile Menu */}
          <AnimatePresence>
            {isMobileMenuOpen && (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: "auto" }}
                exit={{ opacity: 0, height: 0 }}
                className="md:hidden mt-4 overflow-hidden"
              >
                <div className="flex flex-col space-y-4 pb-6 px-4">
                  <div className="pt-4 flex flex-col gap-3">
                    <Link href="/sign-in">
                      <Button
                        variant="outline"
                        className="text-[#2B2C36] rounded-sm hover:text-[#2B2C36] hover:bg-gray-100"
                      >
                        Log in
                      </Button>
                    </Link>
                    <Link href="/sign-up">
                      <Button className="bg-[#0232D4]/90 rounded-sm text-white hover:bg-[#0232D4]/80">
                        Sign up
                      </Button>
                    </Link>
                  </div>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </header>

      {/* Main Content */}
      <main className="relative z-10 pt-12 md:pt-20 pb-32">
        <div className="max-w-7xl mx-auto px-6 md:px-8">
          <div className="max-w-4xl mx-auto text-center">
            {/* Heading */}
            <motion.h1
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.1 }}
              className="text-4xl md:text-6xl font-semibold tracking-tighter text-balance mb-4"
            >
              The AI workspace for <br className="hidden md:block" />
              <LineShadowText
                shadowColor="#2B2C36"
                className="text-[#0232D4]/90 italic font-bold"
              >
                insurance
              </LineShadowText>{" "}
              intelligence
            </motion.h1>

            {/* Subtext */}
            <motion.p
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.2 }}
              className="text-lg md:text-xl text-[#2B2C36] max-w-2xl mx-auto mb-6 leading-relaxed"
            >
              Instantly understand insurance-specific sections from your
              insurance documents and run AI-native analysis and comparisons.
            </motion.p>

            {/* CTAs */}
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.3 }}
              className="flex flex-col sm:flex-row items-center justify-center gap-4"
            >
              <Link href="/sign-up" className="w-full sm:w-auto">
                <Button
                  size="lg"
                  className="w-full sm:w-auto bg-[#0232D4]/90 rounded-sm text-white hover:bg-[#0232D4]/80 transition-all duration-300 ease-in-out transform hover:scale-105"
                >
                  Get Started <ArrowRight className="ml-2 size-5" />
                </Button>
              </Link>
            </motion.div>
          </div>

          <motion.div
            initial={{ opacity: 0, y: 40 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, delay: 0.6, ease: "easeOut" }}
            className="mt-20 max-w-6xl mx-auto w-full"
          >
            <div className="relative aspect-video w-full rounded-2xl border border-white/10 bg-slate-950/40 shadow-[0_0_120px_rgba(31,73,211,0.25)] overflow-hidden group">
              <Image
                src={productPlaceholder}
                alt="InsuraAI Product Preview"
                fill
                className="object-cover opacity-90 group-hover:opacity-100 transition-opacity duration-500"
                priority
              />
              <div className="absolute inset-0 bg-gradient-to-tr from-blue-900/20 to-transparent opacity-60" />
            </div>
          </motion.div>
        </div>
      </main>

      <footer className="relative z-10 border-t border-white/5 backdrop-blur-md">
        <div className="max-w-7xl mx-auto px-6 md:px-8 py-12">
          <div className="flex flex-col md:flex-row justify-between items-center gap-8">
            <Link href="/" className="flex items-center gap-2">
              <Sparkle className="size-5 text-white/40" />
              <span className="text-lg font-semibold text-white/40">
                InsuraAI
              </span>
            </Link>
            <p className="text-sm text-white/40">
              © 2026 InsuraAI. All rights reserved.
            </p>
          </div>
        </div>
      </footer>
    </div>
  );
}
