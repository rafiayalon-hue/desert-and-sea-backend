"""
MiniHotel API integration.
Production: https://api2.minihotel.cloud

Authentication (JSON/Reverse ARI):
  Headers: User, Password, hotel_id

Authentication (ARI XML):
  XML body: <Authentication username="..." password="..." />

Note: MiniHotel does NOT provide a public reservations-fetch API.
Bookings arrive via Webhook (room.occupancy.updated).
This client handles:
  - UpdateCleanStatus (JSON)
  - GetPosItems (JSON)  
  - Bulk ARI update (JSON/XML)
"""
import httpx
from app.config import settings

BASE_URL = "https://api2.minihotel.cloud"
GDS_URL = f"{BASE_URL}/gds"  # ARI XML endpoint


class MiniHotelClient:
    def __init__(self):
        # JSON API headers (Content & Reverse ARI)
        self.headers = {
            "User": settings.MH_USER,
            "Password": settings.MH_PASS,
            "hotel_id": settings.MINIHOTEL_HOTEL_ID,
            "Content-Type": "application/json",
        }

    # ------------------------------------------------------------------
    # Clean Status (JSON)
    # ------------------------------------------------------------------
    async def update_clean_status(self, room_type_code: str, date: str, status: str) -> dict:
        """
        Update room cleaning status.
        status: "Clean" | "Dirty" | "Inspected"
        """
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{BASE_URL}/api/Agents/Sci/UpdateCleanStatus",
                headers=self.headers,
                json={
                    "RoomTypeCode": room_type_code,
                    "Date": date,
                    "Status": status,
                },
                timeout=10,
            )
            response.raise_for_status()
            return response.json()

    # ------------------------------------------------------------------
    # POS Items (JSON)
    # ------------------------------------------------------------------
    async def get_pos_items(self) -> list[dict]:
        """Fetch POS menu items."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{BASE_URL}/api/Agents/Sci/GetPosItems",
                headers=self.headers,
                json={},
                timeout=10,
            )
            response.raise_for_status()
            return response.json()

    # ------------------------------------------------------------------
    # Bulk ARI Update (JSON)
    # Update availability & rates for room types
    # ------------------------------------------------------------------
    async def update_availability(self, room_type_code: str, date: str,
                                   availability: int) -> dict:
        """
        Update room availability for a specific date.
        """
        payload = [
            {
                "RoomTypeCode": room_type_code,
                "Dates": [
                    {
                        "Date": date,
                        "Availability": availability,
                    }
                ],
            }
        ]
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{BASE_URL}/AgentsScreenA/api/Agents/ScreenA",
                headers=self.headers,
                json=payload,
                timeout=10,
            )
            response.raise_for_status()
            return response.json()

    # ------------------------------------------------------------------
    # Health check — verify credentials work
    # ------------------------------------------------------------------
    async def health_check(self) -> dict:
        """Quick check that credentials are valid."""
        try:
            await self.get_pos_items()
            return {"status": "ok"}
        except Exception as e:
            return {"status": "error", "detail": str(e)}


minihotel_client = MiniHotelClient()
