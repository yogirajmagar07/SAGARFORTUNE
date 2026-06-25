import os
from datetime import datetime, timedelta
import pytz
from flask import Flask, request, jsonify, send_file, render_template, session, redirect, Response ,url_for
from azure.data.tables import TableServiceClient
import pandas as pd
from io import BytesIO
from reportlab.platypus import SimpleDocTemplate, Table
from reportlab.lib.pagesizes import letter
import json
from functools import wraps
from io import BytesIO
from math import *
from flask import request, jsonify, send_file
from reportlab.lib.pagesizes import letter, landscape
from reportlab.pdfgen import canvas

app = Flask(__name__)
app.secret_key = "super-secret-key"
app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True

# =========================
# Azure Table Config
# =========================
TABLES_CONN = os.environ.get("TABLES_CONNECTION_STRING")
TABLE_NAME = os.environ.get("TABLE_NAME", "SAGARFORTUNE")

service = TableServiceClient.from_connection_string(TABLES_CONN)
table_client = service.get_table_client(TABLE_NAME)

try:
    table_client.create_table()
except:
    pass

# =========================
# In-Memory Cache (Device Wise)
# =========================
latest_cache = {}

#==========================
# Authentication
#==========================
API_KEY = os.environ.get("API_KEY")

def api_key_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):

        client_key = request.headers.get("X-API-Key")

        if not client_key:
            return jsonify({
                "error": "API Key missing"
            }), 401

        if client_key != API_KEY:
            return jsonify({
                "error": "Invalid API Key"
            }), 401

        return f(*args, **kwargs)

    return decorated

# Login decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Login route
@app.route('/')
def login():
    return render_template('login.html')

# Login API endpoint (for AJAX login)
@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    
    # Simple authentication (use proper auth in production)
    if username == 'admin' and password == 'admin123':
        session['user_id'] = username
        session['username'] = username
        return jsonify({'success': True})
    else:
        return jsonify({'success': False, 'error': 'Invalid credentials'}), 401

# =========================
# LOGOUT
# =========================
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


# =========================
# DASHBOARD PAGE
# =========================
# Dashboard route (protected)
@app.route('/dashboard')
@login_required
def dashboard():
    return render_template("index.html")


# =========================
# REPORT PAGE
# =========================
@app.route("/reports")
@login_required
def reports():
    return render_template("reports.html")


# =========================
# BUILD ENTITY
# =========================
def build_entity(data):

    deviceid = str(data.get("deviceid", "susanad"))

    ist = pytz.timezone("Asia/Kolkata")
    ist_time = datetime.utcnow().replace(tzinfo=pytz.utc).astimezone(ist)

    # ✅ FIX 1 — Unique RowKey
    rowkey = ist_time.strftime("%Y%m%d%H%M%S%f")

    ts = ist_time.strftime("%Y-%m-%d %H:%M:%S")

    entity = {
        "PartitionKey": deviceid,
        "RowKey": rowkey,
        "TimestampIST": ts
    }

    for k, v in data.items():
        if k != "deviceid":
            entity[k] = str(v)

    return entity


# =========================
# INGEST API (SCADA)
# =========================
@app.route("/ingest", methods=["POST"])
def ingest():

    if not request.is_json:
        return jsonify({"error": "JSON required"}), 400

    data = request.get_json()

    try:
        entity = build_entity(data)

        table_client.upsert_entity(entity=entity, mode="replace")

        # ✅ FIX 2 — Multi Device Cache
        latest_cache[entity["PartitionKey"]] = entity

    except Exception as e:
        return jsonify({"error": str(e)}), 500

    return jsonify({"status": "ok"})


# =========================
# Latest Dashboard API
# =========================
@app.route("/api/latest")
@login_required
def latest():
    return jsonify(list(latest_cache.values()))

# =========================
# Fuel Consumption API
# =========================
# @app.route("/API")
# @api_key_required
# def api_readings():
#     from_time = request.args.get("fromTime")
#     to_time = request.args.get("toTime")
#     deviceid = "susanad"

#     if not from_time or not to_time:
#         return jsonify({"error": "fromTime and toTime required"}), 400

#     try:
#         start_dt = datetime.strptime(from_time, "%Y-%m-%dT%H:%M:%SZ")
#         end_dt = datetime.strptime(to_time, "%Y-%m-%dT%H:%M:%SZ")
#     except Exception:
#         return jsonify({"error": "Invalid datetime format. Use YYYY-MM-DDTHH:MM:SSZ"}), 400

#     # Convert API ISO time to Azure stored TimestampIST format
#     azure_from_time = start_dt.strftime("%Y-%m-%d %H:%M:%S")
#     azure_to_time = end_dt.strftime("%Y-%m-%d %H:%M:%S")

#     def get_float(row, key):
#         return float(row.get(key, 0) or 0)

#     def parse_azure_time(ts):
#         for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%SZ"):
#             try:
#                 return datetime.strptime(ts, fmt)
#             except Exception:
#                 pass
#         return None


#     engine_config = {
#         "PME": {
#             "name": "Main Engine 1",
#             "total_col": "ME1VolumeTotal",
#             "inlet_col": "FT1Volumetotal",
#             "outlet_col": "FT2Volumetotal"
#         },
#         "SME": {
#             "name": "Main Engine 2",
#             "total_col": "ME2VolumeTotal",
#             "inlet_col": "FT3Volumetotal",
#             "outlet_col": "FT4Volumetotal"
#         },
#         "AE1": {
#             "name": "Generator 1",
#             "total_col": "AE1VolumeTotal",
#             "inlet_col": "FT5Volumetotal",
#             "outlet_col": "FT6Volumetotal"
#         },
#         "AE2": {
#             "name": "Generator 2",
#             "total_col": "AE2VolumeTotal",
#             "inlet_col": "FT7Volumetotal",
#             "outlet_col": "FT8Volumetotal"
#         },
#         "AE3": {
#             "name": "Generator 3",
#             "total_col": "AE3VolumeTotal",
#             "inlet_col": "FT9Volumetotal",
#             "outlet_col": "FT10Volumetotal"
#         },
#         "AE4": {
#             "name": "Generator 4",
#             "total_col": "AE4VolumeTotal",
#             "inlet_col": "FT11Volumetotal",
#             "outlet_col": "FT12Volumetotal"
#         }
#     }

#     readings = []

#     try:
#         query = (
#             f"PartitionKey eq '{deviceid}' "
#             f"and TimestampIST ge '{azure_from_time}' "
#             f"and TimestampIST le '{azure_to_time}'"
#         )

#         entities = list(table_client.query_entities(query))

#         print("API Records Found =", len(entities))
#         if entities:
#             print("Sample TimestampIST =", entities[0].get("TimestampIST"))
#             print("Sample Keys =", list(entities[0].keys()))

#         current_start = start_dt

