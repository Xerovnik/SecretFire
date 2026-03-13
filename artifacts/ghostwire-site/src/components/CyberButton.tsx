// GhostWire
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
import { motion } from "framer-motion";

interface CyberButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "outline";
  icon?: React.ReactNode;
  children: React.ReactNode;
}

export function CyberButton({ variant = "primary", icon, children, className = "", ...props }: CyberButtonProps) {
  const baseClasses = "relative flex items-center justify-center gap-2 px-6 py-3 font-display font-bold tracking-widest uppercase overflow-hidden group transition-all duration-300";
  
  const variants = {
    primary: "bg-primary text-primary-foreground hover:bg-primary/90 shadow-[0_0_15px_rgba(0,255,255,0.4)] hover:shadow-[0_0_25px_rgba(0,255,255,0.6)]",
    secondary: "bg-secondary text-secondary-foreground hover:bg-secondary/90 shadow-[0_0_15px_rgba(180,0,255,0.4)] hover:shadow-[0_0_25px_rgba(180,0,255,0.6)]",
    outline: "bg-transparent border-2 border-primary text-primary hover:bg-primary/10 hover:shadow-[0_0_20px_rgba(0,255,255,0.3)]",
  };

  return (
    <motion.button
      whileHover={{ scale: 1.02 }}
      whileTap={{ scale: 0.98 }}
      className={`${baseClasses} ${variants[variant]} ${className}`}
      {...props}
    >
      <span className="absolute inset-0 w-full h-full border border-white/20 scale-[0.9] opacity-0 group-hover:scale-100 group-hover:opacity-100 transition-all duration-300 pointer-events-none" />
      {icon && <span className="w-5 h-5">{icon}</span>}
      <span className="relative z-10">{children}</span>
    </motion.button>
  );
}
