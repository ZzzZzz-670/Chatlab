"use client";

import Link from "next/link";
import React from "react";

interface SubPageHeaderProps {
  title: string;
  subtitle?: string;
  backHref?: string;
}

export default function SubPageHeader({ title, subtitle, backHref = "/" }: SubPageHeaderProps) {
  return (
    <div className="page-header-enhanced">
      <div className="subpage-header-inner">
        <Link href={backHref} className="subpage-back" aria-label="返回">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
            <path d="M15 18l-6-6 6-6" />
          </svg>
        </Link>
        <div>
          <div className="page-header-title">{title}</div>
          {subtitle && <div className="page-header-subtitle">{subtitle}</div>}
        </div>
      </div>
    </div>
  );
}