#         while current_start < end_dt:
#             current_end = min(current_start + timedelta(hours=1), end_dt)

#             totals = {
#                 "PME": 0,
#                 "SME": 0,
#                 "AE1": 0,
#                 "AE2": 0,
#                 "AE3": 0,
#                 "AE4": 0
#             }

#             for e in entities:
#                 ts = e.get("TimestampIST")
#                 if not ts:
#                     continue

#                 ts_dt = parse_azure_time(ts)
#                 if not ts_dt:
#                     continue

#                 if current_start <= ts_dt < current_end:
#                     for engine_key, cfg in engine_config.items():
#                         total_value = get_float(e, cfg["total_col"])

#                         # fallback if total column is missing or zero
#                         if total_value == 0:
#                             inlet_value = get_float(e, cfg["inlet_col"])
#                             outlet_value = get_float(e, cfg["outlet_col"])
#                             total_value = inlet_value - outlet_value

#                         totals[engine_key] += total_value

#             main_engine_1_total = totals["PME"]
#             main_engine_2_total = totals["SME"]

#             generator_1_total = totals["AE1"]
#             generator_2_total = totals["AE2"]
#             generator_3_total = totals["AE3"]
#             generator_4_total = totals["AE4"]

#             total_main_engines = main_engine_1_total + main_engine_2_total
#             total_generators = (
#                 generator_1_total +
#                 generator_2_total +
#                 generator_3_total +
#                 generator_4_total
#             )

#             readings.append({
#                 "measurementStartTime": current_start.strftime("%Y-%m-%dT%H:%M:%SZ"),
#                 "measurementEndTime": (current_end - timedelta(seconds=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
#                 "kind": "VESSEL",
#                 "mmsi": "419001287",
#                 "imo": "9458327",
#                 "consumption": {
#                     "mainEnginesTotal": round(total_main_engines, 8),
#                     "generatorsTotal": round(total_generators, 8),
#                     "totalConsumption": round(total_main_engines + total_generators, 8),
#                     "mainEngines": [
#                         {
#                             "name": "Main Engine 1",
#                             "value": round(main_engine_1_total, 8)
#                         },
#                         {
#                             "name": "Main Engine 2",
#                             "value": round(main_engine_2_total, 8)
#                         }
#                     ],
#                     "generators": [
#                         {
#                             "name": "Generator 1",
#                             "value": round(generator_1_total, 8)
#                         },
#                         {
#                             "name": "Generator 2",
#                             "value": round(generator_2_total, 8)
#                         },
#                         {
#                             "name": "Generator 3",
#                             "value": round(generator_3_total, 8)
#                         },
#                         {
#                             "name": "Generator 4",
#                             "value": round(generator_4_total, 8)
#                         }
#                     ]
#                 }
#             })

#             current_start = current_end

#     except Exception as e:
#         return jsonify({"error": str(e)}), 500

#     return Response(
#         json.dumps({"readings": readings}, indent=4),
#         mimetype="application/json"
#     )

@app.route("/API")
@api_key_required
def api_readings():

    from_time = request.args.get("fromTime")
    to_time = request.args.get("toTime")

    deviceid = "susanad"

    if not from_time or not to_time:
        return jsonify({
            "error": "fromTime and toTime required"
        }), 400

    # ==================================================
    # Parse request timestamps
    # Supports:
    # 2026-06-23T00:00:00Z
    # 2026-06-23T00:00:00.00Z
    # ==================================================

    def parse_request_time(value):

        formats = [
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%dT%H:%M:%S.%fZ"
        ]

        for fmt in formats:
            try:
                return datetime.strptime(value, fmt)
            except Exception:
                pass

        raise ValueError("Invalid datetime format")

    try:

        start_dt = parse_request_time(from_time)
        end_dt = parse_request_time(to_time)

        if end_dt <= start_dt:
            return jsonify({
                "error": "toTime must be greater than fromTime"
            }), 400
        max_end_dt = start_dt + timedelta(hours=24)
        if end_dt > max_end_dt:
            print(
                f"Requested window exceeds 24 hours. "
                 f"Clamping end time from {end_dt} to {max_end_dt}"
            )
            end_dt = max_end_dt

    # ==================================================
    # Restrict request window to maximum 24 hours
    # Example:
    # fromTime=2026-06-23T00:00:00Z
    # toTime=2026-06-24T01:00:00Z
    #
    # Internally becomes:
    # toTime=2026-06-24T00:00:00Z
    # ==================================================


    except Exception:
        return jsonify({
            "error":
            "Invalid datetime format. Supported formats: "
            "YYYY-MM-DDTHH:MM:SSZ "
            "or "
            "YYYY-MM-DDTHH:MM:SS.sssZ"
        }), 400

    # ==================================================
    # Azure Date Format
    # ==================================================

    azure_from_time = start_dt.strftime("%Y-%m-%d %H:%M:%S")
    azure_to_time = end_dt.strftime("%Y-%m-%d %H:%M:%S")

    # ==================================================
    # Helpers
    # ==================================================

    def get_float(row, key):

        try:
            return float(row.get(key, 0) or 0)
        except Exception:
            return 0.0
            
    def format_iso_2ms(dt):
        return dt.strftime("%Y-%m-%dT%H:%M:%S") + ".00Z"


    def parse_azure_time(ts):

        for fmt in (
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M:%SZ"
        ):
            try:
                return datetime.strptime(ts, fmt)
            except Exception:
                pass

        return None

    # ==================================================
    # Engine Config
    # ==================================================

    engine_config = {

        "PME": {
            "name": "Main Engine 1",
            "total_col": "ME1Volumetotal",
            "inlet_col": "FT1Volumetotal",
            "outlet_col": "FT2Volumetotal"
        },

        "SME": {
            "name": "Main Engine 2",
            "total_col": "ME2Volumetotal",
            "inlet_col": "FT3Volumetotal",
            "outlet_col": "FT4Volumetotal"
        },

        "AE1": {
            "name": "Generator 1",
            "total_col": "AE1Volumetotal",
            "inlet_col": "FT5Volumetotal",
            "outlet_col": "FT6Volumetotal"
        },

        "AE2": {
            "name": "Generator 2",
            "total_col": "AE2Volumetotal",
            "inlet_col": "FT7Volumetotal",
            "outlet_col": "FT8Volumetotal"
        },

        "AE3": {
            "name": "Generator 3",
            "total_col": "AE3Volumetotal",
            "inlet_col": "FT9Volumetotal",
            "outlet_col": "FT10Volumetotal"
        },

        "AE4": {
            "name": "Generator 4",
            "total_col": "AE4Volumetotal",
            "inlet_col": "FT11Volumetotal",
            "outlet_col": "FT12Volumetotal"
        }
    }

    readings = []

    try:

        query = (
            f"PartitionKey eq '{deviceid}' "
            f"and TimestampIST ge '{azure_from_time}' "
            f"and TimestampIST le '{azure_to_time}'"
        )

        entities = list(
            table_client.query_entities(query)
        )

        print(f"API Records Found = {len(entities)}")

        current_start = start_dt

        # ==================================================
        # Generate hourly blocks
        # ==================================================

        while current_start < end_dt:

            current_end = min(
                current_start + timedelta(hours=1),
                end_dt
            )

            totals = {
                "PME": 0.0,
                "SME": 0.0,
                "AE1": 0.0,
                "AE2": 0.0,
                "AE3": 0.0,
                "AE4": 0.0
            }

            for entity in entities:

                ts = entity.get("TimestampIST")

                if not ts:
                    continue

                ts_dt = parse_azure_time(ts)

                if not ts_dt:
                    continue

                # ==========================================
                # Strict UTC window validation
                # ==========================================

                if not (
                    start_dt <= ts_dt < end_dt
                ):
                    continue

                if not (
                    current_start <= ts_dt < current_end
                ):
                    continue

                for engine_key, cfg in engine_config.items():

                    total_value = get_float(
                        entity,
                        cfg["total_col"]
                    )

                    # fallback
                    if total_value == 0:

                        inlet_value = get_float(
                            entity,
                            cfg["inlet_col"]
                        )

                        outlet_value = get_float(
                            entity,
                            cfg["outlet_col"]
                        )

                        total_value = (
                            inlet_value -
                            outlet_value
                        )

                    totals[engine_key] += total_value

            # ==========================================
            # Convert Litres -> kL
            # ==========================================

            main_engine_1_total = totals["PME"] / 1000
            main_engine_2_total = totals["SME"] / 1000

            generator_1_total = abs(totals["AE1"] / 1000)
            generator_2_total = abs(totals["AE2"] / 1000)
            generator_3_total = abs(totals["AE3"] / 1000)
            generator_4_total = abs(totals["AE4"] / 1000)

            total_main_engines = (
                main_engine_1_total +
                main_engine_2_total
            )

            total_generators = (
                generator_1_total +
                generator_2_total +
                generator_3_total +
                generator_4_total
            )

            readings.append({

                "measurementStartTime":format_iso_2ms(
                    current_start
                    ),

                "measurementEndTime":format_iso_2ms(
                        current_end
                    ),

                "kind": "VESSEL",
                "mmsi": "419001287",
                "imo": "9458327",

                "consumption": {

                    "unit": "kL/hr",

                    "mainEnginesTotal":
                        round(total_main_engines, 8),

                    "generatorsTotal":
                        round(total_generators, 8),

                    "totalConsumption":
                        round(
                            total_main_engines +
                            total_generators,
                            8
                        ),

                    "mainEngines": [
                        {
                            "name": "Main Engine 1",
                            "value": round(
                                main_engine_1_total,
                                8
                            )
                        },
                        {
                            "name": "Main Engine 2",
                            "value": round(
                                main_engine_2_total,
                                8
                            )
                        }
                    ],

                    "generators": [
                        {
                            "name": "Generator 1",
                            "value": round(
                                generator_1_total,
                                8
                            )
                        },
                        {
                            "name": "Generator 2",
                            "value": round(
                                generator_2_total,
                                8
                            )
                        },
                        {
                            "name": "Generator 3",
                            "value": round(
                                generator_3_total,
                                8
                            )
                        },
                        {
                            "name": "Generator 4",
                            "value": round(
                                generator_4_total,
                                8
                            )
                        }
                    ]
                }
            })

            current_start = current_end

    except Exception as e:

        return jsonify({
            "error": str(e)
        }), 500

    response_data = {

        "requestWindow": {
            "fromTime":format_iso_2ms(
                start_dt
                ),
            "toTime":format_iso_2ms(
                end_dt
                ),
            "timezone": "UTC"
        },

        "readings": readings
    }

    return Response(
        json.dumps(response_data, indent=4),
        mimetype="application/json"
    )

