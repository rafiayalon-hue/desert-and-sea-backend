// NEW (25.10.26) — תפעול: הכנת צימר להגעה + תשלום וקבלה אחרי יציאה.
// כל הסימונים ידניים (רפי ואבישג). "המנקה נכנס" מגיע אוטומטית מלוג המנעולים (/api/cleaning).
import { useCallback, useEffect, useMemo, useState } from "react";

const API_BASE = import.meta.env.VITE_API_URL
  ? `${import.meta.env.VITE_API_URL}/api`
  : "https://selfless-happiness-production.up.railway.app/api";

const PREP = {
  dirty:   { label: "מלוכלך",     bg: "#fdecea", fg: "#b3261e", icon: "🔴" },
  partial: { label: "מוכן חלקית", bg: "#fff4e5", fg: "#9a5b00", icon: "🟠" },
  clean:   { label: "נקי",        bg: "#e6f4ea", fg: "#1e7b34", icon: "🟢" },
};

const PAY_COLORS = {
  unpaid:    { bg: "#fdecea", fg: "#b3261e" },
  link_sent: { bg: "#fff4e5", fg: "#9a5b00" },
  paid:      { bg: "#e6f4ea", fg: "#1e7b34" },
};

function payOptions(isAirbnb) {
  return isAirbnb
    ? [{ v: "unpaid", label: "ממתין להעברה" }, { v: "paid", label: "התקבל" }]
    : [{ v: "unpaid", label: "לא שולם" }, { v: "link_sent", label: "קישור נשלח" }, { v: "paid", label: "שולם" }];
}

function payLabel(status, isAirbnb) {
  return (payOptions(isAirbnb).find(o => o.v === status) || { label: status }).label;
}

function fmtDate(iso) {
  if (!iso) return "—";
  const [, m, d] = iso.split("-");
  const days = ["א׳", "ב׳", "ג׳", "ד׳", "ה׳", "ו׳", "ש׳"];
  const wd = days[new Date(`${iso}T12:00:00`).getDay()];
  return `${wd} ${Number(d)}.${Number(m)}`;
}

function daysFrom(todayIso, iso) {
  return Math.round((new Date(`${iso}T12:00:00`) - new Date(`${todayIso}T12:00:00`)) / 86400000);
}

function relDay(n) {
  if (n === 0) return "היום";
  if (n === 1) return "מחר";
  if (n === -1) return "אתמול";
  return n > 0 ? `בעוד ${n} ימים` : `לפני ${-n} ימים`;
}

