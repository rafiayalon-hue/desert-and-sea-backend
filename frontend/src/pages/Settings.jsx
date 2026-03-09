import ImportExcel from "../components/ImportExcel";
import { useState } from "react";
import { WHATSAPP_MESSAGES } from "../data/whatsappMessages";

const PREVIEW = {
  guest: "יובל", checkin: "04.01.26", checkout: "07.01.26",
  checkinTime: "15:00", checkoutTime: "11:00",
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

export default function Settings() {
  const [checkinTime,  setCheckinTime]  = useState("14:00");
  const [checkoutTime, setCheckoutTime] = useState("12:00");
  const [saved,        setSaved]        = useState(false);

  const save = () => { setSaved(true); setTimeout(() => setSaved(false), 2000); };

  return (
    <div style={{ maxWidth: 700 }}>
      <div className="page-header">
        <div className="page-title">הגדרות</div>
      </div>

      <Section title="זמני כניסה ויציאה">
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

      <Section title="📱 הודעות WhatsApp">
        <div style={{ fontSize: ".8rem", color: "var(--text-muted)", marginBottom: 14, padding: "8px 12px", background: "var(--sand-bg)", borderRadius: 8 }}>
          לחץ על הודעה לצפייה ועריכה · 4 שפות · תצוגה מקדימה עם נתוני אורח לדוגמה
        </div>
        {WHATSAPP_MESSAGES.map(msg => (
          <MessageCard key={msg.id} msg={msg} />
        ))}
      </Section>

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
<Section title="📥 ייבוא נתונים">
          <div style={{ fontSize: ".8rem", color: "var(--text-muted)", marginBottom: 12 }}>
            ייבוא הזמנות היסטוריות מקובץ Excel של MiniHotel
          </div>
          <ImportExcel />
        </Section>
     
      <button className="btn btn-primary" onClick={save}>
        {saved ? "✅ נשמר!" : "שמור הגדרות"}
      </button>
    </div>
  );
}
