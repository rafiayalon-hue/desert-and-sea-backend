import { useState, useEffect } from "react";

const USE_MOCK = false;
const API_BASE = import.meta.env.VITE_API_URL 
  ? `${import.meta.env.VITE_API_URL}/api` 
  : "https://selfless-happiness-production.up.railway.app/api";
function enrichBooking(b) {
  return {
    ...b,
    full_name:     `${b.first_name || ""} ${b.last_name || ""}`.trim(),
    room_display:  b.rooms?.includes("desert") && b.rooms?.includes("sea")
                   ? "מדבר + ים"
                   : b.rooms?.includes("desert") ? "מדבר" : "ים",
    room_color:    b.rooms?.includes("desert") && b.rooms?.includes("sea")
                   ? "combined"
                   : b.rooms?.includes("desert") ? "desert" : "sea",
    checkin_label:  formatDate(b.checkin),
    checkout_label: formatDate(b.checkout),
    checkin_time:   b.checkin_time  || "15:00",
    checkout_time:  b.checkout_time || "11:00",
    source_label:   { direct: "ישיר", website: "אתר", airbnb: "Airbnb" }[b.source] || b.source,
    status_label:   b.status === "confirmed" ? "מאושר" : "מבוטל",
    cancellation_label: {
      internal_block: "🔒 חסימה פנימית",
      guest_cancel:   "❌ ביטול אורח",
      direct_switch:  "🔄 מעבר ישיר",
    }[b.cancellation_tag] || null,
  };
}

function formatDate(dateStr) {
  if (!dateStr) return "";
  const d = new Date(dateStr);
  return d.toLocaleDateString("he-IL", { day: "2-digit", month: "2-digit", year: "2-digit" });
}

// טעינה גלובלית אחת של ה-Mock Data
let mockCache = null;
async function loadMock() {
  if (mockCache) return mockCache;
  const res = await fetch("/mock_data/mock_bookings.json");
  mockCache = await res.json();
  return mockCache;
}

export function useBookings(filters = {}) {
  const [bookings, setBookings] = useState([]);
  const [loading, setLoading]   = useState(true);
  const [error, setError]       = useState(null);

  useEffect(() => {
    async function load() {
      try {
        let data;
        if (USE_MOCK) {
          data = await loadMock();
        } else {
          const params = new URLSearchParams(
            Object.entries(filters).filter(([,v]) => v !== undefined && v !== "")
          ).toString();
          const res = await fetch(`${API_BASE}/bookings?${params}`);
          const json = await res.json();
          data = json.bookings;
        }

        let result = data.map(enrichBooking);

        if (filters.status)   result = result.filter(b => b.status  === filters.status);
        if (filters.room)     result = result.filter(b => b.rooms?.includes(filters.room));
        if (filters.source)   result = result.filter(b => b.source  === filters.source);
        if (filters.upcoming) {
          const today = new Date().toISOString().slice(0, 10);
          result = result.filter(b => b.checkin >= today);
        }
        if (filters.search) {
          const q = filters.search.toLowerCase();
          result = result.filter(b =>
            b.full_name.toLowerCase().includes(q) ||
            (b.id || "").toLowerCase().includes(q) ||
            (b.email || "").toLowerCase().includes(q)
          );
        }

        result.sort((a, b) => (a.checkin || "").localeCompare(b.checkin || ""));
        setBookings(result);
      } catch (e) {
        setError(e.message);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [JSON.stringify(filters)]);

  return { bookings, loading, error };
}

export function useBooking(id) {
  const { bookings, loading } = useBookings({});
  const booking = bookings.find(b => b.id === id) || null;
  return { booking, loading };
}

export function useStats() {
  const { bookings } = useBookings({});
  const confirmed  = bookings.filter(b => b.status === "confirmed");
  const today      = new Date().toISOString().slice(0, 10);
  const arrivals   = confirmed.filter(b => b.checkin  === today);
  const departures = confirmed.filter(b => b.checkout === today);
  const nextWeek   = new Date(); nextWeek.setDate(nextWeek.getDate() + 7);
  const nextWeekStr = nextWeek.toISOString().slice(0, 10);
  const upcoming7  = confirmed.filter(b => b.checkin >= today && b.checkin <= nextWeekStr);
  const desertBookings = confirmed.filter(b => b.rooms?.includes("desert"));
  const seaBookings    = confirmed.filter(b => b.rooms?.includes("sea"));
  return { confirmed, arrivals, departures, desertBookings, seaBookings, upcoming7 };
}

export function useOccupancyStats() {
  const { bookings } = useBookings({});
  const confirmed = bookings.filter(b => b.status === "confirmed");

  const monthsHe = ["ינואר","פברואר","מרץ","אפריל","מאי","יוני",
                    "יולי","אוגוסט","ספטמבר","אוקטובר","נובמבר","דצמבר"];

  function daysInMonth(y, m) { return new Date(y, m + 1, 0).getDate(); }

  const now = new Date();
  const months = [];

  for (let delta = 0; delta < 3; delta++) {
    const d     = new Date(now.getFullYear(), now.getMonth() + delta, 1);
    const mStr  = `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,"0")}`;
    const daysIn = daysInMonth(d.getFullYear(), d.getMonth());

    let desertN = 0, seaN = 0, revenue = 0, count = 0;

    for (const b of confirmed) {
      const ci = b.checkin  || "";
      const co = b.checkout || "";
      if (ci.slice(0,7) !== mStr && co.slice(0,7) !== mStr) continue;

      const nights = b.nights || 0;
      const rooms  = b.rooms  || [];

      if (b.is_combined_booking) { desertN += nights; seaN += nights; }
      else if (rooms.includes("desert")) desertN += nights;
      else if (rooms.includes("sea"))    seaN    += nights;

      revenue += (b.total_price || 0);
      count++;
    }

    months.push({
      month: mStr,
      label: `${monthsHe[d.getMonth()]} ${d.getFullYear()}`,
      daysIn,
      desertN,
      seaN,
      desertPct: Math.round(desertN / daysIn * 100),
      seaPct:    Math.round(seaN    / daysIn * 100),
      revenue:   Math.round(revenue),
      count,
    });
  }

  return { months };
}

export { formatDate };
