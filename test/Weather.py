import requests
from datetime import datetime


class Tools:
    """
    Weather tools. Provides current weather and forecast.
    """

    def __init__(self):
        self.url = "https://weather.gc.ca/rss/city/qc-132_e.xml"

    def get_weather_feed(self) -> str:
        """
        Returns the current weather and a 7 day forecast from weather.gc.ca.
        Returns:
            str: RSS formatted weather and forecast
        """

        response = requests.get(self.url)
        if response.status_code != 200:
            raise Exception(
                "There was an error accessing the weather, HTTP status code %s"
                % response.status_code
            )

        result = response.text

        return result


if __name__ == '__main__':
    tools = Tools()
    print(tools.get_weather_feed())


"""
Queries:

<instructions>
You have access to an API that provides a RSS weather feed with the current date, the current weather and a multi-day forecast for the user's location. Your role is to call this weather feed API and provide short answers to user requests.
The RSS feed has <entry/> tags as its main feature. The first <entry/> contains the weather alerts if any. The second <entry/> is the current conditions. The remaining <entry/> tags are the forecast starting with the forecast for the current period. 
Follow these instructions carefully when answering:
1. Do not respond with a simulation. You must call the provided python API and get the real current information.
2. Do not output the API response, only provide a summary that answers the query from the user.
3. When the user requests weather information other than current conditions, ensure that you get the current date from the first <updated/> tag to determine the approximate current time and date. You must use that date when determining what tomorrow is, or what the next 2-3 days are because the forecast is for 7 days starting with the current day.
4. Provide a short answer to the user query.
5. Only if there is an active weather alert in the API feed response, summarize the alert at the top of your response and use a bold font. If there is no active alert, do not mention alerts.
</instructions>

<query>What are the current conditions and what is the forecast for the next 3 days?</query>

-----

<instructions>
You currently have access to a weather API tool called weather_forecast with a get_weather_feed function that provides a RSS weather feed for the user's location. Your role is to call this get_weather_feed and provide short answers to user requests.
Do not simulate the weather information, you must call the get_weather_feed to get the current weather information. Once you have received the get_weather_feed response, follow these instructions:
1. Do not output the get_weather_feed response, only provide a summary that answers the query from the user.
2. When the user requests weather information other than current conditions, ensure that you get the current date from the first <updated/> tag to determine the approximate current time and date. You must use that date when determining what tomorrow is, or what the next 2-3 days are because the forecast is for 7 days starting with the current day.
3. Provide a short answer to the user query.
4. Only if there is an active weather alert in the get_weather_feed feed response, summarize the alert at the top of your response and use a bold font. If there is no active alert, do not mention alerts.
</instructions>

<query>What are the current conditions and what is the forecast for the next 3 days?</query>

"""
