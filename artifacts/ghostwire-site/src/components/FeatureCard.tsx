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

interface FeatureCardProps {
  icon: React.ReactNode;
  title: string;
  description: string;
  delay?: number;
}

export function FeatureCard({ icon, title, description, delay = 0 }: FeatureCardProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-50px" }}
      transition={{ duration: 0.5, delay }}
      className="relative bg-card border border-border p-6 rounded-sm glow-box overflow-hidden group"
    >
      <div className="absolute top-0 right-0 w-16 h-16 bg-primary/10 blur-2xl rounded-full group-hover:bg-primary/20 transition-colors duration-500" />
      <div className="absolute left-0 top-0 w-1 h-full bg-primary/30 group-hover:bg-primary transition-colors duration-300" />
      
      <div className="mb-4 text-primary w-10 h-10 flex items-center justify-center bg-primary/10 border border-primary/20 rounded-sm">
        {icon}
      </div>
      
      <h3 className="text-xl font-display font-bold text-foreground mb-2 group-hover:text-primary transition-colors duration-300">
        {title}
      </h3>
      
      <p className="text-muted-foreground text-sm leading-relaxed">
        {description}
      </p>
    </motion.div>
  );
}
