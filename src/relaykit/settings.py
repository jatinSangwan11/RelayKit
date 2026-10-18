from pydantic import PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict  # pyright: ignore[reportMissingImports]

# we created settings.py for a single, validated enterance for all relaykit configuration, without it migh ask for 
# os.getenv("DATABASE_URL") we eliminated the repition

class Settings(BaseSettings):
    # settings on how to create settings instance/object then follow these instructions
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )

    database_url: PostgresDsn   # PostgresDsn - it validates a postgreSQL connection URL and DSN: data source name
    # only the structure check

settings = Settings()


# Pydanctic reads model_config when the class is created and uses those intructions when we call settings()
"""
1. Python defines the Settings class.

2. Pydantic notices a required field:
   database_url: PostgresDsn

3. We create an instance:
   settings = Settings()

4. model_config tells Pydantic to read .env.

5. Pydantic searches its configuration sources for a value
   corresponding to database_url.

6. Environment-variable matching is case-insensitive by default:
   database_url ↔ DATABASE_URL

7. Pydantic reads DATABASE_URL as raw text.

8. PostgresDsn validates and parses that text.

9. The validated value becomes:
   settings.database_url

"""