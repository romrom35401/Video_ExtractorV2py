# extractor.py
import yt_dlp
import requests
import re
import time
import random

def extract(url, try_yt_dlp=True):
    """
    Extrait l'URL avec stratégies spécifiques aux sites alternatifs
    """
    if not try_yt_dlp:
        return None
    
    # Stratégie selon le site
    if "sibnet.ru" in url:
        return extract_sibnet(url)
    elif "vk.com" in url:
        return extract_vk(url)
    elif any(site in url for site in ["vidmoly.net", "myvi.top", "myvi.tv"]):
        return extract_generic_with_referer(url)
    else:
        return extract_generic(url)

def extract_sibnet(url):
    """Extraction spécifique pour Sibnet"""
    try:
        ydl_opts = {
            "quiet": True,
            "format": "mp4/best",
            "http_headers": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": "https://video.sibnet.ru/",
                "Origin": "https://video.sibnet.ru"
            },
            "socket_timeout": 30
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return info.get("url")
    except:
        return None

def extract_vk(url):
    """Extraction spécifique pour VK"""
    try:
        ydl_opts = {
            "quiet": True,
            "format": "best[height<=720]",  # Limite la qualité
            "http_headers": {
                "User-Agent": "Mozilla/5.0 (compatible; VK App)",
                "Referer": "https://vk.com/"
            }
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return info.get("url")
    except:
        return None

def extract_generic_with_referer(url):
    """Extraction générique avec referer"""
    try:
        domain = url.split('/')[2]
        ydl_opts = {
            "quiet": True,
            "format": "mp4/best",
            "http_headers": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": f"https://{domain}/",
                "Accept": "*/*"
            }
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return info.get("url")
    except:
        return None

def extract_generic(url):
    """Extraction générique de base"""
    try:
        time.sleep(random.uniform(0.5, 2))  # Délai aléatoire
        
        ydl_opts = {
            "quiet": True,
            "format": "worst[ext=mp4]/worst",
            "socket_timeout": 20
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return info.get("url")
    except:
        return None
