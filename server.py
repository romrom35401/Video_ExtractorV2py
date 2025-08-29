# app.py
from flask import Flask, request, jsonify
from extractor import extract  # ton script extractor.py
import yt_dlp
import os

app = Flask(__name__)

@app.route("/api/extract", methods=["GET"])
def api_extract():
    url = request.args.get("url")
    if not url:
        return jsonify({"success": False, "error": "Missing url param"}), 400
    
    try:
        # Configuration yt-dlp optimisée pour Render
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "format": "mp4/best",
            "http_headers": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                              "AppleWebKit/537.36 (KHTML, like Gecko) "
                              "Chrome/114.0.0.0 Safari/537.36",
                "Accept-Language": "en-US,en;q=0.9",
            },
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            video_url = info.get("url")
            
            if not video_url and info.get("formats"):
                mp4_formats = [f for f in info["formats"] if f.get("ext") == "mp4" and f.get("url")]
                if mp4_formats:
                    mp4_formats_sorted = sorted(mp4_formats, key=lambda f: f.get("height", 0), reverse=True)
                    video_url = mp4_formats_sorted[0]["url"]
            
            if video_url:
                return jsonify({
                    "success": True, 
                    "title": info.get("title"), 
                    "url": video_url
                })
        
        # Fallback vers extractor.py
        result = extract(url, try_yt_dlp=True)
        if result:
            return jsonify({"success": True, "url": result})
        else:
            return jsonify({"success": False, "error": "Video not found"}), 404
            
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/", methods=["GET"])
def home():
    return jsonify({"status": "Server is running", "endpoint": "/api/extract?url=YOUR_URL"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
