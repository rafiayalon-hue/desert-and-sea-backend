"""
MiniHotel API integration.
Docs: https://www.minihotel.app/api (replace with actual docs URL when available)
"""
import httpx

from app.config import settings

BASE_URL = "https://api2.minihotel.cloud/api/Agents/Sci"


class MiniHotelClient:
    def __init__(self):
        self.headers = {
            "Authorization": f"Bearer {settings.minihotel_api_key}",
            "Content-Type": "application/json",
        }

    async def get_bookings(self, from_date: str, to_date: str) -> list[dict]:
        """Fetch bookings for a date range (YYYY-MM-DD format)."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{BASE_URL}/reservations",
                headers=self.headers,
                params={
                    "property_id": settings.minihotel_property_id,
                    "from": from_date,
                    "to": to_date,
                },
            )
            response.raise_for_status()
            return response.json()

    async def get_booking(self, booking_id: str) -> dict:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{BASE_URL}/reservations/{booking_id}",
                headers=self.headers,
            )
            response.raise_for_status()
            return response.json()

    async def get_occupancy_stats(self, month: str) -> dict:
        """Get occupancy statistics for a given month (YYYY-MM format)."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{BASE_URL}/stats/occupancy",
                headers=self.headers,
                params={"property_id": settings.minihotel_property_id, "month": month},
            )
            response.raise_for_status()
            return response.json()


minihotel_client = MiniHotelClient()
