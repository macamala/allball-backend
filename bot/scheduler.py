from apscheduler.schedulers.blocking import BlockingScheduler
from .pipeline import run_pipeline

scheduler = BlockingScheduler()


@scheduler.scheduled_job("interval", minutes=5)
def job():
    print("Running AllBall pipeline...")
    run_pipeline()


if __name__ == "__main__":
    scheduler.start()
