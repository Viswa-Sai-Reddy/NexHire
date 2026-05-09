import os

import redis

# REDIS_URL e.g. rediss://:PASSWORD@nexhire-redis-krv.redis.cache.windows.net:6380/0
url = os.environ['REDIS_URL']
r = redis.from_url(url, decode_responses=True)
print(r.ping())
