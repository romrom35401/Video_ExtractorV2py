from flask import Flask, request, jsonify
import yt_dlp
import time
import random
import logging
import os
from urllib.parse import urlparse, parse_qs
import requests
from concurrent.futures import ThreadPoolExecutor, TimeoutError
import json
import base64
import hashlib
import re
from datetime import datetime

app = Flask(__name__)

# Configuration des logs
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

# Cache simple en mémoire
url_cache = {}
CACHE_DURATION = 1800  # 30 minutes pour éviter la détection

class AntiDetectionExtractor:
    """Extracteur avec techniques anti-détection avancées GRATUITES"""
    
    def __init__(self):
        # Pool de User-Agent réalistes et récents
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2.1 Safari/605.1.15"
        ]
        
        # Proxies gratuits publics (mise à jour régulière recommandée)
        self.free_proxies = self.get_free_proxies()
        self.proxy_index = 0
        
        # Compteur de requêtes pour éviter le rate limiting
        self.request_count = {}
        self.last_request = {}
    
    def get_free_proxies(self):
        """Récupère des proxies gratuits depuis des APIs publiques"""
        proxies = []
        
        try:
            # API ProxyScrape (gratuite)
            response = requests.get(
                "https://api.proxyscrape.com/v2/?request=get&protocol=http&timeout=10000&country=all&ssl=all&anonymity=all&format=textplain",
                timeout=10
            )
            if response.status_code == 200:
                proxy_list = response.text.strip().split('\n')
                for proxy in proxy_list[:20]:  # Prendre les 20 premiers
                    if ':' in proxy:
                        proxies.append(f"http://{proxy.strip()}")
        except:
            logger.warning("Failed to fetch proxies from ProxyScrape")
        
        try:
            # API Proxy List (alternative gratuite)
            response = requests.get(
                "https://www.proxy-list.download/api/v1/get?type=http",
                timeout=10
            )
            if response.status_code == 200:
                proxy_list = response.text.strip().split('\n')
                for proxy in proxy_list[:10]:  # Prendre les 10 premiers
                    if ':' in proxy and proxy not in proxies:
                        proxies.append(f"http://{proxy.strip()}")
        except:
            logger.warning("Failed to fetch proxies from proxy-list.download")
        
        # Ajouter des proxies hardcodés fiables (à mettre à jour)
        fallback_proxies = [
            # Ces proxies sont souvent disponibles (à vérifier/mettre à jour)
            # "http://8.210.83.33:80",
            # "http://47.74.152.29:8888"
        ]
        proxies.extend(fallback_proxies)
        
        logger.info(f"Loaded {len(proxies)} free proxies")
        return proxies
    
    def get_working_proxy(self):
        """Trouve un proxy fonctionnel"""
        if not self.free_proxies:
            return None
        
        # Essayer 5 proxies maximum
        for _ in range(min(5, len(self.free_proxies))):
            proxy = self.free_proxies[self.proxy_index % len(self.free_proxies)]
            self.proxy_index += 1
            
            try:
                # Test rapide du proxy
                test_response = requests.get(
                    "http://httpbin.org/ip",
                    proxies={"http": proxy, "https": proxy},
                    timeout=5
                )
                if test_response.status_code == 200:
                    logger.info(f"Using working proxy: {proxy}")
                    return proxy
            except:
                continue
        
        return None
    
    def rate_limit_delay(self, domain):
        """Implémente un délai intelligent pour éviter le rate limiting"""
        now = time.time()
        
        # Compter les requêtes par domaine
        if domain not in self.request_count:
            self.request_count[domain] = 0
            self.last_request[domain] = now
        
        # Si trop de requêtes trop rapidement, attendre
        if self.request_count[domain] > 0 and (now - self.last_request[domain]) < 2:
            delay = random.uniform(2, 5)
            logger.info(f"Rate limiting delay: {delay:.1f}s")
            time.sleep(delay)
        
        self.request_count[domain] += 1
        self.last_request[domain] = now
        
        # Reset counter après 1 minute
        if self.request_count[domain] > 10:
            self.request_count[domain] = 0
    
    def generate_fake_headers(self, url):
        """Génère des headers réalistes avec empreinte browser cohérente"""
        domain = urlparse(url).hostname or ""
        user_agent = random.choice(self.user_agents)
        
        # Headers de base réalistes
        headers = {
            "User-Agent": user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
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
        
        # Ajouter des headers Chrome/Firefox spécifiques selon l'UA
        if "Chrome" in user_agent:
            headers.update({
                "sec-ch-ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"Windows"' if "Windows" in user_agent else '"macOS"' if "Mac" in user_agent else '"Linux"'
            })
        
        # Headers spécifiques par site avec variations
        if "youtube.com" in domain or "youtu.be" in domain:
            headers.update({
                "Referer": "https://www.youtube.com/",
                "Origin": "https://www.youtube.com",
                "X-YouTube-Client-Name": "1",
                "X-YouTube-Client-Version": "2.20240125.00.00"
            })
        elif "vidmoly" in domain:
            headers.update({
                "Referer": f"https://{domain}/",
                "Origin": f"https://{domain}",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
            })
        elif "sibnet.ru" in domain:
            headers.update({
                "Referer": "https://video.sibnet.ru/",
                "Origin": "https://video.sibnet.ru",
                "Cookie": "video_watched=1; age_confirmed=1"
            })
        elif "vk.com" in domain:
            headers.update({
                "Referer": "https://vk.com/",
                "X-Requested-With": "XMLHttpRequest"
            })
        elif "myvi" in domain:
            headers.update({
                "Referer": f"https://{domain}/",
                "Accept": "*/*"
            })
        
        return headers
    
    def get_ydl_options(self, url, use_proxy=True):
        """Configuration yt-dlp avec options anti-détection maximales"""
        headers = self.generate_fake_headers(url)
        domain = urlparse(url).hostname or ""
        
        # Options de base
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": False,
            "skip_download": True,
            "format": "best[ext=mp4]/best",
            "socket_timeout": 45,
            "retries": 5,
            "file_access_retries": 3,
            "force_ipv4": True,
            "http_headers": headers,
            "nocheckcertificate": True,
            "geo_bypass": True,
            "geo_bypass_country": "US",
            # Options anti-détection cruciales
            "sleep_interval": 1,
            "max_sleep_interval": 4,
            "sleep_interval_requests": 1,
            "sleep_interval_subtitles": 1,
            # Fragmentation pour contourner les limites
            "concurrent_fragment_downloads": 1,
            "fragment_retries": 10,
            # Headers HTTP étendus
            "http_chunk_size": 1048576,  # 1MB chunks
            "hls_use_mpegts": False,
            # Cookies et auth
            "cookiefile": None,
            "ignore_config": True,
            "no_cache_dir": True,
            # Extraction info seulement
            "simulate": True,
            "listformats": False,
            # Contournement YouTube spécifique
            "youtube_include_dash_manifest": False,
            "extractor_args": {
                "youtube": {
                    "player_client": ["web", "android"],
                    "skip": ["hls", "dash"]
                }
            }
        }
        
        # Ajouter un proxy fonctionnel si disponible et demandé
        if use_proxy:
            proxy = self.get_working_proxy()
            if proxy:
                ydl_opts["proxy"] = proxy
        
        # Options spécifiques par site
        if "youtube.com" in domain or "youtu.be" in domain:
            ydl_opts.update({
                "format": "best[height<=720]/best",
                "youtube_include_dash_manifest": False,
                "extractor_args": {
                    "youtube": {
                        "player_client": ["web", "android", "ios"],
                        "skip": ["translated_subs"]
                    }
                }
            })
        elif "vk.com" in domain:
            ydl_opts["format"] = "best[height<=480]/worst"
        elif "sibnet" in domain:
            ydl_opts["format"] = "mp4/best[ext=mp4]/best"
        
        return ydl_opts
    
    def extract_with_fallback_methods(self, url, max_attempts=3):
        """Extraction avec méthodes fallback multiples"""
        domain = urlparse(url).hostname or ""
        
        # Appliquer rate limiting
        self.rate_limit_delay(domain)
        
        # Méthode 1: yt-dlp standard avec proxy
        for attempt in range(max_attempts):
            try:
                logger.info(f"Attempt {attempt + 1}: Standard extraction with proxy")
                ydl_opts = self.get_ydl_options(url, use_proxy=True)
                
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                    
                    if info and info.get("url"):
                        return self.format_result(info, domain)
                    elif info and info.get("formats"):
                        # Chercher le meilleur format disponible
                        for fmt in reversed(info["formats"]):
                            if fmt.get("url") and not fmt.get("fragments"):
                                return self.format_result({
                                    "url": fmt["url"],
                                    "title": info.get("title", "Video"),
                                    "duration": info.get("duration"),
                                    "thumbnail": info.get("thumbnail")
                                }, domain, fmt.get("ext") == "m3u8")
            except Exception as e:
                logger.warning(f"Attempt {attempt + 1} failed: {str(e)}")
                if attempt < max_attempts - 1:
                    time.sleep(random.uniform(2, 5))
                continue
        
        # Méthode 2: Sans proxy mais avec headers renforcés
        try:
            logger.info("Fallback: No proxy with enhanced headers")
            ydl_opts = self.get_ydl_options(url, use_proxy=False)
            ydl_opts["http_headers"].update({
                "X-Forwarded-For": self.generate_fake_ip(),
                "X-Real-IP": self.generate_fake_ip(),
                "Via": "1.1 proxy-server"
            })
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if info:
                    return self.format_result(info, domain)
        except Exception as e:
            logger.warning(f"Fallback method failed: {str(e)}")
        
        # Méthode 3: API externe (cobalt.tools)
        return self.extract_with_external_api(url)
    
    def generate_fake_ip(self):
        """Génère une IP fictive pour les headers X-Forwarded-For"""
        return f"{random.randint(1,255)}.{random.randint(1,255)}.{random.randint(1,255)}.{random.randint(1,255)}"
    
    def extract_with_external_api(self, url):
        """Utilise l'API cobalt.tools comme fallback gratuit"""
        try:
            logger.info("Using external API fallback")
            api_url = "https://co.wuk.sh/api/json"
            
            payload = {
                "url": url,
                "vQuality": "720",
                "vCodec": "h264",
                "vFormat": "mp4",
                "isAudioOnly": False,
                "isNoTTWatermark": True,
                "isTTFullAudio": False,
                "dubLang": False
            }
            
            response = requests.post(
                api_url,
                json=payload,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "User-Agent": random.choice(self.user_agents)
                },
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "stream" and data.get("url"):
                    return {
                        "success": True,
                        "url": data["url"],
                        "is_hls": False,
                        "title": "Video",
                        "site": urlparse(url).hostname,
                        "method": "external_api"
                    }
        except Exception as e:
            logger.error(f"External API failed: {e}")
        
        return None
    
    def format_result(self, info, domain, is_hls=False):
        """Formate le résultat d'extraction"""
        if not info:
            return None
        
        # Détecter si c'est du HLS
        url = info.get("url", "")
        is_hls = is_hls or ".m3u8" in url or "master.json" in url
        
        return {
            "success": True,
            "url": url,
            "is_hls": is_hls,
            "title": info.get("title", "Video"),
            "duration": info.get("duration"),
            "thumbnail": info.get("thumbnail"),
            "site": domain,
            "method": "yt-dlp"
        }
    
    def handle_vidmoly_wait(self, url, max_wait=60):
        """Gestion spéciale pour vidmoly qui nécessite une attente"""
        if not url.startswith("https://vidmoly."):
            return True
        
        logger.info("Waiting for vidmoly to be ready...")
        wait_time = 0
        
        while wait_time < max_wait:
            try:
                headers = self.generate_fake_headers(url)
                response = requests.get(url, headers=headers, timeout=10)
                
                if response.status_code == 200 and "Please wait" not in response.text:
                    logger.info("Vidmoly is ready!")
                    return True
                
                time.sleep(3)
                wait_time += 3
                
            except Exception as e:
                logger.warning(f"Vidmoly check failed: {e}")
                time.sleep(2)
                wait_time += 2
        
        logger.warning("Vidmoly wait timeout")
        return False
    
    def extract(self, url):
        """Méthode principale d'extraction avec toutes les techniques anti-403"""
        
        # Vérifier le cache
        cache_key = hashlib.md5(url.encode()).hexdigest()
        if cache_key in url_cache:
            cached_data, cached_time = url_cache[cache_key]
            if time.time() - cached_time < CACHE_DURATION:
                logger.info("Cache hit!")
                return cached_data
        
        # Gestion spéciale vidmoly
        if url.startswith("https://vidmoly."):
            if not self.handle_vidmoly_wait(url):
                raise Exception("Vidmoly wait timeout")
        
        # Extraction avec fallbacks
        result = self.extract_with_fallback_methods(url)
        
        if not result:
            raise Exception("All extraction methods failed - site may have enhanced blocking")
        
        # Mettre en cache
        if result["success"]:
            url_cache[cache_key] = (result, time.time())
        
        return result

