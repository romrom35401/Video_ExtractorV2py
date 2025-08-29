from flask import Flask, request, jsonify
import random
import time
import logging
from urllib.parse import urlparse
from pathlib import Path
import tempfile
import os

import httpx
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

app = Flask(__name__)

# Configuration des logs
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

def reaction_to(error_msg):
    """Détermine la réaction selon l'erreur (adapté de ton code)"""
    if not error_msg:
        return ""
    
    error_msg = error_msg.lower()
    
    # Erreurs qui nécessitent une nouvelle tentative
    if any(term in error_msg for term in [
        "timeout", "connection", "temporary", "try again", 
        "server error", "503", "502", "waiting for vidmoly"
    ]):
        return "retry"
    
    # Erreurs qui nécessitent de passer au player suivant
    if any(term in error_msg for term in [
        "403", "forbidden", "not available", "geo", "blocked",
        "unavailable", "removed", "private"
    ]):
        return "continue"
    
    # Erreurs critiques
    if any(term in error_msg for term in [
        "unsupported url", "no video", "invalid url"
    ]):
        return "crash"
    
    return ""

def check_vidmoly_availability(url):
    """Vérifie si vidmoly est accessible (adapté de ton code)"""
    try:
        if url.startswith("https://vidmoly."):
            response = httpx.get(url, headers={"User-Agent": ""}, timeout=10)
            return "Please wait" not in response.text
        return True
    except:
        return False

def extract_video_url(player_url, max_retry_time=64, format_preference="mp4/best"):
    """Extraction avec retry logic adaptée de ton downloader"""
    
    retry_time = 1
    
    while retry_time <= max_retry_time:
        # Vérification spéciale pour vidmoly
        if not check_vidmoly_availability(player_url):
            logger.warning(f"Vidmoly not ready, waiting {retry_time}s")
            time.sleep(retry_time * random.uniform(0.8, 1.2))
            retry_time *= 2
            continue
        
        try:
            # Configuration yt-dlp adaptée
            ydl_opts = {
                "quiet": True,
                "no_warnings": True,
                "format": format_preference,
                "socket_timeout": 30,
                "retries": 2,
                "force_ipv4": True,
                "extract_flat": False,
                "http_headers": get_headers_for_site(player_url)
            }
            
            with YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(player_url, download=False)
                
                video_url = info.get("url")
                if not video_url and info.get("formats"):
                    # Cherche le meilleur format mp4
                    for fmt in info["formats"]:
                        if fmt.get("ext") == "mp4" and fmt.get("url"):
                            video_url = fmt["url"]
                            break
                    
                    # Fallback : premier format disponible
                    if not video_url:
                        for fmt in info["formats"]:
                            if fmt.get("url"):
                                video_url = fmt["url"]
                                break
                
                if video_url:
                    return {
                        "success": True,
                        "url": video_url,
                        "title": info.get("title", "Unknown"),
                        "site": urlparse(player_url).hostname,
                        "retries": retry_time // 2 if retry_time > 1 else 0
                    }
                else:
                    return {"success": False, "error": "No video URL found"}
        
        except DownloadError as e:
            error_msg = str(e)
            
            # Gestion spéciale vidmoly
            if (player_url.startswith("https://vidmoly.") and 
                "Unsupported URL: https://vidmoly.net/" in error_msg):
                logger.warning("Vidmoly needs waiting, retrying...")
                reaction = "retry"
            else:
                reaction = reaction_to(error_msg)
            
            logger.warning(f"Error: {error_msg}, Reaction: {reaction}")
            
            if reaction == "continue":
                return {"success": False, "error": f"Site blocking: {error_msg}"}
            elif reaction == "retry":
                if retry_time >= max_retry_time:
                    return {"success": False, "error": f"Max retries exceeded: {error_msg}"}
                
                logger.warning(f"Retrying in {retry_time}s...")
                time.sleep(retry_time * random.uniform(0.8, 1.2))
                retry_time *= 2
            elif reaction == "crash":
                return {"success": False, "error": f"Critical error: {error_msg}"}
            else:
                return {"success": False, "error": f"Unhandled error: {error_msg}"}
        
        except Exception as e:
            return {"success": False, "error": f"Unexpected error: {str(e)}"}
    
    return {"success": False, "error": "All retry attempts failed"}

def get_headers_for_site(url):
    """Headers spécifiques par site"""
    domain = urlparse(url).hostname or ""
    
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ]
    
    base_headers = {
        "User-Agent": random.choice(user_agents),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Connection": "keep-alive",
    }
    
    if "sibnet.ru" in domain:
        base_headers.update({
            "Referer": "https://video.sibnet.ru/",
            "Origin": "https://video.sibnet.ru"
        })
    elif "vk.com" in domain:
        base_headers["Referer"] = "https://vk.com/"
    elif any(site in domain for site in ["vidmoly", "myvi", "sendvid"]):
        base_headers["Referer"] = f"https://{domain}/"
    
    return base_headers

@app.route("/api/extract", methods=["GET"])
def api_extract():
    url = request.args.get("url")
    if not url:
        return jsonify({"success": False, "error": "Missing url param"}), 400
    
    # Utilise la logique avancée du downloader
    result = extract_video_url(
        url, 
        max_retry_time=32,  # Réduit pour l'API (pas de téléchargement)
        format_preference="mp4[height<=720]/best[height<=720]/mp4/best"
    )
    
    if result["success"]:
        return jsonify(result), 200
    else:
        # Détermine le code d'erreur approprié
        error_msg = result["error"].lower()
        if "blocking" in error_msg or "403" in error_msg:
            return jsonify(result), 403
        elif "timeout" in error_msg or "retries exceeded" in error_msg:
            return jsonify(result), 408
        elif "critical" in error_msg or "unsupported" in error_msg:
            return jsonify(result), 400
        else:
            return jsonify(result), 500

@app.route("/api/extract/multiple", methods=["POST"])
def api_extract_multiple():
    """Endpoint pour extraire plusieurs URLs (bonus)"""
    data = request.get_json()
    if not data or "urls" not in data:
        return jsonify({"success": False, "error": "Missing urls in JSON body"}), 400
    
    urls = data["urls"]
    if not isinstance(urls, list) or len(urls) > 10:  # Limite pour éviter l'abus
        return jsonify({"success": False, "error": "urls must be a list with max 10 items"}), 400
    
    results = []
    for url in urls:
        result = extract_video_url(url, max_retry_time=16)  # Retry réduit pour multiple
        results.append({"url": url, **result})
    
    return jsonify({"results": results}), 200

@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "status": "Advanced Video Extractor Running",
        "features": [
            "Intelligent retry logic",
            "Site-specific optimizations", 
            "Vidmoly waiting detection",
            "Error categorization"
        ],
        "endpoints": {
            "single": "/api/extract?url=VIDEO_URL",
            "multiple": "/api/extract/multiple (POST with JSON)"
        },
        "supported_sites": [
            "vidmoly.net", "video.sibnet.ru", "vk.com", "sendvid.com", 
            "myvi.top", "movearnpre.com", "oneupload.to", "smoothpre.com", "myvi.tv"
        ]
    })

@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint"""
    return jsonify({"status": "healthy", "timestamp": time.time()}), 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
