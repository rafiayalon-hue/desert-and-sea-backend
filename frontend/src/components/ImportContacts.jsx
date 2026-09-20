// NEW (20.9.26): עדכון שקט של טלפונים ושמות מקובץ Excel — בלי הודעות וואטסאפ.
// הקובץ: עמודות minihotel_id, טלפון, שם אורח (כמו "רשימת חוסרים" שמורידים מהדשבורד/מ-Claude).
// הזמנות עתידיות או שיצאו ב-8 הימים האחרונים לא מתעדכנות כאן (היו מפעילות הודעות) —
// אותן מזינים ידנית בדף ההזמנה.
import { useState } from "react";

const API_BASE = import.meta.env.VITE_API_URL || "https://selfless-happiness-production.up.railway.app";

export default function ImportContacts() {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  const handleUpload = async (e) => {
    const file = e.target.files[0];
    e.target.value = "";
    if (!file) return;
    setLoading(true); setResult(null); setError(null);
    const formData = new FormData();
    formData.append("file", file);
    try {
      const res = await fetch(`${API_BASE}/api/bookings/import-contacts`, { method: "POST", body: formData });
      const data = await res.json();
      if (!res.ok) setError(data.detail || `שגיאה ${res.status}`);
      else setResult(data);
    } catch {
      setError("שגיאה בהעלאה");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ marginTop: 16 }}>
      <div style={{ fontSize: ".8rem", color: "var(--text-muted)", marginBottom: 8 }}>
        השלמת טלפונים ושמות לאורחי עבר מקובץ Excel — <b>לא נשלחות הודעות</b>
      </div>
      <input type="file" accept=".xlsx" onChange={handleUpload} style={{ display: "none" }} id="contacts-upload" />
      <label htmlFor="contacts-upload" className="btn btn-secondary" style={{ cursor: "pointer" }}>
        {loading ? "מעדכן..." : "📇 עדכון טלפונים ושמות"}
      </label>
      {result && (
        <div style={{ marginTop: 10, fontSize: ".85rem" }}>
          <div style={{ color: "var(--success)" }}>
            ✅ עודכנו {result.phones_updated} טלפונים ו-{result.names_updated} שמות · נשלחו 0 הודעות
          </div>
          {result.future_skipped?.length > 0 && (
            <div style={{ color: "var(--warning)", marginTop: 4 }}>
              ⚠ {result.future_skipped.length} הזמנות עתידיות/אחרונות לא עודכנו (להזין ידנית בדף ההזמנה):{" "}
              {result.future_skipped.map(b => b.guest_name).join(", ")}
            </div>
          )}
          {result.not_found?.length > 0 && (
            <div style={{ color: "var(--text-muted)", marginTop: 4 }}>
              לא נמצאו: {result.not_found.join(", ")}
            </div>
          )}
        </div>
      )}
      {error && <div style={{ marginTop: 10, fontSize: ".85rem", color: "var(--error)" }}>❌ {error}</div>}
    </div>
  );
}
