from modules.cache_manager import (
    exists,
    load_dataframe,
    save_dataframe,
    clear_cache,
)


class TurboRuntime:

    def has(self, name: str) -> bool:
        return exists(name)

    def load(self, name: str):
        return load_dataframe(name)

    def save(self, name: str, df):
        save_dataframe(name, df)

    def clear(self):
        clear_cache()


turbo = TurboRuntime()
