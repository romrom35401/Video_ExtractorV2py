#!/usr/bin/env python3
# extractor.py
"""
Extract direct video URLs (mp4 / m3u8) from common anime-host players:
vidmoly.net, video.sibnet.ru, vk.com, sendvid.com, myvi.top, myvi.tv,
movearnpre.com, oneupload.to, smoothpre.com

Usage:
    python extractor.py "https://vidmoly.net/..."        # prints best URL
    python extractor.py -d "https://vidmoly.net/..."     # downloads via yt-dlp
"""

import re
import sys
import json
import argparse
from urllib.parse import urlparse
import httpx
from yt_dlp import YoutubeDL

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114 Safari/537.36"
DEFAULT_HEADERS = {"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"}

# ----------------- Utilities -----------------
def fetch(url, timeout=20, headers=None):
    headers = {**DEFAULT_HEADERS, **(headers or {})}
    with httpx.Client(follow_redirects=True, timeout=timeout) as client:
        r = client.get(url, headers=headers)
        r.raise_for_status()
        return r.text

def decode_escapes(s: str) -> str:
    if not s:
        return s
    # Replace unicode & hex escapes, and escaped slashes
    s = re.sub(r'\\u([0-9a-fA-F]{4})', lambda m: chr(int(m.group(1), 16)), s)
    s = re.sub(r'\\x([0-9a-fA-F]{2})', lambda m: chr(int(m.group(1), 16)), s)
    s = s.replace('\\/', '/').replace('\\"', '"').replace("\\'", "'")
    return s

def find_first_regex(text, patterns):
    for p in patterns:
        m = re.search(p, text, flags=re.I | re.S)
        if m:
            return decode_escapes(m.group(1) if m.groups() else m.group(0))
    return None

def find_all_urls(text):
    return re.findall(r'(https?:\/\/[^"\'\s>]+?\.(?:mp4|m3u8|webm)(?:\?[^"\'>\s]+)?)', text, flags=re.I)

# choose best format from yt-dlp's formats list
def choose_best_from_formats(formats):
    # prefer mp4 with highest height, then m3u8
    mp4s = [f for f in formats if f.get('ext') == 'mp4' and f.get('url')]
    if mp4s:
        mp4s_sorted = sorted(mp4s, key=lambda f: (f.get('height') or 0, f.get('tbr') or 0), reverse=True)
        return mp4s_sorted[0]['url']
    # fallback to any hls
    hls = [f for f in formats if f.get('ext') in ('m3u8',) and f.get('url')]
    if hls:
        return hls[0]['url']
    # last resort: any url field
    for f in formats:
        if f.get('url'):
            return f['url']
    return None

# ----------------- Site-specific extractors -----------------
def extract_vidmoly(url, html=None):
    if html is None:
        html = fetch(url)
    # patterns found in many vidmoly embeds
    patterns = [
        r'player\.setup\(\s*{[\s\S]*?file\s*:\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
        r'sources\s*:\s*\[\s*{[^}]*file\s*:\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
        r'file\s*:\s*["\'](https?:\/\/[^"\']+\.m3u8[^"\']*)["\']',
        r'"(https?:\\\/\\\/[^"]+\.m3u8[^"]*)"'
    ]
    candidate = find_first_regex(html, patterns)
    if candidate:
        return candidate
    # fallback general direct links
    urls = find_all_urls(html)
    if urls:
        # prefer m3u8 then mp4
        for u in urls:
            if '.m3u8' in u:
                return u
        return urls[0]
    return None

