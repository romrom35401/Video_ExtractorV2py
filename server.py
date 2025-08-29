from flask import Flask, request, jsonify
import yt_dlp
import time
import random
import logging
import os
from urllib.parse import urlparse
import requests
from concurrent.futures import ThreadPoolExecutor, TimeoutError
import hashlib
from threading import Thread
from datetime import datetime, timedelta

app = Flask(__name__)

# Configuration des logs - plus léger
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Cache avec expiration
class SimpleCache:
    def __init__(self, ttl_seconds=1800):
        self.cache = {}
        self.ttl = ttl_seconds
    
    def get(self, key):
        if key in self.cache:
            data, timestamp = self.cache[key]
            if time.time() - timestamp < self.ttl:
                return data
            else:
                del self.cache[key]
        return None
    
    def set(self, key, value):
        self.cache[key] = (value, time.time())
    
    def clear(self):
        self.cache.clear()
    
    def size(self):
        return len(self.cache)

# Cache global
url_cache = SimpleCache()

class LightweightExtractor:
    """Extracteur optimisé pour démarrage rapide"""
    
    def __init__(self):
        # User agents minimalistes
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
        ]
        
        # Initialisation différée des proxies
        self.proxies_loaded = False
        self.free_proxies = []
        self.proxy_index = 0
        
        # Rate limiting simple
        self.last_request = {}
        
        # Charger les proxies en arrière-plan après le démarrage
        self.load_proxies_async()
    
    def load_proxies_async(self):
        """Charge les proxies en arrière-plan sans bloquer le démarrage"""
        def load():
            time.sleep(2)  # Attendre que le serveur soit démarré
            try:
                self.free_proxies = self.get_free_proxies()
                self.proxies_loaded = True
                logger.info(f"Proxies loaded: {len(self.free_proxies)}")
            except Exception as e:
                logger.warning(f"Failed to load proxies: {e}")
                self.proxies_loaded = True  # Marquer comme chargé même en cas d'échec
        
        Thread(target=load, daemon=True).start()
    
    def get_free_proxies(self):
        """Récupère des proxies gratuits - version simplifiée"""
        proxies = []
        
        # Une seule source de proxy pour accélérer
        try:
            response = requests.get(
                "https://api.proxyscrape.com/v2/?request=get&protocol=http&timeout=5000&country=all&ssl=all&anonymity=all&format=textplain&limit=10",
                timeout=5
            )
            if response.status_code == 200:
                proxy_list = response.text.strip().split('\n')
                for proxy in proxy_list[:10]:  # Limiter à 10
                    if ':' in proxy:
                        proxies.append(f"http://{proxy.strip()}")
        except Exception as e:
            logger.warning(f"Failed to fetch proxies: {e}")
        
        return proxies
    
    def get_random_proxy(self):
        """Obtient un proxy aléatoire si disponible"""
        if not self.proxies_loaded or not self.free_proxies:
            return None
        return random.choice(self.free_proxies)
    
    def rate_limit_check(self, domain):
        """Vérification simple du rate limiting"""
        now = time.time()
        if domain in self.last_request:
            elapsed = now - self.last_request[domain]
            if elapsed < 1:  # Minimum 1 seconde entre requêtes
                time.sleep(1 - elapsed)
        self.last_request[domain] = time.time()
    
    def get_basic_headers(self, url):
        """Headers basiques mais efficaces"""
        return {
            "User-Agent": random.choice(self.user_agents),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1"
        }
    
    def extract_simple(self, url, use_proxy=False):
        """Extraction simplifiée et rapide"""
        domain = urlparse(url).hostname or ""
        self.rate_limit_check(domain)
        
        # Configuration yt-dlp minimaliste
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": False,
            "skip_download": True,
            "format": "best[ext=mp4]/best",
            "socket_timeout": 30,
            "retries": 3,
            "http_headers": self.get_basic_headers(url),
            "nocheckcertificate": True,
            "geo_bypass": True,
            "simulate": True
        }
        
        # Ajouter proxy si demandé et disponible
        if use_proxy and self.proxies_loaded:
            proxy = self.get_random_proxy()
            if proxy:
                ydl_opts["proxy"] = proxy
                logger.info(f"Using proxy: {proxy}")
        
        # Options spécifiques par site
        if "youtube.com" in domain or "youtu.be" in domain:
            ydl_opts["format"] = "best[height<=720]/best"
        elif "vidmoly" in domain:
            ydl_opts["http_headers"]["Referer"] = f"https://{domain}/"
        elif "sibnet.ru" in domain:
            ydl_opts["http_headers"]["Referer"] = "https://video.sibnet.ru/"
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                
                if info:
                    # Récupérer l'URL directe
                    video_url = info.get("url")
                    if not video_url and info.get("formats"):
                        # Chercher le meilleur format
                        for fmt in reversed(info["formats"]):
                            if fmt.get("url"):
                                video_url = fmt["url"]
                                break
                    
                    if video_url:
                        return {
                            "success": True,
                            "url": video_url,
                            "is_hls": ".m3u8" in video_url,
                            "title": info.get("title", "Video"),
                            "duration": info.get("duration"),
                            "thumbnail": info.get("thumbnail"),
                            "site": domain
                        }
        except Exception as e:
            logger.error(f"Extraction failed: {str(e)[:200]}")
            raise
        
        return None
    
    def extract(self, url):
        """Méthode principale d'extraction"""
        # Vérifier le cache
        cache_key = hashlib.md5(url.encode()).hexdigest()
        cached = url_cache.get(cache_key)
        if cached:
            logger.info("Cache hit!")
            cached["cached"] = True
            return cached
        
        # Essayer d'abord sans proxy (plus rapide)
        try:
            result = self.extract_simple(url, use_proxy=False)
            if result:
                url_cache.set(cache_key, result)
                return result
        except Exception as e:
            logger.warning(f"First attempt failed: {str(e)[:100]}")
        
        # Si échec et proxies disponibles, réessayer avec proxy
        if self.proxies_loaded and self.free_proxies:
            try:
                result = self.extract_simple(url, use_proxy=True)
                if result:
                    url_cache.set(cache_key, result)
                    return result
            except Exception as e:
                logger.warning(f"Proxy attempt failed: {str(e)[:100]}")
        
        # Dernière tentative avec l'API externe
        try:
            result = self.extract_with_cobalt(url)
            if result:
                url_cache.set(cache_key, result)
                return result
        except Exception as e:
            logger.warning(f"Cobalt API failed: {str(e)[:100]}")
        
        raise Exception("All extraction methods failed")
    
    def extract_with_cobalt(self, url):
        """Utilise l'API cobalt comme fallback"""
        try:
            api_url = "https://co.wuk.sh/api/json"
            payload = {
                "url": url,
                "vQuality": "720",
                "vCodec": "h264",
                "vFormat": "mp4",
                "isAudioOnly": False
            }
            
            response = requests.post(
                api_url,
                json=payload,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "User-Agent": random.choice(self.user_agents)
                },
                timeout=15
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "stream" and data.get("url"):
                    return {
                        "success": True,
                        "url": data["url"],
                        "is_hls": False,
                        "title": "Video",
                        "site": urlparse(url).hostname
                    }
        except Exception as e:
            logger.error(f"Cobalt API error: {e}")
        
        return None