# New logic

# Add these imports at the top if not already present
from io import BytesIO
import pandas as pd
from datetime import datetime
from functools import wraps

def parse_dt(value):
    """Parse datetime string to datetime object"""
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        try:
            return datetime.strptime(value, "%Y-%m-%d %H:%M")
        except ValueError:
            return datetime.strptime(value.replace('T', ' '), "%Y-%m-%d %H:%M")

# ========================
# Fetch Engine Consumption
# ========================


import math

def fetch_engine_consumption(engine_type, start, end, interval="hour"):
    deviceid = "susanad"

    engine_config = {
        "PME": {
            "name": "PME Main Engine (P)",
            "inlet_col": "FT1Volumetotal",
            "outlet_col": "FT2Volumetotal",
            "total_col": "ME1Volumetotal",
            "inlet_temp_col": "FT1Temp",
            "outlet_temp_col": "FT2Temp",
            "inlet_density_col": "FT1Density",
            "outlet_density_col": "FT2Density",
            "formula": "FT1Volumetotal - FT2Volumetotal"
        },
        "SME": {
            "name": "SME Main Engine (S)",
            "inlet_col": "FT3Volumetotal",
            "outlet_col": "FT4Volumetotal",
            "total_col": "ME2Volumetotal",
            "inlet_temp_col": "FT3Temp",
            "outlet_temp_col": "FT4Temp",
            "inlet_density_col": "FT3Density",
            "outlet_density_col": "FT4Density",
            "formula": "FT3Volumetotal - FT4Volumetotal"
        },
        "AE1": {
            "name": "AE1 Auxiliary Engine 1",
            "inlet_col": "FT5Volumetotal",
            "outlet_col": "FT6Volumetotal",
            "total_col": "AE1Volumetotal",
            "inlet_temp_col": "FT5Temp",
            "outlet_temp_col": "FT6Temp",
            "inlet_density_col": "FT5Density",
            "outlet_density_col": "FT6Density",
            "formula": "FT5Volumetotal - FT6Volumetotal"
        },
        "AE2": {
            "name": "AE2 Auxiliary Engine 2",
            "inlet_col": "FT7Volumetotal",
            "outlet_col": "FT8Volumetotal",
            "total_col": "AE2Volumetotal",
            "inlet_temp_col": "FT7Temp",
            "outlet_temp_col": "FT8Temp",
            "inlet_density_col": "FT7Density",
            "outlet_density_col": "FT8Density",
            "formula": "FT7Volumetotal - FT8Volumetotal"
        },
        "AE3": {
            "name": "AE3 Auxiliary Engine 3",
            "inlet_col": "FT9Volumetotal",
            "outlet_col": "FT10Volumetotal",
            "total_col": "AE3Volumetotal",
            "inlet_temp_col": "FT9Temp",
            "outlet_temp_col": "FT10Temp",
            "inlet_density_col": "FT9Density",
            "outlet_density_col": "FT10Density",
            "formula": "FT9Volumetotal - FT10Volumetotal"
        },
        "AE4": {
            "name": "AE4 Auxiliary Engine 4",
            "inlet_col": "FT11Volumetotal",
            "outlet_col": "FT12Volumetotal",
            "total_col": "AE4Volumetotal",
            "inlet_temp_col": "FT11Temp",
            "outlet_temp_col": "FT12Temp",
            "inlet_density_col": "FT11Density",
            "outlet_density_col": "FT12Density",
            "formula": "FT11Volumetotal - FT12Volumetotal"
        },
        "BUNKER": {
            "name": "BUNKER Flow Meter",
            "inlet_col": "FT15Volumetotal",
            "outlet_col": None,
            "total_col": "FT15Volumetotal",
            "inlet_temp_col": "FT15Temp",
            "outlet_temp_col": None,
            "inlet_density_col": "FT15Density",
            "outlet_density_col": None,
            "formula": "FT15Volumetotal"
        },
        "TOTAL": {
            "name": "TOTAL Consumption",
            "formula": "ME1 + ME2 + AE1 + AE2 + AE3 + AE4"
        }
    }

    if engine_type not in engine_config:
        return None

    config = engine_config[engine_type]

    try:
        start_dt = parse_dt(start)
        end_dt = parse_dt(end)
    except Exception as e:
        print(f"Date parsing error: {e}")
        return None

    def safe_round(value, digits=5):
        try:
            if value is None or math.isnan(value) or math.isinf(value):
                return 0.0
            return round(value, digits)
        except Exception:
            return 0.0

    def get_float(row, key):
        if not key:
            return 0.0
        try:
            val = float(row.get(key, 0) or 0)
            if math.isnan(val) or math.isinf(val):
                return 0.0
            return val
        except Exception:
            return 0.0

    def get_interval_key(dt, raw_ts):
        if interval == "minute":
            return dt.strftime("%Y-%m-%d %H:%M")
        elif interval == "hour":
            return dt.strftime("%Y-%m-%d %H:00")
        elif interval == "daily":
            return dt.strftime("%Y-%m-%d")
        elif interval == "monthly":
            return dt.strftime("%Y-%m")
        elif interval == "yearly":
            return dt.strftime("%Y")
        elif interval == "raw":
            return raw_ts
        else:
            return raw_ts

    # Query all rows for device
    query = f"PartitionKey eq '{deviceid}'"
    entities = list(table_client.query_entities(query))

    # Filter selected time range
    filtered_entities = []
    for entity in entities:
        ts = entity.get("TimestampIST")
        if not ts:
            continue

        try:
            ts_dt = parse_dt(ts)
            if start_dt <= ts_dt <= end_dt:
                filtered_entities.append(entity)
        except Exception:
            continue

    # Sort by timestamp
    filtered_entities.sort(key=lambda x: parse_dt(x.get("TimestampIST")))

    if not filtered_entities:
        return {
            "engine_type": engine_type,
            "name": config["name"],
            "formula": config["formula"],
            "records": [],
            "total_consumption": 0,
            "avg_consumption": 0,
            "record_count": 0,
            "interval": interval,
            "selected_range_difference": 0,
            "first_record_consumption": 0,
            "last_record_consumption": 0
        }

    raw_records = []

    for entity in filtered_entities:
        ts = entity.get("TimestampIST")
        ts_dt = parse_dt(ts)
        interval_key = get_interval_key(ts_dt, ts)

        if engine_type == "TOTAL":
            me1 = get_float(entity, "ME1Volumetotal")
            me2 = get_float(entity, "ME2Volumetotal")
            ae1 = get_float(entity, "AE1Volumetotal")
            ae2 = get_float(entity, "AE2Volumetotal")
            ae3 = get_float(entity, "AE3Volumetotal")
            ae4 = get_float(entity, "AE4Volumetotal")

            total_consumption = me1 + me2 + ae1 + ae2 + ae3 + ae4

            record = {
                "Timestamp": ts,
                "Interval": interval_key,
                "EngineType": engine_type,
                "EngineName": config["name"],
                "ME1": safe_round(me1),
                "ME2": safe_round(me2),
                "AE1": safe_round(ae1),
                "AE2": safe_round(ae2),
                "AE3": safe_round(ae3),
                "AE4": safe_round(ae4),
                "Inlet": 0,
                "Outlet": 0,
                "TotalConsumption": safe_round(total_consumption),
                "InletTemp": 0,
                "OutletTemp": 0,
                "InletDensity": 0,
                "OutletDensity": 0,
                "Consumption": safe_round(total_consumption)
            }

        else:
            inlet_value = get_float(entity, config["inlet_col"])
            outlet_value = get_float(entity, config["outlet_col"]) if config["outlet_col"] else 0.0
            total_consumption = get_float(entity, config["total_col"])

            # BUNKER is direct FT15 reading
            if engine_type == "BUNKER":
                total_consumption = inlet_value

            # fallback if engine total column missing
            elif total_consumption == 0 and (inlet_value != 0 or outlet_value != 0):
                total_consumption = inlet_value - outlet_value

            record = {
                "Timestamp": ts,
                "Interval": interval_key,
                "EngineType": engine_type,
                "EngineName": config["name"],
                "Inlet": safe_round(inlet_value),
                "Outlet": safe_round(outlet_value),
                "TotalConsumption": safe_round(total_consumption),
                "InletTemp": safe_round(get_float(entity, config["inlet_temp_col"]), 2),
                "OutletTemp": safe_round(get_float(entity, config["outlet_temp_col"]), 2) if config["outlet_temp_col"] else 0,
                "InletDensity": safe_round(get_float(entity, config["inlet_density_col"]), 2),
                "OutletDensity": safe_round(get_float(entity, config["outlet_density_col"]), 2) if config["outlet_density_col"] else 0,
                "Consumption": safe_round(total_consumption)
            }

        raw_records.append(record)

    # RAW interval = actual rows
    if interval == "raw":
        records = raw_records
    else:
        # SCADA-style grouped output: keep only LAST record in each interval
        grouped = {}
        for record in raw_records:
            key = record["Interval"]
            grouped[key] = record

        records = list(grouped.values())
        records.sort(key=lambda x: x["Timestamp"])

    total_consumption = round(
        sum(
            r.get("Consumption", 0)
            for r in records
            if isinstance(r.get("Consumption", 0), (int, float))
        ),
        5
    )

    avg_consumption = round(total_consumption / len(records), 5) if records else 0

    first_record_consumption = float(records[0].get("Consumption", 0) or 0) if records else 0
    last_record_consumption = float(records[-1].get("Consumption", 0) or 0) if records else 0
    selected_range_difference = round(last_record_consumption - first_record_consumption, 5)

    return {
        "engine_type": engine_type,
        "name": config["name"],
        "formula": config["formula"],
        "records": records,
        "total_consumption": total_consumption,
        "avg_consumption": avg_consumption,
        "record_count": len(records),
        "interval": interval,
        "selected_range_difference": selected_range_difference,
        "first_record_consumption": round(first_record_consumption, 5),
        "last_record_consumption": round(last_record_consumption, 5)
    }

