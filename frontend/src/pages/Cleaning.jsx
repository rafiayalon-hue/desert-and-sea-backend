// NEW (4.10.26) — יומן ניקיונות: מתי המנקה נכנס (קוד 5555) אחרי כל יציאת אורח.
// הנתונים מגיעים מלוג המנעולים (TTLock) דרך /api/cleaning — לא צריך להזין כלום ידנית.
import { useEffect, useState } from "react";

const API_BASE = import.meta.env.VITE_API_URL
  ? `${import.meta.env.VITE_API_URL}/api`
  : "https://selfless-happiness-production.up.railway.app/api";

const STATUS = {
  done:    { label: "נוקה",       bg: "#e6f4ea", fg: "#1e7b34" },
  missing: { label: "אין כניסה",  bg: "#fdecea", fg: "#b3261e" },
  pending: { label: "ממתין",      bg: "#fff4e5", fg: "#9a5b00" },
};

function fmtDate(iso) {
  if (!iso) return "—";
  const [y, m, d] = iso.split("-");
  const days = ["א׳", "ב׳", "ג׳", "ד׳", "ה׳", "ו׳", "ש׳"];
  const wd = days[new Date(`${iso}T12:00:00`).getDay()];
  return `${wd} ${Number(d)}.${Number(m)}`;
}

function Badge({ status }) {
  const s = STATUS[status] || STATUS.pending;
  return (
    <span style={{ background: s.bg, color: s.fg, padding: "2px 10px",
                   borderRadius: 12, fontSize: 13, fontWeight: 600, whiteSpace: "nowrap" }}>
      {s.label}
    </span>
  );
}

const th = { textAlign: "right", padding: "8px 10px", fontSize: 13, color: "#666",
             borderBottom: "1px solid #ddd", whiteSpace: "nowrap" };
const td = { padding: "8px 10px", borderBottom: "1px solid #eee", fontSize: 14, verticalAlign: "top" };

export default function Cleaning({ navigate }) {
  const [days, setDays] = useState(30);
  const [cabin, setCabin] = useState("all");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/cleaning?days=${days}`);
      if (!res.ok) throw new Error(`שגיאה ${res.status}`);
      setData(await res.json());
    } catch (e) {
      setError(e.message || "שגיאה בטעינה");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, [days]); // eslint-disable-line react-hooks/exhaustive-deps

  const turnovers = (data?.turnovers || []).filter((t) => cabin === "all" || t.cabin === cabin);
  const other = (data?.other || []).filter((o) => cabin === "all" || o.cabin === cabin);
  const missing = turnovers.filter((t) => t.status === "missing").length;
  const done = turnovers.filter((t) => t.status === "done").length;

  const openBooking = (id) => id && navigate && navigate("booking", id);

  return (
    <div dir="rtl">
      <div className="page-header">
        <div>
          <h1 className="page-title">🧹 ניקיונות</h1>
          <p className="page-subtitle">
            כניסות המנקה (קוד {data?.cleaner_code || "5555"}) לפי לוג המנעולים, מול יציאות האורחים
          </p>
        </div>
      </div>

      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center", marginBottom: 16 }}>
        <select className="select" value={days} onChange={(e) => setDays(Number(e.target.value))}>
          <option value={7}>7 ימים</option>
          <option value={30}>30 ימים</option>
          <option value={60}>60 ימים</option>
          <option value={90}>90 ימים</option>
        </select>
        <select className="select" value={cabin} onChange={(e) => setCabin(e.target.value)}>
          <option value="all">שני הצימרים</option>
          <option value="mdbr">מדבר</option>
          <option value="ym">ים</option>
        </select>
        <button className="btn btn-secondary btn-sm" onClick={load} disabled={loading}>
          {loading ? "טוען…" : "רענן"}
        </button>
        {data && (
          <span style={{ fontSize: 14, color: "#555" }}>
            {done} נוקו · {missing > 0
              ? <b style={{ color: "#b3261e" }}>{missing} בלי כניסת מנקה</b>
              : "אין חוסרים"}
          </span>
        )}
      </div>

      {error && <div className="alert alert-warning">{error}</div>}
      {data?.errors && Object.keys(data.errors).length > 0 && (
        <div className="alert alert-warning">
          לא הצלחתי לקרוא חלק מהמנעולים: {Object.entries(data.errors)
            .map(([c, e]) => `${c === "mdbr" ? "מדבר" : "ים"} (${e})`).join(", ")}
        </div>
      )}

      <div className="detail-section">
        <div className="detail-section-title">יציאות אורחים וניקיון</div>
        {!loading && turnovers.length === 0 && <p style={{ color: "#777" }}>אין יציאות בטווח.</p>}
        {turnovers.length > 0 && (
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr>
                  <th style={th}>צימר</th>
                  <th style={th}>יציאה</th>
                  <th style={th}>אורח יוצא</th>
                  <th style={th}>ניקיון</th>
                  <th style={th}>הגעה הבאה</th>
                  <th style={th}>סטטוס</th>
                </tr>
              </thead>
              <tbody>
                {turnovers.map((t) => (
                  <tr key={`${t.cabin}-${t.checkout_date}-${t.booking_out_id}`}>
                    <td style={td}>{t.cabin_name}</td>
                    <td style={td}>{fmtDate(t.checkout_date)}</td>
                    <td style={td}>
                      <a href="#" onClick={(e) => { e.preventDefault(); openBooking(t.booking_out_id); }}>
                        {t.guest_out || "—"}
                      </a>
                    </td>
                    <td style={td}>
                      {t.cleaning ? (
                        <>
                          {t.cleaning.date !== t.checkout_date && <>{fmtDate(t.cleaning.date)} · </>}
                          <b>{t.cleaning.first}</b>
                          {t.cleaning.last !== t.cleaning.first && <> – {t.cleaning.last}</>}
                          {t.cleaning.entries > 1 && (
                            <span style={{ color: "#888", fontSize: 12 }}> ({t.cleaning.entries} כניסות)</span>
                          )}
                        </>
                      ) : "—"}
                    </td>
                    <td style={td}>
                      {t.next_checkin ? (
                        <>
                          {fmtDate(t.next_checkin)}{" "}
                          <a href="#" onClick={(e) => { e.preventDefault(); openBooking(t.booking_in_id); }}
                             style={{ color: "#666", fontSize: 13 }}>
                            {t.guest_in}
                          </a>
                        </>
                      ) : "—"}
                    </td>
                    <td style={td}><Badge status={t.status} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p style={{ fontSize: 12, color: "#888", marginTop: 8 }}>
          "ניקיון" = כניסה ראשונה ואחרונה של המנקה באותו יום. המנעול רושם כניסות בלבד, לא יציאות.
        </p>
      </div>

      {other.length > 0 && (
        <div className="detail-section" style={{ marginTop: 16 }}>
          <div className="detail-section-title">כניסות מנקה נוספות (לא אחרי יציאת אורח)</div>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <tbody>
              {other.map((o) => (
                <tr key={`${o.cabin}-${o.date}`}>
                  <td style={td}>{o.cabin_name}</td>
                  <td style={td}>{fmtDate(o.date)}</td>
                  <td style={td}>
                    <b>{o.first}</b>{o.last !== o.first && <> – {o.last}</>}
                    {o.entries > 1 && <span style={{ color: "#888", fontSize: 12 }}> ({o.entries} כניסות)</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
