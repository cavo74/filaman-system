import asyncio
import logging
from typing import Any

import httpx

from app.plugins.base import BaseDriver

logger = logging.getLogger(__name__)

# MK4 has one extruder and no AMS, so the whole printer is a single logical
# slot. Reusing "0-0" keeps it consistent with how the manager treats a
# single-slot printer elsewhere (see PluginManager._handle_slots_update).
_SLOT_INDEX = "0-0"

# PrusaLink's own state strings (Buddy firmware /api/v1/status).
_PRINTING_STATES = {"PRINTING", "BUSY", "ATTENTION"}


class Driver(BaseDriver):
    driver_key = "prusa_mk4"

    def __init__(self, printer_id: int, config: dict[str, Any], emitter):
        super().__init__(printer_id, config, emitter)
        self._client: httpx.AsyncClient | None = None
        self._poll_task: asyncio.Task | None = None
        self._last_status: dict[str, Any] | None = None
        self._connected = False
        self._assigned_spool_id: int | None = None
        self._assigned_meta: dict[str, Any] = {}

    def validate_config(self) -> None:
        if not self.config.get("host"):
            raise ValueError("prusa_mk4: 'host' is required")
        if not self.config.get("api_key"):
            raise ValueError("prusa_mk4: 'api_key' is required")

    async def start(self) -> None:
        host = self.config["host"]
        scheme = "https" if self.config.get("use_https") else "http"
        self._client = httpx.AsyncClient(
            base_url=f"{scheme}://{host}",
            headers={"X-Api-Key": self.config["api_key"]},
            timeout=5.0,
        )
        self._running = True
        self._poll_task = asyncio.create_task(self._poll_loop())

    async def stop(self) -> None:
        self._running = False
        if self._poll_task is not None:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except (asyncio.CancelledError, Exception):
                pass
            self._poll_task = None
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _poll_loop(self) -> None:
        interval = int(self.config.get("poll_interval") or 5)
        while self._running:
            await self._poll_once()
            await asyncio.sleep(interval)

    async def _poll_once(self) -> None:
        assert self._client is not None
        try:
            response = await self._client.get("/api/v1/status")
            response.raise_for_status()
            self._last_status = response.json()
            was_connected = self._connected
            self._connected = True
            self.log_debug("in", "/api/v1/status", self._last_status)
            if not was_connected:
                logger.info(f"prusa_mk4: printer {self.printer_id} connected")
        except Exception as e:
            if self._connected:
                logger.warning(f"prusa_mk4: printer {self.printer_id} unreachable: {e}")
            self._connected = False

        self.emit({
            "event_type": "printer_status",
            "connected": self._connected,
        })

    async def assign_pending_spool(
        self,
        spool_id: int,
        filament_data: dict[str, Any],
        timeout_seconds: int = 60,
    ) -> None:
        """Logically assign a spool to the (single) extruder slot.

        PrusaLink has no concept of a spool ID, so there is nothing to push to
        the printer itself — this just tells FilaMan which spool is loaded,
        the same way manually assigning a slot in the UI would.
        """
        self._assigned_spool_id = spool_id
        self._assigned_meta = {
            "tray_type": filament_data.get("material_type"),
            "tray_color": filament_data.get("color"),
        }
        self.emit({
            "event_type": "slots_update",
            "slots": [{
                "slot_index": _SLOT_INDEX,
                "slot_name": "Extruder",
                "present": True,
                "spool_id": spool_id,
                **{k: v for k, v in self._assigned_meta.items() if v},
            }],
        })

    def health(self) -> dict[str, Any]:
        base = super().health()
        base["connected"] = self._connected
        if self._last_status:
            printer = self._last_status.get("printer") or {}
            base["state"] = printer.get("state")
        return base

    async def get_display_state(self) -> dict[str, Any] | None:
        """Cheap, cached snapshot for the Display API — never queries the printer."""
        if self._last_status is None:
            return {"connected": self._connected}

        printer = self._last_status.get("printer") or {}
        job = self._last_status.get("job") or {}

        return {
            "connected": self._connected,
            "state": printer.get("state"),
            "job": {
                "progress": job.get("progress"),
                "remaining_sec": job.get("time_remaining"),
            },
            "temperatures": {
                "nozzle": printer.get("temp_nozzle"),
                "nozzle_target": printer.get("target_nozzle"),
                "bed": printer.get("temp_bed"),
                "bed_target": printer.get("target_bed"),
            },
        }