# ======================
# PDF Download
# ======================

@app.route("/download_pdf")
@login_required
def download_pdf():
    try:
        # Get parameters
        engine_type = request.args.get("type", "PME")
        start = request.args.get("start", "").replace("T", " ")
        end = request.args.get("end", "").replace("T", " ")
        interval = request.args.get("interval", "hour")

        if not start or not end:
            return jsonify({"error": "Start and end time required"}), 400

        # Fetch processed result
        result = fetch_engine_consumption(engine_type, start, end, interval)

        if not result:
            return jsonify({"error": "Invalid engine type"}), 400

        records = sorted(result["records"], key=lambda x: x.get("Timestamp", ""))

        # Add running total and per-row difference
        running_total = 0
        prev_consumption = None

        for record in records:
            current_consumption = float(record.get("Consumption", 0) or 0)

            running_total += current_consumption
            record["RunningTotal"] = round(running_total, 5)

            if prev_consumption is None:
                record["Consumption_Difference"] = 0
            else:
                record["Consumption_Difference"] = round(
                    current_consumption - prev_consumption, 5
                )

            prev_consumption = current_consumption

        # Read selected-range difference from result
        selected_range_difference = result.get("selected_range_difference", 0)
        first_record_consumption = result.get("first_record_consumption", 0)
        last_record_consumption = result.get("last_record_consumption", 0)

        # Create PDF
        buffer = BytesIO()
        c = canvas.Canvas(buffer, pagesize=landscape(letter))
        page_width, page_height = landscape(letter)

        # =====================
        # Summary Page
        # =====================
        c.setFont("Helvetica-Bold", 20)
        c.drawString(50, 550, f"{result['name']} Report")

        c.setFont("Helvetica", 12)
        c.drawString(50, 520, f"From: {start}")
        c.drawString(350, 520, f"To: {end}")
        c.drawString(50, 500, f"Interval: {interval.upper()}")
        c.drawString(350, 500, f"Formula: {result['formula']}")

        c.setFont("Helvetica-Bold", 14)
        c.drawString(50, 450, "Summary Statistics")

        c.setFont("Helvetica", 12)
        c.drawString(50, 420, f"Total Records: {result['record_count']}")
        c.drawString(50, 400, f"Total Consumption: {result['total_consumption']}")
        c.drawString(50, 380, f"Average Consumption: {result['avg_consumption']}")
        c.drawString(50, 360, f"First Record Consumption: {first_record_consumption}")
        c.drawString(50, 340, f"Last Record Consumption: {last_record_consumption}")
        c.drawString(
            50,
            320,
            f"Selected Range Difference (Last - First): {selected_range_difference}"
        )

        if records:
            c.drawString(50, 290, f"First Reading Time: {records[0].get('Timestamp', '')}")
            c.drawString(50, 270, f"Last Reading Time: {records[-1].get('Timestamp', '')}")

        c.line(50, 240, 750, 240)

        # =====================
        # Detailed Data Pages
        # =====================
        c.showPage()

        c.setFont("Helvetica-Bold", 16)
        c.drawString(50, 550, f"{result['name']} - Detailed Readings")

        c.setFont("Helvetica", 10)
        c.drawString(50, 530, f"From: {start}  To: {end}")
        c.drawString(350, 530, f"Interval: {interval.upper()}")

        if not records:
            c.setFont("Helvetica", 12)
            c.drawString(50, 450, "No data found for selected date range")
        else:
            def draw_headers(y):
                c.setFont("Helvetica-Bold", 6)
                if engine_type == "BUNKER":
                    headers = [
                        ("Time", 50),
                        ("VolumeTotal (m³)", 160),
                        ("MassTotal (T)", 320)
                    ]


                elif engine_type == "TOTAL":
                    headers = [
                        ("Time", 50),
                        ("ME1(m³)", 110),
                        ("ME2(m³)", 155),
                        ("AE1(m³)", 200),
                        ("AE2(m³)", 245),
                        ("AE3(m³)", 290),
                        ("AE4(m³)", 335),
                        ("Total(m³)", 385)
                    ]
                else:
                    headers = [
                        ("Time", 50),
                        ("InletVol(m³)", 110),
                        ("OutletVol(m³)", 180),
                        ("Total Consumption(m³)", 260)
                    ]

                for text, x in headers:
                    c.drawString(x, y, text)

            def draw_record(record, y):
                c.setFont("Helvetica", 5.5)

                timestamp = str(record.get("Timestamp", ""))
                short_time = timestamp[5:16] if len(timestamp) >= 16 else timestamp
                c.drawString(50, y, short_time)
                if engine_type == "BUNKER":
                    volume = float(record.get("TotalConsumption", 0) or 0)
                    # Density (kg/m³) → convert to TONNES
                    density = float(record.get("InletDensity", 0) or 0)
                    mass = (volume * density) / 1000 if density else 0

                    c.drawString(160, y, f"{volume:.2f}")
                    c.drawString(320, y, f"{mass:.2f}")


                elif engine_type == "TOTAL":
                    c.drawString(110, y, f"{record.get('ME1', 0):.2f}")
                    c.drawString(155, y, f"{record.get('ME2', 0):.2f}")
                    c.drawString(200, y, f"{record.get('AE1', 0):.2f}")
                    c.drawString(245, y, f"{record.get('AE2', 0):.2f}")
                    c.drawString(290, y, f"{record.get('AE3', 0):.2f}")
                    c.drawString(335, y, f"{record.get('AE4', 0):.2f}")
                    c.drawString(385, y, f"{record.get('TotalConsumption', 0):.2f}")
                else:
                    c.drawString(110, y, f"{record.get('Inlet', 0):.2f}")
                    c.drawString(180, y, f"{record.get('Outlet', 0):.2f}")
                    c.drawString(260, y, f"{record.get('TotalConsumption', 0):.2f}")

            records_per_page = 28
            total_pages = ceil(len(records) / records_per_page)

            for page in range(total_pages):
                if page > 0:
                    c.showPage()
                    c.setFont("Helvetica-Bold", 16)
                    c.drawString(50, 550, f"{result['name']} - Detailed Readings")
                    c.setFont("Helvetica", 10)
                    c.drawString(50, 530, f"From: {start}  To: {end}")
                    c.drawString(350, 530, f"Interval: {interval.upper()}")

                y = 500

                c.setFont("Helvetica-Bold", 8)
                c.drawString(650, 530, f"Page {page + 1}/{total_pages}")

                draw_headers(y)
                y -= 15

                page_records = records[page * records_per_page:(page + 1) * records_per_page]

                for record in page_records:
                    draw_record(record, y)
                    y -= 12

                # Show selected range difference at end of last page
                if page == total_pages - 1:
                    y -= 10
                    c.line(50, y, 750, y)
                    y -= 18
                    c.setFont("Helvetica-Bold", 10)
                    c.drawString(
                        50,
                        y,
                        f"Selected Range Difference (Last Record - First Record): {selected_range_difference} m³"
                    )
                    y -= 14
                    c.setFont("Helvetica", 9)
                    c.drawString(
                        50,
                        y,
                        f"First Record Consumption: {first_record_consumption} m³"
                    )
                    y -= 12
                    c.drawString(
                        50,
                        y,
                        f"Last Record Consumption: {last_record_consumption} m³"
                    )

        c.save()
        buffer.seek(0)

        filename = (
            f"{engine_type}_{interval}_"
            f"{start.replace(' ', '_').replace(':', '-')}_to_"
            f"{end.replace(' ', '_').replace(':', '-')}.pdf"
        )

        return send_file(
            buffer,
            mimetype="application/pdf",
            download_name=filename,
            as_attachment=True
        )

    except Exception as e:
        print(f"PDF download error: {e}")
        return jsonify({"error": str(e)}), 500

