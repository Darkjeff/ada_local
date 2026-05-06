"""
Function Executor - Executes Gemma-routed functions with actual backend calls.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from dataclasses import dataclass, field
import threading
import time


@dataclass
class ActiveTimer:
    """Represents an active countdown timer."""
    label: str
    duration_seconds: int
    start_time: float
    
    @property
    def remaining_seconds(self) -> int:
        elapsed = time.time() - self.start_time
        return max(0, int(self.duration_seconds - elapsed))
    
    @property
    def is_expired(self) -> bool:
        return self.remaining_seconds <= 0
    
    def format_remaining(self) -> str:
        secs = self.remaining_seconds
        mins, secs = divmod(secs, 60)
        hours, mins = divmod(mins, 60)
        if hours:
            return f"{hours}h {mins}m {secs}s"
        elif mins:
            return f"{mins}m {secs}s"
        return f"{secs}s"


class FunctionExecutor:
    """Central executor for all Gemma-routed functions."""
    
    def __init__(self):
        self.task_manager = None
        self.calendar_manager = None
        self.kasa_manager = None
        self.ha_manager = None
        self.weather_manager = None
        self.news_manager = None
        
        # In-memory timer storage
        self.active_timers: Dict[str, ActiveTimer] = {}
        self._timer_lock = threading.Lock()
        
        # Lazy load managers
        self._init_managers()
    
    def _init_managers(self):
        """Initialize manager references."""
        try:
            from core.tasks import TaskManager
            self.task_manager = TaskManager()
        except Exception as e:
            print(f"[FunctionExecutor] TaskManager init failed: {e}")
        
        try:
            from core.calendar_manager import CalendarManager
            self.calendar_manager = CalendarManager()
        except Exception as e:
            print(f"[FunctionExecutor] CalendarManager init failed: {e}")
        
        try:
            from core.kasa_control import kasa_manager
            self.kasa_manager = kasa_manager
        except Exception as e:
            print(f"[FunctionExecutor] KasaManager init failed: {e}")

        try:
            from core.ha_control import ha_manager
            self.ha_manager = ha_manager
        except Exception as e:
            print(f"[FunctionExecutor] HAManager init failed: {e}")
        
        try:
            from core.weather import WeatherManager
            self.weather_manager = WeatherManager()
        except Exception as e:
            print(f"[FunctionExecutor] WeatherManager init failed: {e}")
        
        try:
            from core.news import NewsManager
            self.news_manager = NewsManager()
        except Exception as e:
            print(f"[FunctionExecutor] NewsManager init failed: {e}")
    
    def execute(self, func_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a function and return structured result.
        
        Returns:
            {
                "success": bool,
                "message": str,  # Human-readable result
                "data": Any      # Raw data if applicable
            }
        """
        try:
            if func_name == "control_light":
                return self._control_light(params)
            elif func_name == "set_timer":
                return self._set_timer(params)
            elif func_name == "set_alarm":
                return self._set_alarm(params)
            elif func_name == "create_calendar_event":
                return self._create_calendar_event(params)
            elif func_name == "add_task":
                return self._add_task(params)
            elif func_name == "web_search":
                return self._web_search(params)
            elif func_name == "get_system_info":
                return self._get_system_info()
            else:
                return {"success": False, "message": f"Unknown function: {func_name}", "data": None}
        except Exception as e:
            return {"success": False, "message": f"Error: {str(e)}", "data": None}
    
    # === Action Functions ===
    
    def _control_light(self, params: Dict) -> Dict:
        """Control smart lights via Kasa. Wrapper for async execution."""
        try:
            return asyncio.run(self._async_control_light(params))
        except Exception as e:
            print(f"[FunctionExecutor] Light control failed: {e}")
            return {"success": False, "message": f"Light control failed: {e}", "data": None}

    async def _async_control_light(self, params: Dict) -> Dict:
        """Async implementation of light control."""
        action = params.get("action", "toggle")
        device_name = params.get("device_name", "light")
        brightness = params.get("brightness")
        color = params.get("color")

        # --- HA priority: synchronous, returns early if HA handles the request ---
        if (self.ha_manager
                and self.ha_manager.is_connected
                and self.ha_manager.entities):

            device_name_lower = device_name.lower()
            target_ids = []
            target_names = []

            if device_name_lower in ("all", "lights", "light", "everything"):
                for eid, info in self.ha_manager.entities.items():
                    target_ids.append(eid)
                    target_names.append(info.get("attributes", {}).get("friendly_name", eid))
            else:
                for eid, info in self.ha_manager.entities.items():
                    friendly = info.get("attributes", {}).get("friendly_name", "").lower()
                    if device_name_lower in friendly or friendly in device_name_lower:
                        target_ids.append(eid)
                        target_names.append(info.get("attributes", {}).get("friendly_name", eid))

            if target_ids:
                ha_colors = {
                    "red": [255, 0, 0], "orange": [255, 165, 0], "yellow": [255, 255, 0],
                    "green": [0, 255, 0], "cyan": [0, 255, 255], "blue": [0, 0, 255],
                    "purple": [128, 0, 128], "pink": [255, 192, 203], "white": [255, 255, 255],
                    "warm white": [255, 200, 150], "warm": [255, 200, 150],
                    "cool white": [220, 220, 255], "soft white": [255, 220, 180],
                }
                results = []
                for i, eid in enumerate(target_ids):
                    name = target_names[i]
                    success = False
                    if action == "on":
                        if color:
                            rgb = ha_colors.get(color.lower())
                            success = (self.ha_manager.turn_on(eid, rgb_color=rgb)
                                       if rgb else self.ha_manager.turn_on(eid))
                        else:
                            success = self.ha_manager.turn_on(eid)
                    elif action == "off":
                        success = self.ha_manager.turn_off(eid)
                    elif action == "dim" and brightness is not None:
                        success = self.ha_manager.turn_on(eid, brightness_pct=brightness)
                    elif action == "toggle":
                        state = self.ha_manager.get_state(eid).get("state", "off")
                        success = (self.ha_manager.turn_off(eid)
                                   if state == "on" else self.ha_manager.turn_on(eid))
                    if success:
                        results.append(f"{action} {name}")

                if results:
                    return {
                        "success": True,
                        "message": ", ".join(results),
                        "data": {"device": device_name, "action": action, "targets": target_names}
                    }
            # No HA match — fall through to Kasa

        # --- existing Kasa logic unchanged below ---
        if not self.kasa_manager:
            return {"success": False, "message": "Kasa manager not available", "data": None}
        
        # 1. Ensure we have a cache of devices (alias mapping)
        if not self.kasa_manager.devices:
            # Discovery needed
            print("[FunctionExecutor] No cached devices, discovering...")
            await self.kasa_manager.discover_devices()
            
        devices = self.kasa_manager.devices
        if not devices:
            return {"success": False, "message": "No smart devices found", "data": None}
        
        print(f"\n[FunctionExecutor] _control_light called with: {params}")
        
        # 2. Find Targets (IPs)
        target_ips = []
        target_names = []
        device_name_lower = device_name.lower()
        
        if device_name_lower in ("all", "lights", "light", "everything"):
             for ip, info in devices.items():
                 target_ips.append(ip)
                 target_names.append(info.get("alias", ip))
        else:
            # Fuzzy match
            for ip, info in devices.items():
                alias = info.get("alias", "").lower()
                if device_name_lower in alias or alias in device_name_lower:
                    target_ips.append(ip)
                    target_names.append(info.get("alias", ip))
        
        print(f"[FunctionExecutor] Matched {len(target_ips)} devices: {target_names}")
        
        if not target_ips:
            # Try one more discovery if we didn't find anything and cache might be stale
            print("[FunctionExecutor] No matches, forcing rediscovery...")
            await self.kasa_manager.discover_devices()
            devices = self.kasa_manager.devices
            
            # Retry match
            target_ips = []
            target_names = []
            for ip, info in devices.items():
                alias = info.get("alias", "").lower()
                if device_name_lower in alias or alias in device_name_lower:
                    target_ips.append(ip)
                    target_names.append(info.get("alias", ip))
            
            if not target_ips:
                return {"success": False, "message": f"Device '{device_name}' not found", "data": None}

        # 3. Execute Actions
        results = []
        
        for i, ip in enumerate(target_ips):
            alias = target_names[i]
            success = False
            action_desc = ""
            
            # Handle color parameter
            if action == "on" and color:
                colors = {
                    "red": (0, 100, 100), "orange": (30, 100, 100), "yellow": (60, 100, 100),
                    "green": (120, 100, 100), "cyan": (180, 100, 100), "blue": (240, 100, 100),
                    "purple": (270, 100, 100), "pink": (300, 100, 100), "white": (0, 0, 100),
                    "warm": (30, 80, 100), "warm white": (30, 80, 100), "cool white": (0, 0, 100),
                    "soft white": (30, 60, 100), "daylight": (0, 0, 100),
                    "candle light": (30, 100, 50), "amber": (30, 100, 100), "magenta": (300, 100, 100),
                }
                target_hsv = colors.get(color.lower())
                if target_hsv:
                    h, s, v = target_hsv
                    # PASS ONLY IP - Do not pass 'dev'
                    success = await self.kasa_manager.set_hsv(ip, h, s, v)
                    if success:
                        await self.kasa_manager.turn_on(ip)
                    action_desc = f"Set color to {color} for"
                else:
                    success = False
                    action_desc = f"Unknown color '{color}' for"
                    
            elif action == "on":
                success = await self.kasa_manager.turn_on(ip)
                action_desc = "Turned on"
                
            elif action == "off":
                success = await self.kasa_manager.turn_off(ip)
                action_desc = "Turned off"
                
            elif action == "dim" and brightness is not None:
                success = await self.kasa_manager.set_brightness(ip, brightness)
                action_desc = f"Set brightness to {brightness}% for"
                
            elif action == "toggle":
                # We need to know current state. 
                # Since we can't trust cached state from closed loop, we must check.
                # Just blindly turning off or on is risky. 
                # Let's try to get state first.
                dev, _ = await self.kasa_manager._get_light_module(ip)
                if dev:
                    if dev.is_on:
                        success = await self.kasa_manager.turn_off(ip)
                        action_desc = "Turned off"
                    else:
                        success = await self.kasa_manager.turn_on(ip)
                        action_desc = "Turned on"
                else:
                    success = False
                    action_desc = "Failed to toggle"
            else:
                action_desc = f"Unknown action {action} for"
            
            if success:
                results.append(f"{action_desc} {alias}")

        if not results:
            return {"success": False, "message": "Failed to control any devices", "data": None}
        
        return {
            "success": True, 
            "message": ", ".join(results), 
            "data": {"device": device_name, "action": action, "targets": target_names}
        }

    
    def _set_timer(self, params: Dict) -> Dict:
        """Set a countdown timer."""
        duration_str = params.get("duration", "")
        label = params.get("label", "Timer")
        
        # Parse duration string
        seconds = self._parse_duration(duration_str)
        if seconds <= 0:
            return {"success": False, "message": f"Invalid duration: {duration_str}", "data": None}
        
        timer = ActiveTimer(
            label=label,
            duration_seconds=seconds,
            start_time=time.time()
        )
        
        with self._timer_lock:
            self.active_timers[label] = timer
        
        return {
            "success": True,
            "message": f"Timer '{label}' set for {duration_str}",
            "data": {"label": label, "duration": duration_str, "seconds": seconds}
        }
    
    def _parse_duration(self, duration_str: str) -> int:
        """Parse duration string like '10 minutes' or '1 hour 30 minutes' to seconds."""
        duration_str = duration_str.lower().strip()
        total_seconds = 0
        
        import re
        # Match patterns like "10 minutes", "1 hour", "30 seconds"
        patterns = [
            (r'(\d+)\s*h(?:our)?s?', 3600),
            (r'(\d+)\s*m(?:in(?:ute)?s?)?', 60),
            (r'(\d+)\s*s(?:ec(?:ond)?s?)?', 1),
        ]
        
        for pattern, multiplier in patterns:
            match = re.search(pattern, duration_str)
            if match:
                total_seconds += int(match.group(1)) * multiplier
        
        # If no pattern matched, try to extract just a number (assume minutes)
        if total_seconds == 0:
            nums = re.findall(r'\d+', duration_str)
            if nums:
                total_seconds = int(nums[0]) * 60  # Default to minutes
        
        return total_seconds
    
    def _set_alarm(self, params: Dict) -> Dict:
        """Set an alarm via TaskManager."""
        time_str = params.get("time", "")
        label = params.get("label", "Alarm")
        
        if not self.task_manager:
            return {"success": False, "message": "Task manager not available", "data": None}
        
        # Normalize time format
        normalized_time = self._normalize_time(time_str)
        
        alarm_id = self.task_manager.add_alarm(normalized_time, label)
        
        if alarm_id:
            return {
                "success": True,
                "message": f"Alarm set for {normalized_time}" + (f" ({label})" if label != "Alarm" else ""),
                "data": {"id": alarm_id, "time": normalized_time, "label": label}
            }
        return {"success": False, "message": "Failed to set alarm", "data": None}
    
    def _normalize_time(self, time_str: str) -> str:
        """Normalize time string to HH:MM format."""
        time_str = time_str.lower().strip()
        
        import re
        # Match patterns like "7am", "7:30am", "14:30"
        match = re.match(r'(\d{1,2}):?(\d{2})?\s*(am|pm)?', time_str)
        if match:
            hour = int(match.group(1))
            minute = int(match.group(2)) if match.group(2) else 0
            period = match.group(3)
            
            if period == 'pm' and hour < 12:
                hour += 12
            elif period == 'am' and hour == 12:
                hour = 0
            
            return f"{hour:02d}:{minute:02d}"
        
        return time_str
    
    def _create_calendar_event(self, params: Dict) -> Dict:
        """Create a calendar event."""
        title = params.get("title", "Event")
        date = params.get("date", "today")
        time_str = params.get("time", "09:00")
        duration = params.get("duration", 60)  # Default 1 hour
        
        if not self.calendar_manager:
            return {"success": False, "message": "Calendar manager not available", "data": None}
        
        # Parse date
        event_date = self._parse_date(date)
        
        # Parse time
        normalized_time = self._normalize_time(time_str) if time_str else "09:00"
        
        # Create datetime strings
        start_dt = f"{event_date} {normalized_time}:00"
        
        # Calculate end time
        try:
            start = datetime.strptime(start_dt, "%Y-%m-%d %H:%M:%S")
            end = start + timedelta(minutes=duration if isinstance(duration, int) else 60)
            end_dt = end.strftime("%Y-%m-%d %H:%M:%S")
        except:
            end_dt = start_dt
        
        event = self.calendar_manager.add_event(title, start_dt, end_dt)
        
        if event:
            return {
                "success": True,
                "message": f"Created event '{title}' on {date}" + (f" at {time_str}" if time_str else ""),
                "data": event
            }
        return {"success": False, "message": "Failed to create event", "data": None}
    
    def _parse_date(self, date_str: str) -> str:
        """Parse date string to YYYY-MM-DD format."""
        date_str = date_str.lower().strip()
        
        # Try to parse as explicit date first
        try:
            val = datetime.strptime(date_str, "%Y-%m-%d")
            return val.strftime("%Y-%m-%d")
        except ValueError:
            pass
            
        today = datetime.now()
        
        if date_str in ("today", ""):
            return today.strftime("%Y-%m-%d")
        elif date_str == "tomorrow":
            return (today + timedelta(days=1)).strftime("%Y-%m-%d")
        
        # Day names
        days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        for i, day in enumerate(days):
            if day in date_str:
                current_day = today.weekday()
                days_ahead = i - current_day
                if days_ahead <= 0:
                    days_ahead += 7
                if "next" in date_str:
                    days_ahead += 7
                target = today + timedelta(days=days_ahead)
                return target.strftime("%Y-%m-%d")
        
        return today.strftime("%Y-%m-%d")
    
    def _add_task(self, params: Dict) -> Dict:
        """Add a task to the to-do list."""
        text = params.get("text", "")
        
        if not text:
            return {"success": False, "message": "No task text provided", "data": None}
        
        if not self.task_manager:
            return {"success": False, "message": "Task manager not available", "data": None}
        
        task = self.task_manager.add_task(text)
        
        if task:
            return {
                "success": True,
                "message": f"Added task: {text}",
                "data": task
            }
        return {"success": False, "message": "Failed to add task", "data": None}
    
    def _web_search(self, params: Dict) -> Dict:
        """Perform a web search."""
        query = params.get("query", "")
        
        if not query:
            return {"success": False, "message": "No search query provided", "data": None}
        
        try:
            from duckduckgo_search import DDGS
            
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=5))
            
            if results:
                # Format results for display
                formatted = []
                for r in results[:3]:
                    formatted.append({
                        "title": r.get("title", ""),
                        "body": r.get("body", "")[:200],
                        "url": r.get("href", "")
                    })
                
                return {
                    "success": True,
                    "message": f"Found {len(results)} results for '{query}'",
                    "data": {"query": query, "results": formatted}
                }
            
            return {"success": True, "message": f"No results found for '{query}'", "data": None}
            
        except Exception as e:
            return {"success": False, "message": f"Search failed: {e}", "data": None}
    
    # === System Info ===
    
    def _get_system_info(self) -> Dict:
        """Aggregate all system information."""
        info = {
            "current_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "timers": [],
            "alarms": [],
            "calendar_today": [],
            "tasks": [],
            "smart_devices": [],
            "weather": None,
            "news": []
        }
        
        # Active timers
        with self._timer_lock:
            for label, timer in list(self.active_timers.items()):
                if timer.is_expired:
                    del self.active_timers[label]
                else:
                    info["timers"].append({
                        "label": timer.label,
                        "remaining": timer.format_remaining()
                    })
        
        # Alarms
        if self.task_manager:
            try:
                alarms = self.task_manager.get_alarms()
                info["alarms"] = [{"time": a["time"], "label": a["label"]} for a in alarms]
            except:
                pass
        
        # Calendar events today
        if self.calendar_manager:
            try:
                today = datetime.now().strftime("%Y-%m-%d")
                events = self.calendar_manager.get_events(today)
                info["calendar_today"] = [{"title": e["title"], "time": e["start_time"]} for e in events]
            except:
                pass
        
        # Tasks
        if self.task_manager:
            try:
                tasks = self.task_manager.get_tasks()
                info["tasks"] = [{"text": t["text"], "completed": t["completed"]} for t in tasks]
            except:
                pass
        
        # Smart devices
        if self.kasa_manager and self.kasa_manager.devices:
            for ip, device in self.kasa_manager.devices.items():
                info["smart_devices"].append({
                    "name": device.get("alias", "Unknown"),
                    "is_on": device.get("is_on", False),
                    "type": device.get("type", "Unknown")
                })
        
        # Weather
        if self.weather_manager:
            try:
                weather = self.weather_manager.get_weather()
                if weather and "current" in weather:
                    current = weather["current"]
                    info["weather"] = {
                        "temp": current.get("temp"),
                        "condition": current.get("condition"),
                        "high": weather.get("daily", {}).get("high"),
                        "low": weather.get("daily", {}).get("low")
                    }
            except:
                pass
        
        # News
        if self.news_manager:
            try:
                # Get recent news (cached or fresh)
                news_items = self.news_manager.get_briefing(use_ai=False)
                # Limit to top 5 for system info
                info["news"] = [
                    {
                        "title": item.get("title", ""),
                        "category": item.get("category", "News"),
                        "url": item.get("url", "")
                    }
                    for item in news_items[:5]
                ]
            except Exception as e:
                print(f"[FunctionExecutor] News fetch error: {e}")
                pass
        
        return {
            "success": True,
            "message": "System info retrieved",
            "data": info
        }


# Global instance
executor = FunctionExecutor()
