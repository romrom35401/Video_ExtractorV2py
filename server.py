# server.py
from flask import Flask, request, jsonify
from extractor import extract  # ton script extractor.py
import yt_dlp

app = Flask(__name__)

@app.route("/api/extract", methods=["GET"])
def api_extract():
    url = request.args.get("url")
    if not url:
        return jsonify({"success": False, "error": "Missing url param"}), 400

    try:
        # 🔹 Première tentative : yt-dlp direct (plus fiable pour Sibnet, VK, etc.)
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "format": "mp4/best",  # on privilégie le mp4
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            # yt-dlp peut retourner "url" direct ou "formats"
            video_url = info.get("url")
            if not video_url and info.get("formats"):
                # choisir le meilleur mp4
                mp4_formats = [f for f in info["formats"] if f.get("ext") == "mp4" and f.get("url")]
                if mp4_formats:
                    mp4_formats_sorted = sorted(mp4_formats, key=lambda f: f.get("height", 0), reverse=True)
                    video_url = mp4_formats_sorted[0]["url"]

            if video_url:
                return jsonify({"success": True, "title": info.get("title"), "url": video_url})

        # 🔹 Fallback : ton extractor.py
        result = extract(url, try_yt_dlp=True)
        if result:
            return jsonify({"success": True, "url": result})
        else:
            return jsonify({"success": False, "error": "Video not found"}), 404

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