# Instance globale
extractor = LightweightExtractor()

# Routes Flask

@app.route("/", methods=["GET"])
def home():
    """Page d'accueil avec infos"""
    return jsonify({
        "name": "Fast Video Extractor API v5.0",
        "status": "running",
        "uptime": time.time(),
        "cache_size": url_cache.size(),
        "proxies_ready": extractor.proxies_loaded,
        "proxy_count": len(extractor.free_proxies),
        "endpoints": {
            "extract": "/api/extract?url=VIDEO_URL",
            "health": "/health",
            "cache_clear": "/api/clear-cache"
        }
    }), 200

@app.route("/health", methods=["GET"])
def health():
    """Health check rapide pour monitoring"""
    return jsonify({
        "status": "healthy",
        "timestamp": int(time.time())
    }), 200

@app.route("/api/extract", methods=["GET", "POST"])
def api_extract():
    """Endpoint principal d'extraction"""
    # Récupérer l'URL
    if request.method == "POST":
        data = request.get_json()
        url = data.get("url") if data else None
    else:
        url = request.args.get("url")
    
    if not url:
        return jsonify({
            "success": False,
            "error": "Missing 'url' parameter"
        }), 400
    
    # Validation basique de l'URL
    try:
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            raise ValueError("Invalid URL format")
    except:
        return jsonify({
            "success": False,
            "error": "Invalid URL format"
        }), 400
    
    try:
        # Extraction avec timeout
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(extractor.extract, url)
            result = future.result(timeout=60)  # 60 secondes max
        
        if result and result.get("success"):
            return jsonify({
                "success": True,
                "data": {
                    "url": result["url"],
                    "type": "hls" if result.get("is_hls") else "mp4",
                    "title": result.get("title", "Video"),
                    "duration": result.get("duration"),
                    "thumbnail": result.get("thumbnail"),
                    "source": result.get("site"),
                    "cached": result.get("cached", False)
                }
            }), 200
        else:
            return jsonify({
                "success": False,
                "error": "Failed to extract video URL"
            }), 500
            
    except TimeoutError:
        return jsonify({
            "success": False,
            "error": "Extraction timeout (60s exceeded)"
        }), 408
    
    except Exception as e:
        error_msg = str(e)[:500]  # Limiter la taille du message d'erreur
        logger.error(f"Extraction failed for {url}: {error_msg}")
        
        return jsonify({
            "success": False,
            "error": error_msg
        }), 500

@app.route("/api/clear-cache", methods=["POST"])
def clear_cache():
    """Vide le cache"""
    old_size = url_cache.size()
    url_cache.clear()
    
    return jsonify({
        "success": True,
        "message": f"Cache cleared ({old_size} entries removed)"
    }), 200

@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Endpoint not found"}), 404

@app.errorhandler(500)
def internal_error(e):
    return jsonify({"error": "Internal server error"}), 500

if __name__ == "__main__":
    logger.info("Starting Fast Video Extractor...")
    port = int(os.environ.get("PORT", 8000))
    
    # Mode production avec Gunicorn ou mode dev avec Flask
    if os.environ.get("PRODUCTION"):
        # Production - sera géré par Gunicorn
        logger.info(f"Running in production mode on port {port}")
    else:
        # Développement
        app.run(host="0.0.0.0", port=port, debug=False)
