import argparse
import requests

SERVER_URL = "http://127.0.0.1:5000"

def main():
    parser = argparse.ArgumentParser(description="Create a new match with tags")
    parser.add_argument("--count", type=int, default=40, help="Number of tags to register (default: 40)")
    parser.add_argument("--key", type=str, required=True, help="Match key (required, no default)")
    args = parser.parse_args()

    tag_ids = [str(i) for i in range(1, args.count + 1)]

    r = requests.post(f"{SERVER_URL}/new_match", json={
        "match_key": args.key,
        "tag_ids": tag_ids
    })

    try:
        print(r.json())
    except Exception:
        print("Error: Could not decode response:", r.text)

if __name__ == "__main__":
    main()
