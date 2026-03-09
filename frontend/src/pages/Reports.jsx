import { useState } from "react";
import { useBookings } from "../hooks/useBookings";

const monthsHe = ["ינואר","פברואר","מרץ","אפריל","מאי","יוני",
                  "יולי","אוגוסט","ספטמבר","אוקטובר","נובמבר","דצמבר"];

function daysInMonth(y, m) { return new Date(y, m + 1, 0).getDate(); }

function calcMonthStats(confirmed, year, month) {
  const mStr = `${year}-${String(month + 1).padStart(2, "0")}`;
  const daysIn = daysInMonth(year, month);

  let desertN = 0, seaN = 0, revenue = 0, count = 0;
  const sources = { airbnb: 0, direct: 0, website: 0, other: 0 };

  for (const b of confirmed) {
    const ci = b.checkin || "";
    const co = b.checkout || "";
    if (ci.slice(0, 7) !== mStr && co.slice(0, 7) !== mStr) continue;

    const rooms = b.rooms || [];
    const nights = b.checkin && b.checkout
      ? Math.round((new Date(b.checkout) - new Date(b.checkin)) / (1000 * 60 * 60 * 24))
      : 0;

    if (rooms.includes("desert") && rooms.includes("sea")) { desertN += nights; seaN += nights; }
    else if (rooms.includes("desert")) desertN += nights;
    else if (rooms.includes("sea")) seaN += nights;

    revenue += (b.total_price || 0);
    count++;

    const src = (b.source || "").toLowerCase();
    if (src === "airbnb") sources.airbnb++;
    else if (src === "direct") sources.direct++;
    else if (src === "website" || src === "homepage") sources.website++;
    else sources.other++;
  }

  return {
    mStr, daysIn, desertN, seaN, revenue, count, sources,
    desertPct: Math.round(desertN / daysIn * 100),
    seaPct: Math.round(seaN / daysIn * 100),
    label: `${monthsHe[month]} ${year}`,
  };
}

function OccupancyBar({ pct, color }) {
  return (
    <div style={{ background: "var(--border-card)", borderRadius: 6, height: 8, overflow: "hidden", flex: 1 }}>
      <div style={{
        width: `${Math.min(pct, 100)}%`, height: "100%", borderRadius: 6,
        background: color, transition: "width .4s ease"
      }} />
    </div>
  );
}

function SourceBadge({ label, count, total, color }) {
  const pct = total > 0 ? Math.round(count / total * 100) : 0;
  return (
    <div style={{ marginBottom: 10 }}>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: ".78rem", marginBottom: 4 }}>
        <span style={{ fontWeight: 600, color }}>{label}</span>
        <span style={{ fontWeight: 700 }}>{pct}%
          <span style={{ color: "var(--text-muted)", fontWeight: 400 }}> ({count} הזמנות)</span>
        </span>
      </div>
      <OccupancyBar pct={pct} color={color} />
    </div>
  );
}

// ─── Section 1: Occupancy Navigator ────────────────────────────────────────
function OccupancyNavigator({ confirmed }) {
  const now = new Date();
  const [offset, setOffset] = useState(0); // offset in months from current

  const months = [];
  for (let delta = 0; delta < 3; delta++) {
    const d = new Date(now.getFullYear(), now.getMonth() + offset + delta, 1);
    months.push(calcMonthStats(confirmed, d.getFullYear(), d.getMonth()));
  }

  const startLabel = months[0].label;
  const endLabel = months[2].label;

  return (
    <div className="card" style={{ marginBottom: 20 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
        <div className="card-title" style={{ marginBottom: 0 }}>תפוסה לפי חודש</div>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <button
            onClick={() => setOffset(o => o - 3)}
            style={{
              background: "var(--sand-bg)", border: "1px solid var(--border-card)",
              borderRadius: 8, padding: "6px 14px", cursor: "pointer",
              fontWeight: 700, fontSize: "1rem", color: "var(--terra)"
            }}>←</button>
          <span style={{ fontSize: ".82rem", color: "var(--text-muted)", minWidth: 160, textAlign: "center" }}>
            {startLabel} — {endLabel}
          </span>
          <button
            onClick={() => setOffset(o => o + 3)}
            style={{
              background: "var(--sand-bg)", border: "1px solid var(--border-card)",
              borderRadius: 8, padding: "6px 14px", cursor: "pointer",
              fontWeight: 700, fontSize: "1rem", color: "var(--terra)"
            }}>→</button>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 20 }}>
        {months.map(m => (
          <div key={m.mStr} style={{
            padding: "14px 16px", background: "var(--sand-bg)",
            borderRadius: 10, border: "1px solid var(--border-card)"
          }}>
            <div style={{ fontWeight: 700, fontSize: ".9rem", marginBottom: 12, color: "var(--terra)" }}>
              {m.label}
            </div>
            <div style={{ marginBottom: 8 }}>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: ".78rem", marginBottom: 4 }}>
                <span style={{ color: "var(--desert-color)", fontWeight: 600 }}>🏜️ מדבר</span>
                <span style={{ fontWeight: 700 }}>{m.desertPct}%
                  <span style={{ color: "var(--text-muted)", fontWeight: 400, fontSize: ".72rem" }}>
                    {" "}({m.desertN}/{m.daysIn} לילות)
                  </span>
                </span>
              </div>
              <OccupancyBar pct={m.desertPct} color="var(--desert-color)" />
            </div>
            <div style={{ marginBottom: 10 }}>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: ".78rem", marginBottom: 4 }}>
                <span style={{ color: "var(--teal-dark)", fontWeight: 600 }}>🌊 ים</span>
                <span style={{ fontWeight: 700 }}>{m.seaPct}%
                  <span style={{ color: "var(--text-muted)", fontWeight: 400, fontSize: ".72rem" }}>
                    {" "}({m.seaN}/{m.daysIn} לילות)
                  </span>
                </span>
              </div>
              <OccupancyBar pct={m.seaPct} color="var(--teal)" />
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: ".78rem",
              paddingTop: 8, borderTop: "1px solid var(--border-card)" }}>
              <span style={{ color: "var(--text-muted)" }}>{m.count} הזמנות</span>
              <span style={{ fontWeight: 700 }}>₪{m.revenue.toLocaleString()}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── Section 2: Source Breakdown ───────────────────────────────────────────
