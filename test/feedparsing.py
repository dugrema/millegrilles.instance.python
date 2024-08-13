import feedparser


class Tools:

    def __init__(self):
        self.url = 'https://weather.gc.ca/rss/city/on-52_f.xml'
        # self.url = "https://weather.gc.ca/rss/city/qc-132_e.xml"

    def get_weather_feed(self) -> str:
        """
        Gets a weather feed that includes the current conditions and a forecast for the user's current location.
        Returns:
             str: Weather information and forecast.
        """

        # Fetch current weather
        feed = feedparser.parse(self.url)

        # Retain title and summary of all ATOM entries
        content = ['%s %s' % (e.title, e.summary) for e in feed.entries]

        # Join entries and return as text
        return '\n'.join(content)


if __name__ == '__main__':
    tools = Tools()
    report = tools.get_weather_feed()
    print('Weather report\n-----\n\n%s\n-----' % report)


"""
Here is a weather report with some additional contextual information and a sample output.

<context>
User location: Ottawa, Canada
Current time: 9:00 AM EDT Tuesday 13 August 2024
</context>

<weather>
Aucune veille ou alerte en vigueur, Ottawa (Richmond - Metcalfe) Aucune veille ou alerte en vigueur.
Conditions actuelles: Généralement ensoleillé, 22,3°C <b>Enregistrées à:</b> Aéroport int. Macdonald-Cartier d'Ottawa 11h00 HAE le mardi 13 août 2024<br /> <b>Condition:</b> Généralement ensoleillé<br /> <b>Température:</b> 22,3&deg;C<br /> <b>Pression / Tendance:</b> 101,8 kPa à la hausse<br /> <b>Visibilité:</b> 24 km<br /> <b>Humidité:</b> 74 %<br /> <b>Humidex:</b> 28<br /> <b>Point de rosée:</b> 17,5&deg;C<br /> <b>Vents:</b> O 13 km/h<br /> <b>Cote air santé:</b> n/d<br />
Mardi: Ensoleillé. Maximum 27. Ensoleillé. Vents du nord-ouest de 20 km/h avec rafales à 40. Maximum 27. Humidex 32. Indice UV de 7 ou élevé. Prévisions émises 11h00 HAE le mardi 13 août 2024
Ce soir et cette nuit: Quelques nuages. Minimum 14. Quelques nuages. Minimum 14. Prévisions émises 11h00 HAE le mardi 13 août 2024
Mercredi: Possibilité d'averses. Maximum 29. PdP 30% Ensoleillé le matin et tôt en après-midi. Devenant alternance de soleil et de nuages avec 30 pour cent de probabilité d'averses tard en après-midi. Risque d'un orage tard en après-midi. Maximum 29. Humidex 35. Indice UV de 7 ou élevé. Prévisions émises 11h00 HAE le mardi 13 août 2024
Mercredi soir et nuit: Dégagé. Minimum 14. Dégagé. Minimum 14. Prévisions émises 11h00 HAE le mardi 13 août 2024
Jeudi: Ensoleillé. Maximum 29. Ensoleillé. Maximum 29. Prévisions émises 11h00 HAE le mardi 13 août 2024
Jeudi soir et nuit: Passages nuageux. Minimum 15. Passages nuageux. Minimum 15. Prévisions émises 11h00 HAE le mardi 13 août 2024
Vendredi: Alternance de soleil et de nuages. Maximum 28. Ennuagement. Maximum 28. Prévisions émises 11h00 HAE le mardi 13 août 2024
Vendredi soir et nuit: Possibilité d'averses. Minimum 18. PdP 30% Nuageux avec 30 pour cent de probabilité d'averses. Minimum 18. Prévisions émises 11h00 HAE le mardi 13 août 2024
Samedi: Averses. Maximum 23. Averses. Maximum 23. Prévisions émises 11h00 HAE le mardi 13 août 2024
Samedi soir et nuit: Possibilité d'averses. Minimum 18. PdP 60% Nuageux avec 60 pour cent de probabilité d'averses. Minimum 18. Prévisions émises 11h00 HAE le mardi 13 août 2024
Dimanche: Averses. Maximum 24. Averses. Maximum 24. Prévisions émises 11h00 HAE le mardi 13 août 2024
Dimanche soir et nuit: Averses. Minimum 17. Averses. Minimum 17. Prévisions émises 11h00 HAE le mardi 13 août 2024
Lundi: Averses. Maximum 23. Averses. Maximum 23. Prévisions émises 11h00 HAE le mardi 13 août 2024
</weather>

<sample>
{
    "updated": "Tuesday 13 August 2024 09:00 AM EDT",
    "current": {
        "temperature": 19,
        "humidity": 74,
        "summary": "sunny"
    },
    "warnings": null,
    "forecast": [
        {
            "date": "Tuesday",
            "day": {
                "summary": "Sunny",
                "temperature": 26,
                "pop": null
            },
            "night": {
                "summary": "Clear",
                "temperature": 13,
                "pop": null
            }
        },
        {
            "date": "Wednesday",
            "day": {
                "summary": "Chance of showers",
                "temperature": 27,
                "pop": 60
            },
            "night": {
                "summary": "Cloudy periods",
                "temperature": 17,
                "pop": 10
            }
        },
        {
            "date": "Thursday",
            "day": {
                "summary": "Sunny",
                "temperature": 28,
                "pop": null
            },
            "night": {
                "summary": "Clear",
                "temperature": 16,
                "pop": null
            }
        }
    ]
}
</sample>

<instructions>
The output must be in JSON only. Do not produce any explanations or suggestions, only a JSON output.
From the weather forecast, extract:
1. The output cannot be a simulation or an example.
2. Include an "updated" element with the weather report date and time that can be found next to the "Observed at" portion of the weather report.
3. If warnings are present, put them in a "warnings" JSON element as a string value or null if no warnings have been issued. 
4. Create a "current" element as JSON object with elements "temperature" and "humidity", and if present in the weather forecast also a "summary" for the current weather (sunny, raining, snowing, etc.).
5. Produce a 3 day forecast starting with the current day, output in a "forecast" array of objects including the "date", summary weather for the "day" and the "night" as objects that include the probability of precipitations "pop", the high and the low "temperature".
6. Produce an output in JSON format only. The key names must all be in English as in the sample.
7. Use the French descriptions provided in the weather report. Use French for the "warnings", "summary" and "date" string values. 
</instructions>

"""
