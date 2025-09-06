import json
import time
import os
from pymavlink import mavutil

JSON_UPDATE_RATE = 10
DISCONNECT_TIMEOUT = 1
UDP_ENDPOINT = 'udp:0.0.0.0:14550'
DRONE_ID = 1
DRONE_TYPE = 'DRONE'

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
JSON_PATH = os.path.join(SCRIPT_DIR, "drone_state.json")


def init_drone_state(type_val=None, id_val=None):
    return {
        "type": type_val,
        "id": id_val,
        "x": None,
        "y": None,
        "z": None,
        "pitch": None,
        "roll": None,
        "yaw": None,
        "timestamp": None,
        "armable": None,
        "armed": None,
        "battery_voltage": None,
        "battery_percentage": None,
        "flight_mode": None,
        "rssi": None,
        "messages": []
    }


# Function to create MAVLink connection
def create_master():
    master = mavutil.mavlink_connection(UDP_ENDPOINT)
    print("Waiting for heartbeat...")
    master.wait_heartbeat()
    print(f"Heartbeat from system {master.target_system} component {master.target_component}")
    master.mav.request_data_stream_send(master.target_system, master.target_component,
                                        mavutil.mavlink.MAV_DATA_STREAM_ALL, JSON_UPDATE_RATE, 1)
    return master

# Initial connection
master = create_master()
drone_state = init_drone_state(DRONE_TYPE, DRONE_ID)
last_json_write = 0
last_heartbeat = time.time()
connected = True

while True:
    now = time.time()
    msg = master.recv_match(blocking=False)

    if now - last_heartbeat > DISCONNECT_TIMEOUT:
        if connected:
            print("Drone disconnected!")
            connected = False
            drone_state = init_drone_state()
            with open(JSON_PATH, "w") as f:
                json.dump(drone_state, f, indent=4)

        try:
            master.close()
        except Exception:
            pass

        while not connected:
            try:
                master = create_master()
                connected = True
                last_heartbeat = time.time()
                print("Drone reconnected!")
                drone_state["type"] = DRONE_TYPE
                drone_state["id"] = DRONE_ID
            except Exception as e:
                print("Reconnect failed, retrying in 2s...")
                time.sleep(2)

    if msg and connected:
        mtype = msg.get_type()

        if mtype == "HEARTBEAT":
            last_heartbeat = now
            base_mode = msg.base_mode
            drone_state["armed"] = bool(base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
            drone_state["armable"] = True
            drone_state["flight_mode"] = master.flightmode
            drone_state["type"] = DRONE_TYPE
            drone_state["id"] = DRONE_ID

        elif mtype == "LOCAL_POSITION_NED":
            drone_state["x"] = msg.x
            drone_state["y"] = msg.y
            drone_state["z"] = msg.z

        elif mtype == "ATTITUDE":
            drone_state["pitch"] = msg.pitch
            drone_state["roll"] = msg.roll
            drone_state["yaw"] = msg.yaw

        elif mtype == "BATTERY_STATUS":
            drone_state["battery_voltage"] = msg.voltages[0]/1000.0 if msg.voltages[0]!=65535 else None
            drone_state["battery_percentage"] = msg.battery_remaining if msg.battery_remaining != -1 else None

        elif mtype == "RADIO_STATUS":
            drone_state["rssi"] = msg.rssi

        elif mtype == "STATUSTEXT":
            log_entry = {"severity": msg.severity,
                         "text": msg.text,
                         "timestamp": int(now*1000)}
            drone_state["messages"].append(log_entry)
            print(f"[{msg.severity}] {msg.text}")

    drone_state["timestamp"] = int(now*1000)

    # Write JSON at configured interval
    if now - last_json_write >= 1 / JSON_UPDATE_RATE:
        with open(JSON_PATH, "w") as f:
            json.dump(drone_state, f, indent=4)
        last_json_write = now
