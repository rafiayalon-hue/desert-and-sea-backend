import { useState } from "react";
import { useBookings } from "../hooks/useBookings";
import { API_BASE } from "../hooks/useGuests";

function useIsMobile() {
  return window.innerWidth <= 768;
}

// NEW (16.7.26): מחיקת הזמנה בלתי הפיכה — דורשת אישור מפורש, ועוצרת את
// אירוע הלחיצה על השורה (stopPropagation) כדי לא לפתוח בטעות את פרטי
// ההזמנה כשלוחצים על הפח. אחרי מחיקה — רענון מלא של הדף, כי useBookings
// (בניגוד ל-useGuests) עוד לא תומך ברענון חלקי.
async function deleteBooking(e, bookingId) {
  e.stopPropagation();
  if (!window.confirm("למחוק את ההזמנה הזו לצמיתות? אי אפשר לבטל פעולה זו.")) {
    return;
  }
  try {
    const res = await fetch(`${API_BASE}/bookings/${bookingId}`, { method: "DELETE" });
    if (!res.ok) throw new Error(`status ${res.status}`);
    window.location.reload();
  } catch (err) {
    console.error("[BookingsList] delete booking failed:", err);
    alert("מחיקת ההזמנה נכשלה — נסה שוב");
  }
}

function DeleteButton({ bookingId }) {
  return (
    <button
      title="מחיקת הזמנה"
      onClick={e => deleteBooking(e, bookingId)}
      style={{
        background: "none", border: "none", cursor: "pointer",
        color: "var(--text-muted)", fontSize: "1rem", padding: 4, lineHeight: 1,
      }}
    >
      🗑️
    </button>
  );
}

export default function BookingsList({ navigate }) {
  const [search,   setSearch]   = useState("");
  const [status,   setStatus]   = useState("");
  const [room,     setRoom]     = useState("");
  const [source,   setSource]   = useState("");
  const [upcoming, setUpcoming] = useState(false);

  const { bookings, loading } = useBookings({
    status: status || undefined,
    room:   room   || undefined,
    source: source || undefined,
    upcoming,
    search,
  });

  const confirmed = bookings.filter(b => b.status === "confirmed").length;
  const cancelled = bookings.filter(b => b.status === "cancelled").length;
  const isMobile  = window.innerWidth <= 768;

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="page-title">הזמנות</div>
          <div className="page-subtitle">
            {confirmed} מאושרות · {cancelled} מבוטלות · סה"כ {bookings.length}
          </div>
        </div>
      </div>

      {/* Filters */}
      <div className="filters-bar">
        <input
          className="search-input"
          placeholder="חיפוש לפי שם, מספר הזמנה..."
          value={search}
          onChange={e => setSearch(e.target.value)}
        />
        <button className={`filter-btn ${upcoming ? "active" : ""}`} onClick={() => setUpcoming(!upcoming)}>עתידיות</button>
        <button className={`filter-btn ${status === "confirmed" ? "active" : ""}`} onClick={() => setStatus(status === "confirmed" ? "" : "confirmed")}>מאושרות</button>
        <button className={`filter-btn ${status === "cancelled" ? "active" : ""}`} onClick={() => setStatus(status === "cancelled" ? "" : "cancelled")}>מבוטלות</button>
        <button className={`filter-btn ${room === "desert" ? "active" : ""}`}
          style={room === "desert" ? { background: "var(--desert-color)", borderColor: "var(--desert-color)" } : {}}
          onClick={() => setRoom(room === "desert" ? "" : "desert")}>🏜️ מדבר</button>
        <button className={`filter-btn ${room === "sea" ? "active" : ""}`}
          style={room === "sea" ? { background: "var(--teal)", borderColor: "var(--teal)" } : {}}
          onClick={() => setRoom(room === "sea" ? "" : "sea")}>🌊 ים</button>
        <button className={`filter-btn ${source === "airbnb" ? "active" : ""}`} onClick={() => setSource(source === "airbnb" ? "" : "airbnb")}>Airbnb</button>
        <button className={`filter-btn ${source === "direct" ? "active" : ""}`} onClick={() => setSource(source === "direct" ? "" : "direct")}>ישיר</button>
      </div>

      {/* Table / Cards */}
      <div className="bookings-table">
        {/* Desktop header */}
        <div className="table-header">
          <div>מס'</div>
          <div>אורח</div>
          <div>כניסה</div>
          <div>יציאה</div>
          <div>חדר</div>
          <div>מקור</div>
          <div>סטטוס</div>
          <div></div>
        </div>

        {loading && (
          <div style={{ padding: 32, textAlign: "center", color: "var(--text-muted)" }}>טוען...</div>
        )}

        {!loading && bookings.length === 0 && (
          <div style={{ padding: 32, textAlign: "center", color: "var(--text-muted)" }}>לא נמצאו הזמנות</div>
        )}

        {bookings.map(b => (
          isMobile ? (
            /* Mobile card */
            <div
              key={b.id}
              className={`table-row ${b.status === "cancelled" ? "cancelled" : ""}`}
              onClick={() => navigate("booking", b.id)}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                <div className="table-row-name">{b.full_name}</div>
                <DeleteButton bookingId={b.id} />
              </div>
              <div className="table-row-meta">
                <span>📅 {b.checkin_label} → {b.checkout_label}</span>
                <span>· {b.nights} לילות</span>
              </div>
              <div className="table-row-badges">
                <span className={`room-tag ${b.room_color}`}>{b.room_display}</span>
                <span className={`status-badge ${b.status}`}>{b.status_label}</span>
                <span className="source-badge">{b.source_label}</span>
              </div>
              {b.cancellation_label && (
                <div style={{ fontSize: ".72rem", color: "var(--text-muted)", marginTop: 2 }}>
                  {b.cancellation_label}
                </div>
              )}
            </div>
          ) : (
            /* Desktop row */
            <div
              key={b.id}
              className={`table-row ${b.status === "cancelled" ? "cancelled" : ""}`}
              onClick={() => navigate("booking", b.id)}
            >
              <div style={{ fontFamily: "monospace", fontSize: ".78rem", color: "var(--text-muted)" }}>
                {String(b.id || "").slice(-4)}
              </div>
              <div>
                <div style={{ fontWeight: 600 }}>{b.full_name}</div>
                {b.cancellation_label && (
                  <div style={{ fontSize: ".72rem", color: "var(--text-muted)", marginTop: 2 }}>
                    {b.cancellation_label}
                  </div>
                )}
              </div>
              <div style={{ fontSize: ".85rem" }}>{b.checkin_label}</div>
              <div style={{ fontSize: ".85rem" }}>{b.checkout_label}</div>
              <div><span className={`room-tag ${b.room_color}`}>{b.room_display}</span></div>
              <div className="source-badge">{b.source_label}</div>
              <div><span className={`status-badge ${b.status}`}>{b.status_label}</span></div>
              <div><DeleteButton bookingId={b.id} /></div>
            </div>
          )
        ))}
      </div>
    </div>
  );
}
