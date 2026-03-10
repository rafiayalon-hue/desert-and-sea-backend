import ImportExcel from "../components/ImportExcel";
import { useState, useEffect } from "react";
import { WHATSAPP_MESSAGES } from "../data/whatsappMessages";

const API_BASE = import.meta.env.VITE_API_URL
  ? `${import.meta.env.VITE_API_URL}/api`
  : "https://selfless-happiness-production.up.railway.app/api";

const PREVIEW = {
  guest: "יובל", checkin: "04.01.26", checkout: "07.01.26",
  checkinTime: "14:00", checkoutTime: "14:00",
  room: "מדבר", code: "4829", price: "1,200",
  payment: "https://isracard360.link/xxx",
};

function fillPreview(text) {
  return text
    .replace(/\{שם_אורח\}/g, PREVIEW.guest)
    .replace(/\{צימר\}/g, PREVIEW.room)
    .replace(/\{קוד\}/g, PREVIEW.code)
    .replace(/\{תאריך_כניסה\}/g, PREVIEW.checkin)
    .replace(/\{תאריך_יציאה\}/g, PREVIEW.checkout)
    .replace(/\{שעת_כניסה\}/g, PREVIEW.checkinTime)
    .replace(/\{שעת_יציאה\}/g, PREVIEW.checkoutTime)
    .replace(/\{מחיר\}/g, PREVIEW.price)
    .replace(/\{לינק_סליקה\}/g, PREVIEW.payment);
}

const LANG_LABELS = { he: "🇮🇱 עברית", en: "🇬🇧 English", es: "🇪🇸 Español", fr: "🇫🇷 Français" };

function MessageCard({ msg }) {
  const [open,    setOpen]    = useState(false);
  const [lang,    setLang]    = useState("he");
  const [preview, setPreview] = useState(false);
  const [editing, setEditing] = useState(false);
  const [texts,   setTexts]   = useState({ ...msg.langs });
  const [auto,    setAuto]    = useState(msg.auto);
  const currentText = texts[lang];
  const updateText  = (val) => setTexts(prev => ({ ...prev, [lang]: val }));

  return (
    <div style={{ border: "1px solid var(--border-card)", borderRadius: 12, marginBottom: 10, background: "var(--bg-card)", overflow: "hidden", boxShadow: "var(--shadow-sm)" }}>
      <div onClick={() => setOpen(!open)} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "13px 16px", cursor: "pointer", background: open ? "var(--terra-bg)" : "var(--bg-card)", transition: "background .15s" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span style={{ fontSize: ".95rem", fontWeight: 600 }}>{msg.title}</span>
          {auto
            ? <span style={{ fontSize: ".68rem", background: "#E8F5EE", color: "var(--success)", padding: "2px 8px", borderRadius: 20, fontWeight: 700 }}>אוטומטי</span>
            : <span style={{ fontSize: ".68rem", background: "#FEF3E5", color: "var(--warning)", padding: "2px 8px", borderRadius: 20, fontWeight: 700 }}>ידני</span>}
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: ".72rem", color: "var(--text-muted)" }}>{msg.timing}</span>
          <span style={{ color: "var(--text-muted)" }}>{open ? "▲" : "▼"}</span>
        </div>
      </div>
      {open && (
        <div style={{ padding: "14px 16px", borderTop: "1px solid var(--border-card)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 7, marginBottom: 12, flexWrap: "wrap" }}>
            {Object.keys(LANG_LABELS).map(l => (
              <button key={l} className={"filter-btn" + (lang === l ? " active" : "")}
                style={{ fontSize: ".73rem", padding: "4px 9px" }}
                onClick={() => { setLang(l); setEditing(false); setPreview(false); }}>
                {LANG_LABELS[l]}
              </button>
            ))}
            <div style={{ flex: 1 }} />
            <label style={{ display: "flex", alignItems: "center", gap: 5, fontSize: ".8rem", cursor: "pointer" }}>
              <input type="checkbox" checked={auto} onChange={e => setAuto(e.target.checked)} style={{ accentColor: "var(--terra)" }} />
              אוטומטי
            </label>
            <button className="btn btn-secondary" style={{ fontSize: ".75rem", padding: "5px 10px" }}
              onClick={() => { setPreview(!preview); setEditing(false); }}>
              {preview ? "הסתר" : "👁 תצוגה"}
            </button>
            <button className="btn btn-secondary" style={{ fontSize: ".75rem", padding: "5px 10px" }}
              onClick={() => { setEditing(!editing); setPreview(false); }}>
              {editing ? "ביטול" : "✏️ עריכה"}
            </button>
          </div>
          {preview && (
            <div style={{ background: "#E8F5EE", border: "1px solid #C8E6C9", borderRadius: 12, padding: 14, marginBottom: 12, fontSize: ".84rem", lineHeight: 1.75, whiteSpace: "pre-wrap", direction: lang === "he" ? "rtl" : "ltr" }}>
              <div style={{ fontSize: ".7rem", color: "var(--text-muted)", marginBottom: 6 }}>תצוגה מקדימה — {PREVIEW.guest}</div>
              {fillPreview(currentText)}
            </div>
          )}
          {editing ? (
            <>
              <textarea className="textarea" value={currentText} onChange={e => updateText(e.target.value)}
                rows={10} style={{ fontSize: ".84rem", lineHeight: 1.7, direction: lang === "he" ? "rtl" : "ltr" }} />
              <div style={{ marginTop: 8, display: "flex", gap: 8 }}>
                <button className="btn btn-primary" style={{ fontSize: ".8rem", padding: "6px 14px" }} onClick={() => setEditing(false)}>שמור</button>
                <button className="btn btn-secondary" style={{ fontSize: ".8rem", padding: "6px 14px" }} onClick={() => { updateText(msg.langs[lang]); setEditing(false); }}>איפוס</button>
              </div>
            </>
          ) : (
            <div style={{ background: "var(--sand-bg)", borderRadius: 10, padding: 12, fontSize: ".84rem", lineHeight: 1.75, whiteSpace: "pre-wrap", color: "var(--text-secondary)", direction: lang === "he" ? "rtl" : "ltr" }}>
              {currentText}
            </div>
          )}
          <div style={{ fontSize: ".7rem", color: "var(--text-muted)", marginTop: 8 }}>
            משתנים: {"{שם_אורח}"} · {"{צימר}"} · {"{קוד}"} · {"{תאריך_כניסה}"} · {"{תאריך_יציאה}"} · {"{שעת_כניסה}"} · {"{שעת_יציאה}"} · {"{מחיר}"} · {"{לינק_סליקה}"}
          </div>
        </div>
      )}
    </div>
  );
}

