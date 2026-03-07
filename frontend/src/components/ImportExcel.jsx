import { useState } from "react";

const API_BASE = import.meta.env.VITE_API_URL || "https://selfless-happiness-production.up.railway.app";

export default function ImportExcel() {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  const handleUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    setLoading(true);
    setResult(null);
    setError(null);

    const formData = new FormData();
    formData.append("file", file);

    try {
      const res = await fetch(`${API_BASE}/api/bookings/upload-excel`, {
        method: "POST",
        body: formData,
      });
      const data = await res.json();
      setResult(data);
    } catch (err) {
      setError("שגיאה בהעלאה");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <input
        type="file"
        accept=".xlsx,.xls"
        onChange={handleUpload}
        style={{ display: "none" }}
        id="excel-upload"
      />
      <label htmlFor="excel-upload" className="btn btn-secondary" style={{ cursor: "pointer" }}>
        {loading ? "מעלה..." : "📂 בחר קובץ Excel"}
      </label>
      {result && (
        <div style={{ marginTop: 10, fontSize: ".85rem", color: "var(--success)" }}>
          ✅ יובאו {result.inserted} הזמנות חדשות, עודכנו {result.updated}
        </div>
      )}
      {error && (
        <div style={{ marginTop: 10, fontSize: ".85rem", color: "var(--danger)" }}>
          ❌ {error}
        </div>
      )}
    </div>
  );
}
