"use client";

import Link from "next/link";
import React from "react";

interface SidebarProps {
  isOpen: boolean;
  onClose: () => void;
  onNavigate?: (view: string) => void;
}

const menuItems = [
  { icon: "🏫", text: "清北社区", href: "/community" },
  { icon: "🎯", text: "名校直答", href: "/qa" },
  { icon: "👶", text: "孩子人物", href: "/character" },
  { icon: "🔤", text: "英语角", href: "/english" },
  { icon: "📅", text: "个性化课表", href: "/schedule" },
  { icon: "📝", text: "一键分析试卷", href: "/exam" },
  { icon: "🎬", text: "产品演示", action: "demo" },
];

export default function Sidebar({ isOpen, onClose, onNavigate }: SidebarProps) {
  return (
    <>
      <div className={`sidebar-overlay ${isOpen ? "active" : ""}`} onClick={onClose} />
      <div className={`sidebar ${isOpen ? "active" : ""}`}>
        <div className="sidebar-header">
          <div className="sidebar-title">对话实验室</div>
          <div className="sidebar-subtitle">清北学霸陪你聊教育</div>
        </div>
        <div className="sidebar-menu">
          {menuItems.map((item) =>
            item.action ? (
              <button
                key={item.action}
                className="menu-item"
                type="button"
                onClick={() => {
                  onNavigate?.(item.action!);
                  onClose();
                }}
              >
                <span className="menu-icon">{item.icon}</span>
                <span className="menu-text">{item.text}</span>
              </button>
            ) : (
              <Link key={item.href} href={item.href!} className="menu-item" onClick={onClose}>
                <span className="menu-icon">{item.icon}</span>
                <span className="menu-text">{item.text}</span>
              </Link>
            )
          )}
        </div>
      </div>
    </>
  );
}
