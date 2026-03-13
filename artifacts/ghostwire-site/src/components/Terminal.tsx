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

import React, { useState } from "react";
import { motion } from "framer-motion";
import { Check, Copy } from "lucide-react";

interface TerminalProps {
  code: string;
}

export function Terminal({ code }: TerminalProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.95 }}
      whileInView={{ opacity: 1, scale: 1 }}
      viewport={{ once: true }}
      className="w-full max-w-3xl mx-auto rounded-md overflow-hidden bg-[#0a0a0f] border border-border shadow-[0_0_30px_rgba(0,0,0,0.8)] relative group"
    >
      <div className="terminal-scanline" />
      
      {/* Terminal Header */}
      <div className="flex items-center justify-between px-4 py-2 bg-muted/30 border-b border-border">
        <div className="flex gap-2">
          <div className="w-3 h-3 rounded-full bg-destructive/80" />
          <div className="w-3 h-3 rounded-full bg-amber-500/80" />
          <div className="w-3 h-3 rounded-full bg-emerald-500/80" />
        </div>
        <div className="font-mono text-xs text-muted-foreground tracking-widest">
          SECRETFIRE // LOCAL_INSTALL
        </div>
        <button 
          onClick={handleCopy}
          className="text-muted-foreground hover:text-primary transition-colors z-20 relative p-1"
          aria-label="Copy code"
        >
          {copied ? <Check size={16} /> : <Copy size={16} />}
        </button>
      </div>
      
      {/* Terminal Body */}
      <div className="p-6 font-mono text-sm sm:text-base leading-relaxed overflow-x-auto relative">
        <pre className="text-primary/90">
          <code>
            {code.split('\n').map((line, i) => (
              <div key={i} className="flex gap-4">
                <span className="text-muted-foreground/40 select-none">{i + 1}</span>
                <span>{line}</span>
              </div>
            ))}
          </code>
        </pre>
        {/* Blinking cursor */}
        <motion.div 
          animate={{ opacity: [1, 0, 1] }}
          transition={{ duration: 1, repeat: Infinity }}
          className="w-2.5 h-5 bg-primary inline-block align-middle ml-1 mt-1"
        />
      </div>
    </motion.div>
  );
}
