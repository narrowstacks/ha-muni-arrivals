"""API client for 511.org transit data."""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any

import aiohttp

from .const import (
    API_ENDPOINT,
    CABLE_CAR_LINES,
    LINE_ICONS,
    METRO_LINES,
    TIME_FORMAT_FULL,
    TIME_FORMAT_MINUTES,
    TIME_FORMAT_VERBOSE,
    TROLLEYBUS_ROUTES,
)

_LOGGER = logging.getLogger(__name__)


class MuniAPI:
    """API client for 511.org transit data."""

    def __init__(
        self,
        api_key: str,
        agency: str = "SF",
        session: aiohttp.ClientSession | None = None,
    ) -> None:
        """Initialize the API client."""
        self.api_key = api_key
        self.agency = agency
        self._session = session
        self._close_session = False

    async def get_arrivals(self, stop_code: str) -> list[dict[str, Any]]:
        """Get arrival information for a stop."""
        url = f"{API_ENDPOINT}?api_key={self.api_key}&agency={self.agency}&stopcode={stop_code}&format=json"
        
        session = await self._get_session()
        
        try:
            async with session.get(url) as response:
                if response.status != 200:
                    _LOGGER.error(f"API request failed with status {response.status}")
                    return []
                
                text = await response.text()
                # Handle BOM character
                clean_text = text.encode().decode('utf-8-sig')
                data = json.loads(clean_text)
                
                return self._format_arrivals(data)
                
        except Exception as e:
            _LOGGER.error(f"Error fetching data for stop {stop_code}: {e}")
            return []

    def _format_arrivals(self, data: dict) -> list[dict[str, Any]]:
        """Format arrival data from API response."""
        try:
            arrivals = {}
            
            if not data.get("ServiceDelivery", {}).get("StopMonitoringDelivery", {}).get("MonitoredStopVisit"):
                return []
            
            visits = data["ServiceDelivery"]["StopMonitoringDelivery"]["MonitoredStopVisit"]
            
            for visit in visits:
                journey = visit.get("MonitoredVehicleJourney", {})
                if not journey or not journey.get("MonitoredCall"):
                    continue
                
                line_ref = journey.get("LineRef", "").upper()
                destination = journey.get("DestinationName", "")
                arrival_time = journey.get("MonitoredCall", {}).get("ExpectedArrivalTime")
                
                if not arrival_time:
                    continue
                
                # Calculate arrival time info
                minutes_until = self._calculate_minutes_until_arrival(arrival_time)
                
                # Get line icon
                line_icon = self._get_line_icon(line_ref)
                
                # Format line name with icon
                line_with_icon = f"{line_icon} {line_ref}" if line_icon else line_ref
                
                # Group arrivals by line
                if line_with_icon not in arrivals:
                    arrivals[line_with_icon] = {
                        "line": line_with_icon,
                        "line_ref": line_ref,
                        "destinations": set(),
                        "times": []
                    }
                
                arrivals[line_with_icon]["times"].append({
                    "minutes": minutes_until,
                    "arrival_time": arrival_time,
                    "destination": destination,
                    "formatted_time": f"{minutes_until} min" if minutes_until != "?" else "?"
                })
                
                if destination:
                    arrivals[line_with_icon]["destinations"].add(destination)
            
            # Convert to list and sort
            formatted_arrivals = []
            for line_data in arrivals.values():
                # Sort times by minutes
                line_data["times"].sort(key=lambda x: int(x["minutes"]) if x["minutes"] != "?" else 999)
                # Convert destinations set to list
                line_data["destinations"] = list(line_data["destinations"])
                formatted_arrivals.append(line_data)
            
            # Sort by earliest arrival
            formatted_arrivals.sort(key=lambda x: int(x["times"][0]["minutes"]) if x["times"] and x["times"][0]["minutes"] != "?" else 999)
            
            return formatted_arrivals
            
        except Exception as e:
            _LOGGER.error(f"Error formatting arrivals: {e}")
            return []

    def _calculate_minutes_until_arrival(self, arrival_time_str: str) -> str:
        """Calculate minutes until arrival."""
        try:
            arrival_time = datetime.fromisoformat(arrival_time_str.replace('Z', '+00:00'))
            now = datetime.now(timezone.utc)
            diff = arrival_time - now
            minutes = max(0, int(diff.total_seconds() / 60))
            return str(minutes)
        except Exception:
            return "?"

    def _get_line_icon(self, line_ref: str) -> str:
        """Get appropriate icon for line."""
        # Check if it's a number-based route
        if line_ref.isdigit():
            if line_ref in TROLLEYBUS_ROUTES:
                return LINE_ICONS["trolleybus"]
            else:
                return LINE_ICONS["bus"]
        
        # Cable car lines
        elif line_ref in CABLE_CAR_LINES:
            return LINE_ICONS["cable_car"]
        
        # Metro/streetcar lines
        elif line_ref in METRO_LINES:
            return LINE_ICONS["metro"]
        
        # Special services
        elif line_ref == "91" or "OWL" in line_ref:
            return LINE_ICONS["owl"]
        elif "R" in line_ref:
            return LINE_ICONS["express"]
        
        return ""

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None:
            self._session = aiohttp.ClientSession()
            self._close_session = True
        return self._session

    async def close(self) -> None:
        """Close the session."""
        if self._session and self._close_session:
            await self._session.close()