# Instance globale
extractor = AntiDetectionExtractor()

@app.route("/api/extract", methods=["GET", "POST"])
def api_extract():
    """Endpoint principal avec support GET et POST"""
    
    # Support GET et POST
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
    
    try:
        # Extraction avec timeout généreux
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(extractor.extract, url)
            result = future.result(timeout=120)  # 2 minutes timeout
        
        # Réponse formatée
        response = {
            "success": True,
            "data": {
                "url": result["url"],
                "type": "hls" if result["is_hls"] else "mp4",
                "title": result.get("title", "Video"),
                "duration": result.get("duration"),
                "thumbnail": result.get("thumbnail"),
                "source": result.get("site"),
                "method": result.get("method", "unknown"),
                "cached": False
            }
        }
        
        return jsonify(response), 200
    
    except TimeoutError:
        return jsonify({
            "success": False,
            "error": "Extraction timeout - the site may be blocking requests"
        }), 408
    
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Extraction failed for {url}: {error_msg}")
        
        # Messages d'erreur plus informatifs
        if "403" in error_msg:
            suggestion = "Try again in a few minutes or check if the video is region-locked"
        elif "404" in error_msg:
            suggestion = "Video not found or URL is incorrect"
        elif "timeout" in error_msg.lower():
            suggestion = "Connection timeout - site may be slow or blocking"
        else:
            suggestion = "Check if the video URL is accessible in a browser"
        
        return jsonify({
            "success": False,
            "error": error_msg,
            "suggestion": suggestion
        }), 500

