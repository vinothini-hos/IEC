import { NavLink } from "react-router-dom";
import {
  InboxIcon, FileTextIcon, BookIcon, LayersIcon, PlugIcon, UsersIcon, SlidersIcon,
} from "./Icons";

/**
 * Only "RFQ Inbox" is wired up (the mailbox module built in this pass).
 * The rest of the workflow items reflect the broader RFQ-to-proposal app
 * this mailbox lives in, and are placeholders until those modules exist.
 */
const GROUPS = [
  {
    label: "Workflow",
    items: [
      { key: "rfq-inbox", label: "RFQ Inbox", icon: InboxIcon, to: "/" },
      { key: "proposals", label: "Proposals", icon: FileTextIcon, disabled: true },
      { key: "reviews", label: "Reviews", icon: LayersIcon, disabled: true },
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
            return (
              <NavLink
                to={item.to}
                key={item.key}
                className={({ isActive }) =>
                  "sidebar-item" + (isActive ? " active" : "")
                }
              >
                <span className="icon"><Icon /></span>
                <span className="label">{item.label}</span>
                {!!item.badge && <span className="badge">{item.badge}</span>}
              </NavLink>
            );
          })}
        </div>
      ))}
    </nav>
  );
}
