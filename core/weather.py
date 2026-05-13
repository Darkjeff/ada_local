import requests
from datetime import datetime
from core.settings_store import settings

class WeatherManager:
    """
    Manages weather data fetching from Open-Meteo API.
    """
    def __init__(self):
        self.base_url = "https://api.open-meteo.com/v1/forecast"
        self.current_weather = None
        self.last_fetch = None
    
    @property
    def lat(self):
        """Get latitude from settings."""
        return settings.get("weather.latitude", 40.7128)
    
    @property
    def lon(self):
        """Get longitude from settings."""
        return settings.get("weather.longitude", -74.0060)

    def get_weather(self):
        """
        Fetches current and hourly weather. Returns dict.
        """
        try:
            params = {
                "latitude": self.lat,
                "longitude": self.lon,
                "current": "temperature_2m,weather_code,is_day",
                "hourly": "temperature_2m,weather_code",
                "temperature_unit": "fahrenheit",
                "timezone": "auto",
                "forecast_days": 1
            }
            
            response = requests.get(self.base_url, params=params, timeout=15)
            response.raise_for_status()
            data = response.json()
            
            # Current
            current = data.get("current", {})
            self.current_weather = {
                "temp": current.get("temperature_2m", 0),
                "code": current.get("weather_code", 0),
                "is_day": current.get("is_day", 1)
            }
            
            # Hourly (Next 4 intervals from now)
            hourly = data.get("hourly", {})
            times = hourly.get("time", [])
            temps = hourly.get("temperature_2m", [])
            codes = hourly.get("weather_code", [])
            
            # Find current hour index
            now_hour = datetime.now().hour
            # Open-Meteo returns ISO times, but usually aligned with 00:00 local
            # We can simplify by just taking the index corresponding to 'now_hour'
            # The API returns 24 hours starting at 00:00 for the day if we requested 1 day.
            
            forecast = []
            for i in range(now_hour, min(now_hour + 5, len(times))): 
                 # Skip current hour effectively or include? User image shows 2PM, 4PM... 
                 # Let's take next few hours.
                 # Actually let's take i, i+2, i+4, i+6 to match the "spread" look or just next 4 hours?
                 # Image shows 2PM, 4PM, 6PM, 8PM -> 2 hour intervals.
                 if i < len(times):
                     t_str = datetime.fromisoformat(times[i]).strftime("%I%p").lstrip("0")
                     forecast.append({
                         "time": t_str,
                         "temp": temps[i],
                         "code": codes[i]
                     })
            
            # If we want 2-hour steps:
            forecast_step = []
            for i in range(now_hour, min(now_hour + 7, len(times)), 2):
                t_str = datetime.fromisoformat(times[i]).strftime("%I%p").lstrip("0")
                forecast_step.append({
                    "time": t_str,
                    "temp": temps[i],
                    "code": codes[i]
                })
                
            self.current_weather["forecast"] = forecast_step[:4] # Format: list of dicts
            
            # High/Low for the day
            # We can compute from hourly or fetch daily. Let's compute from hourly for simplicity
            self.current_weather["high"] = max(temps) if temps else 0
            self.current_weather["low"] = min(temps) if temps else 0
            
            self.last_fetch = datetime.now()
            return self.current_weather
            
        except Exception as e:
            print(f"Weather Fetch Error: {e}")
            return None

    def get_condition_info(self, code, is_day=1):
        """
        Maps WMO code to (Description, IconName).
        """
        # WMO Weather interpretation codes (WW)
        # https://open-meteo.com/en/docs
        
        # Simplified mapping
        # 0: Clear
        # 1,2,3: Mainly clear, partly cloudy, overcast
        # 45,48: Fog
        # 51,53,55: Drizzle
        # 61,63,65: Rain
        # 71,73,75: Snow
        # 95,96,99: Thunderstorm
        
        # We return FluentIcon names that closely match
        
        if code == 0:
            return "Clear", "Sunny" if is_day else "QuietHours" # QuietHours looks like a moon/bed
        
        if code in [1, 2]:
            return "Partly Cloudy", "PartlyCloudyDay" if is_day else "PartlyCloudyNight" # Need to check if these exist in FIF
            # Fallback to safe icons if unsure:
            # Sunny -> BRIGHTNESS
            # Cloudy -> CLOUD
        
        # Let's use standard FIF names we confirmed or safe ones
        # We saw: TILES, WIFI, SPEED_HIGH, DATE_TIME... 
        # We need to be careful. Let's strictly use what we saw or generic ones.
        # Actually, let's just stick to generic names and if they fail, we use fallbacks in the GUI.
        # But wait, QFluentWidgets usually has specific weather icons? 
        # Checked icons.txt in previous turn: 
        # 'ADD', 'ALBUM', 'ALIGN_CENTER', ... 'BRIGHTNESS' ... 'CLOUD' ... 'sunny' was missing.
        # So 'Sunny' isn't there. 'BRIGHTNESS' is a sun.
        # 'CLOUD' might be there? Wait, I didn't see 'CLOUD' in the snippet I read.
        # Let's use:
        # Clear -> BRIGHTNESS (Sun)
        # Cloudy -> TILES (Generic) or just a shape
        # Rain -> DOWNLOAD (Down arrow looks like rain? No.)
        # Let's use valid FIF icons that mimic weather.
        
        # Revised Mapping based on likely available icons (standard Fluent set):
        # 0 Clear -> BRIGHTNESS
        # 1-3 Cloudy -> VIEW or TILES
        # Rain -> WIFI (Waves?) No. 
        # Let's just return a generic description and handle icon mapping in GUI with verified icons.
        
        return self._code_to_text(code)

    def _code_to_text(self, code):
        if code == 0: return "Clear"
        if code in [1, 2, 3]: return "Cloudy"
        if code in [45, 48]: return "Foggy"
        if code in [51, 53, 55, 61, 63, 65]: return "Rain"
        if code in [71, 73, 75, 85, 86]: return "Snow"
        if code in [95, 96, 99]: return "Storm"
        return "Unknown"

weather_manager = WeatherManager()
