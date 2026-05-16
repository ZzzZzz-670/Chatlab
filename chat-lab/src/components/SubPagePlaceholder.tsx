"use client";

import React from "react";
import SubPageHeader from "@/components/SubPageHeader";

interface SubPagePlaceholderProps {
  title: string;
  subtitle: string;
  items: string[];
}

export default function SubPagePlaceholder({ title, subtitle, items }: SubPagePlaceholderProps) {
  return (
    <div className="subpage-shell">
      <SubPageHeader title={title} subtitle={subtitle} />
      <main className="subpage-content">
        <div className="subpage-panel">
          <div className="subpage-panel-title">{title}</div>
          <div className="subpage-panel-desc">{subtitle}</div>
          <div className="subpage-list">
            {items.map((item) => (
              <div className="subpage-list-item" key={item}>
                <span className="subpage-list-dot" />
                <span>{item}</span>
              </div>
            ))}
          </div>
        </div>
      </main>
    </div>
  );
}
