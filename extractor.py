# extractor.py
import yt_dlp
import requests
import re
import random
import time

def extract(url, try_yt_dlp=True):
    """
    Extrait l'URL directe avec plusieurs stratégies anti-403
    """
    if try_yt_dlp:
        # Stratégie 1: yt-dlp avec client mobile
        try:
            ydl_opts = {
                "quiet": True,
                "format": "mp4/best[height<=480]",  # Qualité mobile pour éviter détection
                "force_ipv4": True,
                "extractor_args": {
                    "youtube": {
                        "player_client": ["android", "ios"]  # Clients mobiles moins détectés
                    }
                }
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                return info.get("url")
        except:
            pass
        
        # Stratégie 2: Attendre un peu et réessayer
        try:
            time.sleep(random.uniform(1, 3))  # Délai aléatoire
            ydl_opts = {
                "quiet": True,
                "format": "worst[ext=mp4]",  # Prendre la pire qualité pour moins de détection
                "force_ipv4": True,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                return info.get("url")
        except:
            pass
    
    return None
