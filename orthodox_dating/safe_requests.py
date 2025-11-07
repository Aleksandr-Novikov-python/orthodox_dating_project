import requests

def patch_requests():
    original_get = requests.get

    def safe_get(*args, **kwargs):
        url = args[0] if args else kwargs.get('url', '')
        if "example.com" in url:
            raise RuntimeError(f"❌ Заблокирован запрос к: {url}")
        return original_get(*args, **kwargs)

    requests.get = safe_get

