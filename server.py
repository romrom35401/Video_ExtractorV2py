# app.py
from flask import Flask, request, jsonify
from extractor import extract
import yt_dlp
import os
import random

app = Flask(__name__)

# Liste de User-Agents rotatifs pour éviter la détection
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:120.0) Gecko/20100101 Firefox/120.0"
]

@app.route("/api/extract", methods=["GET"])
def api_extract():
    url = request.args.get("url")
    if not url:
        return jsonify({"success": False, "error": "Missing url param"}), 400
    
    try:
        # Configuration optimisée pour éviter les 403
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "format": "mp4/best[height<=720]",  # Limite la qualité pour éviter la détection
            "force_ipv4": True,  # Force IPv4 (peut aider)
            "socket_timeout": 30,
            "retries": 3,
            "fragment_retries": 3,
            "http_headers": {
                "User-Agent": random.choice(USER_AGENTS),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-us,en;q=0.5",
                "Accept-Encoding": "gzip,deflate",
                "Accept-Charset": "ISO-8859-1,utf-8;q=0.7,*;q=0.7",
                "Keep-Alive": "300",
                "Connection": "keep-alive",
            },
            # Utilise des clients alternatifs pour YouTube
            "extractor_args": {
                "youtube": {
                    "player_client": ["web", "tv_embedded", "android_embedded"]
                }
            }
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            video_url = info.get("url")
            
            if not video_url and info.get("formats"):
                # Cherche spécifiquement les formats mp4 de qualité modérée
                mp4_formats = [f for f in info["formats"] 
                              if f.get("ext") == "mp4" 
                              and f.get("url") 
                              and f.get("height", 0) <= 720]
                if mp4_formats:
                    mp4_formats_sorted = sorted(mp4_formats, key=lambda f: f.get("height", 0), reverse=True)
                    video_url = mp4_formats_sorted[0]["url"]
            
            if video_url:
                return jsonify({
                    "success": True, 
                    "title": info.get("title"), 
                    "url": video_url,
                    "quality": info.get("height", "unknown")
                })
        
        # Fallback avec extractor personnalisé
        result = extract(url, try_yt_dlp=True)
        if result:
            return jsonify({"success": True, "url": result})
        else:
            return jsonify({"success": False, "error": "Video not accessible"}), 404
            
    except Exception as e:
        error_msg = str(e)
        if "403" in error_msg or "Forbidden" in error_msg:
            return jsonify({
                "success": False, 
                "error": "Access forbidden - try again later or use different URL format"
            }), 403
        return jsonify({"success": False, "error": error_msg}), 500

@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "status": "Server running", 
        "endpoint": "/api/extract?url=YOUR_URL",
        "note": "Some videos may be blocked due to platform restrictions"
    })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