def extract_sibnet(url, html=None):
    if html is None:
        html = fetch(url)
    # check video tag id
    m = re.search(r'id=["\']video_html5_wrapper_html5_api["\'][^>]*\s(?:src|data-src)=["\']([^"\']+)', html, flags=re.I)
    if m:
        src = decode_escapes(m.group(1))
        if src.startswith('/'):
            return f'https://video.sibnet.ru{src}'
        return src
    # check generic video tags
    m2 = re.search(r'<video[^>]*>(?:[\s\S]*?<source[^>]*src=["\']([^"\']+)["\'])?', html, flags=re.I)
    if m2 and m2.group(1):
        return decode_escapes(m2.group(1))
    # direct sibnet link inside js/html
    m3 = re.search(r'(https?:\/\/[^"\']*video\.sibnet\.ru[^"\']*\.mp4[^"\']*)', html, flags=re.I)
    if m3:
        return m3.group(1)
    # fallback to generic links
    urls = find_all_urls(html)
    if urls:
        # prefer sibnet urls
        for u in urls:
            if 'video.sibnet' in u:
                return u
        return urls[0]
    return None

def extract_sendvid(url, html=None):
    if html is None:
        html = fetch(url)
    # og:video meta
    m = re.search(r'<meta[^>]+property=["\']og:video[^"\']+content=["\']([^"\']+)["\']', html, flags=re.I)
    if m:
        return decode_escapes(m.group(1))
    # video tag
    m2 = re.search(r'<video[^>]*>\s*<source[^>]*src=["\']([^"\']+)', html, flags=re.I)
    if m2:
        return decode_escapes(m2.group(1))
    # fallback general
    urls = find_all_urls(html)
    return urls[0] if urls else None

def extract_myvi(url, html=None):
    if html is None:
        html = fetch(url)
    patterns = [
        r'"contentUrl"\s*:\s*"([^"]+)"',
        r'file\s*:\s*["\']([^"\']+\.mp4[^"\']*)["\']',
        r'PlayerLoader\.CreatePlayer\([^,]+,\s*["\']([^"\']+)["\']'
    ]
    candidate = find_first_regex(html, patterns)
    if candidate:
        return candidate
    urls = find_all_urls(html)
    return urls[0] if urls else None

def extract_movearnpre(url, html=None):
    if html is None:
        html = fetch(url)
    # follow iframe if present
    m = re.search(r'<iframe[^>]+src=["\']([^"\']+)', html, flags=re.I)
    if m:
        iframe = m.group(1)
        if iframe.startswith('//'):
            iframe = 'https:' + iframe
        if iframe.startswith('/'):
            parsed = urlparse(url)
            iframe = f'{parsed.scheme}://{parsed.netloc}{iframe}'
        try:
            iframe_html = fetch(iframe)
            urls = find_all_urls(iframe_html)
            if urls:
                return urls[0]
        except Exception:
            pass
    # fallback general
    urls = find_all_urls(html)
    return urls[0] if urls else None

def extract_oneupload(url, html=None):
    if html is None:
        html = fetch(url)
    patterns = [
        r'sources\s*:\s*\[\s*{[^}]*file\s*:\s*["\']([^"\']+)["\']',
        r'file\s*:\s*["\']([^"\']+\.mp4[^"\']*)["\']',
        r'href=["\']([^"\']+\.mp4[^"\']*download[^"\']*)["\']'
    ]
    candidate = find_first_regex(html, patterns)
    if candidate:
        return candidate
    urls = find_all_urls(html)
    return urls[0] if urls else None

def extract_smoothpre(url, html=None):
    if html is None:
        html = fetch(url)
    patterns = [
        r'playerInstance\.setup\(\s*{[^}]*file:\s*["\']([^"\']+)["\']',
        r'jwplayer\([^)]*\)\.setup\(\s*{[^}]*file:\s*["\']([^"\']+)["\']',
        r'file\s*:\s*["\']([^"\']+\.mp4[^"\']*)["\']',
    ]
    candidate = find_first_regex(html, patterns)
    if candidate:
        return candidate
    urls = find_all_urls(html)
    return urls[0] if urls else None

def extract_vk(url, html=None):
    if html is None:
        html = fetch(url)
    # try quality keys
    for key in ['url2160','url1440','url1080','url720','url480','url360','url240']:
        m = re.search(rf'"{key}"\s*:\s*"([^"]+)"', html)
        if m:
            return decode_escapes(m.group(1)).replace('\\/', '/')
    # fallback to yt-dlp
    return None

