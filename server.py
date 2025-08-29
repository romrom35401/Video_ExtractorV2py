from flask import Flask, request, jsonify
import yt_dlp
import time
import random
import logging
import os
from urllib.parse import urlparse
import httpx
from concurrent.futures import ThreadPoolExecutor, TimeoutError
import json

app = Flask(__name__)

# Configuration des logs
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

# Cache simple en mémoire (remplace Redis pour simplicité)
url_cache = {}
CACHE_DURATION = 3600  # 1 heure

class VideoExtractor:
    """Extracteur optimisé basé sur la logique du downloader.py"""
    
    def __init__(self):
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ]
    
    def check_vidmoly_ready(self, url):
        """Vérifie si vidmoly est prêt (adapté du downloader.py)"""
        if not url.startswith("https://vidmoly."):
            return True
        
        try:
            response = httpx.get(url, headers={"User-Agent": ""}, timeout=10)
            # Si "Please wait" est dans la page, vidmoly n'est pas prêt
            return "Please wait" not in response.text
        except:
            return False
    
    def get_headers_for_site(self, url):
        """Headers optimisés par site"""
        domain = urlparse(url).hostname or ""
        
        headers = {
            "User-Agent": random.choice(self.user_agents),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1"
        }
        
        # Headers spécifiques par site
        if "sibnet.ru" in domain:
            headers.update({
                "Referer": "https://video.sibnet.ru/",
                "Origin": "https://video.sibnet.ru"
            })
        elif "vk.com" in domain:
            headers["Referer"] = "https://vk.com/"
        elif "vidmoly" in domain:
            headers["Referer"] = f"https://{domain}/"
        elif "myvi" in domain:
            headers.update({
                "Referer": f"https://{domain}/",
                "Origin": f"https://{domain}"
            })
        elif "sendvid" in domain:
            headers["Referer"] = f"https://{domain}/"
        elif any(site in domain for site in ["movearnpre", "oneupload", "smoothpre"]):
            headers["Referer"] = f"https://{domain}/"
        
        return headers
    
    def extract_with_yt_dlp(self, url, retry_count=0, max_retries=3):
        """Extraction principale avec yt-dlp"""
        
        # Configuration optimale pour extraction (pas téléchargement)
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": False,
            "skip_download": True,
            "format": "best[ext=mp4]/best",  # Préfère mp4
            "socket_timeout": 30,
            "retries": 3,
            "force_ipv4": True,
            "http_headers": self.get_headers_for_site(url),
            "nocheckcertificate": True,
            "geo_bypass": True,
            "concurrent_fragment_downloads": 1
        }
        
        # Options spécifiques par site
        domain = urlparse(url).hostname or ""
        
        if "vk.com" in domain:
            # VK limite parfois la qualité
            ydl_opts["format"] = "best[height<=720]/best"
        elif "sibnet" in domain:
            ydl_opts["format"] = "mp4/best"
        elif "myvi" in domain or "vidmoly" in domain:
            # Ces sites peuvent avoir des formats particuliers
            ydl_opts["format"] = "best[ext=mp4]/best[ext=m3u8]/best"
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                
                # Extraction de l'URL directe
                direct_url = None
                is_hls = False
                
                # Priorité 1: URL directe
                if info.get("url"):
                    direct_url = info["url"]
                    is_hls = ".m3u8" in direct_url or "master.json" in direct_url
                
                # Priorité 2: Chercher dans les formats
                elif info.get("formats"):
                    # Cherche d'abord un mp4
                    for fmt in info["formats"]:
                        if fmt.get("ext") == "mp4" and fmt.get("url"):
                            direct_url = fmt["url"]
                            break
                    
                    # Si pas de mp4, prend le meilleur format disponible
                    if not direct_url:
                        for fmt in reversed(info["formats"]):  # Du meilleur au pire
                            if fmt.get("url"):
                                direct_url = fmt["url"]
                                is_hls = fmt.get("ext") == "m3u8" or ".m3u8" in fmt.get("url", "")
                                break
                
                # Priorité 3: Entrées de playlist
                elif info.get("entries"):
                    for entry in info["entries"]:
                        if entry.get("url"):
                            direct_url = entry["url"]
                            break
                
                if direct_url:
                    return {
                        "success": True,
                        "url": direct_url,
                        "is_hls": is_hls,
                        "title": info.get("title", "Video"),
                        "duration": info.get("duration"),
                        "thumbnail": info.get("thumbnail"),
                        "site": domain
                    }
                else:
                    raise Exception("No direct URL found in extraction")
        
        except Exception as e:
            error_msg = str(e).lower()
            
            # Gestion des erreurs spécifiques
            if "unsupported url" in error_msg and "vidmoly" in url and retry_count < max_retries:
                # Vidmoly a besoin d'attendre
                wait_time = (retry_count + 1) * 2
                logger.warning(f"Vidmoly needs wait, retrying in {wait_time}s...")
                time.sleep(wait_time)
                return self.extract_with_yt_dlp(url, retry_count + 1, max_retries)
            
            elif any(term in error_msg for term in ["403", "forbidden", "geo"]):
                raise Exception(f"Access blocked: {e}")
            
            elif "timeout" in error_msg and retry_count < max_retries:
                time.sleep(2)
                return self.extract_with_yt_dlp(url, retry_count + 1, max_retries)
            
            raise e
    
    def extract(self, url, max_wait_time=30):
        """Méthode principale d'extraction avec gestion vidmoly"""
        
        # Vérifier le cache
        cache_key = url
        if cache_key in url_cache:
            cached_data, cached_time = url_cache[cache_key]
            if time.time() - cached_time < CACHE_DURATION:
                logger.info(f"Cache hit for {url}")
                return cached_data
        
        # Pour vidmoly, attendre qu'il soit prêt
        if url.startswith("https://vidmoly."):
            wait_time = 0
            while wait_time < max_wait_time:
                if self.check_vidmoly_ready(url):
                    break
                logger.warning(f"Vidmoly not ready, waiting...")
                time.sleep(2)
                wait_time += 2
            
            if wait_time >= max_wait_time:
                raise Exception("Vidmoly timeout - video not ready")
        
        # Extraction
        result = self.extract_with_yt_dlp(url)
        
        # Mettre en cache si succès
        if result["success"]:
            url_cache[cache_key] = (result, time.time())
        
        return result

