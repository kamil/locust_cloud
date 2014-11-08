from locust import HttpLocust, Locust, TaskSet, task

class MainPage(TaskSet):

    @task
    def main(self):
        response = self.client.get("$url", name="main", catch_response=True)
        response.success()

class TestMainPage(HttpLocust):
    task_set = MainPage
    min_wait=10
    max_wait=50
    host = '$host'
