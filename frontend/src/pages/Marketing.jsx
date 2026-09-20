// לשונית שיווק — NEW (19.9.26)
import { useBookings } from "../hooks/useBookings";
import MarketingReports from "../components/MarketingReports";

export default function Marketing({ navigate }) {
  const { bookings, loading } = useBookings({});
  const confirmed = bookings.filter(b => b.status === "confirmed");
  if (loading) return <div style={{ padding: 20, color: "var(--text-muted)" }}>טוען נתונים…</div>;
  return <MarketingReports confirmed={confirmed} navigate={navigate} />;
}
