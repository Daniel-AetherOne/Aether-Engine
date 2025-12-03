# app/config/cache_config.py

CACHE_OFFERTES = "public, max-age=300"                    # ~5 min
CACHE_UPLOADS = "public, max-age=86400"                  # 1 dag
CACHE_STATIC = "public, max-age=31536000, immutable"     # 1 jaar + immutable
