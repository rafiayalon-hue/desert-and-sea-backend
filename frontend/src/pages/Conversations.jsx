import { useState, useEffect } from "react";

const API_BASE = import.meta.env.VITE_API_URL
  ? `${import.meta.env.VITE_API_URL}/api`
  : "https://selfless-happiness-production.up.railway.app/api";

function formatTime(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  const today = new Date();
  const isToday = d.toDateString() === today.toDateString();
  return isToday
    ? d.toLocaleTimeString("he-IL", { hour: "2-digit", minute: "2-digit" })
    : d.toLocaleDateString("he-IL", { day: "2-digit", month: "2-digit" });
}

// ===== בועת הודעה בודדת =====
function MessageBubble({ msg }) {
  const isInbound = msg.direction === "inbound";
  return (
    <div style={{ display: "flex", justifyContent: isInbound ? "flex-start" : "flex-end", marginBottom: 8 }}>
      <div style={{
        maxWidth: "75%",
        background: isInbound ? "var(--bg-card)" : "var(--terra)",
        color: isInbound ? "var(--text-primary)" : "#fff",
        border: isInbound ? "1px solid var(--border-card)" : "none",
        borderRadius: 14,
        borderBottomLeftRadius: isInbound ? 4 : 14,
        borderBottomRightRadius: isInbound ? 14 : 4,
        padding: "9px 13px",
        fontSize: ".87rem",
        lineHeight: 1.5,
        whiteSpace: "pre-wrap",
        boxShadow: "var(--shadow-sm)",
      }}>
        {msg.body}
        <div style={{
          fontSize: ".65rem", marginTop: 4, textAlign: "left",
          color: isInbound ? "var(--text-muted)" : "rgba(255,255,255,0.75)",
        }}>
          {formatTime(msg.created_at)}
          {!isInbound && (msg.status === "failed" ? " · ⚠️ נכשל" : msg.status === "sent" ? " · ✓" : "")}
        </div>
      </div>
    </div>
  );
}

