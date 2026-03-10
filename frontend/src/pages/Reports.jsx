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
  const sourceNights = { airbnb: 0, direct: 0, website: 0, other: 0 };

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
    if (src === "airbnb") { sources.airbnb++; sourceNights.airbnb += nights; }
    else if (src === "direct") { sources.direct++; sourceNights.direct += nights; }
    else if (src === "website" || src === "homepage") { sources.website++; sourceNights.website += nights; }
    else { sources.other++; sourceNights.other += nights; }
  }

  return {
    mStr, daysIn, desertN, seaN, revenue, count, sources, sourceNights,
    desertPct: Math.round(desertN / daysIn * 100),
    seaPct: Math.round(seaN / daysIn * 100),
    label: `${monthsHe[month]} ${year}`,
  };
}

const SOURCE_COLORS = {
  airbnb:  "#FF5A5F",
  direct:  "#A84D3A",
  website: "#2BBFBF",
  other:   "#B0A090",
};
const SOURCE_LABELS = {
  airbnb:  "Airbnb",
  direct:  "ישיר",
  website: "אתר",
  other:   "אחר",
};

// ─── SVG Donut Pie Chart ────────────────────────────────────────────────────
function PieChart({ data, title, subtitle }) {
  const [hovered, setHovered] = useState(null);
  const total = data.reduce((s, d) => s + d.value, 0);

  if (total === 0) return (
    <div style={{ textAlign: "center", color: "var(--text-muted)", fontSize: ".8rem", padding: 20 }}>
      אין נתונים
    </div>
  );

  const SIZE = 150;
  const R = 55;
  const cx = SIZE / 2;
  const cy = SIZE / 2;

  let angle = -Math.PI / 2;
  const slices = data
    .filter(d => d.value > 0)
    .map((d, i) => {
      const sweep = (d.value / total) * 2 * Math.PI;
      const startAngle = angle;
      angle += sweep;
      const endAngle = angle;
      const midAngle = startAngle + sweep / 2;

      const x1 = cx + R * Math.cos(startAngle);
      const y1 = cy + R * Math.sin(startAngle);
      const x2 = cx + R * Math.cos(endAngle);
      const y2 = cy + R * Math.sin(endAngle);
      const largeArc = sweep > Math.PI ? 1 : 0;

      const labelR = R * 0.63;
      const lx = cx + labelR * Math.cos(midAngle);
      const ly = cy + labelR * Math.sin(midAngle);

      return { ...d, x1, y1, x2, y2, largeArc, lx, ly, sweep, midAngle, startAngle, i };
    });

  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center" }}>
      <div style={{ fontSize: ".82rem", fontWeight: 700, color: "var(--terra)", marginBottom: 2 }}>{title}</div>
      <div style={{ fontSize: ".72rem", color: "var(--text-muted)", marginBottom: 6 }}>{subtitle}</div>

      <svg width={SIZE} height={SIZE} style={{ overflow: "visible" }}>
        {slices.map((s) => {
          const isHov = hovered === s.i;
          const off = isHov ? 6 : 0;
          const tx = Math.cos(s.midAngle) * off;
          const ty = Math.sin(s.midAngle) * off;
          return (
            <g key={s.key} transform={`translate(${tx},${ty})`}
               onMouseEnter={() => setHovered(s.i)}
               onMouseLeave={() => setHovered(null)}
               style={{ cursor: "pointer" }}>
              <path
                d={`M ${cx} ${cy} L ${s.x1} ${s.y1} A ${R} ${R} 0 ${s.largeArc} 1 ${s.x2} ${s.y2} Z`}
                fill={s.color}
                opacity={isHov ? 1 : 0.82}
                style={{ transition: "opacity .15s" }}
              />
              {s.sweep > 0.45 && (
                <text x={s.lx} y={s.ly} textAnchor="middle" dominantBaseline="middle"
                  style={{ fontSize: "9px", fill: "white", fontWeight: 700, pointerEvents: "none" }}>
                  {Math.round(s.value / total * 100)}%
                </text>
              )}
            </g>
          );
        })}
        <circle cx={cx} cy={cy} r={R * 0.4} fill="var(--sand-bg)" style={{ pointerEvents: "none" }} />
        {hovered !== null && slices[hovered] ? (
          <>
            <text x={cx} y={cy - 7} textAnchor="middle"
              style={{ fontSize: "12px", fontWeight: 700, fill: slices[hovered].color }}>
              {slices[hovered].value}
            </text>
            <text x={cx} y={cy + 7} textAnchor="middle"
              style={{ fontSize: "8px", fill: "var(--text-muted)" }}>
              {slices[hovered].label}
            </text>
          </>
        ) : (
          <>
            <text x={cx} y={cy - 6} textAnchor="middle"
              style={{ fontSize: "14px", fontWeight: 700, fill: "var(--text-main)" }}>
              {total}
            </text>
            <text x={cx} y={cy + 8} textAnchor="middle"
              style={{ fontSize: "8px", fill: "var(--text-muted)" }}>
              {subtitle}
            </text>
          </>
        )}
      </svg>

      <div style={{ marginTop: 8, display: "flex", flexWrap: "wrap", gap: "4px 10px", justifyContent: "center" }}>
        {slices.map(s => (
          <div key={s.key} style={{ display: "flex", alignItems: "center", gap: 4, fontSize: ".72rem" }}>
            <div style={{ width: 8, height: 8, borderRadius: "50%", background: s.color, flexShrink: 0 }} />
            <span style={{ color: "var(--text-muted)" }}>{s.label}: {s.value}</span>
          </div>
        ))}
      </div>
    </div>
  );
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