# ==================
# csv download
# ==================

@app.route("/download_csv")
@login_required
def download_csv():
    """Download CSV report for selected engine"""
    try:
        # Get parameters
        engine_type = request.args.get("type", "PME")
        start = request.args.get("start", "").replace("T", " ")
        end = request.args.get("end", "").replace("T", " ")
        interval = request.args.get("interval", "hour")
        
        if not start or not end:
            return jsonify({"error": "Start and end time required"}), 400
        
        print(f"CSV Request - Engine: {engine_type}, Interval: {interval}, Start: {start}, End: {end}")
        
        # Fetch data based on engine type
        result = fetch_engine_consumption(engine_type, start, end, interval)
        
        if not result:
            return jsonify({"error": "Invalid engine type"}), 400
        
        # Create DataFrame from records
        if result['records']:
            df = pd.DataFrame(result['records'])
            
            # Reorder columns based on engine type and interval
            base_columns = ['Timestamp', 'Interval', 'EngineType', 'EngineName']
            
            if engine_type == 'consumpution':
                value_columns = ['FT9_VolumeTotal', 'Consumption', 'FT9_MassFlow', 'FT9_Temp', 'FT9_Density']
            else:
                config = {
                    'PME': {'inlet': 'FT1', 'outlet': 'FT2'},
                    'SME': {'inlet': 'FT3', 'outlet': 'FT4'},
                    'PAE': {'inlet': 'FT5', 'outlet': 'FT6'},
                    'SAE': {'inlet': 'FT7', 'outlet': 'FT8'}
                }
                cfg = config[engine_type]
                value_columns = [
                    f"{cfg['inlet']}_VolumeTotal", f"{cfg['outlet']}_VolumeTotal", 'Consumption',
                    f"{cfg['inlet']}_MassFlow", f"{cfg['outlet']}_MassFlow",
                    f"{cfg['inlet']}_Temp", f"{cfg['outlet']}_Temp",
                    f"{cfg['inlet']}_Density", f"{cfg['outlet']}_Density"
                ]
            
            if interval != 'raw':
                base_columns.append('RecordCount')
            
            column_order = base_columns + value_columns
            column_order = [col for col in column_order if col in df.columns]
            df = df[column_order]
            
            # Add summary row
            summary = {
                'EngineType': 'SUMMARY',
                'EngineName': result['name'],
                'Consumption': result['total_consumption'],
                'RecordCount': result['record_count']
            }
            
            # Fill missing columns in summary
            for col in column_order:
                if col not in summary and col not in ['Timestamp', 'Interval']:
                    summary[col] = ''
            
            df = pd.concat([df, pd.DataFrame([summary])], ignore_index=True)
        else:
            df = pd.DataFrame([{
                'Timestamp': 'No data found',
                'EngineType': engine_type,
                'EngineName': result['name'] if result else engine_type,
                'Message': f'No records found for {engine_type} from {start} to {end}'
            }])
        
        # Create CSV
        output = BytesIO()
        df.to_csv(output, index=False)
        output.seek(0)
        
        # Generate filename
        filename = f"{engine_type}_{interval}_{start.replace(' ', '_')}_to_{end.replace(' ', '_')}.csv"
        
        return send_file(
            output,
            mimetype="text/csv",
            download_name=filename,
            as_attachment=True
        )
        
    except Exception as e:
        print(f"CSV download error: {e}")
        return jsonify({"error": str(e)}), 500



