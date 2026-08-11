from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/signalfilter"

    slack_bot_token: str = ""
    slack_app_token: str = ""

    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:3b-instruct"

    embedding_model: str = "all-MiniLM-L6-v2"
    embedding_threshold: float = 0.0
    interrupt_score_threshold: int = 4
    gmail_interrupt_score_threshold: int = 7

    digest_time: str = "18:00"
    feedback_min_votes: int = 10
    attention_budget_daily: int = 10

    class Config:
        env_file = ".env"


settings = Settings()
