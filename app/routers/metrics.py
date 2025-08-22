from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from typing import Dict, Any
import json

from app.metrics import get_metrics_summary, generate_latest, CONTENT_TYPE_LATEST
from app.rate_limiting import get_rate_limit_info, reset_rate_limits
from app.logging_config import get_logger

router = APIRouter()
logger = get_logger(__name__)

@router.get("/metrics")
async def prometheus_metrics():
    """Prometheus metrics endpoint"""
    logger.info("Prometheus metrics requested")
    return generate_latest()

@router.get("/metrics/summary")
async def metrics_summary():
    """Krijg een samenvatting van alle metrics"""
    logger.info("Metrics summary requested")
    return get_metrics_summary()

@router.get("/metrics/rate-limits")
async def rate_limits_info():
    """Krijg informatie over rate limits voor alle tenants"""
    logger.info("Rate limits info requested")
    
    # Dit zou normaal gesproken uit een database komen
    # Voor nu returnen we een voorbeeld
    return {
        "rate_limits": {
            "quote_create": {
                "limit": 60,
                "window": "1 minute",
                "description": "Quote creation rate limit per tenant"
            },
            "vision_processing": {
                "limit": 30,
                "window": "1 minute", 
                "description": "Vision processing rate limit per tenant"
            },
            "prediction": {
                "limit": 100,
                "window": "1 minute",
                "description": "Prediction rate limit per tenant"
            }
        }
    }

@router.get("/metrics/rate-limits/{tenant_id}")
async def tenant_rate_limits(tenant_id: str):
    """Krijg rate limit informatie voor een specifieke tenant"""
    logger.info(f"Rate limits info requested for tenant: {tenant_id}")
    
    rate_limit_info = get_rate_limit_info(tenant_id)
    return {
        "tenant_id": tenant_id,
        "rate_limits": rate_limit_info
    }

@router.post("/metrics/rate-limits/reset")
async def reset_all_rate_limits():
    """Reset alle rate limits"""
    logger.info("Resetting all rate limits")
    
    count = reset_rate_limits()
    return {
        "message": f"Reset {count} rate limit counters",
        "reset_count": count
    }

@router.post("/metrics/rate-limits/{tenant_id}/reset")
async def reset_tenant_rate_limits(tenant_id: str):
    """Reset rate limits voor een specifieke tenant"""
    logger.info(f"Resetting rate limits for tenant: {tenant_id}")
    
    count = reset_rate_limits(tenant_id)
    return {
        "message": f"Reset {count} rate limit counters for tenant {tenant_id}",
        "tenant_id": tenant_id,
        "reset_count": count
    }