# =========================
# RUN APP
# =========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)









# @app.route("/download_pdf")
# @login_required
# def download_pdf():
#     try:
#         from reportlab.lib.pagesizes import letter, landscape
#         from reportlab.pdfgen import canvas
#         from math import ceil

#         # Get parameters
#         engine_type = request.args.get("type", "PME")
#         start = request.args.get("start", "").replace("T", " ")
#         end = request.args.get("end", "").replace("T", " ")
#         interval = request.args.get("interval", "hour")

#         if not start or not end:
#             return jsonify({"error": "Start and end time required"}), 400

#         # Fetch updated report data
#         result = fetch_engine_consumption(engine_type, start, end, interval)

#         if not result:
#             return jsonify({"error": "Invalid engine type"}), 400

#         records = sorted(result["records"], key=lambda x: x.get("Timestamp", ""))

#         # Add running total and difference
#         running_total = 0
#         prev_consumption = None

#         for record in records:
#             current_consumption = float(record.get("Consumption", 0) or 0)

#             running_total += current_consumption
#             record["RunningTotal"] = round(running_total, 5)

#             if prev_consumption is None:
#                 record["Consumption_Difference"] = 0
#             else:
#                 record["Consumption_Difference"] = round(
#                     current_consumption - prev_consumption, 5
#                 )

#             prev_consumption = current_consumption

#         # Create PDF
#         buffer = BytesIO()
#         c = canvas.Canvas(buffer, pagesize=landscape(letter))

#         # =====================
#         # Title / Summary Page
#         # =====================
#         c.setFont("Helvetica-Bold", 20)
#         c.drawString(50, 550, f"{result['name']} Report")

#         c.setFont("Helvetica", 12)
#         c.drawString(50, 520, f"From: {start}")
#         c.drawString(350, 520, f"To: {end}")
#         c.drawString(50, 500, f"Interval: {interval.upper()}")
#         c.drawString(350, 500, f"Formula: {result['formula']}")

#         c.setFont("Helvetica-Bold", 14)
#         c.drawString(50, 450, "Summary Statistics")

#         c.setFont("Helvetica", 12)
#         c.drawString(50, 420, f"Total Records: {result['record_count']}")
#         c.drawString(50, 400, f"Total Consumption: {result['total_consumption']}")
#         c.drawString(50, 380, f"Average Consumption: {result['avg_consumption']}")

