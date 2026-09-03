const base = {
  width: 16,
  height: 16,
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.8,
  strokeLinecap: "round",
  strokeLinejoin: "round",
};

export const InboxIcon = () => (
  <svg {...base}>
    <path d="M22 12h-6l-2 3h-4l-2-3H2" />
    <path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11Z" />
  </svg>
);

export const FileTextIcon = () => (
  <svg {...base}>
    <path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2Z" />
    <path d="M14 2v6h6" />
  </svg>
);

export const BookIcon = () => (
  <svg {...base}>
    <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
    <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2Z" />
  </svg>
);

export const LayersIcon = () => (
  <svg {...base}>
    <path d="m12 2 9 5-9 5-9-5 9-5Z" />
    <path d="m3 12 9 5 9-5" />
    <path d="m3 17 9 5 9-5" />
  </svg>
);

export const SearchIcon = () => (
  <svg {...base}>
    <circle cx="11" cy="11" r="7" />
    <path d="m21 21-4.3-4.3" />
  </svg>
);

export const CopyCheckIcon = () => (
  <svg {...base}>
    <rect x="8" y="8" width="13" height="13" rx="2" />
    <path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2" />
    <path d="m11.5 14.5 2 2 4-4" />
  </svg>
);

export const PlugIcon = () => (
  <svg {...base}>
    <path d="M12 22v-5" />
    <path d="M9 8V2" />
    <path d="M15 8V2" />
    <path d="M6 12h12v2a6 6 0 0 1-12 0v-2Z" />
  </svg>
);

export const UsersIcon = () => (
  <svg {...base}>
    <circle cx="9" cy="8" r="4" />
    <path d="M2 21v-1a6 6 0 0 1 12 0v1" />
    <circle cx="17" cy="9" r="3" />
    <path d="M15 21v-1a5 5 0 0 0-2.3-4.2" />
  </svg>
);

export const SlidersIcon = () => (
  <svg {...base}>
    <path d="M4 21v-7" />
    <path d="M4 10V3" />
    <path d="M12 21v-9" />
    <path d="M12 8V3" />
    <path d="M20 21v-5" />
    <path d="M20 12V3" />
    <path d="M2 14h4" />
    <path d="M10 8h4" />
    <path d="M18 12h4" />
  </svg>
);