function SourceBreakdown({ confirmed }) {
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth());

  const stats = calcMonthStats(confirmed, year, month);
  const total = stats.count;

  const years = [];
  for (let y = 2024; y <= now.getFullYear() + 1; y++) years.push(y);

  return (
    <div className="card" style={{ marginBottom: 20 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
        <div className="card-title" style={{ marginBottom: 0 }}>פילוח לפי מקור הזמנה</div>
        <div style={{ display: "flex", gap: 8 }}>
          <select value={month} onChange={e => setMonth(Number(e.target.value))}
            style={{
              background: "var(--sand-bg)", border: "1px solid var(--border-card)",
              borderRadius: 8, padding: "6px 10px", fontSize: ".82rem", color: "var(--text-main)"
            }}>
            {monthsHe.map((m, i) => <option key={i} value={i}>{m}</option>)}
          </select>
          <select value={year} onChange={e => setYear(Number(e.target.value))}
            style={{
              background: "var(--sand-bg)", border: "1px solid var(--border-card)",
              borderRadius: 8, padding: "6px 10px", fontSize: ".82rem", color: "var(--text-main)"
            }}>
            {years.map(y => <option key={y} value={y}>{y}</option>)}
          </select>
        </div>
      </div>

      {total === 0 ? (
        <div style={{ color: "var(--text-muted)", fontSize: ".85rem" }}>אין נתונים לתקופה זו</div>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20 }}>
          <div style={{ padding: "14px 16px", background: "var(--sand-bg)", borderRadius: 10, border: "1px solid var(--border-card)" }}>
            <div style={{ fontWeight: 700, fontSize: ".85rem", marginBottom: 14, color: "var(--terra)" }}>
              {stats.label} — {total} הזמנות
            </div>
            <SourceBadge label="Airbnb" count={stats.sources.airbnb} total={total} color="#FF5A5F" />
            <SourceBadge label="ישיר" count={stats.sources.direct} total={total} color="var(--terra)" />
            <SourceBadge label="אתר" count={stats.sources.website} total={total} color="var(--teal-dark)" />
            {stats.sources.other > 0 && (
              <SourceBadge label="אחר" count={stats.sources.other} total={total} color="var(--text-muted)" />
            )}
          </div>

          <div style={{ padding: "14px 16px", background: "var(--sand-bg)", borderRadius: 10, border: "1px solid var(--border-card)" }}>
            <div style={{ fontWeight: 700, fontSize: ".85rem", marginBottom: 14, color: "var(--terra)" }}>
              תפוסה ולילות
            </div>
            <div style={{ marginBottom: 10 }}>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: ".78rem", marginBottom: 4 }}>
                <span style={{ color: "var(--desert-color)", fontWeight: 600 }}>🏜️ מדבר</span>
                <span style={{ fontWeight: 700 }}>{stats.desertPct}%
                  <span style={{ color: "var(--text-muted)", fontWeight: 400 }}> ({stats.desertN}/{stats.daysIn})</span>
                </span>
              </div>
              <OccupancyBar pct={stats.desertPct} color="var(--desert-color)" />
            </div>
            <div style={{ marginBottom: 10 }}>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: ".78rem", marginBottom: 4 }}>
                <span style={{ color: "var(--teal-dark)", fontWeight: 600 }}>🌊 ים</span>
                <span style={{ fontWeight: 700 }}>{stats.seaPct}%
                  <span style={{ color: "var(--text-muted)", fontWeight: 400 }}> ({stats.seaN}/{stats.daysIn})</span>
                </span>
              </div>
              <OccupancyBar pct={stats.seaPct} color="var(--teal)" />
            </div>
            <div style={{ paddingTop: 8, borderTop: "1px solid var(--border-card)", fontSize: ".82rem", fontWeight: 700 }}>
              הכנסות: ₪{stats.revenue.toLocaleString()}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Section 3: Year over Year ──────────────────────────────────────────────
