"""Time helpers. All times are epoch milliseconds; the local time zone is Korea (UTC+9, no daylight saving),
the same as the browser simulator run with TZ=Asia/Seoul."""
import datetime as _dt
import math

OFFSET_MS = 9 * 3600000
DAY_MS = 86400000
MIN_MS = 60000
_EPOCH_ORD = _dt.date(1970, 1, 1).toordinal()


def js_round(x):
    """JavaScript Math.round: halves go up (2.5 -> 3, -2.5 -> -2)."""
    return math.floor(x + 0.5)


def i32(x):
    x &= 0xFFFFFFFF
    return x - 0x100000000 if x >= 0x80000000 else x


def u32(x):
    return x & 0xFFFFFFFF


_fields_cache = {}


def day_index(ms):
    """local calendar day as days since 1970-01-01 (JavaScript: Date.UTC(local y, m, d) / 86400000)"""
    return (ms + OFFSET_MS) // DAY_MS


def ymd(day):
    """(year, month 0-11, date 1-31, weekday 0=Sunday) of a local day index"""
    r = _fields_cache.get(day)
    if r is None:
        d = _dt.date.fromordinal(_EPOCH_ORD + day)
        r = (d.year, d.month - 1, d.day, (day + 4) % 7)
        if len(_fields_cache) > 50000:
            _fields_cache.clear()
        _fields_cache[day] = r
    return r


def fields(ms):
    """local (year, month 0-11, date, hours, minutes, seconds, weekday 0=Sunday)"""
    loc = ms + OFFSET_MS
    day, rem = divmod(loc, DAY_MS)
    y, m, d, wd = ymd(day)
    rem = int(rem)
    return y, m, d, rem // 3600000, (rem // 60000) % 60, (rem // 1000) % 60, wd


def hours(ms):
    """local hours + minutes / 60 (seconds ignored, as in the simulator)"""
    rem = int((ms + OFFSET_MS) % DAY_MS)
    return rem // 3600000 + ((rem // 60000) % 60) / 60


def local_ms(y, m0, d=1, h=0, mi=0, s=0):
    """JavaScript new Date(y, m0, d, h, mi, s) in local time; months and days may overflow like in JavaScript"""
    y += m0 // 12
    m0 %= 12
    base = _dt.date(y, m0 + 1, 1).toordinal() - _EPOCH_ORD + (d - 1)
    return base * DAY_MS + h * 3600000 + mi * 60000 + s * 1000 - OFFSET_MS


def utc_day_fields(day):
    """(year, month 0-11, date) of a UTC day index (JavaScript new Date(d * 86400000).getUTC...)"""
    y, m, d, _ = ymd(day)
    return y, m, d


def month_days(y, m0):
    return (_dt.date(y + (m0 + 1) // 12, (m0 + 1) % 12 + 1, 1) - _dt.date(y, m0 + 1, 1)).days


def start_of_day(ms):
    return day_index(ms) * DAY_MS - OFFSET_MS


def iso_local(ms):
    y, m, d, hh, mi, ss, _ = fields(ms)
    return f"{y:04d}-{m + 1:02d}-{d:02d}T{hh:02d}:{mi:02d}:{ss:02d}+09:00"


def parse_iso(s):
    """ms of an iso_local string"""
    y, mo, d = int(s[0:4]), int(s[5:7]), int(s[8:10])
    hh, mi, ss = int(s[11:13]), int(s[14:16]), int(s[17:19])
    return local_ms(y, mo - 1, d, hh, mi, ss)
