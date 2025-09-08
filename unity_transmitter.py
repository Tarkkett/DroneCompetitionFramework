import sys
import socket
import time
import json
import cv2
import requests
import argparse
import os
from pupil_apriltags import Detector
from pymavlink import mavutil
import random

def send_log(sock, text, severity=1):
    log_msg = {
        "type": "LOG",
        "severity": severity,
        "text": str(text),
        "timestamp": int(time.time() * 1000)
    }
    try:
        sock.sendall((json.dumps(log_msg) + "\n").encode("utf-8"))
    except Exception:
        pass

    print(f"[LOG-{severity}] {text}")


def init_drone_state(type_val="DRONE", id_val=1):
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


def create_master(sock, endpoint="udp:0.0.0.0:14550", update_rate=10):
    send_log(sock, "Waiting for heartbeat...", severity=2)
    time.sleep(1)
    master = mavutil.mavlink_connection(endpoint)
    try:
        master.wait_heartbeat()
        # if master.target_system == 0:
        #     send_log(sock, "No real drone detected (system 0). Sending dummy data.", severity=1)
        #     return None  # Dummy data
        send_log(sock, f"Heartbeat from system {master.target_system} component {master.target_component}", severity=3)
        master.mav.request_data_stream_send(
            master.target_system,
            master.target_component,
            mavutil.mavlink.MAV_DATA_STREAM_ALL,
            update_rate,
            1
        )
    except Exception:
        send_log(sock, "No heartbeat detected. Will send dummy drone data.", severity=1)
        return None
    return master



def update_drone_state(sock, master, drone_state):

    if master is None:
        # summy data
        now = time.time()
        drone_state.update({
            "x": 3,
            "y": 3,
            "z": 5,
            "pitch": random.uniform(-0.1, 0.1),
            "roll": random.uniform(-0.1, 0.1),
            "yaw": random.uniform(-3.14, 3.14),
            "armed": False,
            "armable": False,
            "battery_voltage": 12.0,
            "battery_percentage": random.randint(50, 100),
            "flight_mode": "SIMULATION",
            "rssi": 100,
            "messages": [],
            "timestamp": int(now * 1000)
        })
        return

    msg = master.recv_match(blocking=False)
    if not msg:
        return

    mtype = msg.get_type()
    now = time.time()

    if mtype == "HEARTBEAT":
        base_mode = msg.base_mode
        drone_state["armed"] = bool(base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
        drone_state["armable"] = True
        drone_state["flight_mode"] = master.flightmode

    elif mtype == "LOCAL_POSITION_NED":
        drone_state["x"] = msg.x
        drone_state["y"] = msg.y
        drone_state["z"] = msg.z

    elif mtype == "ATTITUDE":
        drone_state["pitch"] = msg.pitch
        drone_state["roll"] = msg.roll
        drone_state["yaw"] = msg.yaw

    elif mtype == "BATTERY_STATUS":
        drone_state["battery_voltage"] = msg.voltages[0] / 1000.0 if msg.voltages[0] != 65535 else None
        drone_state["battery_percentage"] = msg.battery_remaining if msg.battery_remaining != -1 else None

    elif mtype == "RADIO_STATUS":
        drone_state["rssi"] = msg.rssi

    elif mtype == "STATUSTEXT":
        log_entry = {"severity": msg.severity,
                     "text": msg.text,
                     "timestamp": int(now * 1000)}
        drone_state["messages"].append(log_entry)

    drone_state["timestamp"] = int(now * 1000)


def wait_for_unity(unity_host, unity_port, retry_delay=5):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    while True:
        try:
            sock.connect((unity_host, unity_port))
            send_log(sock, "Connected to Unity", severity=3)
            return sock
        except (ConnectionRefusedError, OSError) as e:
            send_log(sock, f"Unity not available yet: {e}. Retrying in {retry_delay} seconds...", severity=1)
            time.sleep(retry_delay)
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)


def wait_for_camera(sock, retry_delay=5):
    while True:
        cap = cv2.VideoCapture(0)
        if cap.isOpened():
            send_log(sock, "Camera opened successfully", severity=3)
            return cap
        else:
            send_log(sock, f"Camera not available. Retrying in {retry_delay} seconds...", severity=1)
            cap.release()
            time.sleep(retry_delay)