# ----------------- YT-DLP fallback (powerful) -----------------
def yt_dlp_extract(url):
    ydl_opts = {'quiet': True, 'no_warnings': True, 'skip_download': True}
    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        # If url present directly (single video)
        if info is None:
            return None
        if info.get('url') and info.get('ext') in ('mp4','m3u8','webm'):
            return info['url']
        # If formats present, choose best
        if info.get('formats'):
            best = choose_best_from_formats(info['formats'])
            if best:
                return best
        # some extractors return 'entries' (playlist) -> pick first entry
        if info.get('entries'):
            for entry in info['entries']:
                if not entry:
                    continue
                if entry.get('url') and entry.get('ext') in ('mp4','m3u8','webm'):
                    return entry['url']
                if entry.get('formats'):
                    best = choose_best_from_formats(entry['formats'])
                    if best:
                        return best
    return None

# ----------------- Dispatcher -----------------
def extract(url, try_yt_dlp=True):
    # 1) direct link?
    if re.search(r'\.(mp4|m3u8|webm)(\?|$|#)', url, flags=re.I):
        return url

    host = urlparse(url).hostname or ''
    host = host.lower()
    html = None
    try:
        html = fetch(url)
    except Exception:
        html = None

    # try site-specific
    try:
        if 'vidmoly' in host:
            res = extract_vidmoly(url, html)
            if res:
                return res
        if 'sibnet' in host or 'video.sibnet' in host:
            res = extract_sibnet(url, html)
            if res:
                return res
        if 'sendvid' in host:
            res = extract_sendvid(url, html)
            if res:
                return res
        if 'myvi' in host:
            res = extract_myvi(url, html)
            if res:
                return res
        if 'movearnpre' in host:
            res = extract_movearnpre(url, html)
            if res:
                return res
        if 'oneupload' in host:
            res = extract_oneupload(url, html)
            if res:
                return res
        if 'smoothpre' in host:
            res = extract_smoothpre(url, html)
            if res:
                return res
        if 'vk.com' in host:
            res = extract_vk(url, html)
            if res:
                return res
    except Exception:
        pass

    # generic heuristics on page
    if html:
        # search for common patterns in scripts / HTML
        # 1) player.setup sources lines and file: "..."
        m = re.search(r'file\s*:\s*["\']([^"\']+\.(?:mp4|m3u8)[^"\']*)["\']', html, flags=re.I)
        if m:
            return decode_escapes(m.group(1))
        # 2) any direct link
        urls = find_all_urls(html)
        if urls:
            # prefer mp4
            for u in urls:
                if '.mp4' in u:
                    return u
            # else return first
            return urls[0]

    # fallback: attempt yt-dlp extraction (very robust for many hosts)
    if try_yt_dlp:
        try:
            y = yt_dlp_extract(url)
            if y:
                return y
        except Exception:
            pass

    return None

# ----------------- CLI -----------------
def main():
    parser = argparse.ArgumentParser(description="Extract or download direct mp4/m3u8 from players")
    parser.add_argument("url", help="URL to extract")
    parser.add_argument("-d", "--download", action="store_true", help="Download using yt-dlp")
    parser.add_argument("-o", "--out", help="Output filename (only for download)")
    args = parser.parse_args()

    url = args.url
    print(f"[+] Trying to extract: {url}", file=sys.stderr)
    res = extract(url, try_yt_dlp=True)
    if not res:
        print(json.dumps({"success": False, "error": "URL vidéo introuvable"}))
        sys.exit(1)

    # If user wants to download -> use yt-dlp with the resolved direct link or original url
    if args.download:
        print(f"[+] Found: {res}. Starting download via yt-dlp...", file=sys.stderr)
        ydl_opts = {"outtmpl": args.out or "%(title)s.%(ext)s"}
        # If res is a raw .m3u8 or .mp4, yt-dlp can download it as well
        with YoutubeDL(ydl_opts) as ydl:
            ydl.download([res])
        sys.exit(0)

    # else print JSON with best candidate
    print(json.dumps({"success": True, "url": res}, ensure_ascii=False))

if __name__ == "__main__":
    main()
