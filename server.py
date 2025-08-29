# server.py
from flask import Flask, request, jsonify
from extractor import extract  # ton script extractor.py

app = Flask(__name__)

@app.route("/api/extract", methods=["GET"])
def api_extract():
    url = request.args.get("url")
    if not url:
        return jsonify({"success": False, "error": "Missing url param"}), 400

    try:
        result = extract(url, try_yt_dlp=True)
        if not result:
            return jsonify({"success": False, "error": "Video not found"}), 404
        return jsonify({"success": True, "url": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
