import { useState, useEffect } from "react";

const API_BASE = import.meta.env.VITE_API_URL
  ? `${import.meta.env.VITE_API_URL}/api`
  : "https://selfless-happiness-production.up.railway.app/api";

const ROOM_LABELS = { desert: "🏜 מדבר (דלת חומה)", sea: "🌊 ים (דלת כחולה)" };

function formatMs(ms) {
  if (!ms) return "—";
  return new Date(Number(ms)).toLocaleString("he-IL", {
    day: "2-digit", month: "2-digit", year: "2-digit", hour: "2-digit", minute: "2-digit",
  });
}

function PasscodeRow({ room, code, onDeleted }) {
  const [deleting, setDeleting] = useState(false);

  async function handleDelete() {
    const label = code.is_orphan
      ? `הקוד ${code.passcode} (יתום, בלי הזמנה מתאימה)`
      : `הקוד ${code.passcode} (${code.guest_name || "?"})`;
    if (!window.confirm(`למחוק את ${label} מהמנעול? אי אפשר לבטל.`)) return;
    setDeleting(true);
    try {
      const res = await fetch(`${API_BASE}/locks/${room}/passcodes/${code.keyboardPwdId}`, { method: "DELETE" });
      if (!res.ok) throw new Error(`status ${res.status}`);
      onDeleted();
    } catch {
      alert("מחיקה נכשלה — נסה שוב");
      setDeleting(false);
    }
  }

  return (
    <div style={{
      display: "flex", justifyContent: "space-between", alignItems: "center",
      padding: "10px 14px", borderRadius: 10, marginBottom: 6,
      background: code.is_orphan ? "#FFF0EE" : "var(--bg-card)",
      border: `1px solid ${code.is_orphan ? "#F5B4AC" : "var(--border-card)"}`,
    }}>
      <div>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontFamily: "monospace", fontWeight: 700, fontSize: "1rem" }}>{code.passcode}</span>
          <span style={{ fontSize: ".85rem", fontWeight: 600 }}>{code.name || "—"}</span>
          {code.is_orphan ? (
            <span style={{ fontSize: ".68rem", background: "var(--terra)", color: "#fff", padding: "2px 8px", borderRadius: 20, fontWeight: 700 }}>
              יתום — אין הזמנה תואמת
            </span>
          ) : (
            <span style={{ fontSize: ".68rem", background: "#E8F5EE", color: "var(--success)", padding: "2px 8px", borderRadius: 20, fontWeight: 700 }}>
              תקין
            </span>
          )}
        </div>
        <div style={{ fontSize: ".75rem", color: "var(--text-muted)", marginTop: 3 }}>
          {formatMs(code.startDate)} → {formatMs(code.endDate)}
          {!code.is_orphan && code.booking_id && (
            <span> · הזמנה #{code.booking_id}</span>
          )}
        </div>
      </div>
      <button
        className="btn btn-secondary"
        style={{ fontSize: ".75rem", padding: "5px 10px", color: "var(--terra)" }}
        onClick={handleDelete}
        disabled={deleting}
      >
        {deleting ? "מוחק..." : "🗑️ מחק"}
      </button>
    </div>
  );
}

function RoomSection({ room, codes, loading, onDeleted }) {
  const orphanCount = codes.filter(c => c.is_orphan).length;
  return (
    <div className="detail-section" style={{ marginBottom: 18 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
        <div className="detail-section-title" style={{ marginBottom: 0, paddingBottom: 0, border: "none" }}>
          {ROOM_LABELS[room] || room}
        </div>
        {orphanCount > 0 && (
          <span style={{ fontSize: ".75rem", color: "var(--terra)", fontWeight: 700 }}>
            {orphanCount} יתומים
          </span>
        )}
      </div>
      {loading ? (
        <div style={{ color: "var(--text-muted)", fontSize: ".85rem" }}>טוען...</div>
      ) : codes.length === 0 ? (
        <div style={{ color: "var(--text-muted)", fontSize: ".85rem" }}>אין קודים פעילים במנעול</div>
      ) : (
        codes.map(c => (
          <PasscodeRow key={c.keyboardPwdId} room={room} code={c} onDeleted={onDeleted} />
        ))
      )}
    </div>
  );
}

export default function LockManagement() {
  const [audit, setAudit]     = useState({ desert: [], sea: [] });
  const [loading, setLoading] = useState(true);

  function loadAudit() {
    setLoading(true);
    fetch(`${API_BASE}/locks/audit`)
      .then(r => r.json())
      .then(data => { setAudit(data); setLoading(false); })
      .catch(() => setLoading(false));
  }

  useEffect(loadAudit, []);

  const totalOrphans = ["desert", "sea"].reduce(
    (sum, room) => sum + (audit[room] || []).filter(c => c.is_orphan).length, 0
  );

  return (
    <div style={{ maxWidth: 700 }}>
      <div className="page-header">
        <div>
          <div className="page-title">ניהול מנעולים</div>
          {totalOrphans > 0 && (
            <div className="page-subtitle">{totalOrphans} קודים יתומים ברחבי שני המנעולים</div>
          )}
        </div>
      </div>

      <div style={{ fontSize: ".8rem", color: "var(--text-muted)", marginBottom: 16, padding: "8px 12px", background: "var(--sand-bg)", borderRadius: 8 }}>
        "יתום" = קוד שקיים בפועל במנעול, אבל אין הזמנה פעילה שמכירה אותו (למשל ניקוי אוטומטי שנכשל). בטוח למחוק, אלא אם אתה יודע שהוא עדיין בשימוש.
      </div>

      <RoomSection room="desert" codes={audit.desert || []} loading={loading} onDeleted={loadAudit} />
      <RoomSection room="sea"    codes={audit.sea    || []} loading={loading} onDeleted={loadAudit} />

      <button className="btn btn-secondary" onClick={loadAudit}>🔄 רענן</button>
    </div>
  );
}
