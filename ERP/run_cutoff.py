from app.modules.assemblers.services.schedule import run_schedule_daily_cutoff_catchup


if __name__ == "__main__":
    result = run_schedule_daily_cutoff_catchup()
    print(f"Cron job finished: {result}")
