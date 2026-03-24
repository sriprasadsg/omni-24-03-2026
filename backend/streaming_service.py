import asyncio
from typing import Dict, List, Any, Callable, Set
from datetime import datetime, timezone
import json
from collections import deque

class StreamBroker:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(StreamBroker, cls).__new__(cls)
            cls._instance.topics: Dict[str, List[Callable]] = {}
            cls._instance.history: Dict[str, deque] = {} # Keep last N messages for history
            cls._instance.metrics: Dict[str, Any] = {}
        return cls._instance

    def __init__(self):
        # Already initialized in __new__
        pass

    async def publish(self, topic: str, event: Dict[str, Any]):
        """Publish an event to a topic"""
        # Add timestamp if missing
        if "timestamp" not in event:
            event["timestamp"] = datetime.now(timezone.utc).isoformat()
            
        # Store in history (keep last 100 per topic)
        if topic not in self.history:
            self.history[topic] = deque(maxlen=100)
        self.history[topic].append(event)
        
        # Notify subscribers
        if topic in self.topics:
            subscribers = self.topics[topic]
            # Send to all subscribers (fire and forget to avoid blocking)
            for callback in subscribers:
                try:
                    await callback(event)
                except Exception as e:
                    print(f"Error in subscriber callback: {e}")
        
        # Update metrics (simple counter for now)
        metric_key = f"{topic}_count"
        self.metrics[metric_key] = self.metrics.get(metric_key, 0) + 1

    def subscribe(self, topic: str, callback: Callable):
        """Subscribe to a topic with a callback function"""
        if topic not in self.topics:
            self.topics[topic] = []
        self.topics[topic].append(callback)

    def unsubscribe(self, topic: str, callback: Callable):
        """Unsubscribe from a topic"""
        if topic in self.topics and callback in self.topics[topic]:
            self.topics[topic].remove(callback)

    def get_recent_events(self, topic: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent events from history"""
        if topic in self.history:
            return list(self.history[topic])[-limit:]
        return []

    def get_metrics(self) -> Dict[str, Any]:
        """Get broker metrics"""
        return self.metrics

# Global Broker Instance
broker = StreamBroker()

class StreamProcessor:
    """Simulates a stream processing engine (like a mini-Flink)"""
    def __init__(self):
        self.broker = broker
        self.window_stats: Dict[str, int] = {}
        self.running = False

    async def start(self):
        self.running = True
        # Subscribe to common topics to calculate aggregates
        self.broker.subscribe("logs", self._process_log)
        self.broker.subscribe("security_events", self._process_security)
        
        # Start a background task to reset windows (simulate sliding window 10s)
        asyncio.create_task(self._window_manager())

    async def stop(self):
        self.running = False

    async def _process_log(self, event: Dict[str, Any]):
        self.window_stats["logs_last_10s"] = self.window_stats.get("logs_last_10s", 0) + 1

    async def _process_security(self, event: Dict[str, Any]):
        self.window_stats["threats_last_10s"] = self.window_stats.get("threats_last_10s", 0) + 1

    async def _window_manager(self):
        """Reset stats every 10 seconds to simulate a window"""
        while self.running:
            await asyncio.sleep(1) # Check every second? No, let's just emit stats stream
            
            # Emit system stats event every second
            stats_event = {
                "type": "window_stats",
                "stats": self.window_stats.copy(),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            await self.broker.publish("system_stats", stats_event)
            
            # Decay stats (simple simulation)
            for k in self.window_stats:
                current = self.window_stats[k]
                self.window_stats[k] = max(0, int(current * 0.9)) # Decay 10% per second

processor = StreamProcessor()
