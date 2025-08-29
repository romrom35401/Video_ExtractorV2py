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
import requests

app = Flask(__name__)

# Configuration des logs
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

# Cache simple en mémoire
url_cache = {}
CACHE_DURATION = 3600  # 1 heure

class VideoExtractor:
    """Extracteur optimisé avec support proxy"""
    
    def __init__(self):
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ]
        
        # Liste de proxies gratuits (à remplacer par des proxies fiables)
        self.proxy_list = self.get_proxy_list()
        self.current_proxy_index = 0
    
    def get_proxy_list(self):
        """Récupère une liste de proxies (à adapter selon votre source)"""
        # Option 1: Proxies gratuits (peu fiables)
        # Vous pouvez utiliser des API comme:
        # - https://www.proxy-list.download/api/v1/get?type=http
        # - https://api.proxyscrape.com/v2/
        
        # Option 2: Variables d'environnement pour proxies payants
        proxy_env = os.environ.get("PROXY_LIST", "")
        if proxy_env:
            return proxy_env.split(",")
        
        # Option 3: Proxies hardcodés (temporaire pour test)
        return [
            # Format: "http://user:pass@host:port" ou "http://host:port"
            # Exemples (à remplacer par de vrais proxies):
            # "http://proxy1.example.com:8080",
            # "socks5://proxy2.example.com:1080"
        ]
    
    def get_next_proxy(self):
        """Rotation des proxies"""
        if not self.proxy_list:
            return None
        
        proxy = self.proxy_list[self.current_proxy_index]
        self.current_proxy_index = (self.current_proxy_index + 1) % len(self.proxy_list)
        return proxy
    
    def check_vidmoly_ready(self, url, proxy=None):
        """Vérifie si vidmoly est prêt"""
        if not url.startswith("https://vidmoly."):
            return True
        
        try:
            proxies = {"http": proxy, "https": proxy} if proxy else None
            response = requests.get(url, headers={"User-Agent": ""}, 
                                   proxies=proxies, timeout=10)
            return "Please wait" not in response.text
        except:
            return False
    
    def get_headers_for_site(self, url):
        """Headers optimisés par site avec anti-détection améliorée"""
        domain = urlparse(url).hostname or ""
        
        headers = {
            "User-Agent": random.choice(self.user_agents),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,fr;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Cache-Control": "max-age=0"
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
        
        return headers
    
    def extract_with_playwright_fallback(self, url):
        """Fallback avec rendu JavaScript (nécessite playwright)"""
        try:
            # Cette méthode nécessiterait playwright pour le rendu JS
            # pip install playwright
            # playwright install chromium
            
            from playwright.sync_api import sync_playwright
            
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=True,
                    args=['--disable-blink-features=AutomationControlled']
                )
                
                context = browser.new_context(
                    viewport={'width': 1920, 'height': 1080},
                    user_agent=random.choice(self.user_agents)
                )
                
                # Injection anti-détection
                context.add_init_script("""
                    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                    Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
                """)
                
                page = context.new_page()
                page.goto(url, wait_until='networkidle')
                
                # Attendre et chercher la vidéo
                time.sleep(3)
                
                # Chercher l'URL de la vidéo dans le DOM
                video_url = page.evaluate("""
                    () => {
                        const video = document.querySelector('video');
                        if (video) return video.src;
                        
                        const source = document.querySelector('source');
                        if (source) return source.src;
                        
                        // Chercher dans les iframes
                        const iframes = document.querySelectorAll('iframe');
                        for (let iframe of iframes) {
                            if (iframe.src && iframe.src.includes('.mp4')) {
                                return iframe.src;
                            }
                        }
                        
                        return null;
                    }
                """)
                
                browser.close()
                
                if video_url:
                    return {
                        "success": True,
                        "url": video_url,
                        "is_hls": ".m3u8" in video_url,
                        "title": "Video",
                        "site": urlparse(url).hostname
                    }
        except ImportError:
            logger.warning("Playwright not installed, skipping JS fallback")
        except Exception as e:
            logger.error(f"Playwright extraction failed: {e}")
        
        return None
    
    def extract_with_yt_dlp(self, url, retry_count=0, max_retries=3):
        """Extraction principale avec yt-dlp et support proxy"""
        
        # Sélectionner un proxy si disponible
        proxy = self.get_next_proxy() if self.proxy_list else None
        
        # Configuration avec proxy
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": False,
            "skip_download": True,
            "format": "best[ext=mp4]/best",
            "socket_timeout": 30,
            "retries": 3,
            "force_ipv4": True,
            "http_headers": self.get_headers_for_site(url),
            "nocheckcertificate": True,
            "geo_bypass": True,
            "concurrent_fragment_downloads": 1,
            # Cookies pour contourner certaines protections
            "cookiefile": os.environ.get("COOKIE_FILE", None),
            # Options anti-détection supplémentaires
            "sleep_interval": 1,
            "max_sleep_interval": 3,
            "sleep_interval_requests": 1
        }
        
        # Ajouter le proxy si disponible
        if proxy:
            ydl_opts["proxy"] = proxy
            logger.info(f"Using proxy: {proxy}")
        
        # Options spécifiques par site
        domain = urlparse(url).hostname or ""
        
        if "vk.com" in domain:
            ydl_opts["format"] = "best[height<=720]/best"
        elif "sibnet" in domain:
            ydl_opts["format"] = "mp4/best"
            # Sibnet nécessite parfois des cookies spécifiques
            ydl_opts["http_headers"]["Cookie"] = "video_watched=1"
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                
                # Extraction de l'URL directe
                direct_url = None
                is_hls = False
                
                if info.get("url"):
                    direct_url = info["url"]
                    is_hls = ".m3u8" in direct_url or "master.json" in direct_url
                
                elif info.get("formats"):
                    for fmt in info["formats"]:
                        if fmt.get("ext") == "mp4" and fmt.get("url"):
                            direct_url = fmt["url"]
                            break
                    
                    if not direct_url:
                        for fmt in reversed(info["formats"]):
                            if fmt.get("url"):
                                direct_url = fmt["url"]
                                is_hls = fmt.get("ext") == "m3u8"
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
        
        except Exception as e:
            error_msg = str(e).lower()
            
            # Si erreur 403 et qu'on a des proxies, réessayer avec un autre
            if "403" in error_msg and self.proxy_list and retry_count < max_retries:
                logger.warning(f"403 error, trying with different proxy...")
                time.sleep(random.uniform(1, 3))
                return self.extract_with_yt_dlp(url, retry_count + 1, max_retries)
            
            # Si erreur 403 sans proxy, essayer le fallback playwright
            elif "403" in error_msg and not self.proxy_list:
                logger.warning("403 error, trying playwright fallback...")
                result = self.extract_with_playwright_fallback(url)
                if result:
                    return result
            
            raise e
    
    def extract_with_api_fallback(self, url):
        """Utilise des API tierces comme fallback"""
        # Option 1: Utiliser cobalt.tools API (gratuit)
        try:
            cobalt_api = "https://co.wuk.sh/api/json"
            response = requests.post(
                cobalt_api,
                json={"url": url, "vQuality": "720"},
                headers={"Accept": "application/json"},
                timeout=10
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
        except:
            pass
        
        # Option 2: Utiliser votre propre instance locale comme proxy
        # (voir solution B ci-dessous)
        
        return None
    
    def extract(self, url, max_wait_time=30):
        """Méthode principale d'extraction avec fallbacks"""
        
        # Vérifier le cache
        cache_key = url
        if cache_key in url_cache:
            cached_data, cached_time = url_cache[cache_key]
            if time.time() - cached_time < CACHE_DURATION:
                logger.info(f"Cache hit for {url}")
                return cached_data
        
        # Pour vidmoly, attendre qu'il soit prêt
        if url.startswith("https://vidmoly."):
            proxy = self.get_next_proxy() if self.proxy_list else None
            wait_time = 0
            while wait_time < max_wait_time:
                if self.check_vidmoly_ready(url, proxy):
                    break
                logger.warning(f"Vidmoly not ready, waiting...")
                time.sleep(2)
                wait_time += 2
        
        # Tentative d'extraction avec plusieurs méthodes
        result = None
        
        try:
            # Méthode 1: yt-dlp avec proxy
            result = self.extract_with_yt_dlp(url)
        except Exception as e:
            logger.error(f"yt-dlp extraction failed: {e}")
            
            # Méthode 2: API externe
            result = self.extract_with_api_fallback(url)
            
            if not result:
                # Méthode 3: Playwright (si installé)
                result = self.extract_with_playwright_fallback(url)
            
            if not result:
                raise Exception(f"All extraction methods failed: {e}")
        
        # Mettre en cache si succès
        if result and result["success"]:
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
    
    try:
        # Extraction avec timeout
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(extractor.extract, url)
            result = future.result(timeout=60)  # Timeout augmenté
        
        # Formater la réponse pour Expo Go
        response = {
            "success": True,
            "data": {
                "url": result["url"],
                "type": "hls" if result["is_hls"] else "mp4",
                "title": result.get("title", "Video"),
                "duration": result.get("duration"),
                "thumbnail": result.get("thumbnail"),
                "source": result.get("site")
            }
        }
        
        # Ajouter des headers CORS pour Expo Go
        headers = {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type"
        }
        
        return jsonify(response), 200, headers
    
    except TimeoutError:
        return jsonify({
            "success": False,
            "error": "Extraction timeout - try again later"
        }), 408
    
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Extraction failed for {url}: {error_msg}")
        
        return jsonify({
            "success": False,
            "error": error_msg,
            "suggestion": "Try using a proxy or local extraction"
        }), 500

@app.route("/api/proxy-status", methods=["GET"])
def proxy_status():
    """Vérifie le statut des proxies"""
    working_proxies = []
    
    for proxy in extractor.proxy_list:
        try:
            test_url = "http://httpbin.org/ip"
            response = requests.get(test_url, proxies={"http": proxy, "https": proxy}, timeout=5)
            if response.status_code == 200:
                working_proxies.append(proxy)
        except:
            pass
    
    return jsonify({
        "total_proxies": len(extractor.proxy_list),
        "working_proxies": len(working_proxies),
        "proxies_configured": len(extractor.proxy_list) > 0
    }), 200

@app.route("/", methods=["GET"])
def home():
    """Page d'accueil avec documentation"""
    return jsonify({
        "name": "Video Extractor API v3.0",
        "status": "running",
        "features": {
            "proxy_support": len(extractor.proxy_list) > 0,
            "fallback_methods": ["yt-dlp", "api", "playwright"],
            "caching": True
        },
        "endpoints": {
            "extract": "/api/extract?url=VIDEO_URL",
            "proxy_status": "/api/proxy-status",
            "health": "/health"
        },
        "configuration": {
            "proxy_list": "Set PROXY_LIST env variable with comma-separated proxies",
            "cookie_file": "Set COOKIE_FILE env variable for cookie authentication"
        }
    }), 200

@app.route("/health", methods=["GET"])
def health():
    """Health check pour Render"""
    return jsonify({
        "status": "healthy",
        "cache_size": len(url_cache),
        "proxies_available": len(extractor.proxy_list) > 0,
        "timestamp": int(time.time())
    }), 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
