import { useState, useEffect } from "react";

const API_BASE = import.meta.env.VITE_API_URL
  ? `${import.meta.env.VITE_API_URL}/api`
  : "https://selfless-happiness-production.up.railway.app/api";

let cache = null;

async function loadBookings() {
  if (cache) return cache;
  const res = await fetch(`${API_BASE}/bookings/`);
  const json = await res.json();
  cache = Array.isArray(json) ? json : (json.bookings || []);
  return cache;
}

function enrichBooking(b) {
  const checkin  = b.check_in  || b.checkin  || "";
  const checkout = b.check_out || b.checkout || "";
  const nights = checkin && checkout
    ? Math.round((new Date(checkout) - new Date(checkin)) / (1000 * 60 * 60 * 24))
    : 0;
  const room_name = (b.room_name || "").toLowerCase().replace(" ", "");
  let rooms = [];
  if (room_name.includes("des_sea") || (room_name.includes("sesert") && room_name.includes("sea"))) rooms = ["desert", "sea"];
  else if (room_name.includes("sesert")) rooms = ["desert"];
  else if (room_name.includes("sea"))    rooms = ["sea"];

  return {
    ...b,
    checkin,
    checkout,
    nights,
    rooms,
    full_name:   b.guest_name || "",
    phone:       b.guest_phone || "",
    email:       b.guest_email || "",
    country:     b.country || "",
    total_price: b.total_price || 0,
    source:      b.source || "direct",
  };
}

function extractBaseName(fullName) {
  if (!fullName) return "";
  return fullName
    .replace(/\s*[-–]\s*.+$/, "")
    .replace(/\s*\(.+\)$/, "")
    .replace(/\s+(חברות|אמא|אבא|דודה|דוד|חברים|אח|אחות|הורים)$/, "")
    .trim();
}

function normalizeStatus(status) {
  if (!status) return "cancelled";
  const s = status.toLowerCase();
  if (s === "confirmed" || s === "channel manager" || s === "homepage") return "confirmed";
  return "cancelled";
}

export function useGuests() {
  const [guests, setGuests]   = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadBookings().then(raw => {
      const bookings = raw.map(enrichBooking);

      const phoneMap = {};
      const guestMap = {};

      for (const b of bookings) {
        if (normalizeStatus(b.status) === "cancelled") continue;

        const baseName = extractBaseName(b.full_name);
        const phone    = b.phone || "";

        let key = null;
        if (phone && phoneMap[phone]) {
          key = phoneMap[phone];
        } else if (guestMap[baseName]) {
          key = baseName;
        } else {
          key = baseName || b.full_name;
        }

        if (phone && !phoneMap[phone]) phoneMap[phone] = key;

        if (!guestMap[key]) {
          guestMap[key] = {
            key,
            display_name: baseName || b.full_name,
            phone,
            email:    b.email || "",
            country:  b.country || "",
            bookings: [],
            notes:    "",
            aliases:  new Set(),
          };
        }

        const g = guestMap[key];
        if (phone && !g.phone) g.phone = phone;
        if (b.email && !g.email) g.email = b.email;
        if (b.full_name !== g.display_name) g.aliases.add(b.full_name);

        g.bookings.push({
          id:        b.id,
          checkin:   b.checkin,
          checkout:  b.checkout,
          nights:    b.nights,
          room:      b.rooms?.[0] || "",
          source:    b.source,
          price:     b.total_price || 0,
          full_name: b.full_name,
        });
      }

      const result = Object.values(guestMap).map(g => {
        g.aliases      = [...g.aliases];
        g.visits       = g.bookings.length;
        g.total_nights = g.bookings.reduce((s, b) => s + (b.nights || 0), 0);
        g.total_spent  = g.bookings.reduce((s, b) => s + (b.price  || 0), 0);
        g.last_visit   = g.bookings.map(b => b.checkin).sort().reverse()[0] || "";
        g.is_returning = g.visits > 1;
        g.suspect_duplicate = g.aliases.length > 2 && !g.phone;
        g.bookings.sort((a, b) => (b.checkin || "").localeCompare(a.checkin || ""));
        return g;
      });

      result.sort((a, b) => (b.last_visit || "").localeCompare(a.last_visit || ""));
      setGuests(result);
      setLoading(false);
    });
  }, []);

  return { guests, loading };
}

