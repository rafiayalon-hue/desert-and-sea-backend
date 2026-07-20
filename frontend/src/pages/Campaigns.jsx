import { useState, useEffect } from "react";

const API_BASE = import.meta.env.VITE_API_URL
  ? `${import.meta.env.VITE_API_URL}/api`
  : "https://selfless-happiness-production.up.railway.app/api";

function formatDate(d) {
  if (!d) return "";
  return new Date(d).toLocaleDateString("he-IL", { day: "2-digit", month: "2-digit", year: "numeric" });
}

// NEW (17.7.26): מחלץ ספרות בלבד + ממיר לפורמט בינלאומי, בשביל קישור
// wa.me — זה פותח את WhatsApp האישי במכשיר (לא דרך Twilio), בדיוק כמו
// שסוכם: פנייה אישית, לא הודעה אוטומטית.
function waLink(phone) {
  let digits = (phone || "").replace(/\D/g, "");
  if (digits.startsWith("00")) {
    // כבר כולל קידומת מדינה בפורמט חיוג בינלאומי (00+קוד מדינה) —
    // רק מסירים את ה"00", לא מוסיפים 972 (זה היה הבאג — ראו ביקורת 17.7.26)
    digits = digits.slice(2);
  } else if (digits.startsWith("0")) {
    digits = "972" + digits.slice(1);
  }
  return `https://wa.me/${digits}`;
}

function GuestOutreachRow({ guest }) {
  return (
    <div style={{
      background: "var(--bg-card)", border: "1px solid var(--border-card)",
      borderRadius: 12, padding: "14px 16px", marginBottom: 10, boxShadow: "var(--shadow-sm)",
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 8 }}>
        <div>
          <div style={{ fontWeight: 700, fontSize: "1rem" }}>{guest.guest_name || "אורח ללא שם"}</div>
          <div style={{ fontSize: ".78rem", color: "var(--text-muted)", marginTop: 2 }}>
            שהו אחרון: {formatDate(guest.last_checkout)} · {guest.last_room || "—"}
          </div>
        </div>
      </div>

      <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
        {guest.phone ? (
          <a
            href={waLink(guest.phone)}
            target="_blank"
            rel="noreferrer"
            style={{
              display: "flex", alignItems: "center", gap: 8,
              background: "#25D366", color: "#fff", textDecoration: "none",
              borderRadius: 10, padding: "9px 16px", fontWeight: 700, fontSize: "1rem",
              direction: "ltr",
            }}
          >
            💬 {guest.phone}
          </a>
        ) : (
          <span style={{ fontSize: ".8rem", color: "var(--text-muted)" }}>אין טלפון</span>
        )}

        {guest.email && (
          <a
            href={`mailto:${guest.email}`}
            style={{
              display: "flex", alignItems: "center", gap: 6,
              background: "var(--sand-bg)", color: "var(--text-primary)", textDecoration: "none",
              borderRadius: 10, padding: "9px 14px", fontSize: ".85rem", border: "1px solid var(--border-card)",
            }}
          >
            ✉️ {guest.email}
          </a>
        )}
      </div>
    </div>
  );
}

export default function Campaigns() {
  const [guests, setGuests]   = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch]   = useState("");
  const [monthsBack, setMonthsBack] = useState(12);

  useEffect(() => {
    setLoading(true);
    fetch(`${API_BASE}/campaigns/winback?months_back=${monthsBack}`)
      .then(r => r.json())
      .then(data => { setGuests(data); setLoading(false); })
      .catch(() => setLoading(false));
  }, [monthsBack]);

  const filtered = guests.filter(g => {
    const q = search.toLowerCase();
    return !q || (g.guest_name || "").toLowerCase().includes(q) || (g.phone || "").includes(q);
  });

  return (
    <div style={{ maxWidth: 700 }}>
      <div className="page-header">
        <div>
          <div className="page-title">קמפיינים</div>
          <div className="page-subtitle">אורחי עבר שטרם הזמינו שוב — לפנייה אישית ישירה</div>
        </div>
      </div>

      {/* פרטי קשר של הצימרים — בולט, לשימוש מהיר */}
      <div style={{
        background: "var(--terra-bg)", border: "1px solid var(--terra)", borderRadius: 12,
        padding: "14px 16px", marginBottom: 16, display: "flex", alignItems: "center",
        justifyContent: "space-between", flexWrap: "wrap", gap: 10,
      }}>
        <div>
          <div style={{ fontWeight: 700, fontSize: ".95rem" }}>📞 מספר הצימרים</div>
          <div style={{ fontSize: ".8rem", color: "var(--text-muted)" }}>לשליחה/הפניית אורחים</div>
        </div>
        <a href="tel:0523730377" style={{
          fontSize: "1.3rem", fontWeight: 800, color: "var(--terra)", textDecoration: "none", direction: "ltr",
        }}>
          052-3730377
        </a>
      </div>

      <div style={{ display: "flex", gap: 10, marginBottom: 14, alignItems: "center", flexWrap: "wrap" }}>
        <input className="search-input" style={{ flex: 1, minWidth: 200 }}
          placeholder="🔍 חיפוש לפי שם או טלפון..."
          value={search} onChange={e => setSearch(e.target.value)} />
        <select className="input" style={{ width: "auto" }} value={monthsBack} onChange={e => setMonthsBack(Number(e.target.value))}>
          <option value={3}>3 חודשים אחרונים</option>
          <option value={6}>6 חודשים אחרונים</option>
          <option value={12}>שנה אחרונה</option>
          <option value={24}>שנתיים אחרונות</option>
        </select>
      </div>

      <div style={{ fontSize: ".8rem", color: "var(--text-muted)", marginBottom: 10 }}>
        {filtered.length} אורחים
      </div>

      {loading
        ? <div style={{ textAlign: "center", color: "var(--text-muted)", padding: 40 }}>טוען...</div>
        : filtered.length === 0
          ? <div style={{ textAlign: "center", color: "var(--text-muted)", padding: 40 }}>אין אורחים מתאימים בטווח שנבחר</div>
          : filtered.map((g, i) => <GuestOutreachRow key={g.phone || g.email || i} guest={g} />)
      }
    </div>
  );
}
