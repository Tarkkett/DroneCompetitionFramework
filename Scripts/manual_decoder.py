import requests
import sys

SERVER_URL = "http://127.0.0.1:5000"

def decode(tag_id, match_key):
    try:
        r = requests.get(f"{SERVER_URL}/decode", params={"tag_id": str(tag_id), "match_key": match_key})
        data = r.json()
        if "points" in data:
            print(f"Tag {tag_id} = {data['points']} points")
        else:
            print("Error:", data.get("error", "Unknown error"))

    except Exception as e:
        print("Connection Error:", e)

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python decode.py <tag_id> <match_key>")
        sys.exit(1)
    
    tag_id = sys.argv[1]
    match_key = sys.argv[2]
    decode(tag_id= tag_id, match_key= match_key)