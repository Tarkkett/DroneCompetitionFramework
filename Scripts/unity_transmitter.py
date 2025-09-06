import sys
import socket
import time
import json
import cv2
import requests
import argparse
from pupil_apriltags import Detector

def decode_tag(tag_id, match_key, server_url):
    try:
        r = requests.get(f"{server_url}/decode", params={"tag_id": str(tag_id), "match_key": match_key}, timeout=2)
        r.raise_for_status()
        data = r.json()
        if "points" in data:
            print(f"Tag {tag_id} = {data['points']} points")
            return data["points"]
        else:
            raise RuntimeError(f"Decoder error: {data.get('error', 'Unknown error')}")
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Decoder server not reachable: {e}")


def wait_for_unity(unity_host, unity_port, retry_delay=2):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    while True:
        try:
            print(f"Trying to connect to Unity at {unity_host}:{unity_port} ...")
            sock.connect((unity_host, unity_port))
            print("Connected to Unity")
            return sock
        except (ConnectionRefusedError, OSError) as e:
            print(f"Unity not available yet: {e}. Retrying in {retry_delay} seconds...")
            time.sleep(retry_delay)
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)


def wait_for_camera(retry_delay=2):
    while True:
        cap = cv2.VideoCapture(0)
        if cap.isOpened():
            print("Camera opened successfully")
            return cap
        else:
            print(f"Camera not available. Retrying in {retry_delay} seconds...")
            cap.release()
            time.sleep(retry_delay)


def main(unity_host, unity_port, match_key, server_url):
    at_detector = Detector(families="tag36h11")

    cap = wait_for_camera()
    sock = wait_for_unity(unity_host, unity_port)

    try:
        dummy_id = 1
        while True:
            t = time.time()
            drone_x = 1.0 + 0.5 * (t % 5)
            drone_y = 2.0 + 0.5 * (t % 3)
            drone_z = -2.0

            drone_msg = {
                "type": "DRONE",
                "id": dummy_id,
                "x": drone_x,
                "y": drone_y,
                "z": drone_z,
                "angle": 0.0,
                "timestamp": int(t * 1000)
            }
            sock.sendall((json.dumps(drone_msg) + "\n").encode("utf-8"))

            ret, frame = cap.read()
            if not ret:
                print("Camera read failed. Reopening camera...")
                cap.release()
                cap = wait_for_camera()
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

                tag_x = drone_x + rel_x
                tag_y = drone_y + rel_y
                tag_z = 0.0  # ground level

                try:
                    points = decode_tag(tag_id, match_key, server_url)
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

            time.sleep(0.05)

    except KeyboardInterrupt:
        print("Stopping...")
    finally:
        cap.release()
        sock.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Unity AprilTag sender")
    parser.add_argument("--host", type=str, required=True, help="Unity server IP")
    parser.add_argument("--port", type=int, required=True, help="Unity server port")
    parser.add_argument("--match", type=str, required=True, help="Match key for server decoding")
    parser.add_argument("--server", type=str, required=True, help="Backend server URL (e.g., http://127.0.0.1:5000)")

    args = parser.parse_args()

    main(args.host, args.port, args.match, args.server)
