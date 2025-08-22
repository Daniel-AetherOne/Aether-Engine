from fastapi import Request, HTTPException, Depends
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from typing import Optional
import redis
import json

# Redis client voor rate limiting
redis_client = redis.Redis(
    host='localhost',
    port=6379,
    db=0,
    decode_responses=True
)

# Rate limiter instance
limiter = Limiter(key_func=get_remote_address)

def get_tenant_id_from_request(request: Request) -> Optional[str]:
    """Haal tenant_id op uit de request"""
    # Probeer uit URL path
    path = request.url.path
    if path.startswith("/tenant/"):
        parts = path.split("/")
        if len(parts) > 2:
            return parts[2]
    
    # Probeer uit query parameters
    tenant_id = request.query_params.get("tenant_id")
    if tenant_id:
        return tenant_id
    
    # Probeer uit headers
    tenant_id = request.headers.get("X-Tenant-ID")
    if tenant_id:
        return tenant_id
    
    # Probeer uit JSON body (voor POST requests)
    try:
        if request.method == "POST":
            body = request.json()
            if isinstance(body, dict) and "tenant_id" in body:
                return body["tenant_id"]
    except:
        pass
    
    return None

def get_tenant_rate_limit_key(request: Request) -> str:
    """Genereer een unieke key voor tenant-specifieke rate limiting"""
    tenant_id = get_tenant_id_from_request(request)
    if not tenant_id:
        tenant_id = "unknown"
    
    # Gebruik IP + tenant_id voor unieke identificatie
    client_ip = get_remote_address(request)
    return f"{client_ip}:{tenant_id}"

def tenant_rate_limit(requests_per_minute: int = 60):
    """Decorator voor tenant-specifieke rate limiting"""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            # Haal request object op uit kwargs
            request = None
            for arg in args:
                if isinstance(arg, Request):
                    request = arg
                    break
            
            if not request:
                for value in kwargs.values():
                    if isinstance(value, Request):
                        request = value
                        break
            
            if not request:
                raise HTTPException(status_code=500, detail="Request object not found")
            
            tenant_id = get_tenant_id_from_request(request)
            if not tenant_id:
                raise HTTPException(status_code=400, detail="Tenant ID required")
            
            # Check rate limit
            key = f"rate_limit:{tenant_id}:{request.url.path}"
            current_requests = redis_client.get(key)
            
            if current_requests and int(current_requests) >= requests_per_minute:
                raise HTTPException(
                    status_code=429,
                    detail=f"Rate limit exceeded: {requests_per_minute} requests per minute"
                )
            
            # Increment counter
            pipe = redis_client.pipeline()
            pipe.incr(key)
            pipe.expire(key, 60)  # Expire after 1 minute
            pipe.execute()
            
            return await func(*args, **kwargs)
        
        return wrapper
    return decorator

def get_rate_limit_info(tenant_id: str) -> dict:
    """Krijg rate limit informatie voor een tenant"""
    key = f"rate_limit:{tenant_id}:*"
    keys = redis_client.keys(key)
    
    info = {}
    for k in keys:
        endpoint = k.split(":")[-1]
        current_requests = redis_client.get(k)
        ttl = redis_client.ttl(k)
        
        info[endpoint] = {
            "current_requests": int(current_requests) if current_requests else 0,
            "ttl_seconds": ttl if ttl > 0 else 0,
            "limit": 60  # Default limit
        }
    
    return info

def reset_rate_limits(tenant_id: str = None):
    """Reset rate limits voor een specifieke tenant of alle tenants"""
    if tenant_id:
        pattern = f"rate_limit:{tenant_id}:*"
    else:
        pattern = "rate_limit:*"
    
    keys = redis_client.keys(pattern)
    if keys:
        redis_client.delete(*keys)
        return len(keys)
    return 0

# Global rate limiter voor alle endpoints
def global_rate_limit():
    """Global rate limiter: 1000 requests per minute per IP"""
    return limiter.limit("1000/minute")

# Tenant-specific rate limiter voor quote creation
def quote_create_rate_limit():
    """Rate limiter voor quote creation: 60 requests per minute per tenant"""
    return tenant_rate_limit(60)

# Tenant-specific rate limiter voor vision processing
def vision_rate_limit():
    """Rate limiter voor vision processing: 30 requests per minute per tenant"""
    return tenant_rate_limit(30)

# Tenant-specific rate limiter voor prediction
def prediction_rate_limit():
    """Rate limiter voor prediction: 100 requests per minute per tenant"""
    return tenant_rate_limit(100)
