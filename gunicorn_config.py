import os
import multiprocessing

# Binding
bind = f"0.0.0.0:{os.environ.get('PORT', 8000)}"

# Workers - moins de workers pour démarrage plus rapide
workers = min(2, multiprocessing.cpu_count())
worker_class = "sync"  # Plus simple et rapide que gevent/eventlet
worker_connections = 1000

# Timeout - important pour éviter les 502
timeout = 120  # 2 minutes pour les extractions longues
graceful_timeout = 30
keepalive = 5

# Preloading - désactivé pour démarrage plus rapide
preload_app = False

# Logging
accesslog = "-"
errorlog = "-"
loglevel = "info"

# Performance
max_requests = 1000  # Recycler les workers après 1000 requêtes
max_requests_jitter = 50

# Limite de mémoire pour éviter les fuites
# worker_tmp_dir = "/dev/shm"  # Si disponible sur votre système

# Hook de démarrage
def on_starting(server):
    server.log.info("Starting Gunicorn server...")

def worker_int(worker):
    worker.log.info("Worker received INT or QUIT signal")

def pre_fork(server, worker):
    server.log.info(f"Worker spawned (pid: {worker.pid})")

def when_ready(server):
    server.log.info("Server is ready. Spawning workers...")

def on_exit(server):
    server.log.info("Shutting down...")

# Configuration pour Render/Heroku
if os.environ.get("DYNO"):
    # Heroku
    workers = 1
    preload_app = False
elif os.environ.get("RENDER"):
    # Render
    workers = 1
    preload_app = False
