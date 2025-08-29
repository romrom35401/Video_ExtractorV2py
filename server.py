from flask import Flask, request, jsonify
import yt_dlp
import os
import random
import time

app = Flask(__name__)

def get_yt_dlp_opts():
    """Configuration yt-dlp optimisée pour Render"""
    user_agents = [
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15",
        "Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X) AppleWebKit/605.1.15",
        "Mozilla/5.0 (Android 13; Mobile; rv:120.0) Gecko/120.0 Firefox/120.0"
    ]
    
    return {
        "quiet": True,
        "no_warnings": True,
        "format": "mp4[height<=720]/best[height<=720]",
        "extractor_args": {
            "youtube": {
                "player_client": ["ios", "android", "tv_embedded"],
                "skip": ["hls", "dash"]  # Force mp4 progressif
            }
        },
        "http_headers": {
            "User-Agent": random.choice(user_agents),
            "Accept-Language": "en-US,en;q=0.9",
        },
        "force_ipv4": True,
        "socket_timeout": 30,
        "retries": 2
    }

@app.route("/api/extract", methods=["GET"])
def api_extract():
    url = request.args.get("url")
    if not url:
        return jsonify({"success": False, "error": "Missing url param"}), 400
    
    try:
        # Stratégie 1: Client iOS (le plus fiable actuellement)
        ydl_opts = get_yt_dlp_opts()
        ydl_opts["extractor_args"]["youtube"]["player_client"] = ["ios"]
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            video_url = info.get("url")
            
            if video_url:
                return jsonify({
                    "success": True, 
                    "title": info.get("title"), 
                    "url": video_url,
                    "method": "ios_client"
                })
        
        # Stratégie 2: Client Android + delay
        time.sleep(random.uniform(1, 3))
        ydl_opts["extractor_args"]["youtube"]["player_client"] = ["android"]
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            video_url = info.get("url")
            
            if video_url:
                return jsonify({
                    "success": True, 
                    "title": info.get("title"), 
                    "url": video_url,
                    "method": "android_client"
                })
        
        # Stratégie 3: TV Embedded (pour certaines videos)
        ydl_opts["extractor_args"]["youtube"]["player_client"] = ["tv_embedded"]
        ydl_opts["format"] = "worst[ext=mp4]"  # Qualité minimale
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            video_url = info.get("url")
            
            if video_url:
                return jsonify({
                    "success": True, 
                    "title": info.get("title"), 
                    "url": video_url,
                    "method": "tv_embedded"
                })
        
        return jsonify({
            "success": False, 
            "error": "All extraction methods failed"
        }), 404
        
    except Exception as e:
        error_msg = str(e).lower()
        if any(term in error_msg for term in ["403", "forbidden", "potoken", "sign in"]):
            return jsonify({
                "success": False, 
                "error": "YouTube blocking detected",
                "suggestion": "Try again later or use different video"
            }), 403
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "status": "Server running", 
        "endpoint": "/api/extract?url=YOUR_URL",
        "note": "Using anti-403 strategies for YouTube"
    })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
