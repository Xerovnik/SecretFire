// SecretFire
// Copyright (C) 2026 J. Zerovnik
//
// This program is free software: you can redistribute it and/or modify
// it under the terms of the GNU General Public License as published by
// the Free Software Foundation, either version 3 of the License, or
// (at your option) any later version.
//
// This program is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
// GNU General Public License for more details.
//
// You should have received a copy of the GNU General Public License
// along with this program.  If not, see <https://www.gnu.org/licenses/>.

import React from "react";
import { motion, useScroll, useTransform } from "framer-motion";
import { 
  Network, 
  Shield, 
  Lock, 
  Code, 
  Download, 
  Monitor, 
  Github, 
  Zap, 
  ArrowRight,
  EyeOff
} from "lucide-react";
import { CyberButton } from "@/components/CyberButton";
import { FeatureCard } from "@/components/FeatureCard";
import { Terminal } from "@/components/Terminal";

export default function Home() {
  const { scrollY } = useScroll();
  const opacity = useTransform(scrollY, [0, 500], [1, 0]);
  const y = useTransform(scrollY, [0, 500], [0, 150]);

  const handleScrollTo = (id: string) => {
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth' });
  };

  return (
    <div className="min-h-screen bg-background selection:bg-primary/30 selection:text-primary">
      {/* Navbar */}
      <nav className="fixed top-0 w-full z-50 bg-background/80 backdrop-blur-md border-b border-primary/20">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          <div className="flex items-center gap-2 text-primary">
            <Network className="w-6 h-6" />
            <span className="font-display font-bold text-xl tracking-widest uppercase">SecretFire</span>
          </div>
          <div className="flex gap-4">
            <button 
              onClick={() => handleScrollTo('features')}
              className="hidden sm:block text-muted-foreground hover:text-primary transition-colors font-sans text-sm uppercase tracking-wider"
            >
              Features
            </button>
            <button 
              onClick={() => handleScrollTo('download')}
              className="text-primary hover:text-primary/80 transition-colors font-sans text-sm uppercase tracking-wider font-bold"
            >
              Download
            </button>
          </div>
        </div>
      </nav>

      {/* Hero Section */}
      <section className="relative min-h-screen flex items-center pt-16 overflow-hidden">
        {/* Background Image */}
        <div className="absolute inset-0 z-0">
          <img 
            src={`${import.meta.env.BASE_URL}images/cyber-bg.png`}
            alt="Cyberpunk background" 
            className="w-full h-full object-cover opacity-30"
          />
          <div className="absolute inset-0 bg-gradient-to-b from-background/50 via-background/80 to-background" />
        </div>

        <div className="relative z-10 max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 w-full">
          <motion.div 
            style={{ opacity, y }}
            className="max-w-3xl"
          >
            <motion.div
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.5 }}
              className="inline-flex items-center gap-2 px-3 py-1 bg-primary/10 border border-primary/30 text-primary text-sm font-mono mb-6"
            >
              <span className="w-2 h-2 rounded-full bg-primary animate-pulse" />
              SYSTEM.STATUS: ONLINE
            </motion.div>
            
            <motion.h1 
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5, delay: 0.1 }}
              className="text-5xl sm:text-6xl md:text-8xl font-display font-bold text-foreground leading-tight mb-6"
            >
              BROADCAST <br />
              <span className="static-wrap">
                <span className="static-text" data-text="FREELY.">FREELY.</span>
                <span className="crt-bars" aria-hidden="true">FREELY.</span>
              </span>
            </motion.h1>
            
            <motion.p 
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5, delay: 0.2 }}
              className="text-xl sm:text-2xl text-muted-foreground mb-8 max-w-2xl leading-relaxed"
            >
              Anonymous P2P microblogging over Tor. No central servers. No surveillance. Just encrypted gossip protocols in the dark web.
            </motion.p>
            
            <motion.div 
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5, delay: 0.3 }}
              className="flex flex-col sm:flex-row gap-4"
            >
              <CyberButton onClick={() => handleScrollTo('download')} icon={<Download />}>
                Download Now
              </CyberButton>
              <CyberButton variant="outline" onClick={() => handleScrollTo('install')} icon={<Code />}>
                View Source
              </CyberButton>
            </motion.div>
          </motion.div>
        </div>
        
        {/* Scroll Indicator */}
        <motion.div 
          animate={{ y: [0, 10, 0] }}
          transition={{ repeat: Infinity, duration: 2 }}
          className="absolute bottom-10 left-1/2 -translate-x-1/2 text-primary/50"
        >
          <ArrowRight className="w-6 h-6 rotate-90" />
        </motion.div>
      </section>

      {/* How It Works */}
      <section className="py-24 bg-background relative border-y border-border">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center mb-16">
            <h2 className="text-3xl md:text-4xl font-display text-foreground mb-4">
              <span className="text-primary">//</span> EXECUTE PROTOCOL
            </h2>
            <p className="text-muted-foreground max-w-2xl mx-auto">
              SecretFire operates entirely on your local machine, connecting to peers through hidden services to ensure untraceable communication.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            {[
              {
                step: "01",
                title: "Download & Run",
                desc: "Download the binary for your OS. On macOS and Linux, run chmod +x on the file first. No installation needed — Tor is bundled inside."
              },
              {
                step: "02",
                title: "Initialize Identity",
                desc: "Your identity is cryptographic. Generate an Ed25519 keypair and a unique .onion hidden service address."
              },
              {
                step: "03",
                title: "Gossip & Sync",
                desc: "Broadcast encrypted message fragments. Nodes sync with each other continually, propagating posts across the network."
              }
            ].map((item, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ delay: i * 0.2 }}
                className="relative p-8 border border-border bg-card/50 hover:bg-card transition-colors"
              >
                <div className="text-6xl font-display font-bold text-primary/10 absolute top-4 right-4 pointer-events-none">
                  {item.step}
                </div>
                <h3 className="text-xl font-display text-foreground mb-3 mt-4 relative z-10">{item.title}</h3>
                <p className="text-muted-foreground text-sm relative z-10">{item.desc}</p>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* Features */}
      <section id="features" className="py-24 relative overflow-hidden">
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[800px] h-[800px] bg-primary/5 blur-[120px] rounded-full pointer-events-none" />
        
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 relative z-10">
          <div className="mb-16">
            <h2 className="text-3xl md:text-4xl font-display text-foreground mb-4">
              <span className="text-primary">//</span> SYSTEM_SPECS
            </h2>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            <FeatureCard 
              icon={<Network />}
              title="No Central Server"
              description="Fully decentralized P2P gossip protocol. The network exists only as long as nodes are communicating."
              delay={0.1}
            />
            <FeatureCard 
              icon={<EyeOff />}
              title="Tor Hidden Services"
              description="All traffic routes through the Tor network. Your IP address is never revealed, only your .onion address."
              delay={0.2}
            />
            <FeatureCard 
              icon={<Lock />}
              title="E2E Encryption"
              description="Message fragments are encrypted using AES-256-GCM. Only intended recipients can reassemble them."
              delay={0.3}
            />
            <FeatureCard 
              icon={<Shield />}
              title="Signed Posts"
              description="Cryptographic integrity. Ed25519 signatures ensure that posts truly originate from their claimed authors."
              delay={0.4}
            />
            <FeatureCard 
              icon={<Code />}
              title="Open Source"
              description="Trust but verify. Inspect every line of code. No hidden telemetry, no tracking analytics, no backdoors."
              delay={0.5}
            />
            <FeatureCard 
              icon={<Zap />}
              title="Resilient Design"
              description="Even if peers go offline, the fragmented message architecture ensures delivery when connectivity restores."
              delay={0.6}
            />
          </div>
        </div>
      </section>

      {/* Downloads */}
      <section id="download" className="py-24 bg-card/50 border-y border-border">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center mb-16">
            <h2 className="text-3xl md:text-4xl font-display text-foreground mb-4">
              <span className="text-primary">//</span> ACQUIRE_BINARY
            </h2>
            <p className="text-muted-foreground">Select your operating system to download the latest build.</p>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {[
              { os: "Windows", label: "Download .exe", href: "https://github.com/Xerovnik/SecretFire/releases/latest/download/SecretFire-windows.exe", icon: <Monitor className="w-8 h-8 mb-4 text-primary" /> },
              { os: "macOS", label: "Download binary", href: "https://github.com/Xerovnik/SecretFire/releases/latest/download/SecretFire-macos", icon: <Monitor className="w-8 h-8 mb-4 text-primary" />, note: "chmod +x then run" },
              { os: "Linux", label: "Download ELF binary", href: "https://github.com/Xerovnik/SecretFire/releases/latest/download/SecretFire-linux", icon: <Monitor className="w-8 h-8 mb-4 text-primary" />, note: "chmod +x then run" },
              { os: "Source", label: "View Repository", href: "https://github.com/Xerovnik/SecretFire", icon: <Github className="w-8 h-8 mb-4 text-primary" />, outline: true }
            ].map((item, i) => (
              <motion.a
                key={i}
                href={item.href}
                target="_blank"
                rel="noopener noreferrer"
                whileHover={{ y: -5 }}
                className={`flex flex-col items-center justify-center p-8 border ${item.outline ? 'border-primary/50 hover:bg-primary/10' : 'border-border bg-background hover:border-primary'} transition-all group`}
              >
                {item.icon}
                <h3 className="font-display text-lg font-bold mb-1">{item.os}</h3>
                <p className="text-sm text-muted-foreground group-hover:text-primary transition-colors">
                  {item.label}
                </p>
                {item.note && (
                  <p className="text-xs text-muted-foreground/60 mt-1 font-mono">{item.note}</p>
                )}
              </motion.a>
            ))}
          </div>
        </div>
      </section>

      {/* Install Instructions */}
      <section id="install" className="py-24 relative">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="mb-10 text-center">
            <h2 className="text-3xl md:text-4xl font-display text-foreground mb-4">
              <span className="text-primary">//</span> MANUAL_BOOT
            </h2>
            <p className="text-muted-foreground">Prefer to run directly from source? Clone and execute.</p>
          </div>
          
          <Terminal code={`git clone https://github.com/Xerovnik/SecretFire.git\ncd SecretFire/desktop-app\npip install -r requirements.txt\npython main.py`} />
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-border bg-background py-12 text-center">
        <div className="max-w-7xl mx-auto px-4 flex flex-col items-center">
          <Network className="w-8 h-8 text-primary mb-6 opacity-50" />
          <p className="text-muted-foreground font-mono text-sm">
            SECRETFIRE v0.1.3 // ANONYMOUS P2P NETWORK
          </p>
          <p className="text-muted-foreground/50 text-xs mt-2 max-w-md mx-auto">
            This software is provided "as is", without warranty of any kind. Use at your own risk. Stay safe out there.
          </p>
        </div>
      </footer>
    </div>
  );
}
