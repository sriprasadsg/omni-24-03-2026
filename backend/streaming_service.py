import asyncio
import logging
from typing import Dict, List, Any, Callable
from datetime import datetime, timezone
from collections import deque

logger = logging.getLogger(__name__)

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
        
        # Notify subscribers with per-callback retry (max 2 attempts)
        if topic in self.topics:
            dead_callbacks = []
            for callback in list(self.topics[topic]):
                for attempt in range(2):
                    try:
                        await callback(event)
                        break
                    except Exception as exc:
                        if attempt == 0:
                            logger.warning(
                                "Subscriber callback on topic '%s' failed (attempt 1): %s — retrying",
                                topic, exc,
                            )
                        else:
                            logger.error(
                                "Subscriber callback on topic '%s' failed permanently: %s — moving to dead-letter",
                                topic, exc,
                            )
                            dead_callbacks.append((topic, event, str(exc)))
            if dead_callbacks:
                dl_topic = f"dead-letter:{topic}"
                if dl_topic not in self.history:
                    self.history[dl_topic] = deque(maxlen=100)
                for _t, _ev, _err in dead_callbacks:
                    self.history[dl_topic].append({**_ev, "_dead_letter_error": _err})
        
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
    """Stream processing engine with a real tumbling 10-second window."""

    _WINDOW_SECONDS = 10

    def __init__(self):
        self.broker = broker
        # Accumulator for the current window
        self._current: Dict[str, int] = {}
        # Snapshot published at each window boundary
        self.window_stats: Dict[str, int] = {}
        self.running = False
        self._tick = 0  # counts 1-second ticks; resets at _WINDOW_SECONDS

    async def start(self):
        self.running = True
        self.broker.subscribe("logs", self._process_log)
        self.broker.subscribe("security_events", self._process_security)
        asyncio.create_task(self._window_manager())

    async def stop(self):
        self.running = False

    async def _process_log(self, event: Dict[str, Any]):
        self._current["logs_last_10s"] = self._current.get("logs_last_10s", 0) + 1

    async def _process_security(self, event: Dict[str, Any]):
        self._current["threats_last_10s"] = self._current.get("threats_last_10s", 0) + 1

    async def _window_manager(self):
        """
        Ticks every second.
        Every _WINDOW_SECONDS ticks: snapshot the current window counts into
        window_stats, reset the accumulator, and publish the snapshot.
        Also publishes a live heartbeat each second so dashboards stay responsive.
        """
        while self.running:
            await asyncio.sleep(1)
            self._tick += 1

            if self._tick >= self._WINDOW_SECONDS:
                # Commit the completed window
                self.window_stats = dict(self._current)
                self._current = {}
                self._tick = 0

            # Emit both the committed window snapshot and in-progress counts
            stats_event = {
                "type": "window_stats",
                "window_seconds": self._WINDOW_SECONDS,
                "committed": self.window_stats,
                "in_progress": dict(self._current),
                "seconds_until_reset": self._WINDOW_SECONDS - self._tick,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            await self.broker.publish("system_stats", stats_event)

processor = StreamProcessor()