#         if records:
#             c.drawString(50, 350, f"First Reading Time: {records[0].get('Timestamp', '')}")
#             c.drawString(50, 330, f"Last Reading Time: {records[-1].get('Timestamp', '')}")

#         c.line(50, 300, 750, 300)

#         # =====================
#         # Detailed Data Page
#         # =====================
#         c.showPage()

#         c.setFont("Helvetica-Bold", 16)
#         c.drawString(50, 550, f"{result['name']} - Detailed Readings")

#         c.setFont("Helvetica", 10)
#         c.drawString(50, 530, f"From: {start}  To: {end}")
#         c.drawString(350, 530, f"Interval: {interval.upper()}")

#         if not records:
#             c.setFont("Helvetica", 12)
#             c.drawString(50, 450, "No data found for selected date range")

#         else:
#             def draw_headers(y):
#                 c.setFont("Helvetica-Bold", 6)

#                 if engine_type == "TOTAL":
#                     headers = [
#                         ("Time", 50),
#                         ("ME1(m³)", 110),
#                         ("ME2(m³)", 155),
#                         ("AE1(m³)", 200),
#                         ("AE2(m³)", 245),
#                         ("AE3(m³)", 290),
#                         ("AE4(m³)", 335),
#                         ("Total(m³)", 385)
#                     ]
#                 else:
#                     headers = [
#                         ("Time", 50),
#                         ("InletVol(m³)", 110),
#                         ("OutletVol(m³)", 165),
#                         ("Total Consumption(m³)", 220)
#                     ]

#                 for text, x in headers:
#                     c.drawString(x, y, text)

#             def draw_record(record, y):
#                 c.setFont("Helvetica", 5.5)

#                 timestamp = str(record.get("Timestamp", ""))
#                 short_time = timestamp[5:16] if len(timestamp) >= 16 else timestamp

#                 c.drawString(50, y, short_time)

#                 if engine_type == "TOTAL":
#                     c.drawString(110, y, f"{record.get('ME1', 0):.2f}")
#                     c.drawString(155, y, f"{record.get('ME2', 0):.2f}")
#                     c.drawString(200, y, f"{record.get('AE1', 0):.2f}")
#                     c.drawString(245, y, f"{record.get('AE2', 0):.2f}")
#                     c.drawString(290, y, f"{record.get('AE3', 0):.2f}")
#                     c.drawString(335, y, f"{record.get('AE4', 0):.2f}")
#                     c.drawString(385, y, f"{record.get('TotalConsumption', 0):.2f}")

#                 else:
#                     c.drawString(110, y, f"{record.get('Inlet', 0):.2f}")
#                     c.drawString(165, y, f"{record.get('Outlet', 0):.2f}")
#                     c.drawString(220, y, f"{record.get('TotalConsumption', 0):.2f}")
#                     # c.drawString(395, y, f"{record.get('InletTemp', 0):.2f}")
#                     # c.drawString(450, y, f"{record.get('OutletTemp', 0):.2f}")
#                     # c.drawString(510, y, f"{record.get('InletDensity', 0):.2f}")
#                     # c.drawString(580, y, f"{record.get('OutletDensity', 0):.2f}")

#             records_per_page = 28
#             total_pages = ceil(len(records) / records_per_page)

#             for page in range(total_pages):
#                 if page > 0:
#                     c.showPage()
#                     c.setFont("Helvetica-Bold", 16)
#                     c.drawString(50, 550, f"{result['name']} - Detailed Readings")

#                     c.setFont("Helvetica", 10)
#                     c.drawString(50, 530, f"From: {start}  To: {end}")
#                     c.drawString(350, 530, f"Interval: {interval.upper()}")

#                 y = 500

#                 c.setFont("Helvetica-Bold", 8)
#                 c.drawString(650, 530, f"Page {page + 1}/{total_pages}")

#                 draw_headers(y)
#                 y -= 15

#                 page_records = records[
#                     page * records_per_page:(page + 1) * records_per_page
#                 ]

#                 for record in page_records:
#                     draw_record(record, y)
#                     y -= 12

#         c.save()
#         buffer.seek(0)

#         filename = (
#             f"{engine_type}_{interval}_"
#             f"{start.replace(' ', '_').replace(':', '-')}_to_"
#             f"{end.replace(' ', '_').replace(':', '-')}.pdf"
#         )

#         return send_file(
#             buffer,
#             mimetype="application/pdf",
#             download_name=filename,
#             as_attachment=True
#         )

#     except Exception as e:
#         print(f"PDF download error: {e}")
#         return jsonify({"error": str(e)}), 500


# @app.route("/download_pdf")
# @login_required
# def download_pdf():
#     """Download PDF report for selected engine"""
#     try:
#         from reportlab.lib.pagesizes import letter, landscape
#         from reportlab.pdfgen import canvas
#         from reportlab.lib.utils import simpleSplit
#         from math import ceil
        
#         # Get parameters
#         engine_type = request.args.get("type", "PME")
#         start = request.args.get("start", "").replace("T", " ")
#         end = request.args.get("end", "").replace("T", " ")
#         interval = request.args.get("interval", "hour")
        
#         if not start or not end:
#             return jsonify({"error": "Start and end time required"}), 400
        
#         # Fetch data
#         result = fetch_engine_consumption(engine_type, start, end, interval)
        
#         if not result:
#             return jsonify({"error": "Invalid engine type"}), 400
        
#         # Create PDF
#         buffer = BytesIO()
#         c = canvas.Canvas(buffer, pagesize=landscape(letter))
        
#         # Title Page
#         c.setFont("Helvetica-Bold", 20)
#         c.drawString(50, 550, f"{result['name']} Report")
        
#         c.setFont("Helvetica", 12)
#         c.drawString(50, 520, f"From: {start}")
#         c.drawString(350, 520, f"To: {end}")
#         c.drawString(50, 500, f"Interval: {interval.upper()}")
#         c.drawString(350, 500, f"Formula: {result['formula']}")
        
#         # Summary Statistics
#         c.setFont("Helvetica-Bold", 14)
#         c.drawString(50, 450, "Summary Statistics")
        
#         c.setFont("Helvetica", 12)
#         c.drawString(50, 420, f"Total Records: {result['record_count']}")
#         c.drawString(50, 400, f"Total Consumption: {result['total_consumption']} L")
#         c.drawString(50, 380, f"Average Consumption: {result['avg_consumption']} L")
        
#         # Add line
#         c.line(50, 350, 750, 350)
        
#         # New page for detailed data
#         c.showPage()
        
#         # Detailed Data Page
#         c.setFont("Helvetica-Bold", 16)
#         c.drawString(50, 550, f"{result['name']} - Detailed Readings")
#         c.setFont("Helvetica", 10)
#         c.drawString(50, 530, f"From: {start}  To: {end}")
#         c.drawString(350, 530, f"Interval: {interval.upper()}")
        
