// דוחות שיווק — מדבר וים (19.9.26)
// כל החישובים מבוססים על "לילות-יחידה": 2 יחידות (מדבר, ים) × מספר הלילות.
import { useState } from "react";

const UNITS = ["desert", "sea"];
const DAY_MS = 86400000;
const WD_LONG = ["ראשון", "שני", "שלישי", "רביעי", "חמישי", "שישי", "מוצ\"ש"];

// מדיניות (לעדכן כאן כשמשנים מחירים / מינימום)
const POLICY = {
  holidayMinNights: 3,
  holidayReleaseDays: 14,   // שבועיים לפני החג — מורידים מינימום ל-2
  airbnbCommission: 0.15,
};

// חגים וחופשות — לילות לינה (מערב החג עד הלילה האחרון). לעדכן פעם בשנה.
const HOLIDAYS = [
  { name: "סוכות",           from: "2026-09-25", to: "2026-10-02" },
  { name: "חנוכה",           from: "2026-12-04", to: "2026-12-12" },
  { name: "פסח",             from: "2027-04-21", to: "2027-04-28" },
  { name: "יום העצמאות",     from: "2027-05-11", to: "2027-05-12" },
  { name: "שבועות",          from: "2027-06-10", to: "2027-06-11" },
  { name: "חופש גדול",       from: "2027-07-01", to: "2027-08-31", long: true },
  { name: "ראש השנה",        from: "2027-10-01", to: "2027-10-03" },
  { name: "סוכות",           from: "2027-10-15", to: "2027-10-22" },
  { name: "חנוכה",           from: "2027-12-24", to: "2028-01-01" },
];

// ─── עזרים ──────────────────────────────────────────────────────────────────
const iso = d => d.toISOString().slice(0, 10);
const parse = s => new Date(s + "T00:00:00Z");
const addDays = (s, n) => iso(new Date(parse(s).getTime() + n * DAY_MS));
const wd = s => parse(s).getUTCDay();
const fmt = s => { const d = parse(s); return `${d.getUTCDate()}.${d.getUTCMonth() + 1}`; };
const nightsOf = b => (b.checkin && b.checkout) ? Math.round((parse(b.checkout) - parse(b.checkin)) / DAY_MS) : 0;
const pct = (a, b) => b ? Math.round(a / b * 100) : 0;
const ils = n => "₪" + Math.round(n).toLocaleString("he-IL");
const phoneKey = b => (b.guest_phone || "").replace(/\D/g, "").slice(-9) || (b.guest_email || "").toLowerCase() || b.full_name;

// מפה: "YYYY-MM-DD|unit" → { rev, booking }
function buildNightMap(confirmed) {
  const map = new Map();
  for (const b of confirmed) {
    const n = nightsOf(b);
    const units = (b.rooms || []).filter(u => UNITS.includes(u));
    if (!n || !units.length) continue;
    const revPerUnitNight = (b.total_price || 0) / n / units.length;
    for (let i = 0; i < n; i++) {
      const day = addDays(b.checkin, i);
      for (const u of units) map.set(`${day}|${u}`, { rev: revPerUnitNight, b });
    }
  }
  return map;
}

function rangeStats(map, from, toIncl) {
  let avail = 0, occ = 0, rev = 0;
  for (let d = from; d <= toIncl; d = addDays(d, 1))
    for (const u of UNITS) { avail++; const x = map.get(`${d}|${u}`); if (x) { occ++; rev += x.rev; } }
  return { avail, occ, free: avail - occ, rev, pct: pct(occ, avail) };
}

// ─── רכיבים ─────────────────────────────────────────────────────────────────
function Kpi({ value, label, note }) {
  return (
    <div className="card" style={{ padding: "14px 16px", marginBottom: 0 }}>
      <div style={{ fontSize: "1.6rem", fontWeight: 800, color: "var(--text-primary)" }}>{value}</div>
      <div style={{ fontSize: ".8rem", fontWeight: 600, color: "var(--text-secondary)" }}>{label}</div>
      {note && <div style={{ fontSize: ".7rem", color: "var(--text-muted)", marginTop: 4 }}>{note}</div>}
    </div>
  );
}

const th = { textAlign: "right", fontSize: ".72rem", color: "var(--text-muted)", fontWeight: 600, padding: "6px 8px", borderBottom: "1px solid var(--border-card)" };
const td = { fontSize: ".8rem", padding: "7px 8px", borderBottom: "1px solid var(--border-card)", color: "var(--text-primary)" };

function Badge({ tone, children }) {
  const tones = {
    bad:  { bg: "#FBE9E7", fg: "var(--error)" },
    warn: { bg: "#FDF1E0", fg: "#9A5A10" },
    good: { bg: "#E5F4EC", fg: "var(--success)" },
    info: { bg: "var(--sand-pale)", fg: "var(--text-secondary)" },
  }[tone];
  return <span style={{ background: tones.bg, color: tones.fg, borderRadius: 6, padding: "2px 8px", fontSize: ".72rem", fontWeight: 700, whiteSpace: "nowrap" }}>{children}</span>;
}

