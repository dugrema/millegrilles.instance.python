import datetime
import pytz

tz_info = pytz.timezone('America/Toronto')

now = datetime.datetime.utcnow()
print("Now : %s" % now)

offset = tz_info.utcoffset(now)
print('Offset %s, seconds %s' % (offset, int(offset.total_seconds())))

dst = tz_info.dst(now)
print("DST : %s" % dst)

print("TZ info : %s, Zone : %s" % (tz_info, tz_info.zone))

date_tz = datetime.datetime.now(tz=tz_info)
print("Date iso : %s" % date_tz.isoformat())

