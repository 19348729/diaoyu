import json
from collections import Counter, defaultdict

path = 'd:/cursor_code/diaoy/data/master_kb.jsonl'
records = []
with open(path, 'r', encoding='utf-8') as f:
    for i, line in enumerate(f, 1):
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except Exception as e:
            print(f'JSON ERROR line {i}: {e}')

n = len(records)
print(f'总条数: {n}')

# 统计字段
fields = Counter()
for r in records:
    for k in r.keys():
        fields[k] += 1
print('\n字段覆盖率:')
for k, v in fields.most_common():
    print(f'  {k}: {v} ({v*100//n}%)')

# 鱼种分布
fish_counter = Counter()
for r in records:
    for f in r.get('fish', []):
        fish_counter[f] += 1
print('\n鱼种分布:')
for k, v in fish_counter.most_common():
    print(f'  {k}: {v}')

# 季节分布
season_counter = Counter(r.get('season', '') for r in records)
print('\n季节分布:')
for k, v in season_counter.most_common():
    print(f'  {k}: {v}')

# 大师分布
master_counter = Counter(r.get('master', '') for r in records)
print('\n大师Top10:')
for k, v in master_counter.most_common(15):
    print(f'  {k}: {v}')

# pressure_state统计
ps_counter = Counter(r.get('pressure_state', '') for r in records)
print('\npressure_state分布:')
for k, v in ps_counter.most_common():
    print(f'  {k}: {v}')

# quality
q_counter = Counter(r.get('quality', '') for r in records)
print('\nquality分布:')
for k, v in q_counter.most_common():
    print(f'  {k}: {v}')

# 温度区间
print('\n温度区间分布:')
temp_buckets = Counter()
for r in records:
    tmin = r.get('temp_min')
    tmax = r.get('temp_max')
    if tmin is not None and tmax is not None:
        bucket = f'{tmin}~{tmax}'
        temp_buckets[bucket] += 1
for k, v in temp_buckets.most_common(15):
    print(f'  {k}: {v}')

# 字段空值检测
print('\n关键字段空值统计:')
empty_fields = ['line', 'float_setup', 'rhythm', 'flavor', 'recipe']
for f in empty_fields:
    empty = sum(1 for r in records if not (r.get(f) or '').strip())
    print(f'  {f} 空值: {empty} ({empty*100//n}%)')

# 重复检测：title去重
title_counter = Counter(r.get('title', '') for r in records)
dup_titles = [(t, c) for t, c in title_counter.items() if c > 1]
print(f'\n重复标题(title)条数: {len(dup_titles)}')
for t, c in dup_titles[:10]:
    print(f'  [{c}] {t[:60]}')

# 重复检测：video_url
url_counter = Counter(r.get('video_url', '') for r in records)
dup_urls = [(u, c) for u, c in url_counter.items() if c > 1]
print(f'\n重复video_url条数: {len(dup_urls)}')
total_dup_records = sum(c for _, c in dup_urls)
print(f'  涉及记录数: {total_dup_records}')

# 同URL不同鱼种 — 即一条视频被拆分到多个鱼种的情况
url_fish_map = defaultdict(set)
for r in records:
    u = r.get('video_url', '')
    for f in r.get('fish', []):
        url_fish_map[u].add(f)
multi_fish_urls = {u: fs for u, fs in url_fish_map.items() if len(fs) > 1}
print(f'\n一URL多鱼种(可能交叉): {len(multi_fish_urls)} 个URL')
for u, fs in list(multi_fish_urls.items())[:5]:
    print(f'  {u}: {fs}')

# 单鱼种字段
single_fish = sum(1 for r in records if len(r.get('fish', [])) == 1)
multi_fish = sum(1 for r in records if len(r.get('fish', [])) > 1)
print(f'\n单鱼种条目: {single_fish}, 多鱼种条目: {multi_fish}')

# id去重
id_counter = Counter(r.get('id', '') for r in records)
dup_ids = [(i, c) for i, c in id_counter.items() if c > 1]
print(f'\n重复id条数: {len(dup_ids)}')

# 平均文本长度
avg_recipe = sum(len(r.get('recipe', '')) for r in records) / max(n, 1)
avg_float = sum(len(r.get('float_setup', '')) for r in records) / max(n, 1)
avg_rhythm = sum(len(r.get('rhythm', '')) for r in records) / max(n, 1)
print(f'\n平均字段长度: recipe={avg_recipe:.1f}, float_setup={avg_float:.1f}, rhythm={avg_rhythm:.1f}')
