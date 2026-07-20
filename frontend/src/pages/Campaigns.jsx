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

function formatDate2(d) {
  if (!d) return "";
  return new Date(d).toLocaleDateString("he-IL", { day: "2-digit", month: "2-digit", year: "2-digit" });
}

// NEW (18.7.26): מעקב קמפיינים — קליל ופשוט, מיועד לאבישג. שם + פלטפורמה
// + תאריכים (+ תקציב אופציונלי), והתוצאות (הזמנות/הכנסה) מחושבות לבד.
function CampaignTracker() {
  const [campaigns, setCampaigns] = useState([]);
  const [loading, setLoading]     = useState(true);
  const [showForm, setShowForm]   = useState(false);
  const [saving, setSaving]       = useState(false);
  const [form, setForm] = useState({
    name: "", platform: "פייסבוק", start_date: "", end_date: "", budget: "",
  });

  function load() {
    setLoading(true);
    fetch(`${API_BASE}/campaigns/list`)
      .then(r => r.json())
      .then(data => { setCampaigns(data); setLoading(false); })
      .catch(() => setLoading(false));
  }

  useEffect(load, []);

  async function addCampaign() {
    if (!form.name || !form.start_date || !form.end_date) return;
    setSaving(true);
    try {
      await fetch(`${API_BASE}/campaigns/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: form.name,
          platform: form.platform,
          start_date: form.start_date,
          end_date: form.end_date,
          budget: form.budget ? Number(form.budget) : null,
        }),
      });
      setForm({ name: "", platform: "פייסבוק", start_date: "", end_date: "", budget: "" });
      setShowForm(false);
      load();
    } catch {
      alert("שמירת הקמפיין נכשלה");
    }
    setSaving(false);
  }

  async function removeCampaign(id) {
    if (!window.confirm("למחוק את הקמפיין הזה?")) return;
    await fetch(`${API_BASE}/campaigns/${id}`, { method: "DELETE" });
    load();
  }

  return (
    <div style={{ marginBottom: 24 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <div className="page-title" style={{ fontSize: "1.1rem" }}>📣 מעקב קמפיינים</div>
        <button className="btn btn-primary" style={{ fontSize: ".82rem", padding: "6px 14px" }}
          onClick={() => setShowForm(!showForm)}>
          {showForm ? "ביטול" : "+ קמפיין חדש"}
        </button>
      </div>

      {showForm && (
        <div style={{ background: "var(--bg-card)", border: "1px solid var(--border-card)", borderRadius: 12, padding: 16, marginBottom: 14 }}>
          <div style={{ marginBottom: 10 }}>
            <div style={{ fontSize: ".78rem", color: "var(--text-muted)", marginBottom: 4 }}>שם הקמפיין</div>
            <input className="input" value={form.name} onChange={e => setForm({ ...form, name: e.target.value })}
              placeholder="למשל: 2+1 קיץ, מילואימניקים" />
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: 10 }}>
            <div>
              <div style={{ fontSize: ".78rem", color: "var(--text-muted)", marginBottom: 4 }}>פלטפורמה</div>
              <select className="input" value={form.platform} onChange={e => setForm({ ...form, platform: e.target.value })}>
                <option>פייסבוק</option>
                <option>אינסטגרם</option>
                <option>שניהם</option>
                <option>אחר</option>
              </select>
            </div>
            <div>
              <div style={{ fontSize: ".78rem", color: "var(--text-muted)", marginBottom: 4 }}>תקציב (₪, אופציונלי)</div>
              <input className="input" type="number" value={form.budget} onChange={e => setForm({ ...form, budget: e.target.value })} />
            </div>
            <div>
              <div style={{ fontSize: ".78rem", color: "var(--text-muted)", marginBottom: 4 }}>תאריך התחלה</div>
              <input className="input" type="date" value={form.start_date} onChange={e => setForm({ ...form, start_date: e.target.value })} />
            </div>
            <div>
              <div style={{ fontSize: ".78rem", color: "var(--text-muted)", marginBottom: 4 }}>תאריך סיום</div>
              <input className="input" type="date" value={form.end_date} onChange={e => setForm({ ...form, end_date: e.target.value })} />
            </div>
          </div>
          <button className="btn btn-primary" onClick={addCampaign} disabled={saving}>
            {saving ? "שומר..." : "שמור קמפיין"}
          </button>
        </div>
      )}

      {loading ? (
        <div style={{ color: "var(--text-muted)", fontSize: ".85rem" }}>טוען...</div>
      ) : campaigns.length === 0 ? (
        <div style={{ color: "var(--text-muted)", fontSize: ".85rem", padding: "10px 0" }}>אין קמפיינים רשומים עדיין</div>
      ) : (
        campaigns.map(c => (
          <div key={c.id} style={{
            background: "var(--bg-card)", border: "1px solid var(--border-card)", borderRadius: 12,
            padding: "12px 16px", marginBottom: 8, boxShadow: "var(--shadow-sm)",
          }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
              <div>
                <div style={{ fontWeight: 700 }}>{c.name}</div>
                <div style={{ fontSize: ".78rem", color: "var(--text-muted)" }}>
                  {c.platform} · {formatDate2(c.start_date)} — {formatDate2(c.end_date)}
                  {c.budget != null && ` · תקציב ₪${c.budget.toLocaleString("he-IL")}`}
                </div>
              </div>
              <button onClick={() => removeCampaign(c.id)} style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text-muted)" }}>🗑️</button>
            </div>
            <div style={{ display: "flex", gap: 16, marginTop: 8 }}>
              <div style={{ fontSize: ".85rem" }}>
                <span style={{ fontWeight: 700, color: "var(--terra)" }}>{c.bookings_count}</span> הזמנות ישירות בטווח
              </div>
              <div style={{ fontSize: ".85rem" }}>
                <span style={{ fontWeight: 700, color: "var(--terra)" }}>₪{c.revenue.toLocaleString("he-IL")}</span> הכנסה
              </div>
            </div>
          </div>
        ))
      )}
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

      <CampaignTracker />

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