@app.route("/api/proxy-test", methods=["GET"])
def proxy_test():
    """Teste les proxies disponibles"""
    working_proxies = []
    
    for i, proxy in enumerate(extractor.free_proxies[:10]):  # Test 10 premiers
        try:
            test_response = requests.get(
                "http://httpbin.org/ip",
                proxies={"http": proxy, "https": proxy},
                timeout=5
            )
            if test_response.status_code == 200:
                ip_data = test_response.json()
                working_proxies.append({
                    "proxy": proxy,
                    "ip": ip_data.get("origin")
                })
        except:
            pass
    
    return jsonify({
        "total_proxies": len(extractor.free_proxies),
        "working_proxies": len(working_proxies),
        "working_list": working_proxies[:5],  # Montrer les 5 premiers
        "cache_entries": len(url_cache)
    }), 200

@app.route("/api/clear-cache", methods=["POST"])
def clear_cache():
    """Vide le cache"""
    global url_cache
    old_size = len(url_cache)
    url_cache.clear()
    
    return jsonify({
        "success": True,
        "message": f"Cache cleared ({old_size} entries removed)"
    }), 200

@app.route("/", methods=["GET"])
def home():
    """Documentation API"""
    return jsonify({
        "name": "Anti-403 Video Extractor API v4.0",
        "status": "running",
        "features": {
            "anti_detection": True,
            "free_proxies": len(extractor.free_proxies) > 0,
            "rate_limiting": True,
            "caching": True,
            "multiple_fallbacks": True
        },
        "endpoints": {
            "extract": "/api/extract?url=VIDEO_URL (GET) or POST with {url: VIDEO_URL}",
            "proxy_test": "/api/proxy-test",
            "clear_cache": "/api/clear-cache (POST)",
            "health": "/health"
        },
        "anti_403_techniques": [
            "Dynamic User-Agent rotation",
            "Free proxy rotation", 
            "Site-specific headers",
            "Rate limiting",
            "External API fallback",
            "Enhanced cookie handling"
        ]
    }), 200

@app.route("/health", methods=["GET"])
def health():
    """Health check pour Render"""
    return jsonify({
        "status": "healthy",
        "cache_size": len(url_cache),
        "proxies_loaded": len(extractor.free_proxies),
        "timestamp": int(time.time())
    }), 200

if __name__ == "__main__":
    # Mise à jour des proxies au démarrage
    logger.info("Starting Anti-403 Video Extractor...")
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=False)