def decode_tag(sock, tag_id, match_key, server_url):
    try:
        verify_resp = requests.get(f"{server_url}/verify_match_key", params={"match_key": match_key}, timeout=2)
        if verify_resp.status_code == 404:
            send_log(sock, f"Invalid match_key: {match_key}", severity=1)  # Error
            # raise RuntimeError(f"Invalid match_key: {match_key}")
        elif verify_resp.status_code != 200:
            send_log(sock, f"Error verifying match_key: {verify_resp.status_code}", severity=1)  # Error
            # raise RuntimeError(f"Error verifying match_key: {verify_resp.status_code}")
    except requests.exceptions.RequestException as e:
        send_log(sock, f"Could not reach the decoder server!", severity=1)  # Error
        # raise RuntimeError(f"Match key verification failed: {e}")

    try:
        r = requests.get(f"{server_url}/decode", params={"tag_id": str(tag_id), "match_key": match_key}, timeout=2)
        r.raise_for_status()
        data = r.json()
        if "points" in data:
            send_log(sock, f"Tag {tag_id} decoded successfully: {data['points']} points", severity=3)  # Success
            return data["points"]
        else:
            send_log(sock, f"Decoder error for tag {tag_id}: {data.get('error', 'Unknown error')}", severity=2)  # Warning
            # raise RuntimeError(f"Decoder error for tag {tag_id}: {data.get('error', 'Unknown error')}")
    except requests.exceptions.RequestException as e:
        send_log(sock, f"Decoder server not reachable: {e}", severity=2)  # Warning
        # raise RuntimeError(f"Decoder server not reachable: {e}")



def main(unity_host, unity_port, match_key, server_url):
    at_detector = Detector(families="tag36h11")
    
    sock = wait_for_unity(unity_host, unity_port)
    cap = wait_for_camera(sock)
    decode_tag(sock, 1, match_key, server_url)

    master = create_master(sock)
    drone_state = init_drone_state()

    try:
        while True:
            update_drone_state(sock, master, drone_state)
            if drone_state["timestamp"]:
                sock.sendall((json.dumps(drone_state) + "\n").encode("utf-8"))

            ret, frame = cap.read()
            if not ret:
                send_log(sock, "Camera read failed. Reopening camera...", severity=2)
                cap.release()
                cap = wait_for_camera(sock)
                continue

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            detections = at_detector.detect(gray)

            for det in detections:
                tag_id = det.tag_id
                cx, cy = det.center
                h, w = gray.shape

                nx, ny = cx / w, cy / h
                rel_x = (nx - 0.5) * 2.0
                rel_y = (ny - 0.5) * 2.0

                tag_x = (drone_state["x"] if drone_state["x"] else 0.0) + rel_x
                tag_y = (drone_state["y"] if drone_state["y"] else 0.0) + rel_y
                tag_z = 0.0

                try:
                    points = decode_tag(sock, tag_id, match_key, server_url)
                except RuntimeError as e:
                    print(e)
                    points = 0

                tag_msg = {
                    "type": "TAG",
                    "id": tag_id,
                    "x": float(tag_x),
                    "y": float(tag_y),
                    "z": float(tag_z),
                    "points": points
                }
                sock.sendall((json.dumps(tag_msg) + "\n").encode("utf-8"))

            time.sleep(0.5)

    except KeyboardInterrupt:
        print("Stopping...")
    finally:
        cap.release()
        sock.close()
        try:
            if master:
                master.close()
        except Exception:
            pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Unity AprilTag + Drone Telemetry sender")
    parser.add_argument("--host", type=str, required=True, help="Unity server IP")
    parser.add_argument("--port", type=int, required=True, help="Unity server port")
    parser.add_argument("--match", type=str, required=True, help="Match key for server decoding")
    parser.add_argument("--server", type=str, required=True, help="Backend server URL (e.g., http://127.0.0.1:5000)")

    args = parser.parse_args()
    main(args.host, args.port, args.match, args.server)