# Instance globale de l'extracteur
extractor = VideoExtractor()

@app.route("/api/extract", methods=["GET"])
def api_extract():
    """Endpoint principal pour extraire une URL vidéo"""
    url = request.args.get("url")
    
    if not url:
        return jsonify({
            "success": False,
            "error": "Missing 'url' parameter"
        }), 400
    
    # Validation basique de l'URL
    supported_sites = [
        "vidmoly.net", "video.sibnet.ru", "vk.com", "sendvid.com",
        "myvi.top", "myvi.tv", "movearnpre.com", "oneupload.to", "smoothpre.com"
    ]
    
    if not any(site in url for site in supported_sites):
        return jsonify({
            "success": False,
            "error": f"Unsupported site. Supported: {', '.join(supported_sites)}"
        }), 400
    
    try:
        # Extraction avec timeout
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(extractor.extract, url)
            result = future.result(timeout=45)  # Timeout global de 45 secondes
        
        # Formater la réponse pour Expo Go
        response = {
            "success": True,
            "data": {
                "url": result["url"],  # URL directe du mp4/m3u8
                "type": "hls" if result["is_hls"] else "mp4",
                "title": result.get("title", "Video"),
                "duration": result.get("duration"),
                "thumbnail": result.get("thumbnail"),
                "source": result.get("site")
            }
        }
        
        return jsonify(response), 200
    
    except TimeoutError:
        return jsonify({
            "success": False,
            "error": "Extraction timeout - try again later"
        }), 408
    
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Extraction failed for {url}: {error_msg}")
        
        # Déterminer le code d'erreur approprié
        if "blocked" in error_msg.lower() or "403" in error_msg:
            status_code = 403
        elif "timeout" in error_msg.lower():
            status_code = 408
        elif "unsupported" in error_msg.lower():
            status_code = 400
        else:
            status_code = 500
        
        return jsonify({
            "success": False,
            "error": error_msg
        }), status_code

@app.route("/api/batch", methods=["POST"])
def api_batch_extract():
    """Endpoint bonus pour extraire plusieurs URLs à la fois"""
    data = request.get_json()
    
    if not data or "urls" not in data:
        return jsonify({
            "success": False,
            "error": "Missing 'urls' in request body"
        }), 400
    
    urls = data["urls"]
    if not isinstance(urls, list) or len(urls) > 5:  # Limite à 5 pour éviter les abus
        return jsonify({
            "success": False,
            "error": "urls must be a list with max 5 items"
        }), 400
    
    results = []
    for url in urls:
        try:
            result = extractor.extract(url, max_wait_time=15)  # Timeout réduit pour batch
            results.append({
                "url": url,
                "success": True,
                "data": {
                    "url": result["url"],
                    "type": "hls" if result["is_hls"] else "mp4",
                    "title": result.get("title")
                }
            })
        except Exception as e:
            results.append({
                "url": url,
                "success": False,
                "error": str(e)
            })
    
    return jsonify({
        "success": True,
        "results": results
    }), 200

@app.route("/", methods=["GET"])
def home():
    """Page d'accueil avec documentation"""
    return jsonify({
        "name": "Video Extractor API for Expo Go",
        "version": "2.0",
        "endpoints": {
            "extract": {
                "method": "GET",
                "url": "/api/extract?url=VIDEO_URL",
                "description": "Extract direct video URL from supported sites"
            },
            "batch": {
                "method": "POST", 
                "url": "/api/batch",
                "body": {"urls": ["url1", "url2"]},
                "description": "Extract multiple URLs (max 5)"
            },
            "health": {
                "method": "GET",
                "url": "/health",
                "description": "Health check endpoint"
            }
        },
        "supported_sites": [
            "vidmoly.net", "video.sibnet.ru", "vk.com", "sendvid.com",
            "myvi.top", "myvi.tv", "movearnpre.com", "oneupload.to", "smoothpre.com"
        ],
        "response_format": {
            "success": True,
            "data": {
                "url": "direct_video_url",
                "type": "mp4 or hls",
                "title": "video_title",
                "duration": "seconds",
                "thumbnail": "thumbnail_url",
                "source": "site_domain"
            }
        }
    }), 200

@app.route("/health", methods=["GET"])
def health():
    """Health check pour Render"""
    return jsonify({
        "status": "healthy",
        "cache_size": len(url_cache),
        "timestamp": int(time.time())
    }), 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