#         if not result['records']:
#             c.setFont("Helvetica", 12)
#             c.drawString(50, 450, "No data found for selected date range")
#         else:
#             # Table headers
#             y = 500
#             c.setFont("Helvetica-Bold", 8)
            
#             if engine_type == 'consumpution':
#                 c.drawString(50, y, "Timestamp")
#                 c.drawString(180, y, "FT9 Volume")
#                 c.drawString(260, y, "Consumption")
#                 c.drawString(340, y, "Mass Flow")
#                 c.drawString(420, y, "Temp")
#                 c.drawString(500, y, "Density")
#             else:
#                 c.drawString(50, y, "Timestamp")
#                 c.drawString(170, y, "Inlet Vol")
#                 c.drawString(240, y, "Outlet Vol")
#                 c.drawString(310, y, "Consumption")
#                 c.drawString(380, y, "Inlet Mass")
#                 c.drawString(450, y, "Outlet Mass")
#                 c.drawString(520, y, "Inlet Temp")
#                 c.drawString(590, y, "Outlet Temp")
            
#             y -= 15
#             c.setFont("Helvetica", 7)
            
#             # Calculate pages needed
#             records_per_page = 30
#             total_pages = ceil(len(result['records']) / records_per_page)
            
#             for page in range(total_pages):
#                 if page > 0:
#                     c.showPage()
#                     y = 550
#                     c.setFont("Helvetica-Bold", 8)
#                     c.drawString(50, y, f"{result['name']} - Page {page+1}/{total_pages}")
#                     y -= 20
#                     c.setFont("Helvetica-Bold", 8)
                    
#                     if engine_type == 'consumpution':
#                         c.drawString(50, y, "Timestamp")
#                         c.drawString(180, y, "FT9 Volume")
#                         c.drawString(260, y, "Consumption")
#                         c.drawString(340, y, "Mass Flow")
#                         c.drawString(420, y, "Temp")
#                         c.drawString(500, y, "Density")
#                     else:
#                         c.drawString(50, y, "Timestamp")
#                         c.drawString(170, y, "Inlet Vol")
#                         c.drawString(240, y, "Outlet Vol")
#                         c.drawString(310, y, "Consumption")
#                         c.drawString(380, y, "Inlet Mass")
#                         c.drawString(450, y, "Outlet Mass")
#                         c.drawString(520, y, "Inlet Temp")
#                         c.drawString(590, y, "Outlet Temp")
                    
#                     y -= 15
#                     c.setFont("Helvetica", 7)
                
#                 page_records = result['records'][page * records_per_page:(page + 1) * records_per_page]
                
#                 for record in page_records:
#                     if y < 50:
#                         break
                    
#                     if engine_type == 'consumpution':
#                         c.drawString(50, y, str(record.get('Timestamp', ''))[:16])
#                         c.drawString(180, y, f"{record.get('FT9_VolumeTotal', 0):.2f}")
#                         c.drawString(260, y, f"{record.get('Consumption', 0):.2f}")
#                         c.drawString(340, y, f"{record.get('FT9_MassFlow', 0):.2f}")
#                         c.drawString(420, y, f"{record.get('FT9_Temp', 0):.1f}")
#                         c.drawString(500, y, f"{record.get('FT9_Density', 0):.2f}")
#                     else:
#                         c.drawString(50, y, str(record.get('Timestamp', ''))[:16])
                        
#                         if engine_type == 'PME':
#                             c.drawString(170, y, f"{record.get('FT1_VolumeTotal', 0):.2f}")
#                             c.drawString(240, y, f"{record.get('FT2_VolumeTotal', 0):.2f}")
#                             c.drawString(310, y, f"{record.get('Consumption', 0):.2f}")
#                             c.drawString(380, y, f"{record.get('FT1_MassFlow', 0):.2f}")
#                             c.drawString(450, y, f"{record.get('FT2_MassFlow', 0):.2f}")
#                             c.drawString(520, y, f"{record.get('FT1_Temp', 0):.1f}")
#                             c.drawString(590, y, f"{record.get('FT2_Temp', 0):.1f}")
#                         elif engine_type == 'SME':
#                             c.drawString(170, y, f"{record.get('FT3_VolumeTotal', 0):.2f}")
#                             c.drawString(240, y, f"{record.get('FT4_VolumeTotal', 0):.2f}")
#                             c.drawString(310, y, f"{record.get('Consumption', 0):.2f}")
#                             c.drawString(380, y, f"{record.get('FT3_MassFlow', 0):.2f}")
#                             c.drawString(450, y, f"{record.get('FT4_MassFlow', 0):.2f}")
#                             c.drawString(520, y, f"{record.get('FT3_Temp', 0):.1f}")
#                             c.drawString(590, y, f"{record.get('FT4_Temp', 0):.1f}")
#                         elif engine_type == 'PAE':
#                             c.drawString(170, y, f"{record.get('FT5_VolumeTotal', 0):.2f}")
#                             c.drawString(240, y, f"{record.get('FT6_VolumeTotal', 0):.2f}")
#                             c.drawString(310, y, f"{record.get('Consumption', 0):.2f}")
#                             c.drawString(380, y, f"{record.get('FT5_MassFlow', 0):.2f}")
#                             c.drawString(450, y, f"{record.get('FT6_MassFlow', 0):.2f}")
#                             c.drawString(520, y, f"{record.get('FT5_Temp', 0):.1f}")
#                             c.drawString(590, y, f"{record.get('FT6_Temp', 0):.1f}")
#                         elif engine_type == 'SAE':
#                             c.drawString(170, y, f"{record.get('FT7_VolumeTotal', 0):.2f}")
#                             c.drawString(240, y, f"{record.get('FT8_VolumeTotal', 0):.2f}")
#                             c.drawString(310, y, f"{record.get('Consumption', 0):.2f}")
#                             c.drawString(380, y, f"{record.get('FT7_MassFlow', 0):.2f}")
#                             c.drawString(450, y, f"{record.get('FT8_MassFlow', 0):.2f}")
#                             c.drawString(520, y, f"{record.get('FT7_Temp', 0):.1f}")
#                             c.drawString(590, y, f"{record.get('FT8_Temp', 0):.1f}")
                    
#                     y -= 12
        
#         c.save()
#         buffer.seek(0)
        
#         # Generate filename
#         filename = f"{engine_type}_{interval}_{start.replace(' ', '_')}_to_{end.replace(' ', '_')}.pdf"
        
#         return send_file(
#             buffer,
#             mimetype="application/pdf",
#             download_name=filename,
#             as_attachment=True
#         )
        
#     except Exception as e:
#         print(f"PDF download error: {e}")
#         return jsonify({"error": str(e)}), 500






















