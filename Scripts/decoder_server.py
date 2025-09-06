from flask import Flask, request, jsonify
from flask_cors import CORS
import random

app = Flask(__name__)
CORS(app)

match_mappings = {}

def generate_mapping(match_key, tag_ids, min_points=5, max_points=50, mine_chance=0.1, mine_value=-45):
    mapping = {}
    for tid in tag_ids:
        if random.random() < mine_chance:
            mapping[tid] = mine_value
        else:
            mapping[tid] = random.randint(min_points, max_points)
    match_mappings[match_key] = mapping
    return mapping

@app.route("/decode", methods=["GET"])
def decode():
    tag_id = request.args.get("tag_id")
    match_key = request.args.get("match_key")

    if not tag_id or not match_key:
        return jsonify({"error": "Missing tag_id or match_key"}), 400

    if match_key not in match_mappings:
        return jsonify({"error": "Invalid or expired match key"}), 403

    mapping = match_mappings[match_key]
    if tag_id not in mapping:
        return jsonify({"error": "Unknown tag_id"}), 404

    return jsonify({"tag_id": tag_id, "points": mapping[tag_id]})

@app.route("/new_match", methods=["POST"])
def new_match():
    """Admin endpoint to start a new match"""
    data = request.json
    match_key = data.get("match_key")
    tag_ids = data.get("tag_ids")

    if not match_key or not tag_ids:
        return jsonify({"error": "Missing match_key or tag_ids"}), 400

    mapping = generate_mapping(match_key, tag_ids)
    return jsonify({
        "match_key": match_key,
        "mapping": mapping,
        "tag_count": len(mapping)
    })

@app.route("/verify_match_key", methods=["GET"])
def verify_match_key():
    match_key = request.args.get("match_key")
    if not match_key:
        return jsonify({"error": "Missing match_key"}), 400

    if match_key in match_mappings:
        return jsonify({"valid": True}), 200
    else:
        return jsonify({"valid": False}), 404

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000)
