"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/",          label: "Machine"   },
  { href: "/dashboard", label: "Dashboard" },
  { href: "/logs",      label: "Logs"      },
];

export function NavLinks() {
  const path = usePathname();
  return (
    <nav className="flex items-center gap-1">
      {LINKS.map(({ href, label }) => (
        <Link
          key={href}
          href={href}
          className={[
            "text-xs px-3 py-1 rounded-md transition-colors",
            path === href
              ? "bg-muted text-foreground font-medium"
              : "text-muted-foreground hover:text-foreground hover:bg-muted/50",
          ].join(" ")}
        >
          {label}
        </Link>
      ))}
    </nav>
  );
}
