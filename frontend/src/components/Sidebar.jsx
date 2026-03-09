export default function Sidebar({ currentPage, navigate }) {
  const items = [
    { id: "dashboard", label: "לוח בקרה", icon: "🏠" },
    { id: "bookings",  label: "הזמנות",   icon: "📋" },
    { id: "guests",    label: "אורחים",   icon: "👥" },
    { id: "reports",   label: "דוחות",    icon: "📊" },
    { id: "settings",  label: "הגדרות",   icon: "⚙️" },
  ];
  return (
    <aside className="sidebar">
      <div className="sidebar-logo">
        <div className="sidebar-logo-circle">
          <svg width="22" height="22" viewBox="0 0 100 100" fill="none">
            <circle cx="50" cy="50" r="48" fill="none" stroke="#A84D3A" strokeWidth="14"/>
            <path d="M15 65 Q35 50 50 58 Q65 66 85 55" stroke="#D4956A" strokeWidth="9" fill="none" strokeLinecap="round"/>
            <path d="M10 76 Q35 60 50 68 Q65 76 90 65" stroke="#E8C9A0" strokeWidth="7" fill="none" strokeLinecap="round"/>
            <path d="M8 88 Q35 75 50 80 Q65 85 92 76" stroke="#2BBFBF" strokeWidth="8" fill="none" strokeLinecap="round"/>
          </svg>
        </div>
        <div className="sidebar-logo-text">
          <div className="sidebar-logo-title">מדבר וים</div>
          <div className="sidebar-logo-sub">מקום של חופש</div>
        </div>
      </div>
      <nav className="sidebar-nav">
        {items.map(item => (
          <button
            key={item.id}
            className={`nav-item ${
              currentPage === item.id ||
              (currentPage === "booking" && item.id === "bookings")
                ? "active" : ""
            }`}
            onClick={() => navigate(item.id)}
          >
            <span className="icon">{item.icon}</span>
            {item.label}
          </button>
        ))}
      </nav>
      <div className="sidebar-footer">מדבר וים © 2026</div>
    </aside>
  );
}
