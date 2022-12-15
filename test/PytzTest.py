import datetime
import pytz

tz_info = pytz.timezone('ZZAmerica/Toronto')

now = datetime.datetime.utcnow()
print("Now : %s" % now)

offset = tz_info.utcoffset(now)
print('Offset %s, seconds %s' % (offset, int(offset.total_seconds())))

dst = tz_info.dst(now)
print("DST : %s" % dst)

print("TZ info : %s, Zone : %s" % (tz_info, tz_info.zone))
