import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
import requests
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
from google.protobuf.json_format import MessageToDict
from flask import Flask, request, jsonify

app = Flask(__name__)

# AES Encryption Keys
KEY = bytes([89, 103, 38, 116, 99, 37, 68, 69, 117, 104, 54, 37, 90, 99, 94, 56])
IV = bytes([54, 111, 121, 90, 68, 114, 50, 50, 69, 51, 121, 99, 104, 106, 77, 37])

VALID_API_KEY = "rfg_gamer"

# Check Protobuf Module
try:
    import follow_pb2
except ImportError:
    print("[!] Error: 'follow_pb2.py' file missing in this directory!")
    sys.exit(1)


def encrypt_payload(data: bytes) -> bytes:
    cipher = AES.new(KEY, AES.MODE_CBC, IV)
    return cipher.encrypt(pad(data, AES.block_size))


def load_jwt_tokens(file_path: str) -> list:
    if not os.path.exists(file_path):
        return []

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if isinstance(data, list):
            tokens = [t.strip() for t in data if isinstance(t, str) and t.strip()]
        elif isinstance(data, dict):
            tokens = data.get("tokens", [])
            if isinstance(tokens, list):
                tokens = [t.strip() for t in tokens if isinstance(t, str) and t.strip()]
            else:
                tokens = []
        else:
            tokens = []

        return [t for t in tokens if "YOUR_JWT_TOKEN" not in t]
    except Exception:
        return []


def send_single_follow(jwt_token: str, target_id: int, url: str) -> tuple:
    req = follow_pb2.CSFollowReq()
    req.target_id = target_id
    encrypted_data = encrypt_payload(req.SerializeToString())

    headers = {
        "User-Agent": "UnityPlayer/2022.3.47f1 (UnityWebRequest/1.0, libcurl/8.5.0-DEV)",
        "Accept": "*/*",
        "Accept-Encoding": "deflate, gzip",
        "Authorization": f"Bearer {jwt_token}",
        "X-Ga": "v1 1",
        "Releaseversion": "OB54",
        "Content-Type": "application/x-www-form-urlencoded",
        "X-Unity-Version": "2022.3.47f1",
    }

    try:
        response = requests.post(url, headers=headers, data=encrypted_data, timeout=15)

        if response.status_code == 200:
            res = follow_pb2.CSFollowRes()
            res.ParseFromString(response.content)
            res_dict = MessageToDict(res, preserving_proto_field_name=True)

            if "fail_info" in res_dict and res_dict["fail_info"]:
                return False, None

            account_info = res_dict.get("info", {})
            nickname = account_info.get("nickname", "Unknown")
            return True, nickname
        else:
            return False, None

    except Exception:
        return False, None


# -----------------------------------------------------------
# নতুন যুক্ত করা অংশ: মেইন ইউআরএল এ ভিজিট করলে এই রেসপন্স দেখাবে
# -----------------------------------------------------------
@app.route('/', methods=['GET'])
def home():
    return jsonify({
        "status": "success",
        "message": "API is running successfully!",
        "credit": "@RFG_GAMER"
    }), 200


@app.route('/uid', methods=['GET'])
def follow_api():
    # 1. API Key Validation
    apikey = request.args.get('apikey')
    if apikey != VALID_API_KEY:
        return jsonify({"status": "error", "message": "Invalid API Key"}), 403

    # 2. Target UID Validation
    target_uid_param = request.args.get('uid')
    if not target_uid_param or not target_uid_param.isdigit():
        return jsonify({"status": "error", "message": "Invalid or missing Target UID"}), 400
    target_id = int(target_uid_param)

    # 3. Parameters extraction
    follow_number_param = request.args.get('follownumber')
    region_param = request.args.get('regoin', 'BD').upper()

    # 4. Region Selection & Token File Mapping
    if region_param in ["IND", "INDIA"]:
        selected_url = "https://client.ind.freefiremobile.com/Follow"
        region_name = "India (IND)"
        token_file = "token_ind.json"
    elif region_param in ["BD", "BANGLADESH"]:
        selected_url = "https://clientbp.ggpolarbear.com/Follow"
        region_name = "Bangladesh (BD)"
        token_file = "token_bd.json"
    else:
        selected_url = "https://clientbp.ggpolarbear.com/Follow"
        region_name = f"Others ({region_param})"
        token_file = "token_bd.json"

    # 5. Load Tokens based on Region
    all_tokens = load_jwt_tokens(token_file)
    if not all_tokens:
        return jsonify({"status": "error", "message": f"No valid JWT tokens found in '{token_file}'"}), 500

    # 6. Determine token count
    if follow_number_param and follow_number_param.isdigit():
        req_count = int(follow_number_param)
        selected_count = min(req_count, len(all_tokens))
    else:
        selected_count = len(all_tokens)

    tokens_to_use = all_tokens[:selected_count]

    # 7. Execute Requests using ThreadPool
    success_count = 0
    failed_count = 0
    player_nickname = "Unknown"

    max_workers = min(10, len(tokens_to_use))

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [
            executor.submit(send_single_follow, token, target_id, selected_url)
            for token in tokens_to_use
        ]

        for future in futures:
            is_success, nickname = future.result()
            if is_success:
                success_count += 1
                if nickname and nickname != "Unknown":
                    player_nickname = nickname
            else:
                failed_count += 1

    # 8. Return JSON Response
    return jsonify({
        "status": "success",
        "target_uid": target_id,
        "player_name": player_nickname,
        "region": region_name,
        "requested_follows": selected_count,
        "successful_follows": success_count,
        "failed_follows": failed_count,
        "Credit": "@RFG_GAMER"
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