function YearOverYear({ confirmed }) {
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth());

  const curr = calcMonthStats(confirmed, year, month);
  const prev = calcMonthStats(confirmed, year - 1, month);

  const years = [];
  for (let y = 2025; y <= now.getFullYear() + 1; y++) years.push(y);

  function Delta({ curr, prev, suffix = "" }) {
    if (prev === 0) return <span style={{ color: "var(--text-muted)", fontSize: ".75rem" }}>—</span>;
    const diff = curr - prev;
    const pct = Math.round(diff / prev * 100);
    const color = diff >= 0 ? "#2e9e6b" : "#c0392b";
    const arrow = diff >= 0 ? "▲" : "▼";
    return (
      <span style={{ color, fontSize: ".75rem", fontWeight: 700 }}>
        {arrow} {Math.abs(pct)}%{suffix}
      </span>
    );
  }

  function CompareRow({ label, currVal, prevVal, suffix = "", format }) {
    const display = format || (v => `${v}${suffix}`);
    return (
      <div style={{
        display: "flex", justifyContent: "space-between", alignItems: "center",
        padding: "10px 0", borderBottom: "1px solid var(--border-card)", fontSize: ".82rem"
      }}>
        <span style={{ color: "var(--text-muted)" }}>{label}</span>
        <div style={{ display: "flex", gap: 20, alignItems: "center" }}>
          <span style={{ color: "var(--text-muted)", minWidth: 80, textAlign: "left" }}>
            {display(prevVal)}
          </span>
          <span style={{ fontWeight: 700, minWidth: 80, textAlign: "left" }}>
            {display(currVal)}
          </span>
          <Delta curr={currVal} prev={prevVal} />
        </div>
      </div>
    );
  }

  return (
    <div className="card" style={{ marginBottom: 20 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
        <div className="card-title" style={{ marginBottom: 0 }}>השוואה שנה מול שנה</div>
        <div style={{ display: "flex", gap: 8 }}>
          <select value={month} onChange={e => setMonth(Number(e.target.value))}
            style={{
              background: "var(--sand-bg)", border: "1px solid var(--border-card)",
              borderRadius: 8, padding: "6px 10px", fontSize: ".82rem", color: "var(--text-main)"
            }}>
            {monthsHe.map((m, i) => <option key={i} value={i}>{m}</option>)}
          </select>
          <select value={year} onChange={e => setYear(Number(e.target.value))}
            style={{
              background: "var(--sand-bg)", border: "1px solid var(--border-card)",
              borderRadius: 8, padding: "6px 10px", fontSize: ".82rem", color: "var(--text-main)"
            }}>
            {years.map(y => <option key={y} value={y}>{y}</option>)}
          </select>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 8,
        background: "var(--sand-bg)", borderRadius: 8, padding: "10px 16px",
        marginBottom: 16, fontSize: ".75rem", fontWeight: 700 }}>
        <span style={{ color: "var(--text-muted)" }}>מדד</span>
        <span style={{ color: "var(--text-muted)" }}>{monthsHe[month]} {year - 1}</span>
        <span style={{ color: "var(--terra)" }}>{monthsHe[month]} {year}</span>
      </div>

      <CompareRow label="הזמנות" currVal={curr.count} prevVal={prev.count} />
      <CompareRow label="לילות מדבר" currVal={curr.desertN} prevVal={prev.desertN} suffix=" לילות" />
      <CompareRow label="לילות ים" currVal={curr.seaN} prevVal={prev.seaN} suffix=" לילות" />
      <CompareRow label="תפוסה מדבר" currVal={curr.desertPct} prevVal={prev.desertPct} suffix="%" />
      <CompareRow label="תפוסה ים" currVal={curr.seaPct} prevVal={prev.seaPct} suffix="%" />
      <CompareRow
        label="הכנסות"
        currVal={curr.revenue}
        prevVal={prev.revenue}
        format={v => `₪${v.toLocaleString()}`}
      />

      {prev.count === 0 && (
        <div style={{ marginTop: 12, color: "var(--text-muted)", fontSize: ".8rem" }}>
          * אין נתונים ל-{monthsHe[month]} {year - 1}
        </div>
      )}
    </div>
  );
}

// ─── Main Reports Page ──────────────────────────────────────────────────────
export default function Reports() {
  const { bookings } = useBookings({});
  const confirmed = bookings.filter(b => b.status === "confirmed");

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="page-title">דוחות</div>
          <div className="page-subtitle">ניתוח תפוסה, מקורות והשוואות</div>
        </div>
      </div>

      <OccupancyNavigator confirmed={confirmed} />
      <SourceBreakdown confirmed={confirmed} />
      <YearOverYear confirmed={confirmed} />
    </div>
  );
}
