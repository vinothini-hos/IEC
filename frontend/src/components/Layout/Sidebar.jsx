import { Link, useLocation } from "react-router-dom";
import {
  InboxIcon, BookIcon, LayersIcon, CopyCheckIcon, PlugIcon, UsersIcon, SlidersIcon,
} from "./Icons";

/**
 * "RFQ Inbox", "Spec Extraction", and "Similar Projects" are wired up. The
 * rest of the workflow items reflect the broader RFQ-to-proposal app this
 * mailbox lives in, and are placeholders until those modules exist.
 *
 * `isActive` is computed manually (rather than via NavLink's built-in
 * prefix matching) because NavLink's default matching for `to="/"` matches
 * every route, which would make "RFQ Inbox" light up on Spec Extraction
 * pages too.
 */
const GROUPS = [
  {
    label: "Workflow",
    items: [
      {
        key: "rfq-inbox", label: "RFQ Inbox", icon: InboxIcon, to: "/",
        isActive: (p) => p === "/" || p.startsWith("/threads/"),
      },
      {
        key: "spec-extraction", label: "Spec Extraction", icon: LayersIcon, to: "/spec-extraction",
        isActive: (p) => p.startsWith("/spec-extraction"),
      },
      {
        key: "similar-projects", label: "Similar Projects", icon: CopyCheckIcon, to: "/similar-projects",
        isActive: (p) => p.startsWith("/similar-projects"),
      },
    ],
  },
  {
    label: "Knowledge",
    items: [
      { key: "historical-matches", label: "Historical Matches", icon: BookIcon, disabled: true },
    ],
  },
  {
    label: "Settings",
    items: [
      { key: "integrations", label: "Integrations", icon: PlugIcon, disabled: true },
      { key: "team", label: "Team", icon: UsersIcon, disabled: true },
      { key: "preferences", label: "Preferences", icon: SlidersIcon, disabled: true },
    ],
  },
];

export default function Sidebar() {
  const location = useLocation();

  return (
    <nav className="sidebar">
      {GROUPS.map((group) => (
        <div className="sidebar-group" key={group.label}>
          <div className="sidebar-group-label">{group.label}</div>
          {group.items.map((item) => {
            const Icon = item.icon;
            if (item.disabled) {
              return (
                <div
                  className="sidebar-item"
                  key={item.key}
                  style={{ opacity: 0.5, cursor: "default" }}
                  title="Not built yet"
                >
                  <span className="icon"><Icon /></span>
                  <span className="label">{item.label}</span>
                </div>
              );
            }
            const active = item.isActive(location.pathname);
            return (
              <Link
                to={item.to}
                key={item.key}
                className={"sidebar-item" + (active ? " active" : "")}
              >
                <span className="icon"><Icon /></span>
                <span className="label">{item.label}</span>
                {!!item.badge && <span className="badge">{item.badge}</span>}
              </Link>
            );
          })}
        </div>
      ))}
    </nav>
  );
}
