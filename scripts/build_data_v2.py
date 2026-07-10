#!/usr/bin/env python3
"""
Rebuild data_v2.json for the Hub Visit Dashboard from a fresh raw export.

v2 changes (from user-reported bugs):
  - LOCATION FIX: location is now taken from `final_location` for BOTH
    walk-in-row filtering and funnel-row filtering (previously walk-in rows
    were bucketed by `walkin_location`, which is blank for ~10% of real
    walk-ins -- those rows silently fell out of every per-location bucket
    while still counting in Overall). final_location is never blank and
    agrees with walkin_location in 100% of cases where walkin_location is
    populated, so this is a strict fix, not a behavior change for the
    other 90%.
  - FULL STRUCTURE: emits the complete data model the current index.html
    actually reads -- channel_by_month, ch_to_chcat, by_week_chcat,
    by_month_chcat, by_week_ch, by_month_ch, by_week_leadtype,
    by_month_leadtype -- in addition to by_month/by_week/by_day,
    ch_by_month, agent_by_month, lead_by_month, tc_by_month. The previous
    version only emitted the subset used by the OLD (pre-filter) UI, which
    is why the Lead Type / Channel Source / Source filters had no data to
    read and silently broke.
"""
import csv
import json
import math
import sys
from datetime import datetime, timedelta

IN_CSV = sys.argv[1] if len(sys.argv) > 1 else "uploads/data-1783676618173.csv"
OUT_JSON = sys.argv[2] if len(sys.argv) > 2 else "outputs/data_v2_new.json"
TODAY = datetime(2026, 7, 10)  # today's date per env, truncated to midnight

MONTHS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
LOCS = ['Overall', 'Hyderabad', 'Damaigudda', 'Nagole Dost', 'HYD LB Nagar']
LEAD_TYPES = ['active', 'new join', 'rejoin', 'resurrection']

NULLS = {'', 'NULL', 'null', None, '-', 'NaT', 'nan'}


def raw_date(val):
    if val in NULLS:
        return None
    s = str(val).strip()
    if s in NULLS:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%m/%d/%Y %H:%M:%S", "%m/%d/%Y"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d")
    except ValueError:
        return None


def to_midnight(val):
    d = raw_date(val)
    if d is None:
        return None
    return datetime(d.year, d.month, d.day)


def to_ts(val):
    return raw_date(val)


def week_label(ts):
    return f"{ts.day} {MONTHS[ts.month-1]} {ts.year}"


def month_label(ts):
    return f"{MONTHS[ts.month-1]} {ts.year}"


def day_label(ts):
    return f"{ts.year:04d}-{ts.month:02d}-{ts.day:02d}"


def month_start(label):
    mon, year = label.split(' ')
    return datetime(int(year), MONTHS.index(mon) + 1, 1)


def month_end(label):
    mon, year = label.split(' ')
    m = MONTHS.index(mon) + 1
    y = int(year)
    if m == 12:
        return datetime(y + 1, 1, 1)
    return datetime(y, m + 1, 1)


def pct(n, d):
    if d <= 0:
        return 0
    x = n / d * 1000
    return math.floor(x + 0.5) / 10


def get(row, key):
    v = row.get(key)
    if v in NULLS:
        return None
    v = str(v).strip()
    return v if v not in NULLS else None


def num(row, key):
    v = get(row, key)
    if v is None:
        return 0
    try:
        return float(v)
    except ValueError:
        return 0


