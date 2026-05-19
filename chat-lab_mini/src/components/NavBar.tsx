"use client";

import React from "react";

interface NavBarProps {
  onMenuClick: () => void;
  onHistoryClick: () => void;
}

export default function NavBar({ onMenuClick, onHistoryClick }: NavBarProps) {
  return (
    <div className="navbar">
      <button className="navbar-left" onClick={onMenuClick} type="button" aria-label="打开菜单">
        <svg viewBox="0 0 24 24">
          <path d="M3 12h18M3 6h18M3 18h18" />
        </svg>
      </button>
      <div className="navbar-title-wrap">
        <div className="navbar-title">对话实验室</div>
        <div className="navbar-subtitle">内容由深度清北教育经验生成</div>
      </div>
      <button className="navbar-right" onClick={onHistoryClick} type="button" aria-label="新对话">
        <svg viewBox="0 0 24 24">
          <path d="M12 8v4l3 3M3 12a9 9 0 1 0 18 0 9 9 0 0 0-18 0z" />
        </svg>
      </button>
    </div>
  );
}
