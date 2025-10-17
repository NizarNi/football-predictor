class ClientError(Exception):
    pass


class ClientTimeout:
    def __init__(self, total=None):
        self.total = total


class ClientSession:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False
