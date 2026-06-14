from flask import Flask, send_file, request, jsonify, Response
import re
from datetime import datetime, timezone, timedelta
import csv
from io import StringIO

app = Flask(__name__)

downtime_events = []

IST = timezone(timedelta(hours=5, minutes=30))

def get_ist_timestamp():
    return datetime.now(IST).strftime("%Y-%m-%d %I:%M:%S %p")

NAME_MAP = {
    # Exact names
    "cnc machine": "CNC Machine",
    "cnc": "CNC Machine",
    "lathe machine": "Lathe Machine",
    "lathe": "Lathe Machine",
    "grinder machine": "Grinder",
    "grinder": "Grinder",
    # Common misspellings / typos
    "grider": "Grinder",
    "grider machine": "Grinder",
    "gridder": "Grinder",
    "grindr": "Grinder",
    # Number aliases
    "machine 1": "CNC Machine",
    "machine 2": "Lathe Machine",
    "machine 3": "Grinder",
    "1": "CNC Machine",
    "2": "Lathe Machine",
    "3": "Grinder",
}

def extract_downtime_info(text):
    text_lower = text.lower()
    result = {"machine": None, "cause": "unknown"}
    sorted_keys = sorted(NAME_MAP.keys(), key=len, reverse=True)
    for key in sorted_keys:
        if key in text_lower:
            result["machine"] = NAME_MAP[key]
            remaining = re.sub(rf'\b{re.escape(key)}\b', '', text_lower, flags=re.IGNORECASE).strip()
            remaining = re.sub(r'^(stopped|down|failed|issue|problem|band|off|is)\s*', '', remaining)
            if remaining:
                result["cause"] = remaining[:100]
            break
    if result["cause"] == "unknown":
        if "bearing" in text_lower:
            result["cause"] = "bearing failure"
        elif "motor" in text_lower:
            result["cause"] = "motor failure"
        elif "power" in text_lower or "bijli" in text_lower or "electric" in text_lower:
            result["cause"] = "power failure"
        elif "belt" in text_lower:
            result["cause"] = "belt broken"
        elif "operator" in text_lower or "chai" in text_lower or "absent" in text_lower:
            result["cause"] = "operator absent"
    return result

@app.route('/')
def home():
    return send_file('reliability.html')

@app.route('/shopfloor')
def shopfloor():
    return send_file('voice_recorder.html')

@app.route('/worker')
def worker_redirect():
    return send_file('voice_recorder.html')

@app.route('/whatsapp', methods=['POST'])
def whatsapp_webhook():
    incoming_msg = request.values.get("Body", "").lower()
    extracted = extract_downtime_info(incoming_msg)
    if extracted["machine"]:
        now = get_ist_timestamp()
        downtime_events.append({
            "machine": extracted["machine"],
            "cause": extracted["cause"],
            "start_time": now,
            "end_time": None
        })
        return f"✅ {extracted['machine']} downtime logged at {now}. Cause: {extracted['cause']}"
    else:
        return f"❌ Could not recognise machine in '{incoming_msg}'. Please say machine name (CNC, Lathe, Grinder) or number (1,2,3)."

@app.route('/get_events')
def get_events():
    active_events = [e for e in downtime_events if e['end_time'] is None]
    events_for_dashboard = [{
        "machine": e["machine"],
        "cause": e["cause"],
        "timestamp": e["start_time"]
    } for e in active_events]
    return jsonify({"events": events_for_dashboard})

@app.route('/all_events')
def all_events():
    events_for_reliability = []
    for event in downtime_events:
        events_for_reliability.append({
            "machine": event["machine"],
            "cause": event["cause"],
            "start_time": event["start_time"],
            "end_time": event["end_time"]
        })
    return jsonify({"events": events_for_reliability})

@app.route('/reset')
def reset():
    downtime_events.clear()
    return jsonify({"status": "reset"})

@app.route('/reset_machine', methods=['POST'])
def reset_machine():
    data = request.get_json()
    machine_name = data.get('machine')
    if not machine_name:
        return jsonify({"error": "Machine name required"}), 400
    global downtime_events
    now = get_ist_timestamp()
    for event in downtime_events:
        if event['machine'] == machine_name and event['end_time'] is None:
            event['end_time'] = now
            break
    return jsonify({"status": f"Reset {machine_name}"})

@app.route('/export_reliability')
def export_reliability():
    si = StringIO()
    si.write('\uFEFF')  # UTF-8 BOM for Excel
    cw = csv.writer(si)
    cw.writerow(["Start Time", "End Time", "Duration (minutes)", "Machine", "Cause", "Status"])
    
    for event in downtime_events:
        start_str = event['start_time']
        end_str = event['end_time'] if event['end_time'] else "Still open"
        status = "Closed" if event['end_time'] else "Open"
        # Calculate duration
        try:
            start_dt = datetime.strptime(start_str, "%Y-%m-%d %I:%M:%S %p")
            if event['end_time']:
                end_dt = datetime.strptime(event['end_time'], "%Y-%m-%d %I:%M:%S %p")
                duration_min = int((end_dt - start_dt).total_seconds() / 60)
            else:
                duration_min = "N/A"
        except:
            duration_min = "N/A"
        
        cw.writerow([start_str, end_str, duration_min, event['machine'], event['cause'], status])
    
    output = si.getvalue()
    return Response(output, mimetype='text/csv', 
                    headers={"Content-Disposition": "attachment;filename=reliability_report.csv"})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8080)