# ── Load CSV ──────────────────────────────────────────────────────────────
with open(IN_CSV, newline='', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    raw_rows = list(reader)

rows = []        # new-join rows (walkin + alloc/funnel), fRows pool
all_rows = []     # all-category walkin rows, for lead_by_month
lt_rows = []      # all-category walkin rows w/ ww, for lead-type funnel breakdown
emp_first_walkin = {}

for r in raw_rows:
    if (get(r, 'final_city') or '') != 'Hyderabad':
        continue

    ww = to_midnight(get(r, 'walkin_week'))
    aw = to_midnight(get(r, 'allocation_week'))

    if ww is not None and ww > TODAY:
        continue

    cat = (get(r, 'category') or '').strip()
    date_ts = to_ts(get(r, 'date'))
    emp = get(r, 'employee_id') or ''

    # LOCATION FIX: final_location is authoritative and never blank for
    # in-scope rows; walkin_location agrees with it whenever populated but
    # is blank ~10% of the time on real walk-ins. Use final_location for
    # both the walk-in-row location and the funnel-row location so a
    # missing walkin_location no longer drops a real walk-in out of its hub.
    loc = get(r, 'final_location') or get(r, 'walkin_location') or ''

    if ww is not None:
        all_rows.append({'cat': cat, 'wwMon': month_label(ww)})
        if emp:
            if emp not in emp_first_walkin or ww < emp_first_walkin[emp]:
                emp_first_walkin[emp] = ww

    if ww is not None and cat in LEAD_TYPES:
        lt_rows.append({
            'emp': emp, 'cat': cat,
            'wLoc': loc, 'fLoc': loc,
            'ww': ww, 'aw': aw,
            'wwLbl': week_label(ww), 'wwMon': month_label(ww),
            'evRank': num(r, 'walkin_week_event_rank'),
            'wkRank': num(r, 'walkin_week_rank'),
            'dayLbl': day_label(date_ts) if date_ts else None,
            'etDt': to_ts(get(r, 'et_creation_date')),
            'docDt': to_ts(get(r, 'documentation_timestamp')),
            'sdDt': to_ts(get(r, 'sd_timestamp')),
            'dtDt': to_ts(get(r, 'driving_test_pass_timestamp')),
            'trnDt': to_ts(get(r, 'training_complete_timestamp')),
            'cnDt': to_ts(get(r, 'driver_contract_signed_timestamp')),
        })

    if cat != 'new join':
        continue

    rows.append({
        'emp': emp,
        'wLoc': loc, 'fLoc': loc,
        'ww': ww,
        'wwLbl': week_label(ww) if ww else None,
        'wwMon': month_label(ww) if ww else None,
        'aw': aw,
        'evRank': num(r, 'walkin_week_event_rank'),
        'wkRank': num(r, 'walkin_week_rank'),
        'dayLbl': day_label(date_ts) if (date_ts and ww) else None,
        'etDt': to_ts(get(r, 'et_creation_date')),
        'docDt': to_ts(get(r, 'documentation_timestamp')),
        'sdDt': to_ts(get(r, 'sd_timestamp')),
        'dtDt': to_ts(get(r, 'driving_test_pass_timestamp')),
        'trnDt': to_ts(get(r, 'training_complete_timestamp')),
        'cnDt': to_ts(get(r, 'driver_contract_signed_timestamp')),
        'chCat': get(r, 'channel_category') or '',
        'ch': get(r, 'channel') or '',
        'agent': get(r, 'agent_username') or '',
        'tc': get(r, 'telecaller_id_before_walkin'),
        'walkinTs': to_ts(get(r, 'walkin_timestamp')),
    })

print(f"rows (new join, fRows pool): {len(rows)}", file=sys.stderr)
print(f"all_rows (any category, walkin only): {len(all_rows)}", file=sys.stderr)
print(f"lt_rows (lead-type walkin rows): {len(lt_rows)}", file=sys.stderr)

# ── periods ──────────────────────────────────────────────────────────────
weeks_map, months_map, days_map = {}, {}, {}
for r in rows:
    if r['ww'] is None:
        continue
    weeks_map[r['wwLbl']] = r['ww']
    months_map[r['wwMon']] = 1
    if r['dayLbl']:
        days_map[r['dayLbl']] = 1

weeks = sorted(weeks_map.keys(), key=lambda k: weeks_map[k])
months = sorted(months_map.keys(), key=lambda k: month_start(k))
days = sorted(days_map.keys())


# ── metric engine ────────────────────────────────────────────────────────
def compute_metrics(w_rows, f_rows, p_start, p_end):
    tw = len(w_rows)
    tu_set = {r['emp'] for r in w_rows}

    fresh_set, spill_set = set(), set()
    for emp in tu_set:
        if not emp:
            continue
        first_wk = emp_first_walkin.get(emp)
        if first_wk is None or first_wk >= p_start:
            fresh_set.add(emp)
        else:
            spill_set.add(emp)

    tu, fresh, spill = len(tu_set), len(fresh_set), len(spill_set)

    def c_ts(field):
        s = set()
        for r in f_rows:
            t = r[field]
            if t is not None and p_start <= t < p_end:
                s.add(r['emp'])
        return len(s)

    ob, doc, dtest = c_ts('etDt'), c_ts('docDt'), c_ts('dtDt')
    sd, train, contr = c_ts('sdDt'), c_ts('trnDt'), c_ts('cnDt')

    alloc_set = set()
    for r in f_rows:
        if r['aw'] is not None and p_start <= r['aw'] < p_end:
            alloc_set.add(r['emp'])
    alloc = len(alloc_set)

    na_set = set()
    for r in w_rows:
        if r['evRank'] == 1:
            in_p = r['aw'] is not None and p_start <= r['aw'] < p_end
            if not in_p:
                na_set.add(r['emp'])
    not_alloc = len(na_set)

    drop = drop2 = 0
    if not_alloc > 0:
        has_ob = set()
        for r in f_rows:
            if r['emp'] in na_set and r['etDt'] is not None:
                has_ob.add(r['emp'])
        drop2 = len(has_ob)
        drop = not_alloc - drop2

    return {
        'tw': tw, 'tu': tu,
        'fresh': fresh, 'fresh_pct': pct(fresh, tu),
        'spill': spill, 'spill_pct': pct(spill, tu),
        'ob': ob, 'ob_pct': pct(ob, tu),
        'doc': doc, 'doc_pct': pct(doc, tu),
        'dtest': dtest, 'dtest_pct': pct(dtest, tu),
        'sd': sd, 'sd_pct': pct(sd, tu),
        'train': train, 'train_pct': pct(train, tu),
        'contr': contr, 'contr_pct': pct(contr, tu),
        'alloc': alloc, 'alloc_pct': pct(alloc, tu),
        'not_alloc': not_alloc,
        'drop': drop, 'drop_pct': pct(drop, tw),
        'drop2': drop2, 'drop2_pct': pct(drop2, tw),
    }


def w_for_loc(w_rows, loc):
    if loc == 'Overall':
        return w_rows
    return [r for r in w_rows if r['wLoc'] == loc]


def f_for_loc(loc):
    if loc == 'Overall':
        return rows
    return [r for r in rows if r['fLoc'] == loc]


# ── by_week / by_month / by_day ─────────────────────────────────────────
by_week = {}
for lbl in weeks:
    s = weeks_map[lbl]
    e = s + timedelta(days=7)
    w = [r for r in rows if r['ww'] == s]
    by_week[lbl] = {loc: compute_metrics(w_for_loc(w, loc), f_for_loc(loc), s, e) for loc in LOCS}

by_month = {}
for lbl in months:
    s, e = month_start(lbl), month_end(lbl)
    w = [r for r in rows if r['wwMon'] == lbl]
    by_month[lbl] = {loc: compute_metrics(w_for_loc(w, loc), f_for_loc(loc), s, e) for loc in LOCS}

by_day = {}
for d_str in days:
    y, m, dd = (int(x) for x in d_str.split('-'))
    s = datetime(y, m, dd)
    e = s + timedelta(days=1)
    w = [r for r in rows if r['dayLbl'] == d_str]
    by_day[d_str] = {loc: compute_metrics(w_for_loc(w, loc), f_for_loc(loc), s, e) for loc in LOCS}

# ── first-entry source attribution ──────────────────────────────────────
emp_week_first_src = {}
wk_sorted = sorted(
    [r for r in rows if r['ww'] is not None],
    key=lambda r: (r['evRank'], r['walkinTs'] if r['walkinTs'] is not None else datetime.max)
)
for r in wk_sorted:
    if not r['emp'] or not r['wwLbl']:
        continue
    key = r['emp'] + '|' + r['wwLbl']
    if key not in emp_week_first_src:
        emp_week_first_src[key] = {'ch': r['ch'], 'chCat': r['chCat']}

emp_mon_first_src = {}


def mon_sort_key(r):
    if r['walkinTs'] is not None:
        return (0, r['walkinTs'])
    return (1, r['ww'] or datetime.min, r['evRank'])


mon_sorted = sorted([r for r in rows if r['ww'] is not None], key=mon_sort_key)
for r in mon_sorted:
    if not r['emp'] or not r['wwMon']:
        continue
    key = r['emp'] + '|' + r['wwMon']
    if key not in emp_mon_first_src:
        emp_mon_first_src[key] = {'ch': r['ch'], 'chCat': r['chCat']}

# ── ch_by_month / channel_by_month / ch_to_chcat / agent_by_month / tc_by_month
ch_by_month, channel_by_month, ch_to_chcat = {}, {}, {}
agent_by_month, tc_by_month = {}, {}
for lbl in months:
    w = [r for r in rows if r['wwMon'] == lbl and r['ww'] is not None]
    ch_cat_map, ch_map, ag, tc = {}, {}, {}, {}
    seen = set()
    for r in w:
        mon_key = r['emp'] + '|' + lbl
        if mon_key not in seen:
            seen.add(mon_key)
            src = emp_mon_first_src.get(mon_key) or {'ch': r['ch'], 'chCat': r['chCat']}
            if src['chCat']:
                ch_cat_map[src['chCat']] = ch_cat_map.get(src['chCat'], 0) + 1
            if src['ch']:
                ch_map[src['ch']] = ch_map.get(src['ch'], 0) + 1
        if r['ch'] and r['chCat']:
            ch_to_chcat[r['ch']] = r['chCat']
        if r['agent']:
            ag[r['agent']] = ag.get(r['agent'], 0) + 1
        t = r['tc'] or 'Un-Mapped'
        tc[t] = tc.get(t, 0) + 1
    ch_by_month[lbl] = ch_cat_map
    channel_by_month[lbl] = ch_map
    agent_by_month[lbl] = ag
    tc_by_month[lbl] = tc

# ── per-chcat full funnel breakdown (by_week_chcat, by_month_chcat) ─────
chcat_list = list(ch_by_month.get(months[0], {}).keys()) if months else []
for lbl in months:
    for c in ch_by_month.get(lbl, {}):
        if c not in chcat_list:
            chcat_list.append(c)

by_week_chcat = {}
for wk_lbl in weeks:
    wk_ts = weeks_map[wk_lbl]
    wk_end = wk_ts + timedelta(days=7)
    w_rows_wk = [r for r in rows if r['ww'] == wk_ts]
    by_week_chcat[wk_lbl] = {}
    for chcat in chcat_list:
        emp_set = set()
        for r in w_rows_wk:
            src = emp_week_first_src.get(r['emp'] + '|' + wk_lbl)
            if src and src['chCat'] == chcat:
                emp_set.add(r['emp'])
        if not emp_set:
            continue
        w_ch = [r for r in w_rows_wk if r['emp'] in emp_set]
        f_ch = [r for r in rows if r['emp'] in emp_set]
        by_week_chcat[wk_lbl][chcat] = compute_metrics(w_ch, f_ch, wk_ts, wk_end)

by_month_chcat = {}
for lbl in months:
    s, e = month_start(lbl), month_end(lbl)
    w_mon = [r for r in rows if r['wwMon'] == lbl and r['ww'] is not None]
    by_month_chcat[lbl] = {}
    for chcat in chcat_list:
        emp_set = set()
        for r in w_mon:
            src = emp_mon_first_src.get(r['emp'] + '|' + lbl)
            if src and src['chCat'] == chcat:
                emp_set.add(r['emp'])
        if not emp_set:
            continue
        w_ch = [r for r in w_mon if r['emp'] in emp_set]
        f_ch = [r for r in rows if r['emp'] in emp_set]
        by_month_chcat[lbl][chcat] = compute_metrics(w_ch, f_ch, s, e)

# ── per-source (specific channel) full funnel breakdown ────────────────
src_list = []
for r in rows:
    if r['ch'] and r['ch'] not in src_list:
        src_list.append(r['ch'])

by_week_ch = {}
for wk_lbl in weeks:
    wk_ts = weeks_map[wk_lbl]
    wk_end = wk_ts + timedelta(days=7)
    w_rows_wk = [r for r in rows if r['ww'] == wk_ts]
    by_week_ch[wk_lbl] = {}
    for src in src_list:
        emp_set = set()
        for r in w_rows_wk:
            s_ = emp_week_first_src.get(r['emp'] + '|' + wk_lbl)
            if s_ and s_['ch'] == src:
                emp_set.add(r['emp'])
        if not emp_set:
            continue
        w_src = [r for r in w_rows_wk if r['emp'] in emp_set]
        f_src = [r for r in rows if r['emp'] in emp_set]
        by_week_ch[wk_lbl][src] = compute_metrics(w_src, f_src, wk_ts, wk_end)

by_month_ch = {}
for lbl in months:
    s, e = month_start(lbl), month_end(lbl)
    w_mon = [r for r in rows if r['wwMon'] == lbl and r['ww'] is not None]
    by_month_ch[lbl] = {}
    for src in src_list:
        emp_set = set()
        for r in w_mon:
            ms = emp_mon_first_src.get(r['emp'] + '|' + lbl)
            if ms and ms['ch'] == src:
                emp_set.add(r['emp'])
        if not emp_set:
            continue
        w_src = [r for r in w_mon if r['emp'] in emp_set]
        f_src = [r for r in rows if r['emp'] in emp_set]
        by_month_ch[lbl][src] = compute_metrics(w_src, f_src, s, e)

# ── lead-type funnel breakdown (all categories) ─────────────────────────
by_week_leadtype = {}
for wk_lbl in weeks:
    wk_ts = weeks_map[wk_lbl]
    wk_end = wk_ts + timedelta(days=7)
    by_week_leadtype[wk_lbl] = {}
    for lt in LEAD_TYPES:
        w_lt = [r for r in lt_rows if r['ww'] == wk_ts and r['cat'] == lt]
        if not w_lt:
            continue
        f_lt = rows if lt == 'new join' else [r for r in lt_rows if r['cat'] == lt]
        by_week_leadtype[wk_lbl][lt] = compute_metrics(w_lt, f_lt, wk_ts, wk_end)

by_month_leadtype = {}
for lbl in months:
    s, e = month_start(lbl), month_end(lbl)
    by_month_leadtype[lbl] = {}
    for lt in LEAD_TYPES:
        w_lt = [r for r in lt_rows if r['wwMon'] == lbl and r['cat'] == lt]
        if not w_lt:
            continue
        f_lt = rows if lt == 'new join' else [r for r in lt_rows if r['cat'] == lt]
        by_month_leadtype[lbl][lt] = compute_metrics(w_lt, f_lt, s, e)

# ── lead type by month, all Hyderabad categories ────────────────────────
lead_by_month = {}
for lbl in months:
    cat_counts = {}
    for r in all_rows:
        if r['wwMon'] == lbl:
            cat_counts[r['cat']] = cat_counts.get(r['cat'], 0) + 1
    lead_by_month[lbl] = cat_counts

result = {
    'months': months,
    'weeks': weeks,
    'days': days,
    'locations': LOCS,
    'by_month': by_month,
    'by_week': by_week,
    'by_day': by_day,
    'ch_by_month': ch_by_month,
    'channel_by_month': channel_by_month,
    'ch_to_chcat': ch_to_chcat,
    'by_week_chcat': by_week_chcat,
    'by_month_chcat': by_month_chcat,
    'by_week_ch': by_week_ch,
    'by_month_ch': by_month_ch,
    'by_week_leadtype': by_week_leadtype,
    'by_month_leadtype': by_month_leadtype,
    'agent_by_month': agent_by_month,
    'lead_by_month': lead_by_month,
    'tc_by_month': tc_by_month,
}

with open(OUT_JSON, 'w') as f:
    json.dump(result, f)

print(f"Wrote {OUT_JSON}", file=sys.stderr)
print(f"months: {months}", file=sys.stderr)
print(f"weeks: {len(weeks)}  days: {len(days)}", file=sys.stderr)
print(f"chcat_list: {chcat_list}", file=sys.stderr)
print(f"src_list ({len(src_list)}): {src_list[:10]}...", file=sys.stderr)
