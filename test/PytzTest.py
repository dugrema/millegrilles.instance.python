from datetime import datetime, timezone
import pytz

tz_info = pytz.timezone('America/Toronto')

now = datetime.now()
local_timezone = datetime.now(timezone.utc).astimezone().tzinfo
print("Now : %s (%s)" % (now, local_timezone))
print(f"Now formatted: {now.strftime("%a, %d %b %Y %H:%M:%S")} {local_timezone}")

offset = tz_info.utcoffset(now)
print('Offset %s, seconds %s' % (offset, int(offset.total_seconds())))

dst = tz_info.dst(now)
print("DST : %s" % dst)

print("TZ info : %s, Zone : %s" % (tz_info, tz_info.zone))

date_tz = datetime.now(tz=tz_info)
print("Date iso : %s" % date_tz.isoformat())

mtl_tz = pytz.timezone('America/Montreal')
date_tz = datetime.now(tz=mtl_tz)
print(f"Montreal TZ: {mtl_tz}, general TZ for montreal: ")
print(f"Now formatted: {date_tz.strftime("%a, %d %b %Y %H:%M:%S %Z")}")

class Tools:

    def __init__(self):
        pass

    def get_epoch_time(self) -> int:
        """
        The current time in epoch format (number of seconds since January 1, 1970).

        Returns:
            int: Epoch time
        """
        now = datetime.now()
        return int(now.timestamp())

    def get_current_date_and_time(self) -> str:
        """
        Get the current date and time in a more human-readable format.
        Note that the system returns UTC time.

        Returns:
            str: The current date and time.
        """
        now = datetime.now()
        current_time = now.strftime("%I:%M:%S %p")  # Using 12-hour format with AM/PM
        current_date = now.strftime(
            "%A, %B %d, %Y"
        )  # Full weekday, month name, day, and year

        return f"Current Date and Time = {current_date}, {current_time}"


if __name__ == '__main__':
    tools = Tools()
    ct = tools.get_current_date_and_time()
    print("Current time : %s" % ct)
    ep = tools.get_current_epoch_time()
    print("Epoch : %s" % ep)
    print("Local timezone: %s" % tools.get_local_timezone())