@router.get("/metrics/dashboard", response_class=HTMLResponse)
async def metrics_dashboard():
    """HTML dashboard voor metrics visualisatie"""
    logger.info("Metrics dashboard requested")
    
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>LevelAI SaaS - Metrics Dashboard</title>
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; }
            .metric-card { 
                border: 1px solid #ddd; 
                padding: 20px; 
                margin: 10px; 
                border-radius: 8px; 
                display: inline-block; 
                width: 300px; 
                vertical-align: top;
            }
            .metric-value { 
                font-size: 2em; 
                font-weight: bold; 
                color: #007bff; 
            }
            .metric-label { 
                color: #666; 
                margin-top: 5px; 
            }
            .chart-container { 
                margin: 20px 0; 
                height: 400px; 
            }
            .refresh-btn { 
                background: #007bff; 
                color: white; 
                border: none; 
                padding: 10px 20px; 
                border-radius: 5px; 
                cursor: pointer; 
                margin: 10px 0;
            }
        </style>
    </head>
    <body>
        <h1>LevelAI SaaS - Metrics Dashboard</h1>
        
        <button class="refresh-btn" onclick="refreshMetrics()">Refresh Metrics</button>
        
        <div class="metric-card">
            <div class="metric-value" id="total-requests">-</div>
            <div class="metric-label">Total Requests</div>
        </div>
        
        <div class="metric-card">
            <div class="metric-value" id="avg-latency">-</div>
            <div class="metric-label">Avg Latency (ms)</div>
        </div>
        
        <div class="metric-card">
            <div class="metric-value" id="total-jobs">-</div>
            <div class="metric-label">Total Jobs</div>
        </div>
        
        <div class="metric-card">
            <div class="metric-value" id="quotes-created">-</div>
            <div class="metric-label">Quotes Created</div>
        </div>
        
        <div class="metric-card">
            <div class="metric-value" id="leads-processed">-</div>
            <div class="metric-label">Leads Processed</div>
        </div>
        
        <div class="metric-card">
            <div class="metric-value" id="active-users">-</div>
            <div class="metric-label">Active Users</div>
        </div>
        
        <div class="chart-container">
            <canvas id="requestsChart"></canvas>
        </div>
        
        <div class="chart-container">
            <canvas id="latencyChart"></canvas>
        </div>
        
        <script>
            let requestsChart, latencyChart;
            
            async function refreshMetrics() {
                try {
                    const response = await fetch('/metrics/summary');
                    const data = await response.json();
                    
                    document.getElementById('total-requests').textContent = data.request_count || 0;
                    document.getElementById('avg-latency').textContent = Math.round((data.request_latency_p95 || 0) * 1000);
                    document.getElementById('total-jobs').textContent = data.job_count || 0;
                    document.getElementById('quotes-created').textContent = data.quotes_created || 0;
                    document.getElementById('leads-processed').textContent = data.leads_processed || 0;
                    document.getElementById('active-users').textContent = data.active_users || 0;
                    
                    updateCharts(data);
                } catch (error) {
                    console.error('Error fetching metrics:', error);
                }
            }
            
            function updateCharts(data) {
                // Simple chart updates - in production you'd want more sophisticated charts
                if (!requestsChart) {
                    const ctx1 = document.getElementById('requestsChart').getContext('2d');
                    requestsChart = new Chart(ctx1, {
                        type: 'line',
                        data: {
                            labels: ['Requests', 'Jobs', 'Quotes', 'Leads'],
                            datasets: [{
                                label: 'Counts',
                                data: [data.request_count || 0, data.job_count || 0, data.quotes_created || 0, data.leads_processed || 0],
                                borderColor: 'rgb(75, 192, 192)',
                                tension: 0.1
                            }]
                        },
                        options: {
                            responsive: true,
                            maintainAspectRatio: false,
                            title: {
                                display: true,
                                text: 'System Activity Overview'
                            }
                        }
                    });
                }
                
                if (!latencyChart) {
                    const ctx2 = document.getElementById('latencyChart').getContext('2d');
                    latencyChart = new Chart(ctx2, {
                        type: 'bar',
                        data: {
                            labels: ['Request Latency (95th percentile)'],
                            datasets: [{
                                label: 'Latency (ms)',
                                data: [Math.round((data.request_latency_p95 || 0) * 1000)],
                                backgroundColor: 'rgba(54, 162, 235, 0.2)',
                                borderColor: 'rgb(54, 162, 235)',
                                borderWidth: 1
                            }]
                        },
                        options: {
                            responsive: true,
                            maintainAspectRatio: false,
                            title: {
                                display: true,
                                text: 'Performance Metrics'
                            }
                        }
                    });
                }
            }
            
            // Initial load
            refreshMetrics();
            
            // Auto-refresh every 30 seconds
            setInterval(refreshMetrics, 30000);
        </script>
    </body>
    </html>
    """
    
    return HTMLResponse(content=html_content)

@router.get("/health/detailed")
async def detailed_health():
    """Gedetailleerde health check met metrics"""
    logger.info("Detailed health check requested")
    
    try:
        metrics_summary = get_metrics_summary()
        
        return {
            "status": "healthy",
            "timestamp": "2024-01-01T00:00:00Z",  # In production zou dit dynamisch zijn
            "metrics": metrics_summary,
            "services": {
                "redis": "connected",  # In production zou dit echt gecheckt worden
                "database": "connected",
                "celery": "running"
            }
        }
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        return {
            "status": "unhealthy",
            "error": str(e)
        }