// ===== חלון שיחה מלאה =====
function ThreadView({ conversation, onClose }) {
  const [messages, setMessages] = useState([]);
  const [loading, setLoading]   = useState(true);
  const [draft, setDraft]       = useState("");
  const [sending, setSending]   = useState(false);

  useEffect(() => {
    fetch(`${API_BASE}/messages/conversations/${encodeURIComponent(conversation.phone)}`)
      .then(r => r.json())
      .then(data => { setMessages(data); setLoading(false); })
      .catch(() => setLoading(false));
  }, [conversation.phone]);

  async function sendReply() {
    if (!draft.trim()) return;
    setSending(true);
    try {
      const res = await fetch(`${API_BASE}/messages/send`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          phone: conversation.phone,
          body: draft,
          booking_id: conversation.booking_id || null,
          message_type: "manual",
        }),
      });
      const result = await res.json();
      setMessages(prev => [...prev, {
        body: draft,
        direction: "outbound",
        status: result.status,
        created_at: new Date().toISOString(),
      }]);
      setDraft("");
      if (result.status === "failed") {
        alert("השליחה נכשלה — ייתכן שאין חלון שירות פתוח (24 שעות) עם האורח הזה");
      }
    } catch {
      alert("שליחה נכשלה — נסה שוב");
    }
    setSending(false);
  }

  return (
    <div style={{
      position: "fixed", inset: 0, background: "rgba(0,0,0,0.45)",
      zIndex: 1000, display: "flex", alignItems: "flex-end", justifyContent: "center",
    }} onClick={onClose}>
      <div style={{
        background: "var(--bg-main)", borderRadius: "16px 16px 0 0", width: "100%", maxWidth: 560,
        height: "80vh", display: "flex", flexDirection: "column", boxShadow: "0 -10px 40px rgba(0,0,0,0.2)",
      }} onClick={e => e.stopPropagation()}>

        {/* Header */}
        <div style={{ background: "var(--terra)", borderRadius: "16px 16px 0 0", padding: "16px 20px", color: "#fff", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div>
            <div style={{ fontWeight: 700, fontSize: "1.05rem" }}>{conversation.guest_name || conversation.phone}</div>
            <div style={{ fontSize: ".75rem", opacity: 0.85, direction: "ltr", textAlign: "right" }}>{conversation.phone}</div>
          </div>
          <button onClick={onClose} style={{ background: "rgba(255,255,255,0.2)", border: "none", color: "#fff", width: 30, height: 30, borderRadius: "50%", cursor: "pointer" }}>✕</button>
        </div>

        {/* Messages */}
        <div style={{ flex: 1, overflowY: "auto", padding: "16px", display: "flex", flexDirection: "column" }}>
          {loading
            ? <div style={{ textAlign: "center", color: "var(--text-muted)", marginTop: 40 }}>טוען שיחה...</div>
            : messages.length === 0
              ? <div style={{ textAlign: "center", color: "var(--text-muted)", marginTop: 40 }}>אין הודעות עדיין</div>
              : messages.map((m, i) => <MessageBubble key={i} msg={m} />)
          }
        </div>

        {/* Reply box */}
        <div style={{ padding: 12, borderTop: "1px solid var(--border-card)", display: "flex", gap: 8 }}>
          <input
            className="input"
            style={{ flex: 1 }}
            placeholder="כתוב תשובה..."
            value={draft}
            onChange={e => setDraft(e.target.value)}
            onKeyDown={e => e.key === "Enter" && sendReply()}
          />
          <button className="btn btn-primary" onClick={sendReply} disabled={sending || !draft.trim()}>
            {sending ? "..." : "שלח"}
          </button>
        </div>
        <div style={{ fontSize: ".68rem", color: "var(--text-muted)", padding: "0 12px 10px", textAlign: "center" }}>
          תשובה חופשית עובדת רק בתוך 24 שעות מאז שהאורח כתב לאחרונה
        </div>
      </div>
    </div>
  );
}

// ===== שורת שיחה ברשימה =====
function ConversationRow({ conversation, onClick }) {
  const isUnanswered = conversation.last_direction === "inbound";
  return (
    <div onClick={onClick} style={{
      display: "flex", alignItems: "center", gap: 12, padding: "12px 14px",
      background: "var(--bg-card)", border: "1px solid var(--border-card)",
      borderRadius: 12, marginBottom: 8, cursor: "pointer", boxShadow: "var(--shadow-sm)",
    }}>
      <div style={{
        width: 42, height: 42, borderRadius: "50%", background: "var(--terra-bg)",
        display: "flex", alignItems: "center", justifyContent: "center",
        fontSize: "1.1rem", fontWeight: 700, color: "var(--terra)", flexShrink: 0,
      }}>
        {(conversation.guest_name || conversation.phone || "?")[0]}
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <span style={{ fontWeight: 600, fontSize: ".92rem" }}>
            {conversation.guest_name || conversation.phone}
          </span>
          <span style={{ fontSize: ".7rem", color: "var(--text-muted)" }}>
            {formatTime(conversation.last_at)}
          </span>
        </div>
        <div style={{
          fontSize: ".8rem", color: isUnanswered ? "var(--text-primary)" : "var(--text-muted)",
          fontWeight: isUnanswered ? 600 : 400,
          overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
        }}>
          {conversation.last_direction === "outbound" && "אתם: "}
          {conversation.last_message}
        </div>
      </div>
      {isUnanswered && (
        <span style={{ width: 9, height: 9, borderRadius: "50%", background: "var(--terra)", flexShrink: 0 }} />
      )}
    </div>
  );
}

export default function Conversations({ onOpenConversation }) {
  const [conversations, setConversations] = useState([]);
  const [loading, setLoading]     = useState(true);
  const [selected, setSelected]   = useState(null);
  const [search, setSearch]       = useState("");

  useEffect(() => {
    fetch(`${API_BASE}/messages/conversations`)
      .then(r => r.json())
      .then(data => { setConversations(data); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  function openConversation(c) {
    setSelected(c);
    onOpenConversation?.(); // מאפס את מונה ה"לא נקרא" ב-App.jsx
  }

  const filtered = conversations.filter(c => {
    const q = search.toLowerCase();
    return !q || (c.guest_name || "").toLowerCase().includes(q) || (c.phone || "").includes(q);
  });

  const unansweredCount = conversations.filter(c => c.last_direction === "inbound").length;

  if (loading) return <div style={{ padding: 40, textAlign: "center", color: "var(--text-muted)" }}>טוען שיחות...</div>;

  return (
    <div style={{ maxWidth: 700 }}>
      <div className="page-header">
        <div>
          <div className="page-title">שיחות</div>
          {unansweredCount > 0 && (
            <div className="page-subtitle">{unansweredCount} ממתינות לתגובה</div>
          )}
        </div>
      </div>

      <div style={{ marginBottom: 14 }}>
        <input className="search-input" style={{ width: "100%", boxSizing: "border-box" }}
          placeholder="🔍 חיפוש לפי שם או טלפון..."
          value={search} onChange={e => setSearch(e.target.value)} />
      </div>

      {filtered.length === 0
        ? <div style={{ textAlign: "center", color: "var(--text-muted)", padding: 40 }}>אין שיחות עדיין</div>
        : filtered.map(c => (
            <ConversationRow key={c.phone} conversation={c} onClick={() => openConversation(c)} />
          ))
      }

      {selected && (
        <ThreadView conversation={selected} onClose={() => setSelected(null)} />
      )}
    </div>
  );
}
