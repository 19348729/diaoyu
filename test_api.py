import urllib.request, json, time

ts = int(time.time())
payload = {
    'fish_type': '鲫鱼',
    'sensors': [
        {'timestamp': ts - 600 + i*5, 't_bottom': 18.0+i*0.01, 't_mid': 19.0+i*0.01, 't_surface': 20.0+i*0.01, 'p_local': 1008.0+i*0.01}
        for i in range(120)
    ],
    'wind_speed': 2.5,
    'altitude': 150.0,
    'weather_trend': 'sunny',
}
req = urllib.request.Request(
    'http://localhost:8000/api/predict',
    data=json.dumps(payload).encode(),
    headers={'Content-Type': 'application/json'},
)
r = urllib.request.urlopen(req)
result = json.loads(r.read())
print(f"bite_index: {result['bite_index']}")
print(f"confidence: {result['confidence']}%")
print(f"report_stage: {result['report_stage']}")
print(f"do_trend: {result['do_trend']} mg/L")
print(f"tags count: {len(result['tactical_tags'])}")
print(f"advice: {result.get('tactical_advice', {})}")
print('OK')
