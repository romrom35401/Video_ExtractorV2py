from flask import Flask, request, jsonify
import yt_dlp
import os
import random
import time

app = Flask(__name__)

# Configuration directe dans le code (au lieu de variables d'env)
APP_CONFIG = {
    "cache_dir": "/tmp/yt-dlp-cache",
    "no_update_check": True,
    "debug_mode": False  # Change à True pour plus de logs
}

def get_site_specific_config(url):
    """Configuration spécifique selon le site"""
    
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ]
    
    base_config = {
        "quiet": not APP_CONFIG["debug_mode"],
        "no_warnings": True,
        "format": "mp4/best[ext=mp4]/best",
        "socket_timeout": 45,
        "retries": 3,
        "force_ipv4": True,
        "cachedir": APP_CONFIG["cache_dir"],
        "no_check_certificate": True,  # Ignore les certificats SSL invalides
    }
    
    base_headers = {
        "User-Agent": random.choice(user_agents),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Connection": "keep-alive",
    }
    
    # Configuration spécifique par site
    if "sibnet.ru" in url:
        base_config["http_headers"] = {
            **base_headers,
            "Referer": "https://video.sibnet.ru/",
            "Origin": "https://video.sibnet.ru"
        }
    elif "vk.com" in url:
        base_config["http_headers"] = {
            **base_headers,
            "Referer": "https://vk.com/",
        }
    elif any(site in url for site in ["vidmoly.net", "myvi", "sendvid.com"]):
        domain = url.split('/')[2] if '/' in url else ""
        base_config["http_headers"] = {
            **base_headers,
            "Referer": f"https://{domain}/",
        }
    else:
        base_config["http_headers"] = base_headers
    
    return base_config

@app.route("/api/extract", methods=["GET"])
def api_extract():
    url = request.args.get("url")
    if not url:
        return jsonify({"success": False, "error": "Missing url param"}), 400
    
    # Log pour debug (seulement si PYTHONUNBUFFERED=1)
    if APP_CONFIG["debug_mode"]:
        print(f"Processing URL: {url}")
    
    try:
        # Nettoie le cache au début (remplace la variable d'env)
        clear_cache()
        
        # Stratégie principale
        ydl_opts = get_site_specific_config(url)
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            video_url = info.get("url")
            
            if not video_url and info.get("formats"):
                for fmt in info["formats"]:
                    if fmt.get("ext") == "mp4" and fmt.get("url"):
                        video_url = fmt["url"]
                        break
                
                # Fallback : premier format avec URL
                if not video_url:
                    for fmt in info["formats"]:
                        if fmt.get("url"):
                            video_url = fmt["url"]
                            break
            
            if video_url:
                return jsonify({
                    "success": True, 
                    "title": info.get("title", "Unknown"),
                    "url": video_url,
                    "site": url.split('/')[2] if '/' in url else "unknown"
                })
        
        # Stratégie fallback simplifiée
        time.sleep(random.uniform(1, 2))
        
        simple_opts = {
            "quiet": True,
            "format": "worst",
            "http_headers": {"User-Agent": random.choice([
                "Mozilla/5.0 (compatible; Googlebot/2.1)",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            ])},
            "socket_timeout": 20
        }
        
        with yt_dlp.YoutubeDL(simple_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if info and info.get("url"):
                return jsonify({
                    "success": True,
                    "title": info.get("title", "Unknown"),
                    "url": info["url"],
                    "method": "fallback"
                })
        
        return jsonify({
            "success": False, 
            "error": "Video URL not extractable"
        }), 404
        
    except Exception as e:
        error_msg = str(e).lower()
        if "403" in error_msg:
            return jsonify({
                "success": False, 
                "error": "Access forbidden by site",
                "suggestion": "Site blocking detected - try different URL or wait"
            }), 403
        return jsonify({"success": False, "error": str(e)}), 500

def clear_cache():
    """Nettoie le cache yt-dlp"""
    try:
        import shutil
        cache_dir = APP_CONFIG["cache_dir"]
        if os.path.exists(cache_dir):
            shutil.rmtree(cache_dir, ignore_errors=True)
    except:
        pass

@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "status": "Server running", 
        "endpoint": "/api/extract?url=YOUR_URL",
        "config": "Single env var mode",
        "supported_sites": [
            "vidmoly.net", "video.sibnet.ru", "vk.com", "sendvid.com", 
            "myvi.top", "movearnpre.com", "oneupload.to", "smoothpre.com", "myvi.tv"
        ]
    })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