// 1. תפוסה לפי יום בשבוע
function WeekdayOccupancy({ map, today }) {
  const [period, setPeriod] = useState("past");
  const from = period === "past" ? addDays(today, -365) : today;
  const to   = period === "past" ? addDays(today, -1) : addDays(today, 89);
  const acc = Array.from({ length: 7 }, () => ({ avail: 0, occ: 0, rev: 0 }));
  for (let d = from; d <= to; d = addDays(d, 1)) {
    const a = acc[wd(d)];
    for (const u of UNITS) { a.avail++; const x = map.get(`${d}|${u}`); if (x) { a.occ++; a.rev += x.rev; } }
  }
  const order = [0, 1, 2, 3, 4, 5, 6];
  return (
    <div className="card" style={{ marginBottom: 20 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <div className="card-title" style={{ marginBottom: 0 }}>תפוסה לפי לילה בשבוע</div>
        <div style={{ display: "flex", gap: 6 }}>
          {[["past", "12 חודשים אחרונים"], ["future", "90 יום קדימה (מוזמן)"]].map(([k, l]) => (
            <button key={k} onClick={() => setPeriod(k)} className={`btn ${period === k ? "btn-primary" : ""}`}
              style={{ fontSize: ".75rem", padding: "4px 10px" }}>{l}</button>
          ))}
        </div>
      </div>
      {order.map(i => {
        const a = acc[i], p = pct(a.occ, a.avail), adr = a.occ ? a.rev / a.occ : 0;
        const weekend = i === 4 || i === 5;
        return (
          <div key={i} title={`${WD_LONG[i]}: ${a.occ}/${a.avail} לילות-יחידה · מחיר ממוצע ללילה ${ils(adr)}`}
            style={{ display: "grid", gridTemplateColumns: "70px 1fr 48px 70px", alignItems: "center", gap: 10, padding: "5px 0" }}>
            <span style={{ fontSize: ".8rem", fontWeight: weekend ? 700 : 500, color: "var(--text-secondary)" }}>ליל {WD_LONG[i]}</span>
            <div style={{ background: "var(--sand-pale)", borderRadius: 4, height: 14 }}>
              <div style={{ width: `${p}%`, height: "100%", borderRadius: 4, background: weekend ? "var(--terra)" : "var(--sand-dark)", transition: "width .3s" }} />
            </div>
            <span style={{ fontSize: ".82rem", fontWeight: 700, textAlign: "left" }}>{p}%</span>
            <span style={{ fontSize: ".72rem", color: "var(--text-muted)", textAlign: "left" }}>{adr ? ils(adr) : "—"}</span>
          </div>
        );
      })}
      <div style={{ fontSize: ".7rem", color: "var(--text-muted)", marginTop: 8 }}>
        העמודה השמאלית: מחיר ממוצע ללילה ליחידה בפועל (כולל ילדים). ליל שבת חלש מובנה — אין כניסות בשבת; המנוף הוא "הארכה למוצ"ש".
      </div>
    </div>
  );
}

// 2. חגים וחופשות
function HolidayPace({ map, confirmed, today }) {
  const upcoming = HOLIDAYS.filter(h => h.to >= today).slice(0, 6);
  return (
    <div className="card" style={{ marginBottom: 20 }}>
      <div className="card-title">חגים וחופשות — כמה כבר מוזמן</div>
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead><tr>
          <th style={th}>חג</th><th style={th}>לילות</th><th style={th}>עוד</th><th style={th}>מוזמן</th>
          <th style={th}>פנוי</th><th style={th}>הזמנות קצרות מ-{POLICY.holidayMinNights}</th><th style={th}>מה עושים</th>
        </tr></thead>
        <tbody>
          {upcoming.map(h => {
            const s = rangeStats(map, h.from, h.to);
            const daysTo = Math.round((parse(h.from) - parse(today)) / DAY_MS);
            const short = confirmed.filter(b => b.checkin <= h.to && b.checkout > h.from && nightsOf(b) < POLICY.holidayMinNights).length;
            let action;
            if (daysTo < 0) action = <Badge tone="info">החג בעיצומו</Badge>;
            else if (s.free === 0) action = <Badge tone="good">✓ מלא</Badge>;
            else if (h.long) action = <Badge tone="info">חבילת 3 לילות למשפחות</Badge>;
            else if (daysTo > POLICY.holidayReleaseDays) action = <Badge tone="info">מינימום {POLICY.holidayMinNights} · מחיר חג</Badge>;
            else if (s.pct < 70) action = <Badge tone="bad">⚠ לפתוח ל-2 לילות + הודעה לאורחים</Badge>;
            else action = <Badge tone="warn">לפתוח ל-2 לילות</Badge>;
            return (
              <tr key={h.name + h.from}>
                <td style={{ ...td, fontWeight: 700 }}>{h.name}</td>
                <td style={td}>{fmt(h.from)}–{fmt(addDays(h.to, 1))}</td>
                <td style={td}>{daysTo > 0 ? `${daysTo} ימים` : "—"}</td>
                <td style={{ ...td, fontWeight: 700 }}>{s.pct}%</td>
                <td style={td}>{s.free} לילות</td>
                <td style={td}>{short || "—"}</td>
                <td style={td}>{action}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <div style={{ fontSize: ".7rem", color: "var(--text-muted)", marginTop: 8 }}>
        מדיניות: מינימום {POLICY.holidayMinNights} לילות במחיר חג; {POLICY.holidayReleaseDays} יום לפני החג — מה שפנוי נפתח ל-2 לילות. "פנוי" = לילות-יחידה (2 יחידות × לילות).
      </div>
    </div>
  );
}

// 3. 90 יום קדימה — לפי שבוע
function Forward90({ map, today }) {
  const start = addDays(today, -wd(today)); // ראשון של השבוע הנוכחי
  const weeks = [];
  for (let w = 0; w < 13; w++) {
    const sun = addDays(start, w * 7);
    const mid = rangeStats(map, sun < today ? today : sun, addDays(sun, 3));
    const thu = rangeStats(map, addDays(sun, 4), addDays(sun, 4));
    const fri = rangeStats(map, addDays(sun, 5), addDays(sun, 5));
    const sat = rangeStats(map, addDays(sun, 6), addDays(sun, 6));
    const daysTo = Math.round((parse(addDays(sun, 4)) - parse(today)) / DAY_MS);
    weeks.push({ sun, mid, thu, fri, sat, daysTo });
  }
  const cell = (s, isWeekend) => {
    if (s.avail === 0) return <td style={{ ...td, color: "var(--text-muted)" }}>—</td>;
    const tone = s.free === 0 ? "good" : isWeekend ? "warn" : "info";
    return <td style={td}><Badge tone={tone}>{s.free === 0 ? "✓ מלא" : `${s.free} פנויים`}</Badge></td>;
  };
  return (
    <div className="card" style={{ marginBottom: 20 }}>
      <div className="card-title">90 יום קדימה — לילות פנויים לפי שבוע</div>
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead><tr>
          <th style={th}>שבוע</th><th style={th}>א'–ד' (מתוך 8)</th><th style={th}>חמישי</th><th style={th}>שישי</th><th style={th}>מוצ"ש</th><th style={th}>פעולה</th>
        </tr></thead>
        <tbody>
          {weeks.map(w => {
            const weFree = w.thu.free + w.fri.free;
            let action = null;
            if (weFree > 0 && w.daysTo >= 0 && w.daysTo <= 5) action = <Badge tone="bad">⚠ שישי פתוח ללילה בודד</Badge>;
            else if (weFree > 0 && w.daysTo <= 21) action = <Badge tone="warn">הודעה לרשימה</Badge>;
            else if (w.mid.free >= 6 && w.daysTo <= 30) action = <Badge tone="info">לדחוף חבילת א'–ד'</Badge>;
            return (
              <tr key={w.sun}>
                <td style={{ ...td, fontWeight: 600 }}>{fmt(w.sun)}–{fmt(addDays(w.sun, 6))}</td>
                {cell(w.mid, false)}{cell(w.thu, true)}{cell(w.fri, true)}{cell(w.sat, false)}
                <td style={td}>{action}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <div style={{ fontSize: ".7rem", color: "var(--text-muted)", marginTop: 8 }}>
        כלל: סופ"ש שלא נמכר עד שלישי נפתח ללילה אחד. אמצע שבוע — מינימום 2 לילות; חבילת 3 לילות א'–ד' במחיר קבוע.
      </div>
    </div>
  );
}

// 4. ערוצים ועמלות + 5. אורחים חוזרים וחבילות (12 חודשים אחרונים)
function ChannelsAndLoyalty({ confirmed, today }) {
  const from = addDays(today, -365);
  const past = confirmed.filter(b => b.checkin >= from && b.checkin < today);
  const bySrc = {};
  for (const b of past) {
    const s = (b.source || "direct").toLowerCase();
    const k = s === "airbnb" ? "Airbnb" : (s === "website" || s === "homepage") ? "אתר" : "ישיר";
    bySrc[k] = bySrc[k] || { n: 0, rev: 0 };
    bySrc[k].n++; bySrc[k].rev += b.total_price || 0;
  }
  const total = past.length;
  const airbnbFee = (bySrc["Airbnb"]?.rev || 0) * POLICY.airbnbCommission;

  // אורחים חוזרים — על כל ההיסטוריה עד היום
  const hist = confirmed.filter(b => b.checkin < today);
  const counts = {};
  for (const b of hist) { const k = phoneKey(b); counts[k] = (counts[k] || 0) + 1; }
  const guests = Object.keys(counts).length;
  const repeaters = Object.values(counts).filter(c => c > 1).length;
  const repeatBookings = past.filter(b => counts[phoneKey(b)] > 1).length;

  // חבילות אמצע שבוע: כניסה א'–ג', 3 לילות ומעלה
  const pkg = confirmed.filter(b => b.checkin >= from && [0, 1, 2].includes(wd(b.checkin)) && nightsOf(b) >= 3);
  const pkgFuture = pkg.filter(b => b.checkin >= today).length;

  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20, marginBottom: 20 }}>
      <div className="card">
        <div className="card-title">ערוצים — 12 חודשים אחרונים</div>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead><tr><th style={th}>ערוץ</th><th style={th}>הזמנות</th><th style={th}>%</th><th style={th}>הכנסה</th></tr></thead>
          <tbody>
            {Object.entries(bySrc).sort((a, b) => b[1].n - a[1].n).map(([k, v]) => (
              <tr key={k}><td style={{ ...td, fontWeight: 600 }}>{k}</td><td style={td}>{v.n}</td><td style={td}>{pct(v.n, total)}%</td><td style={td}>{ils(v.rev)}</td></tr>
            ))}
          </tbody>
        </table>
        <div style={{ fontSize: ".78rem", marginTop: 10, color: "var(--text-secondary)" }}>
          עלות עמלת Airbnb משוערת: <b>{ils(airbnbFee)}</b> ({POLICY.airbnbCommission * 100}%)
        </div>
        <div style={{ fontSize: ".7rem", color: "var(--text-muted)", marginTop: 4 }}>
          Airbnb משמש בעיקר תיירים מחו"ל. אסור לפנות לאורחי Airbnb לשיווק ישיר (מדיניות Airbnb).
        </div>
      </div>
      <div className="card">
        <div className="card-title">אורחים חוזרים וחבילות</div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
          <Kpi value={`${pct(repeatBookings, total)}%`} label="מההזמנות — אורחים חוזרים" note={`${repeaters} מתוך ${guests} אורחים הגיעו יותר מפעם אחת`} />
          <Kpi value={pkg.length} label="חבילות א'–ד' (3+ לילות)" note={`12 חודשים אחרונים + עתידי · ${pkgFuture} עתידיות`} />
        </div>
      </div>
    </div>
  );
}

// ─── ראשי ───────────────────────────────────────────────────────────────────
export default function MarketingReports({ confirmed }) {
  const today = iso(new Date());
  const map = buildNightMap(confirmed);
  const next30 = rangeStats(map, today, addDays(today, 29));
  let weFree = 0;
  for (let d = today; d <= addDays(today, 89); d = addDays(d, 1))
    if ([4, 5].includes(wd(d))) for (const u of UNITS) if (!map.has(`${d}|${u}`)) weFree++;
  const nextHoliday = HOLIDAYS.find(h => h.to >= today);
  const nh = nextHoliday && rangeStats(map, nextHoliday.from, nextHoliday.to);

  return (
    <div>
      <div className="page-header" style={{ marginTop: 10 }}>
        <div>
          <div className="page-title" style={{ fontSize: "1.3rem" }}>שיווק</div>
          <div className="page-subtitle">איפה חסרות הזמנות ומה עושים</div>
        </div>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 14, marginBottom: 20 }}>
        <Kpi value={`${next30.pct}%`} label="תפוסה ב-30 יום הקרובים" note={`${next30.free} לילות-יחידה פנויים`} />
        <Kpi value={weFree} label={"לילות סופ\"ש פנויים ב-90 יום"} note="חמישי + שישי, שתי היחידות" />
        {nh && <Kpi value={`${nh.pct}%`} label={`מוזמן ל${nextHoliday.name}`} note={`${nh.free} לילות פנויים`} />}
        <ChannelKpi confirmed={confirmed} today={today} />
      </div>
      <HolidayPace map={map} confirmed={confirmed} today={today} />
      <Forward90 map={map} today={today} />
      <WeekdayOccupancy map={map} today={today} />
      <ChannelsAndLoyalty confirmed={confirmed} today={today} />
    </div>
  );
}

function ChannelKpi({ confirmed, today }) {
  const past = confirmed.filter(b => b.checkin >= addDays(today, -365) && b.checkin < today);
  const direct = past.filter(b => (b.source || "").toLowerCase() !== "airbnb").length;
  return <Kpi value={`${pct(direct, past.length)}%`} label="הזמנות ישירות (12 ח')" note="ישיר + אתר" />;
}