// ─── Section 1: Occupancy Navigator ────────────────────────────────────────
function OccupancyNavigator({ confirmed }) {
  const now = new Date();
  const [offset, setOffset] = useState(0);

  const months = [];
  for (let delta = 0; delta < 3; delta++) {
    const d = new Date(now.getFullYear(), now.getMonth() + offset + delta, 1);
    months.push(calcMonthStats(confirmed, d.getFullYear(), d.getMonth()));
  }

  return (
    <div className="card" style={{ marginBottom: 20 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
        <div className="card-title" style={{ marginBottom: 0 }}>תפוסה לפי חודש</div>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <button onClick={() => setOffset(o => o - 3)} style={{
            background: "var(--sand-bg)", border: "1px solid var(--border-card)",
            borderRadius: 8, padding: "6px 14px", cursor: "pointer",
            fontWeight: 700, fontSize: "1rem", color: "var(--terra)"
          }}>←</button>
          <span style={{ fontSize: ".82rem", color: "var(--text-muted)", minWidth: 160, textAlign: "center" }}>
            {months[0].label} — {months[2].label}
          </span>
          <button onClick={() => setOffset(o => o + 3)} style={{
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

// ─── Section 2: Source Breakdown with Pie Charts ────────────────────────────
function SourceBreakdown({ confirmed }) {
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth());

  const stats = calcMonthStats(confirmed, year, month);
  const total = stats.count;

  const years = [];
  for (let y = 2024; y <= now.getFullYear() + 1; y++) years.push(y);

  const sourceKeys = ["airbnb", "direct", "website", "other"];

  const bookingData = sourceKeys
    .filter(k => stats.sources[k] > 0)
    .map(k => ({ key: k, value: stats.sources[k], color: SOURCE_COLORS[k], label: SOURCE_LABELS[k] }));

  const nightsData = sourceKeys
    .filter(k => stats.sourceNights[k] > 0)
    .map(k => ({ key: k, value: stats.sourceNights[k], color: SOURCE_COLORS[k], label: SOURCE_LABELS[k] }));

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
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 20, alignItems: "start" }}>
          <div style={{ padding: "16px", background: "var(--sand-bg)", borderRadius: 10, border: "1px solid var(--border-card)" }}>
            <PieChart data={bookingData} title={stats.label} subtitle="הזמנות" />
          </div>
          <div style={{ padding: "16px", background: "var(--sand-bg)", borderRadius: 10, border: "1px solid var(--border-card)" }}>
            <PieChart data={nightsData} title={stats.label} subtitle="לילות" />
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

  // עמודות: מדד (40%) | שנה קודמת (25%) | שנה נוכחית (25%) | דלתא (10%)
  const COLS = "2fr 1.2fr 1.2fr 0.6fr";

  function Delta({ curr, prev }) {
    if (prev === 0) return <span style={{ color: "var(--text-muted)", fontSize: ".75rem" }}>—</span>;
    const diff = curr - prev;
    const pct = Math.round(diff / prev * 100);
    const color = diff >= 0 ? "#2e9e6b" : "#c0392b";
    return (
      <span style={{ color, fontSize: ".75rem", fontWeight: 700 }}>
        {diff >= 0 ? "▲" : "▼"} {Math.abs(pct)}%
      </span>
    );
  }

  function CompareRow({ label, currVal, prevVal, format }) {
    const display = format || (v => v);
    return (
      <div style={{
        display: "grid",
        gridTemplateColumns: COLS,
        alignItems: "center",
        padding: "10px 0",
        borderBottom: "1px solid var(--border-card)",
        fontSize: ".82rem",
      }}>
        <span style={{ color: "var(--text-muted)" }}>{label}</span>
        <span style={{ color: "var(--text-muted)" }}>{display(prevVal)}</span>
        <span style={{ fontWeight: 700, color: "var(--text-main)" }}>{display(currVal)}</span>
        <span><Delta curr={currVal} prev={prevVal} /></span>
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

      {/* כותרת טבלה — אותו grid כמו השורות */}
      <div style={{
        display: "grid", gridTemplateColumns: COLS,
        background: "var(--sand-bg)", borderRadius: 8,
        padding: "10px 0", marginBottom: 4,
        fontSize: ".75rem", fontWeight: 700,
      }}>
        <span style={{ color: "var(--text-muted)" }}>מדד</span>
        <span style={{ color: "var(--text-muted)" }}>{monthsHe[month]} {year - 1}</span>
        <span style={{ color: "var(--terra)" }}>{monthsHe[month]} {year}</span>
        <span></span>
      </div>

      <CompareRow label="הזמנות"      currVal={curr.count}     prevVal={prev.count}     format={v => `${v}`} />
      <CompareRow label="לילות מדבר"  currVal={curr.desertN}   prevVal={prev.desertN}   format={v => `${v} לילות`} />
      <CompareRow label="לילות ים"    currVal={curr.seaN}      prevVal={prev.seaN}      format={v => `${v} לילות`} />
      <CompareRow label="תפוסה מדבר" currVal={curr.desertPct} prevVal={prev.desertPct} format={v => `${v}%`} />
      <CompareRow label="תפוסה ים"   currVal={curr.seaPct}    prevVal={prev.seaPct}    format={v => `${v}%`} />
      <CompareRow label="הכנסות"      currVal={curr.revenue}   prevVal={prev.revenue}   format={v => `₪${v.toLocaleString()}`} />

      {prev.count === 0 && (
        <div style={{ marginTop: 12, color: "var(--text-muted)", fontSize: ".8rem" }}>
          * אין נתונים ל-{monthsHe[month]} {year - 1}
        </div>
      )}
    </div>
  );
}

// ─── Main ───────────────────────────────────────────────────────────────────
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
