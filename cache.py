"""Caching manager for Muni Times integration."""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .exceptions import MuniCacheError

_LOGGER = logging.getLogger(__name__)


class MuniTimesCache:
    """Cache manager for transit data with file persistence."""
    
    def __init__(
        self,
        hass: HomeAssistant,
        cache_duration_minutes: int = 30,
        max_cache_size_mb: int = 10,
        cache_dir: str | None = None,
    ) -> None:
        """Initialize the cache manager."""
        self.hass = hass
        self.cache_duration = timedelta(minutes=cache_duration_minutes)
        self.max_cache_size_bytes = max_cache_size_mb * 1024 * 1024
        
        # Set up cache directory
        if cache_dir:
            self.cache_dir = Path(cache_dir)
        else:
            self.cache_dir = Path(hass.config.path("muni_times_cache"))
        
        self.cache_dir.mkdir(exist_ok=True)
        self.cache_file = self.cache_dir / "transit_data.json"
        self.metadata_file = self.cache_dir / "cache_metadata.json"
        
        # In-memory cache for performance
        self._memory_cache: dict[str, dict[str, Any]] = {}
        self._cache_timestamps: dict[str, datetime] = {}
        self._lock = asyncio.Lock()
        
        # Load existing cache
        self._load_cache_from_disk()
    
    def _load_cache_from_disk(self) -> None:
        """Load cache data from disk on startup."""
        try:
            if self.cache_file.exists():
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)
                
                # Load cached data with timestamp validation
                current_time = dt_util.utcnow()
                for stop_code, data in cache_data.items():
                    cached_at_str = data.get("cached_at")
                    if cached_at_str:
                        try:
                            cached_at = datetime.fromisoformat(cached_at_str.replace('Z', '+00:00'))
                            age = current_time - cached_at
                            
                            if age <= self.cache_duration:
                                self._memory_cache[stop_code] = data
                                self._cache_timestamps[stop_code] = cached_at
                            else:
                                _LOGGER.debug(
                                    "Discarding expired cache entry for stop %s (age: %s)",
                                    stop_code, age
                                )
                        except ValueError as e:
                            _LOGGER.warning(
                                "Invalid timestamp in cache for stop %s: %s",
                                stop_code, e
                            )
                
                _LOGGER.info(
                    "Loaded %d valid cache entries from disk",
                    len(self._memory_cache)
                )
            
        except Exception as e:
            _LOGGER.warning("Failed to load cache from disk: %s", e)
            self._memory_cache = {}
            self._cache_timestamps = {}
    
    async def _save_cache_to_disk(self) -> None:
        """Save current cache to disk."""
        try:
            # Prepare data for serialization
            cache_data = {}
            for stop_code, data in self._memory_cache.items():
                cache_data[stop_code] = data.copy()
            
            # Write to temporary file first, then rename (atomic operation)
            temp_file = self.cache_file.with_suffix('.tmp')
            
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2)
            
            # Atomic rename
            temp_file.rename(self.cache_file)
            
            # Update metadata
            metadata = {
                "last_saved": dt_util.utcnow().isoformat(),
                "entry_count": len(cache_data),
                "file_size_bytes": self.cache_file.stat().st_size,
            }
            
            with open(self.metadata_file, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, ensure_ascii=False, indent=2)
            
        except Exception as e:
            _LOGGER.error("Failed to save cache to disk: %s", e)
            raise MuniCacheError(f"Failed to save cache: {e}") from e
    
    async def cache_data(self, stop_code: str, data: dict[str, Any]) -> None:
        """Cache data for a specific stop."""
        if not stop_code or not data:
            return
        
        async with self._lock:
            try:
                current_time = dt_util.utcnow()
                
                # Prepare cache entry
                cache_entry = {
                    "stop_code": stop_code,
                    "cached_at": current_time.isoformat(),
                    "arrivals": data.get("arrivals", []),
                    "config": data.get("config", {}),
                }
                
                # Store in memory cache
                self._memory_cache[stop_code] = cache_entry
                self._cache_timestamps[stop_code] = current_time
                
                # Clean up expired entries
                await self._cleanup_expired_entries()
                
                # Check cache size and clean up if needed
                await self._enforce_cache_size_limit()
                
                # Save to disk (async to avoid blocking)
                asyncio.create_task(self._save_cache_to_disk())
                
                _LOGGER.debug("Cached data for stop %s", stop_code)
                
            except Exception as e:
                _LOGGER.error("Failed to cache data for stop %s: %s", stop_code, e)
                raise MuniCacheError(f"Failed to cache data: {e}") from e
    
    async def get_cached_data(self, stop_code: str) -> dict[str, Any] | None:
        """Get cached data for a specific stop."""
        if not stop_code:
            return None
        
        async with self._lock:
            try:
                if stop_code not in self._memory_cache:
                    return None
                
                cached_at = self._cache_timestamps.get(stop_code)
                if not cached_at:
                    # Remove invalid entry
                    self._memory_cache.pop(stop_code, None)
                    return None
                
                # Check if cache is still valid
                age = dt_util.utcnow() - cached_at
                if age > self.cache_duration:
                    # Remove expired entry
                    self._memory_cache.pop(stop_code, None)
                    self._cache_timestamps.pop(stop_code, None)
                    _LOGGER.debug("Cache expired for stop %s (age: %s)", stop_code, age)
                    return None
                
                cached_data = self._memory_cache[stop_code].copy()
                cached_data["cache_age_minutes"] = age.total_seconds() / 60
                
                _LOGGER.debug(
                    "Retrieved cached data for stop %s (age: %.1f minutes)",
                    stop_code, cached_data["cache_age_minutes"]
                )
                
                return cached_data
                
            except Exception as e:
                _LOGGER.error("Failed to get cached data for stop %s: %s", stop_code, e)
                return None
    
    async def clear_cache(self, stop_code: str | None = None) -> None:
        """Clear cache for a specific stop or all stops."""
        async with self._lock:
            try:
                if stop_code:
                    # Clear specific stop
                    self._memory_cache.pop(stop_code, None)
                    self._cache_timestamps.pop(stop_code, None)
                    _LOGGER.info("Cleared cache for stop %s", stop_code)
                else:
                    # Clear all cache
                    self._memory_cache.clear()
                    self._cache_timestamps.clear()
                    _LOGGER.info("Cleared all cache data")
                
                # Save updated cache to disk
                await self._save_cache_to_disk()
                
            except Exception as e:
                _LOGGER.error("Failed to clear cache: %s", e)
                raise MuniCacheError(f"Failed to clear cache: {e}") from e
    
    async def _cleanup_expired_entries(self) -> None:
        """Remove expired entries from cache."""
        current_time = dt_util.utcnow()
        expired_stops = []
        
        for stop_code, cached_at in self._cache_timestamps.items():
            age = current_time - cached_at
            if age > self.cache_duration:
                expired_stops.append(stop_code)
        
        for stop_code in expired_stops:
            self._memory_cache.pop(stop_code, None)
            self._cache_timestamps.pop(stop_code, None)
        
        if expired_stops:
            _LOGGER.debug("Cleaned up %d expired cache entries", len(expired_stops))
    
    async def _enforce_cache_size_limit(self) -> None:
        """Enforce cache size limits by removing oldest entries."""
        # Estimate memory usage (rough calculation)
        estimated_size = 0
        for data in self._memory_cache.values():
            estimated_size += len(json.dumps(data, ensure_ascii=False))
        
        if estimated_size > self.max_cache_size_bytes:
            # Remove oldest entries until under limit
            sorted_entries = sorted(
                self._cache_timestamps.items(),
                key=lambda x: x[1]  # Sort by timestamp
            )
            
            removed_count = 0
            for stop_code, _ in sorted_entries:
                self._memory_cache.pop(stop_code, None)
                self._cache_timestamps.pop(stop_code, None)
                removed_count += 1
                
                # Recalculate size
                estimated_size = sum(
                    len(json.dumps(data, ensure_ascii=False))
                    for data in self._memory_cache.values()
                )
                
                if estimated_size <= self.max_cache_size_bytes * 0.8:  # Leave some headroom
                    break
            
            if removed_count > 0:
                _LOGGER.info(
                    "Removed %d old cache entries to stay under size limit",
                    removed_count
                )
    
    def get_cache_info(self) -> dict[str, Any]:
        """Get information about the current cache state."""
        current_time = dt_util.utcnow()
        
        # Calculate cache statistics
        total_entries = len(self._memory_cache)
        valid_entries = 0
        expired_entries = 0
        
        for stop_code, cached_at in self._cache_timestamps.items():
            age = current_time - cached_at
            if age <= self.cache_duration:
                valid_entries += 1
            else:
                expired_entries += 1
        
        # Calculate estimated size
        estimated_size_bytes = sum(
            len(json.dumps(data, ensure_ascii=False))
            for data in self._memory_cache.values()
        )
        
        # Get file size if cache file exists
        file_size_bytes = 0
        if self.cache_file.exists():
            file_size_bytes = self.cache_file.stat().st_size
        
        return {
            "total_entries": total_entries,
            "valid_entries": valid_entries,
            "expired_entries": expired_entries,
            "cache_duration_minutes": self.cache_duration.total_seconds() / 60,
            "estimated_memory_size_kb": estimated_size_bytes / 1024,
            "file_size_kb": file_size_bytes / 1024,
            "max_cache_size_mb": self.max_cache_size_bytes / (1024 * 1024),
            "cache_directory": str(self.cache_dir),
            "cache_file_exists": self.cache_file.exists(),
        }
    
    async def has_cached_data(self, stop_code: str) -> bool:
        """Check if we have valid cached data for a stop."""
        cached_data = await self.get_cached_data(stop_code)
        return cached_data is not None
    
    def get_cached_stop_codes(self) -> list[str]:
        """Get list of stop codes that have cached data."""
        return list(self._memory_cache.keys())
    
    async def cleanup(self) -> None:
        """Clean up cache resources."""
        try:
            # Save final state to disk
            await self._save_cache_to_disk()
            
            # Clear memory cache
            self._memory_cache.clear()
            self._cache_timestamps.clear()
            
            _LOGGER.debug("Cache cleanup completed")
            
        except Exception as e:
            _LOGGER.warning("Error during cache cleanup: %s", e)