function Section({ title, children }) {
  return (
    <div className="detail-section" style={{ marginBottom: 16 }}>
      <div className="detail-section-title">{title}</div>
      {children}
    </div>
  );
}

function Field({ label, value, onChange }) {
  return (
    <div style={{ marginBottom: 10 }}>
      <div style={{ fontSize: ".78rem", color: "var(--text-muted)", marginBottom: 4 }}>{label}</div>
      <input className="input" value={value || ""} onChange={e => onChange(e.target.value)} />
    </div>
  );
}

export default function Settings() {
  const [checkinTime,  setCheckinTime]  = useState("14:00");
  const [checkoutTime, setCheckoutTime] = useState("14:00");
  const [saved,        setSaved]        = useState(false);
  const [bizSaved,     setBizSaved]     = useState(false);
  const [loading,      setLoading]      = useState(true);

  const [biz, setBiz] = useState({
    business_name_he: "מדבר וים",
    business_name_en: "Desert and Sea",
    business_type: "שותפות רשומה",
    company_id: "558487823",
    address: "קיבוץ מעלה צרויה 2, עין גדי, ישראל",
    website: "https://desert-sea.co.il/",
    phone_business: "052-3730377",
    email_business: "rafi@desert-sea.co.il",
    owner1_name_he: "רפי איילון",
    owner1_name_en: "Rafi Ayalon",
    owner1_phone: "058-4222666",
    owner1_email: "rafiayalon@gmail.com",
    owner1_vat_id: "022058580",
    owner2_name_he: "אבישג איילון",
    owner2_name_en: "Avishag Ayalon",
    owner2_phone: "052-3960773",
    owner2_email: "avishaga@ein-gedi.co.il",
    owner2_vat_id: "032081937",
  });

  useEffect(() => {
    fetch(`${API_BASE}/settings/`)
      .then(r => r.json())
      .then(data => {
        if (data.business_name_he) setBiz(prev => ({ ...prev, ...data }));
        if (data.default_checkin_time)  setCheckinTime(data.default_checkin_time);
        if (data.default_checkout_time) setCheckoutTime(data.default_checkout_time);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  const updateBiz = (field, val) => setBiz(prev => ({ ...prev, [field]: val }));

  const saveAll = async () => {
    try {
      await fetch(`${API_BASE}/settings/`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ...biz,
          default_checkin_time: checkinTime,
          default_checkout_time: checkoutTime,
        }),
      });
      setSaved(true);
      setBizSaved(true);
      setTimeout(() => { setSaved(false); setBizSaved(false); }, 2500);
    } catch { alert("שמירה נכשלה"); }
  };

  if (loading) return <div style={{ padding: 40, textAlign: "center", color: "var(--text-muted)" }}>טוען...</div>;

  return (
    <div style={{ maxWidth: 700 }}>
      <div className="page-header">
        <div className="page-title">הגדרות</div>
      </div>

      {/* פרטי העסק */}
      <Section title="🏢 פרטי העסק">
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
          <Field label="שם העסק (עברית)"   value={biz.business_name_he} onChange={v => updateBiz("business_name_he", v)} />
          <Field label="שם העסק (אנגלית)"  value={biz.business_name_en} onChange={v => updateBiz("business_name_en", v)} />
          <Field label="סוג התאגדות"        value={biz.business_type}    onChange={v => updateBiz("business_type", v)} />
          <Field label="ח.פ / מספר חברה"   value={biz.company_id}       onChange={v => updateBiz("company_id", v)} />
          <Field label="טלפון עסקי"         value={biz.phone_business}   onChange={v => updateBiz("phone_business", v)} />
          <Field label="מייל עסקי"          value={biz.email_business}   onChange={v => updateBiz("email_business", v)} />
          <Field label="אתר"                value={biz.website}          onChange={v => updateBiz("website", v)} />
          <Field label="כתובת"              value={biz.address}          onChange={v => updateBiz("address", v)} />
        </div>
      </Section>

      {/* רפי */}
      <Section title="👤 רפי איילון — בעלים 50%">
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
          <Field label="שם (עברית)"   value={biz.owner1_name_he} onChange={v => updateBiz("owner1_name_he", v)} />
          <Field label="שם (אנגלית)"  value={biz.owner1_name_en} onChange={v => updateBiz("owner1_name_en", v)} />
          <Field label="טלפון"        value={biz.owner1_phone}   onChange={v => updateBiz("owner1_phone", v)} />
          <Field label="מייל"         value={biz.owner1_email}   onChange={v => updateBiz("owner1_email", v)} />
          <Field label="עוסק מורשה"   value={biz.owner1_vat_id}  onChange={v => updateBiz("owner1_vat_id", v)} />
        </div>
      </Section>

      {/* אבישג */}
      <Section title="👤 אבישג איילון — בעלים 50%">
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
          <Field label="שם (עברית)"   value={biz.owner2_name_he} onChange={v => updateBiz("owner2_name_he", v)} />
          <Field label="שם (אנגלית)"  value={biz.owner2_name_en} onChange={v => updateBiz("owner2_name_en", v)} />
          <Field label="טלפון"        value={biz.owner2_phone}   onChange={v => updateBiz("owner2_phone", v)} />
          <Field label="מייל"         value={biz.owner2_email}   onChange={v => updateBiz("owner2_email", v)} />
          <Field label="עוסק מורשה"   value={biz.owner2_vat_id}  onChange={v => updateBiz("owner2_vat_id", v)} />
        </div>
      </Section>

      {/* זמני כניסה ויציאה */}
      <Section title="🕐 זמני כניסה ויציאה (ברירת מחדל)">
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
          <div>
            <div style={{ fontSize: ".82rem", color: "var(--text-muted)", marginBottom: 6 }}>שעת כניסה</div>
            <input className="input" type="time" value={checkinTime} onChange={e => setCheckinTime(e.target.value)} />
          </div>
          <div>
            <div style={{ fontSize: ".82rem", color: "var(--text-muted)", marginBottom: 6 }}>שעת יציאה</div>
            <input className="input" type="time" value={checkoutTime} onChange={e => setCheckoutTime(e.target.value)} />
          </div>
        </div>
      </Section>

      {/* WhatsApp */}
      <Section title="📱 הודעות WhatsApp">
        <div style={{ fontSize: ".8rem", color: "var(--text-muted)", marginBottom: 14, padding: "8px 12px", background: "var(--sand-bg)", borderRadius: 8 }}>
          לחץ על הודעה לצפייה ועריכה · 4 שפות · תצוגה מקדימה עם נתוני אורח לדוגמה
        </div>
        {WHATSAPP_MESSAGES.map(msg => (
          <MessageCard key={msg.id} msg={msg} />
        ))}
      </Section>

      {/* MiniHotel */}
      <Section title="MiniHotel">
        <div className="detail-row">
          <span className="detail-label">מלון</span>
          <span className="detail-value">desert89</span>
        </div>
        <div className="detail-row">
          <span className="detail-label">מצב</span>
          <span className="detail-value" style={{ color: "var(--success)" }}>🟢 מחובר — Production</span>
        </div>
      </Section>

      {/* TTLock */}
      <Section title="TTLock">
        <div className="detail-row">
          <span className="detail-label">מדבר (דלת חומה)</span>
          <span className="detail-value" style={{ color: "var(--text-muted)" }}>לא מוגדר</span>
        </div>
        <div className="detail-row">
          <span className="detail-label">ים (דלת כחולה)</span>
          <span className="detail-value" style={{ color: "var(--text-muted)" }}>לא מוגדר</span>
        </div>
      </Section>

      {/* ייבוא */}
      <Section title="📥 ייבוא נתונים">
        <div style={{ fontSize: ".8rem", color: "var(--text-muted)", marginBottom: 12 }}>
          ייבוא הזמנות היסטוריות מקובץ Excel של MiniHotel
        </div>
        <ImportExcel />
      </Section>

      <button className="btn btn-primary" onClick={saveAll}>
        {saved ? "✅ נשמר!" : "שמור הגדרות"}
      </button>
    </div>
  );
}
