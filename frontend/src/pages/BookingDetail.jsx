import { useState } from "react";
import { useBooking } from "../hooks/useBookings";
import { WHATSAPP_MESSAGES } from "../data/whatsappMessages";

const API_BASE = import.meta.env.VITE_API_URL
  ? `${import.meta.env.VITE_API_URL}/api`
  : "https://selfless-happiness-production.up.railway.app/api";

const LANGUAGES = [
  { value: "he", label: "🇮🇱 עברית" },
  { value: "en", label: "🇬🇧 English" },
  { value: "es", label: "🇪🇸 Español" },
  { value: "fr", label: "🇫🇷 Français" },
];

const MESSAGES = [
  { type: "booking_confirmation", label: "1. אישור הזמנה",    templateId: 1 },
  { type: "pre_arrival",          label: "2. לפני הגעה",      templateId: 2 },
  { type: "checkin_code",         label: "3. כניסה + קוד",    templateId: 3 },
  { type: "checkout_payment",     label: "4. יציאה + תשלום",  templateId: 4 },
  { type: "review_request",       label: "5. ביקורת",         templateId: 5 },
];

const CANCELLATION_TAGS = [
  { value: "internal_block", label: "🔒 חסימה פנימית" },
  { value: "guest_cancel",   label: "❌ ביטול אורח" },
  { value: "direct_switch",  label: "🔄 מעבר ישיר מ-Airbnb" },
];

function Section({ title, children }) {
  return (
    <div className="detail-section">
      <div className="detail-section-title">{title}</div>
      {children}
    </div>
  );
}

function Row({ label, children }) {
  return (
    <div className="detail-row">
      <span className="detail-label">{label}</span>
      <span className="detail-value">{children || "—"}</span>
    </div>
  );
}

function buildMessageBody(templateId, lang, booking, ttlockCode, paymentLink, checkinTime, checkoutTime) {
  const tpl = WHATSAPP_MESSAGES.find(m => m.id === templateId);
  if (!tpl) return "";
  const text = tpl.langs[lang] || tpl.langs["he"] || "";
  const roomDisplay = booking.rooms?.includes("desert") && booking.rooms?.includes("sea")
    ? "מדבר + ים" : booking.rooms?.includes("desert") ? "מדבר" : "ים";
  return text
    .replace(/\{שם_אורח\}/g,      booking.full_name || "")
    .replace(/\{צימר\}/g,          roomDisplay)
    .replace(/\{תאריך_כניסה\}/g,   booking.checkin_label  || booking.checkin  || "")
    .replace(/\{תאריך_יציאה\}/g,   booking.checkout_label || booking.checkout || "")
    .replace(/\{שעת_כניסה\}/g,     checkinTime  || "14:00")
    .replace(/\{שעת_יציאה\}/g,     checkoutTime || "14:00")
    .replace(/\{קוד\}/g,           ttlockCode || "____")
    .replace(/\{מחיר\}/g,          booking.total_price?.toLocaleString() || "")
    .replace(/\{לינק_סליקה\}/g,    paymentLink || "");
}

async function patchBooking(bookingId, data) {
  const res = await fetch(`${API_BASE}/bookings/${bookingId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  return res.ok;
}

// ─── Inline time editor (reusable) ─────────────────────────────────────────
function TimeEditor({ label, value, onSave }) {
  const [editing, setEditing] = useState(false);
  const [input,   setInput]   = useState(value);
  const [saving,  setSaving]  = useState(false);

  const handleSave = async () => {
    setSaving(true);
    await onSave(input);
    setSaving(false);
    setEditing(false);
  };

  return (
    <div className="detail-row">
      <span className="detail-label">{label}</span>
      <span className="detail-value">
        {editing ? (
          <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
            <input
              type="time"
              className="input"
              style={{ width: 110, padding: "4px 8px", fontSize: ".85rem" }}
              value={input}
              onChange={e => setInput(e.target.value)}
              autoFocus
            />
            <button className="btn btn-primary btn-sm" onClick={handleSave} disabled={saving}>
              {saving ? "..." : "שמור"}
            </button>
            <button className="btn btn-secondary btn-sm" onClick={() => setEditing(false)}>ביטול</button>
          </div>
        ) : (
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <span>{value}</span>
            <button className="btn btn-ghost btn-sm" style={{ fontSize: ".72rem", padding: "2px 6px" }}
              onClick={() => { setInput(value); setEditing(true); }}>✏️</button>
          </div>
        )}
      </span>
    </div>
  );
}

export default function BookingDetail({ bookingId, navigate }) {
  const { booking, loading } = useBooking(bookingId);

  const [language,      setLanguage]      = useState("");
  const [cancelTag,     setCancelTag]     = useState("");
  const [backupOpen,    setBackupOpen]    = useState(false);
  const [backup,        setBackup]        = useState({ first_name: "", phone: "", language: "he" });
  const [sentMessages,  setSentMessages]  = useState([]);
  const [sendingType,   setSendingType]   = useState(null);
  const [previewMsg,    setPreviewMsg]    = useState(null);

  // שם אורח
  const [editingName,  setEditingName]  = useState(false);
  const [nameInput,    setNameInput]    = useState("");
  const [savingName,   setSavingName]   = useState(false);
  const [localName,    setLocalName]    =