async function patchOps(id, body) {
  const res = await fetch(`${API_BASE}/ops/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`שגיאה ${res.status}`);
  return res.json();
}

const card = {
  background: "var(--bg-card, #fff)", border: "1px solid var(--border-card, #eee)",
  borderRadius: 12, padding: "12px 14px", marginBottom: 10,
  boxShadow: "0 1px 3px rgba(0,0,0,.05)",
};

function Chip({ bg, fg, children, onClick, title }) {
  return (
    <span onClick={onClick} title={title}
      style={{ background: bg, color: fg, padding: "2px 10px", borderRadius: 12, fontSize: 12.5,
               fontWeight: 600, whiteSpace: "nowrap", cursor: onClick ? "pointer" : "default" }}>
      {children}
    </span>
  );
}

function SegBtn({ active, onClick, children, color }) {
  return (
    <button onClick={onClick}
      style={{
        flex: 1, padding: "8px 6px", fontSize: 13, fontWeight: 600, cursor: "pointer",
        borderRadius: 8, border: `1.5px solid ${active ? (color?.fg || "#A84D3A") : "#ddd"}`,
        background: active ? (color?.bg || "#F9EDE9") : "#fff",
        color: active ? (color?.fg || "#A84D3A") : "#666",
      }}>
      {children}
    </button>
  );
}

// ───────────────────────── הגעות + הכנה ─────────────────────────

function ArrivalCard({ a, today, cleaner, onChange }) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);

  const effective = a.prep_status === "dirty" && cleaner ? "partial" : a.prep_status;
  const p = PREP[effective];
  const inDays = daysFrom(today, a.check_in);
  const stillOccupied = a.prev.some(x => !x.vacated);

  const items = [
    { key: "milk", label: a.milk ? `חלב — ${a.milk}` : "חלב (סוג לא ידוע)" },
    { key: "notes", label: "פתקים" },
    { key: "balconies", label: "מרפסות (אם נדרש)" },
    ...(a.gift_needed ? [{ key: "gift", label: "יין / תשורה" }] : []),
    { key: "inspected", label: "נבדק אחרי המנקה" },
  ];

  async function save(body) {
    setBusy(true);
    try {
      const state = await patchOps(a.booking_id, body);
      onChange(a.booking_id, state);
    } catch (e) {
      alert("השמירה נכשלה, נסו שוב");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ ...card, opacity: busy ? 0.7 : 1, borderRight: `5px solid ${p.fg}` }}>
      <div onClick={() => setOpen(!open)} style={{ cursor: "pointer" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
          <div style={{ fontWeight: 700, fontSize: 15 }}>
            {a.cabins.join(" + ")} · {a.guest_name}
          </div>
          <Chip bg={p.bg} fg={p.fg}>{p.icon} {p.label}</Chip>
        </div>
        <div style={{ fontSize: 13, color: "#666", marginTop: 4 }}>
          הגעה {fmtDate(a.check_in)} ({relDay(inDays)}) · {a.nights} לילות
          {a.adults ? ` · ${a.adults} מבוגרים` : ""}{a.children ? ` + ${a.children} ילדים` : ""}
        </div>
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 6 }}>
          {stillOccupied && (
            <Chip bg="#eee" fg="#555">
              תפוס עד {fmtDate(a.prev.find(x => !x.vacated).check_out)}
            </Chip>
          )}
          {cleaner && <Chip bg="#e8f0fe" fg="#1a56c4">🧹 המנקה נכנס {fmtDate(cleaner.date)} {cleaner.first}</Chip>}
          {a.milk && <Chip bg="#f3ece6" fg="#7a4a35">🥛 {a.milk}</Chip>}
          {a.gift_needed && <Chip bg="#fdeef5" fg="#a0275f">🎁 תשורה</Chip>}
          {!a.gift_needed && a.is_returning && (
            <Chip bg="#fdeef5" fg="#a0275f" title="לחצו להוספה לרשימה"
              onClick={(e) => { e.stopPropagation(); save({ gift_needed: true }); }}>
              🎁 לקוח חוזר — להוסיף יין/תשורה?
            </Chip>
          )}
        </div>
      </div>

      {open && (
        <div style={{ marginTop: 12, borderTop: "1px solid #eee", paddingTop: 10 }}>
          <div style={{ display: "flex", gap: 6, marginBottom: 10 }}>
            {Object.entries(PREP).map(([k, v]) => (
              <SegBtn key={k} active={effective === k} color={v}
                onClick={() => save({ prep_status: k })}>
                {v.icon} {v.label}
              </SegBtn>
            ))}
          </div>

          {items.map(it => {
            const done = !!a.checklist[it.key];
            return (
              <label key={it.key}
                style={{ display: "flex", alignItems: "center", gap: 10, padding: "9px 4px",
                         borderBottom: "1px solid #f3f3f3", cursor: "pointer", fontSize: 15 }}>
                <input type="checkbox" checked={done} style={{ width: 20, height: 20 }}
                  onChange={() => save({ checklist: { [it.key]: !done } })} />
                <span style={{ textDecoration: done ? "line-through" : "none", color: done ? "#999" : "inherit" }}>
                  {it.label}
                </span>
              </label>
            );
          })}

          <label style={{ display: "flex", alignItems: "center", gap: 10, padding: "10px 4px 2px",
                          fontSize: 13.5, color: "#666", cursor: "pointer" }}>
            <input type="checkbox" checked={a.gift_needed} style={{ width: 18, height: 18 }}
              onChange={() => save({ gift_needed: !a.gift_needed })} />
            🎂 יום הולדת / יין / תשורה
          </label>

          <div style={{ fontSize: 12, color: "#999", marginTop: 8 }}>
            כשכל הפריטים (חוץ ממרפסות) מסומנים — הצימר עובר ל"נקי" אוטומטית.
          </div>
        </div>
      )}
    </div>
  );
}

// ───────────────────────── תשלומים + קבלות ─────────────────────────

function PaymentCard({ p, today, onChange }) {
  const [busy, setBusy] = useState(false);
  const out = daysFrom(today, p.check_out);
  const needsReceipt = p.pay_status === "paid" && !p.receipt_issued;
  const color = PAY_COLORS[p.pay_status];

  async function save(body) {
    setBusy(true);
    try {
      const state = await patchOps(p.booking_id, body);
      onChange(p.booking_id, state);
    } catch (e) {
      alert("השמירה נכשלה, נסו שוב");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ ...card, opacity: busy ? 0.7 : 1, borderRight: `5px solid ${needsReceipt ? "#1a56c4" : color.fg}` }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
        <div style={{ fontWeight: 700, fontSize: 15 }}>{p.cabins.join(" + ")} · {p.guest_name}</div>
        <Chip bg={color.bg} fg={color.fg}>{payLabel(p.pay_status, p.is_airbnb)}</Chip>
      </div>
      <div style={{ fontSize: 13, color: "#666", marginTop: 4 }}>
        יציאה {fmtDate(p.check_out)} ({relDay(out)}) · {p.is_airbnb ? "Airbnb" : "ישיר/אתר"}
        {p.total_price ? ` · ₪${Math.round(p.total_price).toLocaleString("he-IL")}` : ""}
        {p.balance > 0 && !p.is_airbnb ? ` · יתרה ₪${Math.round(p.balance).toLocaleString("he-IL")}` : ""}
      </div>

      <div style={{ display: "flex", gap: 6, marginTop: 10 }}>
        {payOptions(p.is_airbnb).map(o => (
          <SegBtn key={o.v} active={p.pay_status === o.v} color={PAY_COLORS[o.v]}
            onClick={() => save({ pay_status: o.v })}>
            {o.label}
          </SegBtn>
        ))}
      </div>

      <label style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 10, fontSize: 14.5, cursor: "pointer",
                      color: needsReceipt ? "#1a56c4" : "inherit", fontWeight: needsReceipt ? 700 : 400 }}>
        <input type="checkbox" checked={p.receipt_issued} style={{ width: 20, height: 20 }}
          onChange={() => save({ receipt_issued: !p.receipt_issued })} />
        חשבונית מס / קבלה הוצאה (רפי)
        {needsReceipt && <span> — ממתין לרפי</span>}
      </label>
    </div>
  );
}

// ───────────────────────── העמוד ─────────────────────────

export default function Ops() {
  const [tab, setTab] = useState("arrivals");
  const [filter, setFilter] = useState("all");
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [cleanerMap, setCleanerMap] = useState({});

  const load = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/ops/board`);
      if (!res.ok) throw new Error(`שגיאה ${res.status}`);
      setData(await res.json());
      setError(null);
    } catch (e) {
      setError(String(e.message || e));
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  // זיהוי "המנקה נכנס" — best effort; אם נכשל פשוט לא מציגים את התג
  useEffect(() => {
    (async () => {
      try {
        const res = await fetch(`${API_BASE}/cleaning?days=21`);
        if (!res.ok) return;
        const j = await res.json();
        const map = {};
        for (const t of j.turnovers || []) {
          if (t.booking_in_id && t.cleaning) {
            const cur = map[t.booking_in_id];
            if (!cur || t.cleaning.date < cur.date) map[t.booking_in_id] = t.cleaning;
          }
        }
        setCleanerMap(map);
      } catch { /* ignore */ }
    })();
  }, []);

  function applyState(listKey) {
    return (id, state) =>
      setData(d => {
        const list = d[listKey].map(x => (x.booking_id === id ? { ...x, ...state } : x));
        return { ...d, [listKey]: list };
      });
  }

  const stats = useMemo(() => {
    if (!data) return null;
    const notClean = data.arrivals.filter(a => {
      const eff = a.prep_status === "dirty" && cleanerMap[a.booking_id] ? "partial" : a.prep_status;
      return eff !== "clean";
    }).length;
    return {
      arrivals: data.arrivals.length,
      notClean,
      unpaid: data.payments.filter(p => p.pay_status !== "paid").length,
      receipts: data.payments.filter(p => p.pay_status === "paid" && !p.receipt_issued).length,
    };
  }, [data, cleanerMap]);

  const payments = useMemo(() => {
    if (!data) return [];
    if (filter === "unpaid") return data.payments.filter(p => p.pay_status !== "paid");
    if (filter === "receipt") return data.payments.filter(p => p.pay_status === "paid" && !p.receipt_issued);
    return data.payments;
  }, [data, filter]);

  const tile = (n, label, warn) => (
    <div style={{ flex: 1, textAlign: "center", background: warn && n > 0 ? "#fff4e5" : "#fff",
                  border: "1px solid var(--border-card, #eee)", borderRadius: 12, padding: "10px 4px" }}>
      <div style={{ fontSize: 24, fontWeight: 700, color: warn && n > 0 ? "#9a5b00" : "inherit" }}>{n}</div>
      <div style={{ fontSize: 12, color: "#777" }}>{label}</div>
    </div>
  );

  return (
    <div style={{ maxWidth: 760, margin: "0 auto", padding: "0 4px 40px" }}>
      <h2 style={{ margin: "4px 0 12px" }}>🧭 תפעול</h2>

      {error && <div style={{ color: "#b3261e", marginBottom: 10 }}>❌ {error}</div>}
      {!data && !error && <div>טוען…</div>}

      {data && (
        <>
          <div style={{ display: "flex", gap: 8, marginBottom: 14 }}>
            {tile(stats.notClean, "צימרים לא מוכנים (מתוך " + stats.arrivals + " הגעות)", true)}
            {tile(stats.unpaid, "ממתינים לתשלום", true)}
            {tile(stats.receipts, "ממתינים לקבלה", true)}
          </div>

          <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
            <SegBtn active={tab === "arrivals"} onClick={() => { setTab("arrivals"); load(); }}>🧹 הגעות והכנה</SegBtn>
            <SegBtn active={tab === "payments"} onClick={() => { setTab("payments"); load(); }}>💳 תשלומים וקבלות</SegBtn>
          </div>

          {tab === "arrivals" && (
            data.arrivals.length === 0
              ? <div style={{ color: "#888" }}>אין הגעות ב-10 הימים הקרובים.</div>
              : data.arrivals.map(a => (
                  <ArrivalCard key={a.booking_id} a={a} today={data.today}
                    cleaner={cleanerMap[a.booking_id]} onChange={applyState("arrivals")} />
                ))
          )}

          {tab === "payments" && (
            <>
              <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
                <SegBtn active={filter === "all"} onClick={() => setFilter("all")}>הכל ({data.payments.length})</SegBtn>
                <SegBtn active={filter === "unpaid"} onClick={() => setFilter("unpaid")}>לא שולם ({stats.unpaid})</SegBtn>
                <SegBtn active={filter === "receipt"} onClick={() => setFilter("receipt")}>ממתין לקבלה ({stats.receipts})</SegBtn>
              </div>
              {payments.length === 0
                ? <div style={{ color: "#888" }}>הכל מסודר ✅</div>
                : payments.map(p => (
                    <PaymentCard key={p.booking_id} p={p} today={data.today} onChange={applyState("payments")} />
                  ))}
            </>
          )}
        </>
      )}
    </div>
  );
}
