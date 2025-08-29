from flask import Flask, request, jsonify
import yt_dlp
import os
import random
import time

app = Flask(__name__)

def get_site_specific_config(url):
    """Configuration spécifique selon le site"""
    
    # Configuration de base
    base_config = {
        "quiet": True,
        "no_warnings": True,
        "format": "mp4/best[ext=mp4]/best",
        "socket_timeout": 45,
        "retries": 3,
        "force_ipv4": True,
    }
    
    # Headers communs anti-détection
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ]
    
    base_headers = {
        "User-Agent": random.choice(user_agents),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
    }
    
    # Configuration spécifique par site
    if "sibnet.ru" in url:
        base_config.update({
            "http_headers": {
                **base_headers,
                "Referer": "https://video.sibnet.ru/",
                "Origin": "https://video.sibnet.ru"
            }
        })
    
    elif "vk.com" in url:
        base_config.update({
            "http_headers": {
                **base_headers,
                "Referer": "https://vk.com/",
                "Origin": "https://vk.com"
            },
            # Utilise l'extracteur spécifique VK si disponible
            "extractor_args": {
                "generic": {"default_search": "auto"}
            }
        })
    
    elif "vidmoly.net" in url or "myvi" in url:
        base_config.update({
            "http_headers": {
                **base_headers,
                "Referer": url.split('/')[0] + '//' + url.split('/')[2] + '/',
            }
        })
    
    elif "sendvid.com" in url or "oneupload.to" in url:
        base_config.update({
            "http_headers": {
                **base_headers,
                "Referer": url,
            },
            "format": "best[ext=mp4]/mp4/best"
        })
    
    else:  # Pour smoothpre.com, movearnpre.com, etc.
        base_config.update({
            "http_headers": base_headers
        })
    
    return base_config

@app.route("/api/extract", methods=["GET"])
def api_extract():
    url = request.args.get("url")
    if not url:
        return jsonify({"success": False, "error": "Missing url param"}), 400
    
    try:
        # Stratégie 1: Configuration optimisée pour le site
        ydl_opts = get_site_specific_config(url)
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            video_url = info.get("url")
            
            if not video_url and info.get("formats"):
                # Cherche le meilleur format mp4
                mp4_formats = [f for f in info["formats"] 
                              if f.get("ext") == "mp4" and f.get("url")]
                if mp4_formats:
                    # Trie par qualité (hauteur)
                    mp4_formats_sorted = sorted(mp4_formats, 
                                              key=lambda f: f.get("height", 0), reverse=True)
                    video_url = mp4_formats_sorted[0]["url"]
                else:
                    # Fallback : n'importe quel format avec URL
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
        
        # Stratégie 2: Fallback avec extracteur générique
        time.sleep(random.uniform(1, 3))  # Délai aléatoire
        
        generic_opts = {
            "quiet": True,
            "format": "worst[ext=mp4]/worst",  # Qualité minimale
            "force_ipv4": True,
            "socket_timeout": 30,
            "http_headers": {
                "User-Agent": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
                "Referer": url
            }
        }
        
        with yt_dlp.YoutubeDL(generic_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if info and info.get("url"):
                return jsonify({
                    "success": True,
                    "title": info.get("title", "Unknown"),
                    "url": info["url"],
                    "method": "generic_fallback"
                })
        
        return jsonify({
            "success": False, 
            "error": "Video URL not found"
        }), 404
        
    except Exception as e:
        error_msg = str(e).lower()
        if "403" in error_msg or "forbidden" in error_msg:
            return jsonify({
                "success": False, 
                "error": "Site blocking detected",
                "suggestion": f"Site {url.split('/')[2] if '/' in url else 'unknown'} may be blocking cloud IPs"
            }), 403
        elif "timeout" in error_msg:
            return jsonify({
                "success": False, 
                "error": "Connection timeout",
                "suggestion": "Try again later"
            }), 408
        else:
            return jsonify({
                "success": False, 
                "error": str(e)
            }), 500

@app.route("/", methods=["GET"])
def home():
    supported_sites = [
        "vidmoly.net", "video.sibnet.ru", "vk.com", "sendvid.com", 
        "myvi.top", "movearnpre.com", "oneupload.to", "smoothpre.com", "myvi.tv"
    ]
    return jsonify({
        "status": "Server running", 
        "endpoint": "/api/extract?url=YOUR_URL",
        "supported_sites": supported_sites,
        "note": "Optimized for alternative video platforms"
    })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
