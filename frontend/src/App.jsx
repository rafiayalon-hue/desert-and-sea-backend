import { useState, useEffect, useRef } from "react";
import Sidebar from "./components/Sidebar";
import Dashboard from "./pages/Dashboard";
import BookingsList from "./pages/BookingsList";
import BookingDetail from "./pages/BookingDetail";
import Settings from "./pages/Settings";
import Guests from "./pages/Guests";
import Reports from "./pages/Reports";
import Conversations from "./pages/Conversations"; // NEW (17.7.26)
import Campaigns from "./pages/Campaigns";         // NEW (17.7.26)

const API_BASE = import.meta.env.VITE_API_URL
  ? `${import.meta.env.VITE_API_URL}/api`
  : "https://selfless-happiness-production.up.railway.app/api";

// NEW (17.7.26): כמה זמן בין בדיקות לשיחות חדשות. 20 שניות — מספיק מהיר
// כדי להרגיש "כמעט מיידי" בלי להעמיס יותר מדי על השרת.
const POLL_INTERVAL_MS = 20000;
const LAST_SEEN_KEY = "desertSea_lastSeenInboundAt";

function MobileHeader({ currentPage }) {
  const titles = {
    dashboard: "לוח בקרה",
    bookings:  "הזמנות",
    booking:   "פרטי הזמנה",
    guests:    "אורחים",
    conversations: "שיחות", // NEW (17.7.26)
    campaigns: "קמפיינים",  // NEW (17.7.26)
    reports:   "דוחות",
    settings:  "הגדרות",
  };
  return (
    <header className="mobile-header">
      <div className="mobile-header-logo">
        <div className="mobile-header-logo-circle">
          <svg width="16" height="16" viewBox="0 0 100 100" fill="none">
            <circle cx="50" cy="50" r="48" fill="none" stroke="#A84D3A" strokeWidth="16"/>
            <path d="M15 65 Q35 50 50 58 Q65 66 85 55" stroke="#D4956A" strokeWidth="10" fill="none" strokeLinecap="round"/>
            <path d="M8 80 Q35 65 50 72 Q65 79 92 68" stroke="#2BBFBF" strokeWidth="9" fill="none" strokeLinecap="round"/>
          </svg>
        </div>
        <span className="mobile-header-title">מדבר וים</span>
      </div>
      <span className="mobile-header-date">
        {new Date().toLocaleDateString("he-IL", { weekday: "short", day: "numeric", month: "short" })}
      </span>
    </header>
  );
}
function BottomNav({ currentPage, navigate, unreadCount }) {
  const items = [
    { id: "dashboard", label: "בקרה",   icon: "🏠" },
    { id: "bookings",  label: "הזמנות", icon: "📋" },
    { id: "guests",    label: "אורחים",  icon: "👥" },
    { id: "conversations", label: "שיחות", icon: "💬", badge: unreadCount },
    { id: "reports",   label: "דוחות",  icon: "📊" },
    { id: "settings",  label: "הגדרות", icon: "⚙️" },
  ];
  return (
    <nav className="bottom-nav">
      <div className="bottom-nav-items">
        {items.map(item => (
          <button
            key={item.id}
            className={`bottom-nav-item ${
              currentPage === item.id ||
              (currentPage === "booking" && item.id === "bookings")
                ? "active" : ""
            }`}
            onClick={() => navigate(item.id)}
            style={{ position: "relative" }}
          >
            <span className="nav-icon">{item.icon}</span>
            {item.label}
            {item.badge > 0 && (
              <span style={{
                position: "absolute", top: 2, left: "50%", marginLeft: 6,
                background: "var(--terra)", color: "#fff", borderRadius: 20,
                fontSize: ".6rem", minWidth: 14, height: 14, display: "flex",
                alignItems: "center", justifyContent: "center", padding: "0 3px", fontWeight: 700,
              }}>{item.badge}</span>
            )}
          </button>
        ))}
      </div>
    </nav>
  );
}

// NEW (17.7.26): בדיקה תקופתית לשיחות חדשות — עובד ברקע בכל העמודים,
// לא רק בעמוד "שיחות" עצמו, כדי שההתראה תקפוץ גם אם המשתמש נמצא
// בעמוד אחר (או שהטאב פתוח ברקע).
function useUnreadInboundPolling() {
  const [unreadCount, setUnreadCount] = useState(0);
  const lastSeenRef = useRef(localStorage.getItem(LAST_SEEN_KEY) || "");

  useEffect(() => {
    // מבקשים הרשאת התראות דפדפן פעם אחת, בטעינה הראשונה
    if (typeof Notification !== "undefined" && Notification.permission === "default") {
      Notification.requestPermission();
    }

    async function poll() {
      try {
        const res = await fetch(`${API_BASE}/messages/conversations`);
        const conversations = await res.json();

        const inboundNewer = conversations.filter(c =>
          c.last_direction === "inbound" &&
          (!lastSeenRef.current || c.last_at > lastSeenRef.current)
        );

        if (inboundNewer.length > 0) {
          // Browser notification — רק אם יש הרשאה ואת/ה לא כרגע מסתכל/ת בטאב
          if (typeof Notification !== "undefined" && Notification.permission === "granted" && document.hidden) {
            const newest = inboundNewer[0];
            new Notification("הודעת WhatsApp חדשה", {
              body: `${newest.guest_name || newest.phone}: ${(newest.last_message || "").slice(0, 80)}`,
              icon: "/favicon.ico",
            });
          }
        }

        // ספירת "לא נקראו" — כל שיחה שההודעה האחרונה בה נכנסת (מחכה לתגובה)
        const unread = conversations.filter(c => c.last_direction === "inbound").length;
        setUnreadCount(unread);
      } catch {
        // best-effort — לא מציגים שגיאה למשתמש על polling ברקע
      }
    }

    poll();
    const interval = setInterval(poll, POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, []);

  // נקרא מעמוד השיחות כשנפתחת שיחה, כדי לאפס את מונה ה"לא נקרא"
  function markSeen() {
    const now = new Date().toISOString();
    lastSeenRef.current = now;
    localStorage.setItem(LAST_SEEN_KEY, now);
    setUnreadCount(0);
  }

  return { unreadCount, markSeen };
}

export default function App() {
  const [currentPage, setCurrentPage] = useState("dashboard");
  const [selectedBookingId, setSelectedBookingId] = useState(null);
  const { unreadCount, markSeen } = useUnreadInboundPolling();

  function navigate(page, bookingId = null) {
    setCurrentPage(page);
    if (bookingId) setSelectedBookingId(bookingId);
    window.scrollTo(0, 0);
  }
  function renderPage() {
    switch (currentPage) {
      case "dashboard": return <Dashboard navigate={navigate} />;
      case "bookings":  return <BookingsList navigate={navigate} />;
      case "booking":   return <BookingDetail bookingId={selectedBookingId} navigate={navigate} />;
      case "guests":    return <Guests navigate={navigate} />;
      case "conversations": return <Conversations navigate={navigate} onOpenConversation={markSeen} />;
      case "campaigns": return <Campaigns />; // NEW (17.7.26)
      case "reports":   return <Reports />;
      case "settings":  return <Settings />;
      default:          return <Dashboard navigate={navigate} />;
    }
  }
  return (
    <div className="app-shell">
      <MobileHeader currentPage={currentPage} />
      <Sidebar currentPage={currentPage} navigate={navigate} unreadCount={unreadCount} />
      <main className="main-content">
        {renderPage()}
      </main>
      <BottomNav currentPage={currentPage} navigate={navigate} unreadCount={unreadCount} />
    </div>
  );
}
