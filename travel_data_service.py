import xmlrpc.client
import requests
import time
from threading import Thread

PORT = 5003
POLL_INTERVAL = 60
CHAT_RPC = "http://localhost:5001/"

locations = {
    "helsinki":   (60.17, 24.94),
    "vilnius":    (54.69, 25.28),
    "bratislava": (48.15, 17.11),
    "kyiv":       (50.45, 30.52),
}

#Fetches current weather for a city using Open-Meteo API
def weather(city):
    coords = locations.get(city)
    if coords is None:
        return None
    lat, lon = coords
    loc_url = "https://api.open-meteo.com/v1/forecast?latitude=" + str(lat) + "&longitude=" + str(lon) + "&current=temperature_2m,windspeed_10m"
    try:
        answer = requests.get(loc_url, timeout=5)
        answer.raise_for_status()
        current = answer.json()["current"]
        temp = current["temperature_2m"]
        wind = current["windspeed_10m"]
        return "Weather in " + city.title() + ": " + str(temp) + "C, wind " + str(wind) + " km/h"
    except Exception as e:
        print("Weather fetch failed for " + city + ": " + str(e))
        return None

#Runs in background, asks chat server which channels are active and pushes weather into them
def gettingweather():
    server = xmlrpc.client.ServerProxy(CHAT_RPC, allow_none=True)
    print("travel_data_service started")
    while True:
        try:
            current_channels = server.list_channels()
            for city in current_channels:
                msg = weather(city)
                if msg:
                    server.push_to_channel(city, msg)
                    print("Pushed to #" + city + ": " + msg)
        except Exception as e:
            print("RPC failed: " + str(e))
        time.sleep(POLL_INTERVAL)

def main():
    weather_info = Thread(target=gettingweather)
    weather_info.daemon = True
    weather_info.start()
    weather_info.join()

main()